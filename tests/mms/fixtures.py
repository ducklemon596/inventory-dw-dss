"""Small in-memory stand-ins for the mart reader, outcomes and risk model."""
from datetime import date, timedelta
from types import SimpleNamespace

from inventory_dw_dss.mms.schemas import InventoryRow, InventorySnapshot, MMSError, Observation

T = date(2025, 6, 2)
VERSION = "replenishment-mart-v1:fixture:2025-12-31"


def row(sku, available, dispensary=None, *, sales_90d=90., std=None, revenue=900., abc=None, eligible=True, **extra):
    """A product selling sales_90d / 90 units a day."""
    return InventoryRow(sku, "Tab", available_stock=float(available),
                        dispensary_stock=float(available if dispensary is None else dispensary),
                        sales_7d=sales_90d * 7 / 90, sales_30d=sales_90d / 3, sales_90d=sales_90d,
                        revenue_90d=revenue, product_name=f"Product {sku}", sales_std_90d=std, abc_class=abc,
                        eligible=eligible, **extra)


class Outcomes:
    """Daily observations keyed by (sku, date); window() mirrors MartOutcomes."""

    def __init__(self, observations, data_cutoff, version="outcomes-fixture"):
        self.index = {(o.sku_id, o.observation_date): o for o in observations}
        self.data_cutoff, self.version = data_cutoff, version

    def window(self, t, sku_ids, horizon):
        if self.data_cutoff < t + timedelta(days=horizon):
            raise MMSError("Outcomes are not complete at the data cutoff")
        return {s: tuple(self.index[(s, t + timedelta(days=d))] for d in range(1, horizon + 1)) for s in sku_ids}


def daily_sales(skus, t, horizon, *, qty=1., stockout=lambda sku, day: False, stocktake=lambda sku, day: False):
    return [Observation(t + timedelta(days=d), s, qty, stockout(s, d), stocktake=stocktake(s, d))
            for s in skus for d in range(1, horizon + 1)]


class Reader:
    """Returns the same rows for every date."""

    def __init__(self, rows, outcomes=None):
        self.rows, self._outcomes = rows, outcomes

    def snapshot(self, t):
        return InventorySnapshot(t, VERSION, self.rows)

    def data_version(self):
        return VERSION, date(2025, 12, 31)

    def outcomes(self):
        return self._outcomes


class RiskModel:
    """Scores 1 / (1 + available stock): emptier products rank first."""
    version, target, horizon_days = "fixture-model", "pharmacy_shortfall", 14
    manifest = {"supervised_data_cutoff": "2025-05-26"}

    def __init__(self, target="pharmacy_shortfall"):
        self.target = target

    def check_snapshot(self, snapshot):
        pass

    def score(self, rows):
        return tuple(1 / (1 + max(r.available_stock, 0)) for r in rows)


class Client:
    """clickhouse_connect-like client that answers the MartReader queries from dicts."""

    def __init__(self, snapshot_rows, positions=()):
        self.snapshot_rows, self.positions, self.queries = snapshot_rows, list(positions), []

    def query(self, sql, parameters=None):
        self.queries.append(sql)
        if "max(snapshot_date)" in sql:
            rows = [{"dataset_name": "fixture", "export_end": date(2025, 12, 31)}]
        elif "fct_product_replenishment_snapshot AS s" in sql:
            rows = self.snapshot_rows
        else:
            rows = [p for p in self.positions if p["sku_id"] in parameters["skus"]
                    and parameters["t"] < p["position_date"] <= parameters["end"]]
        names = list(rows[0]) if rows else []
        return SimpleNamespace(column_names=names, result_rows=[tuple(r[n] for n in names) for r in rows])

    def close(self):
        pass
