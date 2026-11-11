from datetime import timedelta
from dataclasses import replace

import pytest

from inventory_dw_dss.mms.core.schemas import MMSValidationError, ScenarioConfig
from inventory_dw_dss.mms.evaluation.metrics import demand_metrics, risk_metrics
from inventory_dw_dss.mms.evaluation.backtesting import Backtester, Observation, OutcomeProvider
from test_scenarios import service
from test_data import T


def outcomes(t=T, horizon=30, cutoff=None):
    rows = [Observation(t+timedelta(days=d), sku, sales_quantity=2,
                        stockout=(sku == "C" and d == 3), received_quantity=(5 if d == 2 else 0))
            for sku in "ABCD" for d in range(1, horizon+1)]
    return OutcomeProvider(rows, cutoff or t+timedelta(days=horizon), "outcomes-v1")


def test_metrics_have_defined_denominators_and_ties():
    assert demand_metrics([10, 20], [5, 25]) == {"wape": 1/3, "bias": 0.0}
    assert demand_metrics([0], [0]) == {"wape": None, "bias": None}
    m = risk_metrics([0, 1, 1, 0], [.9, .8, .8, .1], ["A", "B", "C", "D"], 2)
    assert m["precision_at_k"] == .5 and m["recall_at_k"] == .5 and m["lift"] == 1
    assert m["roc_auc"] == .5
    assert risk_metrics([0, 0], [.8, .1], ["A", "B"], 2)["roc_auc"] is None


def test_backtest_separates_existing_stockouts_and_uses_independent_future_window():
    s = service()
    report = Backtester(s, outcomes()).run(ScenarioConfig(T), [T], 7)
    day = report.per_date[0]
    assert day["status"] == "evaluated"
    assert day["existing_stockout_count"] == 2  # B and D already at zero at T
    assert day["new_stockout_count"] == 1  # C only
    assert day["risk"]["precision_at_k"] == .5  # only A,C in incident-risk cohort
    assert day["risk"]["recall_at_k"] == 1
    assert day["demand"] == {"wape": .5, "bias": -.5}
    assert report.aggregate["evaluated_dates"] == 1
    assert s.provider.calls == 1
    assert day["metadata"]["outcome_version"] == "outcomes-v1"
    assert day["allocation"]["q_zero_frequency"] == 1/3


def test_incomplete_windows_and_stocktaking_are_reported_not_scored():
    incomplete = Backtester(service(), outcomes(cutoff=T+timedelta(days=6)))
    assert incomplete.run(ScenarioConfig(T), [T], 7).per_date[0]["status"] == "incomplete"
    t = T.replace(month=7, day=31)
    # Special affected date must be excluded before attempting to fetch inputs.
    s = service()
    report = Backtester(s, outcomes(t)).run(ScenarioConfig(t), [t], 30)
    assert report.per_date[0]["status"] == "excluded_sop202508"
    assert s.provider.calls == 0
    provider = outcomes(horizon=7)
    provider = OutcomeProvider([replace(o, sop_day=True) if o.observation_date.day == 2 else o
                                for o in provider.observations], T+timedelta(days=7), "v2")
    assert Backtester(service(), provider).run(ScenarioConfig(T), [T], 7).per_date[0]["status"] == "excluded_sop"


def test_missing_or_duplicate_outcomes_not_zero_and_horizon_validation():
    p = outcomes(horizon=7)
    missing = OutcomeProvider(p.observations[1:], p.data_cutoff, "v1")
    assert Backtester(service(), missing).run(ScenarioConfig(T), [T], 7).per_date[0]["status"] == "incomplete"
    with pytest.raises(MMSValidationError): OutcomeProvider([p.observations[0]]*2, p.data_cutoff, "v1")
    with pytest.raises(MMSValidationError): Backtester(service(), p).run(ScenarioConfig(T), [T], 8)


def test_optional_outcome_tables_missing_are_clear_service_errors():
    import duckdb
    with duckdb.connect() as connection:
        with pytest.raises(MMSValidationError, match="outcome export"):
            OutcomeProvider.from_duckdb(connection)


def test_backtest_enforces_supervised_artifact_cutoff_before_scoring():
    from inventory_dw_dss.mms.models.histgb import HistGBRiskModel
    from inventory_dw_dss.mms.core.schemas import ArtifactError
    s = service()
    s.executor.risk_model = HistGBRiskModel(None, dict(artifact_version="future-trained",
        calibrated=False, compatible_data_versions=["export-v1"], supervised_data_cutoff="2025-07-30"))
    with pytest.raises(ArtifactError, match="cutoff"):
        Backtester(s, outcomes()).run(ScenarioConfig(T), [T], 30)


def test_negative_balance_is_quality_failure_not_existing_stockout_label():
    s = service()
    rows = s.provider.snapshot.rows
    s.provider.snapshot = replace(s.provider.snapshot, rows=(replace(rows[0], available_stock=-3), *rows[1:]))
    day = Backtester(s, outcomes()).run(ScenarioConfig(T), [T], 7).per_date[0]
    assert day["existing_stockout_count"] == 2
    assert day["negative_balance_count"] == 1
