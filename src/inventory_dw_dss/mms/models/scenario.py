from ..core.schemas import DecisionItem, MMSValidationError, ScenarioResult, finite
from ..diagnostics.flags import diagnostic_flags
from .replenishment import suggested_quantity


def execute(snapshot, config, risk_scores, metadata):
    """Provisional MVP: pstar → profile sort → K → greedy partial allocation.

    Q is an abstract sum of product-specific stock units, not currency or a
    shared physical unit. It is an explicit scenario resource assumption.
    """
    if config.analysis_date != snapshot.analysis_date:
        raise MMSValidationError("Scenario date differs from frozen snapshot")
    if len(risk_scores) != len(snapshot.rows):
        raise MMSValidationError("Risk scores must align with snapshot rows")
    for score in risk_scores:
        if not 0 <= finite(score, "risk_score") <= 1:
            raise MMSValidationError("Risk scores must be in [0,1]")
    candidates = [(r, s) for r, s in zip(snapshot.rows, risk_scores) if s >= config.pstar]
    if config.profile == "RevenueAtRisk" and any(r.revenue_90d is None for r, _ in candidates):
        raise MMSValidationError("RevenueAtRisk requires a verified revenue proxy for every candidate")

    def key(pair):
        row, risk = pair
        if config.profile == "RiskFirst": value = -risk
        elif config.profile == "LowStock": value = row.available_stock
        elif config.profile == "DOS": value = row.dos if row.dos is not None else float("inf")
        else: value = -risk * row.revenue_90d
        return value, row.sku_id

    ranked = sorted(candidates, key=key)[:config.top_k]
    remaining = config.unit_budget_q
    review = []
    for rank, (row, risk) in enumerate(ranked, 1):
        q = suggested_quantity(row, config.coverage_tau_days)
        allocated = q if remaining is None else min(q, remaining)
        if remaining is not None:
            remaining -= allocated
        review.append(DecisionItem(row.sku_id, rank, risk, row.available_stock, row.stock_unit,
            row.dos, row.vel90, q, allocated, row.eligible, diagnostic_flags(row),
            f"{config.profile} rank {rank}; risk score {risk:.4f} >= {config.pstar}; "
            f"coverage target {config.coverage_tau_days:g} days; suggested {q}, allocated {allocated}. "
            "Manager review required; risk alone is not a purchase instruction."))
    orders = tuple(item for item in review if item.eligible and item.suggested_q > 0 and item.allocated_q > 0)
    return ScenarioResult(config, tuple(review), orders, {
        "selected_sku_count": len(review), "candidate_count": len(candidates),
        "order_sku_count": len(orders), "units_suggested": sum(r.suggested_q for r in review),
        "units_allocated": sum(r.allocated_q for r in orders), "budget_remaining": remaining,
        "q_zero_count": sum(r.suggested_q == 0 for r in review),
        "mean_selected_risk_score": sum(r.risk_score for r in review) / len(review) if review else None,
        "resource_utilization": (sum(r.allocated_q for r in orders) / config.unit_budget_q
                                 if config.unit_budget_q else None),
    }, dict(metadata, policy_version="scenario-mvp-v1", allocation="greedy_partial",
            parameter_order="pstar,profile,K,tau,Q", provisional_tn_rules=True))
