"""Service-level order-up-to policy (MB3 service_level).

Demand over review + lead time follows a negative binomial matched to the 90-day daily mean
and standard deviation; when the variance does not exceed the mean it falls back to Poisson.
On the 2025 pharmacy test period this hit the nominal service level for slow, medium and fast
movers, unlike the plain coverage rule (see docs/mms-real-data-evaluation.md).
"""
from dataclasses import dataclass
import math

import numpy as np
from scipy import stats

from ..core.schemas import MMSValidationError, finite
from .replenishment import suggested_quantity

POLICY_VERSIONS = {"coverage": "coverage-mvp-v1", "service_level": "service-level-nb-v1"}
# Optional per-class targets: protect the products that carry most of the sales value.
ABC_SERVICE_LEVELS = {"A": 0.98, "B": 0.95, "C": 0.90}


def demand_quantile(mean_daily, std_daily, days, service_level):
    """Quantile of total demand over `days`; vectorized over numpy arrays.

    Days are treated as independent, so mean and variance scale with the horizon. A missing
    standard deviation means Poisson variance. Zero mean demand gives a zero quantile.
    """
    mean = np.asarray(mean_daily, dtype=float) * days
    std = np.asarray(np.nan if std_daily is None else std_daily, dtype=float)
    var = np.where(np.isnan(std), mean, std ** 2 * days)
    q = np.asarray(service_level, dtype=float)
    over = var > mean * (1 + 1e-9)
    safe_var = np.where(over, var, mean + 1)
    p = np.clip(np.divide(mean, safe_var, out=np.ones_like(mean), where=safe_var > 0), 1e-9, 1 - 1e-9)
    n = np.maximum(mean * p / (1 - p), 1e-9)
    value = np.where(over, stats.nbinom.ppf(q, n, p), stats.poisson.ppf(q, np.maximum(mean, 1e-12)))
    return np.where(mean > 0, value, 0.0)


@dataclass(frozen=True)
class PolicyDecision:
    suggested_q: int
    target_level: float | None
    safety_stock: float | None
    service_level: float | None
    explanation: str


def row_service_level(row, config):
    if config.abc_service and row.abc_class in ABC_SERVICE_LEVELS:
        return ABC_SERVICE_LEVELS[row.abc_class]
    return config.service_level


def order_up_to(row, review_days, lead_time_days, service_level):
    """Order up to the service-level quantile of demand over review + lead time."""
    review = finite(review_days, "review_days")
    lead = finite(lead_time_days, "lead_time_days", 0)
    level = finite(service_level, "service_level")
    if review <= 0 or not 0.5 <= level < 1:
        raise MMSValidationError("review_days must be positive and service_level in [0.5, 1)")
    horizon = review + lead
    mean = row.vel90 * horizon
    std = row.sales_std_90d
    target = float(demand_quantile(row.vel90, std, horizon, level))
    safety = target - mean
    if not row.eligible or row.available_stock < 0 or row.vel90 == 0:
        q = 0
    else:
        q = max(0, math.ceil(target - row.available_stock))
    return PolicyDecision(q, target, safety, level,
        f"service level {level:.0%}: demand over {horizon:g} days <= {target:g} {row.stock_unit} "
        f"(mean {mean:.1f}, safety {safety:.1f}); available {row.available_stock:g}, suggested {q}")


def propose(row, config):
    """Quantity proposal for one row under the scenario's replenishment policy."""
    if config.policy == "service_level":
        return order_up_to(row, config.coverage_tau_days, config.lead_time_days, row_service_level(row, config))
    q = suggested_quantity(row, config.coverage_tau_days)
    return PolicyDecision(q, None, None, None, f"coverage target {config.coverage_tau_days:g} days; suggested {q}")
