"""Order quantity per product (MB3).

coverage: order enough for `coverage_days` of average demand (MA90). It targets the mean,
    so it covers actual demand only about 60% of the time and ignores lead time.
service_level: order up to S, the `service_level` quantile of demand over the review period
    plus lead time. Demand follows a negative binomial matched to the 90-day daily mean and
    standard deviation (Poisson when the variance does not exceed the mean). S minus the mean
    demand is the safety stock, so erratic products carry more buffer than steady ones.
"""
from dataclasses import dataclass
import math

import numpy as np
from scipy import stats

POLICY_VERSIONS = {"coverage": "coverage-v1", "service_level": "service-level-nb-v1"}
ABC_SERVICE_LEVELS = {"A": 0.98, "B": 0.95, "C": 0.90}


def demand_quantile(mean_daily, std_daily, days, service_level):
    """Quantile of total demand over `days`; vectorized over numpy arrays.

    Days are treated as independent, so mean and variance scale with the horizon.
    """
    mean = np.asarray(mean_daily, dtype=float) * days
    std = np.asarray(np.nan if std_daily is None else std_daily, dtype=float)
    var = np.where(np.isnan(std), mean, std ** 2 * days)
    level = np.asarray(service_level, dtype=float)
    overdispersed = var > mean * (1 + 1e-9)
    safe_var = np.where(overdispersed, var, mean + 1)
    p = np.clip(np.divide(mean, safe_var, out=np.ones_like(mean), where=safe_var > 0), 1e-9, 1 - 1e-9)
    n = np.maximum(mean * p / (1 - p), 1e-9)
    quantile = np.where(overdispersed, stats.nbinom.ppf(level, n, p), stats.poisson.ppf(level, np.maximum(mean, 1e-12)))
    return np.where(mean > 0, quantile, 0.0)


@dataclass(frozen=True)
class Proposal:
    suggested_qty: int
    target_level: float | None = None
    safety_stock: float | None = None
    service_level: float | None = None


def propose(row, config):
    """Suggested quantity for one row; ineligible products and products without demand get 0."""
    orderable = row.eligible and row.daily_demand > 0
    if config.policy == "coverage":
        qty = math.ceil(config.coverage_days * row.daily_demand - row.available_stock) if orderable else 0
        return Proposal(max(0, qty))
    level = ABC_SERVICE_LEVELS.get(row.abc_class, config.service_level) if config.abc_service else config.service_level
    horizon = config.coverage_days + config.lead_time_days
    target = float(demand_quantile(row.daily_demand, row.sales_std_90d, horizon, level))
    qty = max(0, math.ceil(target - row.available_stock)) if orderable else 0
    return Proposal(qty, target, target - row.daily_demand * horizon, level)
