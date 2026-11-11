from dataclasses import replace
import hashlib
import json

import joblib
import numpy as np
import pytest
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

from inventory_dw_dss.mms.core.schemas import ArtifactError, MMSValidationError, ScenarioConfig
from inventory_dw_dss.mms.core.executor import ModelExecutor
from inventory_dw_dss.mms.data.mock import MockDataProvider
from inventory_dw_dss.mms.models.histgb import HistGBRiskModel
from inventory_dw_dss.mms.models.ma90 import forecast
from inventory_dw_dss.mms.models.replenishment import suggested_quantity
from test_data import records, T


def snapshot():
    return MockDataProvider(*records()).get_snapshot(T)


def test_ma90_and_coverage_rounding_zero_demand_and_eligibility():
    row = snapshot().rows[0]
    assert forecast(row) == {"vel90": 1, "forecast_30d": 30}
    assert suggested_quantity(row, 14) == 0
    assert suggested_quantity(replace(row, available_stock=0.2), 14) == 14
    assert suggested_quantity(replace(row, sales_7d=0, sales_30d=0, sales_90d=0), 14) == 0
    assert suggested_quantity(replace(row, available_stock=-1), 14) == 0
    assert suggested_quantity(replace(row, eligible=False), 60) == 0


@pytest.mark.parametrize("kwargs", [dict(pstar=-1), dict(pstar=float('nan')), dict(top_k=0),
    dict(top_k=True), dict(top_k=1.5), dict(unit_budget_q=-1), dict(unit_budget_q=2.5),
    dict(coverage_tau_days=0), dict(profile="Other"), dict(analysis_date="2025-02-30")])
def test_invalid_config(kwargs):
    with pytest.raises(MMSValidationError):
        ScenarioConfig(**({"analysis_date": T} | kwargs))


def test_directory_executor_and_structured_errors():
    executor = ModelExecutor()
    assert [m.model_id for m in executor.list_models()] == ["MB1", "MB2", "MB3", "MB4"]
    snap = snapshot()
    a = executor.run_model("MB1", snap, {})
    assert a == executor.run_model("MB1", snap, {})
    assert a.ok and a.items[0]["forecast_30d"] == 30
    assert a.metadata["snapshot_version"] == snap.snapshot_version
    assert executor.run_model("MB2", snap, {}).error.code == "artifact_unavailable"
    assert executor.run_model("bad", snap, {}).error.code == "invalid_request"
    assert executor.run_model("MB1", snap, {"tau": 2}).error.code == "invalid_request"
    assert not executor.run_model("MB3", snap, {"coverage_tau_days": -1}).ok


def test_real_histgb_artifact_order_hash_and_version_contract(tmp_path):
    import pandas as pd
    x = pd.DataFrame({"sales_90d": [0, 1, 90, 180] * 10, "available_stock": [30, 20, 0, 1] * 10})
    model = HistGradientBoostingClassifier(max_iter=2, min_samples_leaf=2, random_state=7).fit(x, [0, 0, 1, 1]*10)
    artifact = tmp_path / "risk.joblib"
    joblib.dump(model, artifact)
    manifest = dict(artifact_version="test-only-v1", sklearn_version=sklearn.__version__,
                    sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    features=["sales_90d", "available_stock"], positive_class=1,
                    preprocessing="embedded", calibrated=False,
                    compatible_data_versions=["export-v1"],
                    supervised_data_cutoff="2025-06-29")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    scorer = HistGBRiskModel.load(artifact, manifest_path)
    snap = snapshot()
    expected = model.predict_proba(pd.DataFrame({"sales_90d": [90.], "available_stock": [30.]}))[0, 1]
    assert scorer.score(snap.rows) == pytest.approx([expected])
    assert not scorer.calibrated
    scorer.validate_snapshot(snap)
    with pytest.raises(ArtifactError, match="data version"):
        scorer.validate_snapshot(replace(snap, data_version="incompatible-export"))
    with pytest.raises(ArtifactError, match="cutoff"):
        scorer.validate_snapshot(replace(snap, analysis_date="2025-06-01"))
    with pytest.raises(ArtifactError, match="feature"):
        scorer.score([replace(snap.rows[0], features={"sales_90d": 123})])
    manifest["features"].reverse()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ArtifactError, match="order"):
        HistGBRiskModel.load(artifact, manifest_path)
    manifest["features"].reverse()
    manifest["sha256"] = "bad"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ArtifactError, match="checksum"):
        HistGBRiskModel.load(artifact, manifest_path)
