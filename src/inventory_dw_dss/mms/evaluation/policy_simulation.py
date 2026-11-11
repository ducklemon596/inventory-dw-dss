"""Replay replenishment policies over historical demand (pharmacy-wide, periodic review).

Each review day the policy orders up to its target from on-hand plus pipeline stock; orders
arrive after the lead time. Daily demand is recorded sales, which are censored on days the
pharmacy was empty; `impute_censored` adds MA90 demand on those days. Supply is assumed
complete and on time, with no pack sizes or minimum orders, so results compare policies
with each other, not with recorded history.
"""
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from ..schemas import MMSError, as_date
from ..models.policy import ABC_SERVICE_LEVELS, demand_quantile


@dataclass(frozen=True)
class PolicySpec:
    kind: str           # "coverage" or "service_level"
    value: float | None  # coverage days, or service level; None with abc
    abc: bool = False

    @property
    def label(self):
        if self.kind == "coverage":
            return f"coverage:{self.value:g}"
        return "service:abc" if self.abc else f"service:{self.value:g}"


def parse_policy(text):
    """'coverage:14', 'service:0.95' or 'service:abc'."""
    kind, _, value = text.strip().partition(":")
    try:
        if kind == "coverage" and float(value) > 0:
            return PolicySpec("coverage", float(value))
        if kind == "service" and value == "abc":
            return PolicySpec("service_level", None, abc=True)
        if kind == "service" and 0.5 <= float(value) < 1:
            return PolicySpec("service_level", float(value))
    except ValueError:
        pass
    raise MMSError(f"Invalid policy '{text}'; use coverage:<days>, service:<level> or service:abc")


@dataclass(frozen=True)
class SimulationData:
    """Day x product matrices for one cohort; review inputs are indexed by review date."""
    days: tuple
    product_ids: tuple
    demand: np.ndarray
    actual_stock: np.ndarray
    unit_value: np.ndarray
    mean_daily: dict
    std_daily: dict
    abc_class: dict

    def __post_init__(self):
        shape = (len(self.days), len(self.product_ids))
        if self.demand.shape != shape or self.actual_stock.shape != shape:
            raise MMSError("Simulation matrices must be days x products")


def load_simulation_data(reader, start, end, review_weekday=0):
    """Read the cohort orderable at `start` and its positions/snapshots through `end` (SELECT only)."""
    start, end = as_date(start), as_date(end)
    if end <= start:
        raise MMSError("Simulation end must follow its start")
    cohort = ("SELECT product_id FROM {db}.fct_product_replenishment_snapshot "
              "WHERE snapshot_date = {start:Date} AND is_orderable = 1")
    params = {"start": start, "end": end}
    positions = pd.DataFrame(reader.query(
        "SELECT product_id, position_date, toFloat64(greatest(sold_qty, 0)) AS sold, "
        "toFloat64(greatest(pharmacy_on_hand_qty, 0)) AS stock "
        "FROM {db}.fct_product_daily_position "
        "WHERE position_date BETWEEN {start:Date} AND {end:Date} AND product_id IN (" + cohort + ")", params))
    snapshots = pd.DataFrame(reader.query(
        "SELECT product_id, snapshot_date, avg_daily_sold_qty_90d AS mean_daily, sold_qty_std_90d AS std_daily, "
        "unit_sales_value_90d AS unit_value, abc_class "
        "FROM {db}.fct_product_replenishment_snapshot "
        "WHERE snapshot_date BETWEEN {start:Date} AND {end:Date} AND toDayOfWeek(snapshot_date) = {weekday:UInt8} "
        "AND product_id IN (" + cohort + ")", params | {"weekday": review_weekday + 1}))
    if positions.empty or snapshots.empty:
        raise MMSError(f"No orderable cohort or positions between {start} and {end}")
    days = tuple(start + timedelta(days=i) for i in range((end - start).days + 1))
    products = tuple(sorted(positions.product_id.unique()))
    positions["position_date"] = positions.position_date.map(as_date)
    snapshots["snapshot_date"] = snapshots.snapshot_date.map(as_date)

    def matrix(column):
        return (positions.pivot(index="position_date", columns="product_id", values=column)
                .reindex(index=list(days), columns=list(products)).fillna(0).to_numpy())

    def by_date(column, fill):
        table = snapshots.pivot(index="snapshot_date", columns="product_id", values=column)
        table = table.reindex(columns=list(products))
        return {t: row.to_numpy(dtype=object if column == "abc_class" else float, na_value=fill)
                for t, row in table.iterrows()}

    first = snapshots[snapshots.snapshot_date == snapshots.snapshot_date.min()].set_index("product_id")
    unit_value = first.unit_value.reindex(list(products)).astype(float).fillna(0).to_numpy()
    return SimulationData(days, products, matrix("sold"), matrix("stock"), unit_value,
                          by_date("mean_daily", 0.0), by_date("std_daily", np.nan), by_date("abc_class", None))


