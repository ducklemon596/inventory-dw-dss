from datetime import timedelta
import json

import pytest

from inventory_dw_dss.mms.core.schemas import ArtifactError, MMSValidationError, ScenarioConfig
from inventory_dw_dss.mms.runtime import SourceSettings, build_runtime
from inventory_dw_dss.mms.training import build_synthetic_bundle, train_histgb
from inventory_dw_dss.mms.verification import run_reference_suite


def test_new_trained_bundle_is_reproducible_and_temporally_held_out(tmp_path):
    info = build_synthetic_bundle(tmp_path / "bundle", seed=7)
    assert info["data_kind"] == "synthetic" and info["original_tn_reproduction"] is False
    settings = SourceSettings(source="duckdb", duckdb_path=info["database"],
        artifact_path=info["artifact"], manifest_path=info["manifest"])
    runtime = build_runtime(settings)
    assert runtime.is_demo  # trained model must still be labelled synthetic
    config = ScenarioConfig("2025-06-30", pstar=0, unit_budget_q=150)
    result = runtime.service.execute_scenario(config)
    assert result.summary["units_allocated"] <= 150
    manifest = json.loads(open(info["manifest"], encoding="utf-8").read())
    assert manifest["supervised_data_cutoff"] < "2025-06-30"
    assert manifest["training_samples"] >= 20
    assert len(manifest["training_data_sha256"]) == 64
    with pytest.raises(ArtifactError, match="cutoff"):
        runtime.service.execute_scenario(ScenarioConfig("2025-04-01"))
    spec = json.loads(open(info["reference"], encoding="utf-8").read())
    assert run_reference_suite(runtime.service, spec, runtime.load_outcomes())["passed"]
    with pytest.raises(MMSValidationError, match="exists"):
        build_synthetic_bundle(tmp_path / "bundle", seed=7)
    other = build_synthetic_bundle(tmp_path / "other", seed=7)
    other_manifest = json.loads(open(other["manifest"], encoding="utf-8").read())
    assert manifest["training_data_sha256"] == other_manifest["training_data_sha256"]
    other_runtime = build_runtime(SourceSettings(source="duckdb", duckdb_path=other["database"],
        artifact_path=other["artifact"], manifest_path=other["manifest"]))
    assert result == other_runtime.service.execute_scenario(config)


def test_invalid_seed_is_rejected_before_reading_training_data(tmp_path):
    with pytest.raises(MMSValidationError,match="seed"):
        train_histgb(None,None,["2025-06-30"],tmp_path/"bad-seed","invalid",data_kind="synthetic",seed=-1)
