from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from inventory_dw_dss.mms.core.executor import ModelExecutor
from inventory_dw_dss.mms.core.schemas import InventoryRow, InventorySnapshot, MMSValidationError, ScenarioConfig
from inventory_dw_dss.mms.evaluation.policy_simulation import SimulationData, parse_policy, simulate
from inventory_dw_dss.mms.models.policy import demand_quantile, order_up_to, propose
from inventory_dw_dss.mms.models.scenario import execute

T = date(2025, 6, 30)


def row(sku="A", stock=5., std=2., abc=None, **kwargs):
    # 90 units in 90 days: one unit per day on average.
    return InventoryRow(sku, "Tab", available_stock=stock, sales_7d=7, sales_30d=30, sales_90d=90,
                        revenue_90d=900., sales_std_90d=std, abc_class=abc, **kwargs)


def test_demand_quantile_matches_hand_computed_negative_binomial_and_poisson():
    # 9 days, mean 1/day, std 2/day: mean 9, variance 36 → NB(n=3, p=0.25).
    assert demand_quantile(1, 2, 9, .95) == 20 and demand_quantile(1, 2, 9, .90) == 17
    # Missing or under-dispersed std falls back to Poisson(9).
    assert demand_quantile(1, None, 9, .95) == demand_quantile(1, .5, 9, .95) == 14
    assert demand_quantile(0, None, 9, .95) == 0
    # Vectorized over products and monotone in level and horizon.
    assert list(demand_quantile(np.array([1., 0.]), np.array([2., np.nan]), 9, .95)) == [20, 0]
    assert demand_quantile(1, 2, 9, .98) > 20 and demand_quantile(1, 2, 16, .95) > 20


def test_order_up_to_quantity_safety_stock_and_eligibility():
    decision = order_up_to(row(stock=5), review_days=7, lead_time_days=2, service_level=.95)
    assert (decision.target_level, decision.safety_stock, decision.suggested_q) == (20, 11, 15)
    assert order_up_to(row(stock=25), 7, 2, .95).suggested_q == 0
    assert order_up_to(row(eligible=False), 7, 2, .95).suggested_q == 0
    assert order_up_to(row(stock=-1), 7, 2, .95).suggested_q == 0
    with pytest.raises(MMSValidationError):
        order_up_to(row(), 7, 2, 1.0)


def test_policy_config_keeps_coverage_default_and_uses_abc_levels():
    coverage = propose(row(stock=5), ScenarioConfig(T))
    assert (coverage.suggested_q, coverage.target_level) == (9, None)  # ceil(14 x 1 - 5)
    config = ScenarioConfig(T, policy="service_level", coverage_tau_days=7, abc_service=True, service_level=.9)
    assert propose(row(abc="A"), config).service_level == .98
    assert propose(row(abc=None), config).service_level == .9
    for bad in (dict(policy="other"), dict(service_level=1.), dict(lead_time_days=-1), dict(abc_service=1)):
        with pytest.raises(MMSValidationError):
            ScenarioConfig(T, **bad)
    with pytest.raises(MMSValidationError):
        row(abc="D")


def test_scenario_allocates_budget_and_records_policy():
    snapshot = InventorySnapshot(T, "s1", "d1", (row("A", stock=5), row("B", stock=0)))
    config = ScenarioConfig(T, pstar=0, unit_budget_q=25, policy="service_level", coverage_tau_days=7)
    result = execute(snapshot, config, (.9, .8), {})
    assert [(i.sku_id, i.suggested_q, i.allocated_q) for i in result.review_list] == [("A", 15, 15), ("B", 20, 10)]
    assert result.review_list[0].target_level == 20 and "service level 95%" in result.review_list[0].explanation
    assert result.metadata["replenishment_version"] == "service-level-nb-v1"
    mb3 = ModelExecutor().run_model("MB3", snapshot, {"policy": "service_level", "coverage_tau_days": 7})
    assert mb3.ok and mb3.items[0]["suggested_q"] == 15 and mb3.items[0]["safety_stock"] == 11


def fixture_data():
    """X sells one unit a day from an empty start; Y has no demand. Reviews on days 0 and 7."""
    days = tuple(T + timedelta(days=i) for i in range(14))
    demand = np.tile([1., 0.], (14, 1))
    reviews = (days[0], days[7])
    return SimulationData(days, (1, 2), demand, np.zeros((14, 2)), np.array([10., 10.]),
                          {d: np.array([1., 0.]) for d in reviews}, {d: np.array([np.nan, np.nan]) for d in reviews},
                          {d: np.array(["A", None], dtype=object) for d in reviews})


def test_simulation_replays_orders_by_hand():
    data = fixture_data()
    result = simulate(data, parse_policy("coverage:7"), review_days=7, lead_time_days=0)
    # Each week 7 units arrive at once and sell out on the 7th day.
    assert result["fill_rate"] == 1 and result["units_ordered"] == 14 and result["order_lines_per_review"] == 1
    assert result["stockout_day_share"] == 2 / 14
    assert result["avg_inventory_value"] == 2 * (6 + 5 + 4 + 3 + 2 + 1) * 10 / 14
    late = simulate(data, parse_policy("coverage:7"), review_days=7, lead_time_days=2)
    assert late["fill_rate"] < 1
    # Both lose the first two days to the empty start; covering review + lead time avoids later gaps.
    service = simulate(data, parse_policy("service:0.95"), 7, 2)
    assert service["fill_rate"] == late["fill_rate"] == 12 / 14
    assert service["stockout_day_share"] < late["stockout_day_share"]
    assert parse_policy("service:abc").abc
    with pytest.raises(MMSValidationError):
        parse_policy("service:1.2")