def _target(spec, mean, std, abc, review_days, lead_time_days):
    if spec.kind == "coverage":
        return np.ceil(spec.value * mean)
    level = (np.array([ABC_SERVICE_LEVELS.get(c, 0.95) for c in abc]) if spec.abc
             else spec.value)
    return demand_quantile(mean, std, review_days + lead_time_days, level)


def simulate(data, spec, review_days=7, lead_time_days=2, impute_censored=False):
    """Replay one policy; returns service and inventory metrics over the period."""
    lead = int(lead_time_days)
    if lead < 0 or lead != lead_time_days:
        raise MMSError("lead_time_days must be a nonnegative integer in simulation")
    first_mean = data.mean_daily[min(data.mean_daily)]
    demand = data.demand
    if impute_censored:
        demand = demand + np.where(data.actual_stock <= 0, first_mean, 0.0)
    active = first_mean > 0
    stock = data.actual_stock[0].copy()
    pipeline = {}
    served = lost = served_value = lost_value = inventory_value = stockout_days = 0.0
    units = lines = reviews = 0
    for k, day in enumerate(data.days):
        stock += pipeline.pop(k, 0)
        if day in data.mean_daily:
            target = _target(spec, data.mean_daily[day], data.std_daily[day], data.abc_class[day],
                             review_days, lead_time_days)
            order = np.maximum(0, np.ceil(target - stock - sum(pipeline.values())))
            if lead:
                pipeline[k + lead] = pipeline.get(k + lead, 0) + order
            else:
                stock += order
            units += int(order.sum())
            lines += int((order > 0).sum())
            reviews += 1
        sold = np.minimum(stock, demand[k])
        short = demand[k] - sold
        served += sold.sum()
        lost += short.sum()
        served_value += (sold * data.unit_value).sum()
        lost_value += (short * data.unit_value).sum()
        stock -= sold
        stockout_days += ((stock <= 0) & active).sum()
        inventory_value += (stock * data.unit_value).sum()
    n_days = len(data.days)
    total = served + lost
    total_value = served_value + lost_value
    return {
        "policy": spec.label,
        "fill_rate": served / total if total else None,
        "value_fill_rate": served_value / total_value if total_value else None,
        "stockout_day_share": stockout_days / (n_days * active.sum()) if active.any() else None,
        "avg_inventory_value": inventory_value / n_days,
        "units_ordered": units,
        "order_lines_per_review": lines / reviews if reviews else None,
    }


def recorded_baseline(data):
    """What the recorded history held, for context only (different supply conditions)."""
    active = data.mean_daily[min(data.mean_daily)] > 0
    n_days = len(data.days)
    return {"policy": "recorded",
            "stockout_day_share": ((data.actual_stock <= 0) & active).sum() / (n_days * active.sum()),
            "avg_inventory_value": (data.actual_stock * data.unit_value).sum() / n_days}
