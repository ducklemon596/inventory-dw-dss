from datetime import date
import json

import pytest

from inventory_dw_dss.mms.core.schemas import MMSValidationError
from inventory_dw_dss.mms.runtime import SourceSettings, build_runtime
from inventory_dw_dss.mms.cli import main


def test_default_demo_and_legacy_duckdb_settings_without_silent_production_fallback():
    settings = SourceSettings.from_env({})
    assert settings.source == "demo"
    runtime = build_runtime(settings)
    assert runtime.is_demo
    assert runtime.load_outcomes().version == "synthetic-outcomes-v1"
    assert SourceSettings.from_env({"MMS_DUCKDB_PATH": "approved.duckdb"}).source == "duckdb"
    for env in ({"MMS_DATA_SOURCE": "other"}, {"MMS_DATA_SOURCE": "clickhouse"},
                {"MMS_DATA_SOURCE": "duckdb"}, {"MMS_ARTIFACT_PATH": "risk.joblib"}):
        with pytest.raises(MMSValidationError): build_runtime(SourceSettings.from_env(env))


def test_clickhouse_settings_are_shared_but_secrets_are_not_printable():
    settings = SourceSettings.from_env({"MMS_DATA_SOURCE": "clickhouse", "MMS_RELEASE_ID": "r1",
        "CLICKHOUSE_PASSWORD": "sensitive", "MMS_ARTIFACT_PATH": "approved.joblib", "MMS_MANIFEST_PATH": "manifest.json"})
    assert settings.source == "clickhouse" and settings.release_id == "r1"
    assert "sensitive" not in repr(settings)
    with pytest.raises(MMSValidationError): SourceSettings.from_env({"CLICKHOUSE_HTTP_PORT": "bad"})


def test_cli_demo_scenario_and_validation_failures_are_json(capsys, monkeypatch):
    monkeypatch.delenv("MMS_DATA_SOURCE", raising=False)
    monkeypatch.delenv("MMS_DUCKDB_PATH", raising=False)
    monkeypatch.delenv("MMS_ARTIFACT_PATH", raising=False)
    monkeypatch.delenv("MMS_MANIFEST_PATH", raising=False)
    monkeypatch.delenv("MMS_RELEASE_ID", raising=False)
    assert main(["scenario", "--date", "2025-06-30", "--unit-budget", "15"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["summary"]["units_allocated"] == 15
    assert payload["synthetic_demo"] is True
    assert main(["check-artifact", "--artifact", "absent.joblib", "--manifest", "absent.json"]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_reference_cli_missing_original_file_does_not_claim_reproduction(capsys):
    assert main(["verify-reference", "--reference", "absent-original-tn.json"]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False


@pytest.mark.parametrize("cases", [None, 1])
def test_reference_cli_malformed_case_list_returns_json_error(tmp_path, cases, capsys):
    path=tmp_path/"malformed.json"
    path.write_text(json.dumps({"cases": cases}),encoding="utf-8")
    assert main(["verify-reference","--reference",str(path)]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_readiness_flags_synthetic_artifact_consistently(monkeypatch):
    from inventory_dw_dss.mms import cli
    from inventory_dw_dss.mms.demo import build_demo_service
    from inventory_dw_dss.mms.runtime import MMSRuntime
    service=build_demo_service()
    service.executor.risk_model.manifest={"data_kind":"synthetic"}
    settings=SourceSettings(source="duckdb",duckdb_path="synthetic.duckdb")
    monkeypatch.setattr(cli,"build_provider",lambda _:service.provider)
    monkeypatch.setattr(cli,"build_runtime",lambda _:MMSRuntime(service,settings))
    report=cli.readiness(settings,"2025-06-30")
    assert report["synthetic_demo"] is True
    assert report["production_ready"] is False
