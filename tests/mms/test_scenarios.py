from dataclasses import replace

import pytest

from inventory_dw_dss.mms.core.schemas import ArtifactError, MMSValidationError, ScenarioConfig, to_dict
from inventory_dw_dss.mms.service import MMSService
from test_models import snapshot
from test_data import T


class FixtureRisk:
    version = "fixture-scores-v1"
    calibrated = False

    def __init__(self): self.calls = 0

    def score(self, rows):
        self.calls += 1
        return [dict(A=.9, B=.8, C=.8, D=.1)[r.sku_id] for r in rows]


class FrozenProvider:
    def __init__(self):
        row = snapshot().rows[0]
        self.snapshot = replace(snapshot(), rows=(row,
            replace(row, sku_id="B", available_stock=0, revenue_90d=500),
            replace(row, sku_id="C", available_stock=2, revenue_90d=100),
            replace(row, sku_id="D", available_stock=0)))
        self.calls = 0

    def get_snapshot(self, t, filters=None):
        self.calls += 1
        return self.snapshot


def service(): return MMSService(FrozenProvider(), FixtureRisk())


def test_review_includes_q_zero_order_excludes_it_and_partial_budget():
    s = service()
    result = s.execute_scenario(ScenarioConfig(T, top_k=3, unit_budget_q=15))
    assert [r.sku_id for r in result.review_list] == ["A", "B", "C"]
    assert [r.suggested_q for r in result.review_list] == [0, 14, 12]
    assert [(r.sku_id, r.allocated_q) for r in result.order_proposal] == [("B", 14), ("C", 1)]
    assert result.summary["units_suggested"] == 26
    assert result.summary["units_allocated"] == 15
    assert result.summary["budget_remaining"] == 0
    assert result == s.execute_scenario(result.config)


@pytest.mark.parametrize("profile,expected", [("RiskFirst", ["A", "B", "C"]),
    ("LowStock", ["B", "C", "A"]), ("DOS", ["B", "C", "A"]),
    ("RevenueAtRisk", ["B", "A", "C"])])
def test_profile_definitions_and_ties(profile, expected):
    result = service().execute_scenario(ScenarioConfig(T, profile=profile))
    assert [r.sku_id for r in result.review_list] == expected


def test_threshold_then_ranking_then_k_and_parameters_have_expected_effect():
    s = service()
    assert len(s.execute_scenario(ScenarioConfig(T, pstar=.85)).review_list) == 1
    assert len(s.execute_scenario(ScenarioConfig(T, top_k=1)).review_list) == 1
    zero = s.execute_scenario(ScenarioConfig(T, unit_budget_q=0))
    assert len(zero.review_list) == 3 and not zero.order_proposal
    long = s.execute_scenario(ScenarioConfig(T, coverage_tau_days=40))
    assert long.review_list[0].suggested_q == 10
    assert [r.sku_id for r in long.review_list] == [r.sku_id for r in zero.review_list]


def test_compare_freezes_snapshot_and_scores_once_and_requires_2_to_4_same_date():
    s = service()
    a = ScenarioConfig(T)
    comparison = s.compare_scenarios([a, replace(a, profile="LowStock")])
    assert s.provider.calls == 1 and s.executor.risk_model.calls == 1
    assert comparison.overlap[0]["review_jaccard"] == 1
    assert comparison.overlap[0]["order_jaccard"] == 1
    for configs in ([a], [a]*5, [a, replace(a, analysis_date="2025-07-01")]):
        with pytest.raises(MMSValidationError): s.compare_scenarios(configs)


def test_diagnostics_negative_stock_and_no_artifact_fallback():
    s = service()
    row = s.provider.snapshot.rows[0]
    s.provider.snapshot = replace(s.provider.snapshot, rows=(replace(row,
        available_stock=-1, observed_stockout_days=29, diagnostic_observed_days=30,
        flags=("sop_excluded_diagnostics",)),))
    result = s.execute_scenario(ScenarioConfig(T))
    assert "chronic_stockout" in result.review_list[0].flags
    assert "negative_stock" in result.review_list[0].flags
    assert not result.order_proposal
    assert result.review_list[0].explanation
    with pytest.raises(ArtifactError):
        MMSService(s.provider).execute_scenario(ScenarioConfig(T))
    import json
    json.dumps(to_dict(result), allow_nan=False)
