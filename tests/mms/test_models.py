from dataclasses import replace

import numpy as np
import pytest

from inventory_dw_dss.mms.models.policy import demand_quantile, propose
from inventory_dw_dss.mms.models.scenario import build_plan
from inventory_dw_dss.mms.models.targets import target_label, target_stock
from inventory_dw_dss.mms.schemas import InventorySnapshot, MMSError, ScenarioConfig

from fixtures import T, VERSION, daily_sales, row


def test_demand_quantile_matches_hand_computed_values():
    # 9 days at mean 1/day, std 2/day: mean 9, variance 36 -> negative binomial n=3, p=0.25.
    assert demand_quantile(1, 2, 9, .95) == 20 and demand_quantile(1, 2, 9, .90) == 17
    # Missing or under-dispersed std falls back to Poisson(9); no demand gives 0.
    assert demand_quantile(1, None, 9, .95) == demand_quantile(1, .5, 9, .95) == 14
    assert list(demand_quantile(np.array([1., 0.]), np.array([2., np.nan]), 9, .95)) == [20, 0]
    assert demand_quantile(1, 2, 9, .98) > 20 and demand_quantile(1, 2, 16, .95) > 20


def test_policies_quantity_safety_stock_and_eligibility():
    product = row("A", 5, std=2.)
    assert propose(product, ScenarioConfig(T, policy="coverage")).suggested_qty == 9   # ceil(14 x 1 - 5)
    service = ScenarioConfig(T, policy="service_level", coverage_days=7, lead_time_days=2)
    p = propose(product, service)
    assert (p.target_level, p.safety_stock, p.suggested_qty) == (20, 11, 15)
    assert propose(replace(product, eligible=False), service).suggested_qty == 0
    abc = replace(service, abc_service=True, service_level=.9)
    assert propose(replace(product, abc_class="A"), abc).service_level == .98
    assert propose(product, abc).service_level == .9   # no class: the slider level


@pytest.mark.parametrize("bad", [dict(pstar=2), dict(top_k=0), dict(unit_budget=-1), dict(policy="x"),
                                 dict(service_level=1.), dict(lead_time_days=-1), dict(profile="LowStock")])
def test_invalid_configuration(bad):
    with pytest.raises(MMSError):
        ScenarioConfig(T, **bad)


def test_plan_filters_ranks_and_allocates_budget_in_rank_order():
    snapshot = InventorySnapshot(T, VERSION, (row("A", 5), row("B", 0), row("C", 50)))
    config = ScenarioConfig(T, pstar=.1, unit_budget=20, policy="coverage")
    plan = build_plan(snapshot, config, (.6, .9, .05))
    # C is below pstar; B ranks first and takes its full 14, A gets the remaining 6 of 9.
    assert [(i.sku_id, i.suggested_qty, i.allocated_qty) for i in plan.items] == [("B", 14, 14), ("A", 9, 6)]
    assert plan.summary["budget_remaining"] == 0 and plan.summary["allocated_value"] == 20 * 10
    by_supply = build_plan(snapshot, replace(config, profile="DaysOfSupply", pstar=0), (.6, .9, .05))
    assert [i.sku_id for i in by_supply.items] == ["B", "A", "C"]


def test_revenue_at_risk_weights_risk_by_sales_value():
    snapshot = InventorySnapshot(T, VERSION, (row("A", 5, revenue=100.), row("B", 5, revenue=10_000.)))
    plan = build_plan(snapshot, ScenarioConfig(T, pstar=0, profile="RevenueAtRisk"), (.9, .2))
    assert [i.sku_id for i in plan.items] == ["B", "A"]   # 0.2 x 10,000 > 0.9 x 100


def test_targets_label_pharmacy_shortfall_and_dispensary_stockout():
    product = row("A", 10, dispensary=3)
    window = daily_sales(["A"], T, 7, qty=1., stockout=lambda s, d: d == 4)
    assert target_stock(product, "pharmacy_shortfall") == 10 and target_stock(product, "dispensary_stockout") == 3
    assert target_label(product, window, "pharmacy_shortfall") == 0    # 7 sold < 10 held
    assert target_label(product, window, "dispensary_stockout") == 1
