"""Build a review list and allocate a unit budget (MB4).

Steps: keep products with risk >= pstar -> rank by profile -> keep top_k -> quantity per
policy -> allocate the budget greedily in rank order (a line may get part of its quantity).
"""
from ..schemas import DecisionItem, MMSError, ScenarioResult
from .policy import POLICY_VERSIONS, propose


def _rank_key(profile):
    if profile == "RiskFirst":
        return lambda row, risk: (-risk, row.sku_id)
    if profile == "RevenueAtRisk":
        # Expected daily sales value at risk: risk x 90-day revenue.
        return lambda row, risk: (-risk * (row.revenue_90d or 0), row.sku_id)
    return lambda row, risk: (row.days_of_supply if row.days_of_supply is not None else float("inf"), row.sku_id)


def build_plan(snapshot, config, risk_scores, metadata=None):
    if config.analysis_date != snapshot.analysis_date:
        raise MMSError("Scenario date differs from the snapshot date")
    if len(risk_scores) != len(snapshot.rows):
        raise MMSError("Risk scores must align with snapshot rows")
    key = _rank_key(config.profile)
    candidates = [(r, s) for r, s in zip(snapshot.rows, risk_scores) if s >= config.pstar]
    ranked = sorted(candidates, key=lambda pair: key(*pair))[:config.top_k]
    remaining = config.unit_budget
    items = []
    for rank, (row, risk) in enumerate(ranked, 1):
        proposal = propose(row, config)
        allocated = proposal.suggested_qty if remaining is None else min(proposal.suggested_qty, remaining)
        if remaining is not None:
            remaining -= allocated
        items.append(DecisionItem(
            rank, row.sku_id, row.product_name, row.stock_unit, risk, row.available_stock, row.dispensary_stock,
            row.daily_demand, row.days_of_supply, proposal.suggested_qty, allocated, row.unit_value,
            proposal.target_level, proposal.safety_stock, proposal.service_level, row.abc_class, row.flags))
    allocated_value = sum(i.allocated_qty * (i.unit_value or 0) for i in items)
    summary = {
        "candidates": len(candidates),
        "review_items": len(items),
        "order_lines": sum(i.allocated_qty > 0 for i in items),
        "units_suggested": sum(i.suggested_qty for i in items),
        "units_allocated": sum(i.allocated_qty for i in items),
        "budget_remaining": remaining,
        "allocated_value": allocated_value,
    }
    return ScenarioResult(config, tuple(items), summary,
                          dict(metadata or {}, policy_version=POLICY_VERSIONS[config.policy]))
