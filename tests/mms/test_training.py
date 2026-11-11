import json
from datetime import timedelta

import pytest

from inventory_dw_dss.mms.evaluation.backtesting import Backtester, risk_metrics
from inventory_dw_dss.mms.models.risk import RiskModel
from inventory_dw_dss.mms.schemas import ArtifactError, MMSError, ScenarioConfig
from inventory_dw_dss.mms.service import MMSService
from inventory_dw_dss.mms.training import train

from fixtures import T, Outcomes, Reader, RiskModel as FixtureModel, daily_sales, row

# Product i holds i units in total and i // 2 on the shelf; each sells one unit a day.
ROWS = tuple(row(f"S{i:02d}", i, i // 2) for i in range(40))
SKUS = [r.sku_id for r in ROWS]


def outcomes(horizon=7, stocktake_sku=None):
    observations = daily_sales(SKUS, T, horizon, stockout=lambda s, d: int(s[1:]) // 2 < d,
                               stocktake=lambda s, d: s == stocktake_sku and d == 1)
    return Outcomes(observations, T + timedelta(days=horizon))


def small_model(monkeypatch, **params):
    """Few features and trees: the fixture has 40 rows and no mart columns."""
    import inventory_dw_dss.mms.training as training
    monkeypatch.setattr(training, "FEATURES", ("available_stock", "dispensary_stock", "vel90"))
    monkeypatch.setattr(training, "PARAMS", training.PARAMS | {"max_iter": 20, "min_samples_leaf": 2} | params)


def test_risk_metrics_by_hand():
    m = risk_metrics([1, 0, 1, 0], [.9, .8, .7, .1], k=2)
    assert (m["precision_at_k"], m["recall_at_k"], m["lift"], m["roc_auc"]) == (.5, .5, 1., .75)


def test_training_labels_pharmacy_shortfall_and_writes_a_loadable_bundle(tmp_path, monkeypatch):
    small_model(monkeypatch)
    info = train(Reader(ROWS), outcomes(stocktake_sku="S05"), [T], tmp_path / "model", "test-v1", horizon_days=7)
    manifest = json.loads((tmp_path / "model/manifest.json").read_text())
    # S00 holds nothing; S05's window has a stocktake; 7 units sold empty S01..S07 except S05.
    assert info["training_rows"] == 38 and info["positive_rows"] == 6 and manifest["stocktake_rows_dropped"] == 1
    assert manifest["risk_target"] == "pharmacy_shortfall" and manifest["supervised_data_cutoff"] == "2025-06-09"
    model = RiskModel.load(tmp_path / "model/histgb.joblib", tmp_path / "model/manifest.json")
    assert len(model.score(ROWS)) == 40
    with pytest.raises(ArtifactError, match="saw outcomes"):
        model.check_snapshot(Reader(ROWS).snapshot(T))
    with pytest.raises(MMSError, match="new directory"):
        train(Reader(ROWS), outcomes(), [T], tmp_path / "model", "again", horizon_days=7)


def test_tampered_bundle_is_refused(tmp_path, monkeypatch):
    small_model(monkeypatch, max_iter=5)
    train(Reader(ROWS), outcomes(), [T], tmp_path / "m", "v", horizon_days=7)
    (tmp_path / "m/histgb.joblib").write_bytes(b"changed")
    with pytest.raises(ArtifactError, match="checksum"):
        RiskModel.load(tmp_path / "m/histgb.joblib", tmp_path / "m/manifest.json")


# Pharmacy: S01..S39 hold stock and S01..S07 sell out. Shelf: S02..S39 hold stock, S02..S13 run empty.
@pytest.mark.parametrize("target, cohort, events", [("pharmacy_shortfall", 39, 7), ("dispensary_stockout", 38, 12)])
def test_backtest_labels_follow_the_model_target(target, cohort, events):
    service = MMSService(Reader(ROWS), FixtureModel(target))
    report = Backtester(service, outcomes()).run(ScenarioConfig(T, pstar=0, top_k=5), [T], 7)
    risk = report.per_date[0]["risk"]
    assert (risk["cohort"], risk["events"], report.target) == (cohort, events, target)
    assert risk["precision_at_k"] == 1   # the fixture model ranks the emptiest products first
