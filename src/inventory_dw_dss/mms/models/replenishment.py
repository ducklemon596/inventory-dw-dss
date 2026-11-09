import math

from ..core.schemas import MMSValidationError, finite


def suggested_quantity(row, coverage_tau_days):
    """Provisional coverage rule; eligibility gates ordering, never risk alerts."""
    tau = finite(coverage_tau_days, "coverage_tau_days")
    if tau <= 0:
        raise MMSValidationError("coverage_tau_days must be positive")
    if not row.eligible or row.available_stock < 0 or row.vel90 == 0:
        return 0
    return max(0, math.ceil(tau * row.vel90 - row.available_stock))
