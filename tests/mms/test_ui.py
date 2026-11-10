import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from inventory_dw_dss.mms.demo import build_demo_service, demo_outcomes
from inventory_dw_dss.mms.core.schemas import ScenarioConfig, to_dict
from inventory_dw_dss.mms.evaluation.backtesting import Backtester


def test_deterministic_demo_runs_all_models_and_evaluation():
    service = build_demo_service()
    result = service.execute_scenario(ScenarioConfig("2025-06-30", unit_budget_q=15))
    assert result == build_demo_service().execute_scenario(result.config)
    assert result.metadata["artifact_version"] == "synthetic-demo-v1"
    snapshot = service.provider.get_snapshot("2025-06-30")
    for model in service.list_models():
        assert service.run_model(model.model_id, snapshot).ok
    report = Backtester(service, demo_outcomes()).run(result.config, ["2025-06-30"], 30)
    assert report.aggregate["evaluated_dates"] == 1
    json.dumps(to_dict(report), allow_nan=False)


def test_streamlit_compare_save_reopen_and_parameter_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_DECISIONS_PATH", str(tmp_path / "ui.sqlite"))
    for key in ("MMS_DUCKDB_PATH", "MMS_ARTIFACT_PATH", "MMS_MANIFEST_PATH"):
        monkeypatch.delenv(key, raising=False)
    app = AppTest.from_file(str(Path(__file__).parents[2] / "src/inventory_dw_dss/mms/ui.py"), default_timeout=20).run()
    assert not app.exception
    app.button(key="run_scenarios").click().run()
    assert not app.exception
    assert len(app.dataframe) >= 4  # independent Review/Order for two scenarios
    app.selectbox(key="action_0_B").set_value("edited")
    app.number_input(key="edit_0_B").set_value(3)
    app.button(key="save_decision").click().run()
    assert not app.exception
    assert any("Saved" in msg.value for msg in app.success)
    app.button(key="reopen_session").click().run()
    assert not app.exception
    assert any("Saved decision" in h.value for h in app.subheader)
    app.number_input(key="q_0").set_value(0)
    app.button(key="run_scenarios").click().run()
    assert not app.exception
    assert app.session_state["comparison"].results[0].summary["units_allocated"] == 0
    assert app.selectbox(key="action_0_B").value == "pending"
    assert app.number_input(key="edit_0_B").value == 0
    app.button(key="evaluate").click().run()
    assert not app.exception


def test_sqlite_path_error_is_rendered_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_DECISIONS_PATH", str(tmp_path))
    monkeypatch.delenv("MMS_DUCKDB_PATH", raising=False)
    app = AppTest.from_file(str(Path(__file__).parents[2] / "src/inventory_dw_dss/mms/ui.py"), default_timeout=20).run()
    assert not app.exception
    assert any("Database" in error.value for error in app.error)


def test_team_application_can_embed_mms_without_reconfiguring_page(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_DECISIONS_PATH", str(tmp_path / "embedded.sqlite"))
    monkeypatch.setenv("MMS_DATA_SOURCE", "demo")
    script = "import streamlit as st\nst.set_page_config(page_title='Team DSS')\nfrom inventory_dw_dss.mms.ui import render\nrender(configure_page=False)"
    app = AppTest.from_string(script, default_timeout=20).run()
    assert not app.exception
    app.button(key="run_scenarios").click().run()
    assert not app.exception and len(app.dataframe) >= 4


def test_explicit_production_mode_missing_release_never_displays_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_DATA_SOURCE", "clickhouse")
    monkeypatch.delenv("MMS_RELEASE_ID", raising=False)
    app = AppTest.from_file(str(Path(__file__).parents[2] / "src/inventory_dw_dss/mms/ui.py"), default_timeout=20).run()
    assert not app.exception
    assert any("MMS_RELEASE_ID" in msg.value for msg in app.error)
    assert not any("SYNTHETIC" in msg.value for msg in app.warning)


def test_runtime_switch_clears_results_and_manager_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MMS_DECISIONS_PATH",str(tmp_path/"switch.sqlite"))
    script = '''import streamlit as st
from inventory_dw_dss.mms.runtime import MMSRuntime, SourceSettings
from inventory_dw_dss.mms.demo import build_demo_service
from inventory_dw_dss.mms.ui import render
mode=st.selectbox("Runtime",["demo","duckdb"],key="host_runtime")
render(application_runtime=MMSRuntime(build_demo_service(),SourceSettings(source=mode,duckdb_path="different-source.duckdb")))
'''
    app=AppTest.from_string(script,default_timeout=20).run()
    app.button(key="run_scenarios").click().run()
    assert not app.exception and len(app.dataframe)>=4
    app.selectbox(key="action_0_B").set_value("edited")
    app.selectbox(key="host_runtime").set_value("duckdb").run()
    assert not app.exception
    assert not app.dataframe
    assert "comparison" not in app.session_state
    assert not any(b.key=="save_decision" for b in app.button)
