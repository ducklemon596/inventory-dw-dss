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
    assert app.title[0].value == "Replenishment"
    assert app.button(key="run_scenarios").label == "View plan"
    assert not any("Dữ liệu mô phỏng" in message.value or "Chỉ dùng thử" in message.value for message in app.caption)
    assert not any("Chọn thông tin bên trái" in message.value for message in app.info)
    assert app.selectbox(key="scenario_count").value == 1
    app.button(key="run_scenarios").click().run()
    assert not app.exception
    assert len(app.dataframe) >= 4  # independent Review/Order for two scenarios
    app.selectbox(key="action_0_B").set_value("edited")
    app.number_input(key="edit_0_B").set_value(3)
    app.button(key="save_decision").click().run()
    assert not app.exception
    assert any("Decision saved" in msg.value for msg in app.success)
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


def test_unsubmitted_parameter_changes_disable_saving_stale_plan(tmp_path,monkeypatch):
    monkeypatch.setenv("MMS_DATA_SOURCE","demo")
    monkeypatch.setenv("MMS_DECISIONS_PATH",str(tmp_path/"stale.sqlite"))
    app=AppTest.from_file(str(Path(__file__).parents[2]/"src/inventory_dw_dss/mms/ui.py"),default_timeout=20).run()
    app.button(key="run_scenarios").click().run()
    app.number_input(key="q_0").set_value(0).run()
    assert not app.exception
    assert app.button(key="save_decision").disabled
    app.button(key="run_scenarios").click().run()
    assert not app.button(key="save_decision").disabled


def test_pending_notes_and_backtest_report_survive_reruns(tmp_path,monkeypatch):
    from inventory_dw_dss.mms.tracking.repository import DecisionRepository
    path=tmp_path/"notes.sqlite"
    monkeypatch.setenv("MMS_DATA_SOURCE","demo")
    monkeypatch.setenv("MMS_DECISIONS_PATH",str(path))
    app=AppTest.from_file(str(Path(__file__).parents[2]/"src/inventory_dw_dss/mms/ui.py"),default_timeout=20).run()
    app.button(key="run_scenarios").click().run()
    app.text_input(key="note_0_B").set_value("Cần kiểm đếm")
    app.button(key="save_decision").click().run()
    repo=DecisionRepository(path)
    saved=repo.get_session(repo.list_sessions()[0]["session_id"])
    assert saved["actions"][0]["action"] == "pending"
    app.button(key="evaluate").click().run()
    assert "_mms_backtest" in app.session_state
    app.text_input(key="sku_search").set_value("B").run()
    assert not app.exception
    assert "_mms_backtest" in app.session_state


def test_manager_drafts_survive_switching_comparison_scenarios(tmp_path,monkeypatch):
    monkeypatch.setenv("MMS_DATA_SOURCE","demo")
    monkeypatch.setenv("MMS_DECISIONS_PATH",str(tmp_path/"drafts.sqlite"))
    app=AppTest.from_file(str(Path(__file__).parents[2]/"src/inventory_dw_dss/mms/ui.py"),default_timeout=20).run()
    app.selectbox(key="scenario_count").set_value(2).run()
    app.button(key="run_scenarios").click().run()
    app.button(key="approve_allocated").click().run()
    app.selectbox(key="action_0_B").set_value("edited")
    app.number_input(key="edit_0_B").set_value(3)
    app.text_input(key="note_0_B").set_value("Giữ ghi chú khi so sánh").run()
    app.selectbox(key="active_scenario").set_value(1).run()
    app.selectbox(key="active_scenario").set_value(0).run()
    assert not app.exception
    assert app.selectbox(key="action_0_B").value == "edited"
    assert app.number_input(key="edit_0_B").value == 3
    assert app.text_input(key="note_0_B").value == "Giữ ghi chú khi so sánh"


def test_simple_workflow_retains_advanced_evaluation_and_explains_limits(tmp_path,monkeypatch):
    monkeypatch.setenv("MMS_DATA_SOURCE","demo")
    monkeypatch.setenv("MMS_DECISIONS_PATH",str(tmp_path/"simple.sqlite"))
    app=AppTest.from_file(str(Path(__file__).parents[2]/"src/inventory_dw_dss/mms/ui.py"),default_timeout=20).run()
    app.number_input(key="q_0").set_value(0)
    app.button(key="run_scenarios").click().run()
    assert not app.exception
    assert [tab.label for tab in app.tabs[:3]] == ["Review","Approve","History"]
    assert len(app.metric)==3
    assert app.session_state['comparison'].results[0].summary['units_allocated']==0
    frame=app.dataframe[0].value
    assert 'advice' in frame.columns
    assert any(text=='Limit reached' for text in frame['advice'])
    app.button(key="evaluate").click().run()
    assert not app.exception
    assert '_mms_backtest' in app.session_state


def test_unlimited_mode_disables_visible_quantity_and_explains_override(tmp_path,monkeypatch):
    monkeypatch.setenv("MMS_DATA_SOURCE","demo")
    monkeypatch.setenv("MMS_DECISIONS_PATH",str(tmp_path/"unlimited.sqlite"))
    app=AppTest.from_file(str(Path(__file__).parents[2]/"src/inventory_dw_dss/mms/ui.py"),default_timeout=20).run()
    app.checkbox(key="unlimited_0").check().run()
    assert app.number_input(key="q_0").disabled
    assert any('Unlimited quantity' in msg.value for msg in app.info)
    app.button(key="run_scenarios").click().run()
    assert not app.exception
    assert app.session_state['comparison'].results[0].config.unit_budget_q is None
    app.checkbox(key="unlimited_0").uncheck().run()
    assert not app.number_input(key="q_0").disabled
    assert app.button(key="save_decision").disabled


def test_start_screen_has_overview_and_create_plan_action(tmp_path,monkeypatch):
    monkeypatch.setenv("MMS_DATA_SOURCE","demo")
    monkeypatch.setenv("MMS_DECISIONS_PATH",str(tmp_path/'start.sqlite'))
    app=AppTest.from_file(str(Path(__file__).parents[2]/"src/inventory_dw_dss/mms/ui.py"),default_timeout=20).run()
    assert not app.exception
    assert len(app.metric)==3
    from datetime import date
    assert app.date_input(key="analysis_date").value==date(2025,6,30)
    assert app.date_input(key="analysis_date").min==date(2025,6,30)
    assert app.date_input(key="analysis_date").max==date(2025,6,30)
    app.button(key="create_plan").click().run()
    assert not app.exception
    assert 'comparison' in app.session_state


def test_planning_dates_preserve_gaps_and_exclude_training_future(monkeypatch):
    from datetime import date
    from types import SimpleNamespace
    from inventory_dw_dss.mms import ui
    monkeypatch.setattr(ui.st,'session_state',{})
    dates=(date(2025,6,2),date(2025,6,3),date(2025,6,10))
    runtime=SimpleNamespace(service=SimpleNamespace(
        provider=SimpleNamespace(snapshot_dates=lambda:dates),
        executor=SimpleNamespace(risk_model=SimpleNamespace(manifest={'supervised_data_cutoff':'2025-06-03'}))))
    assert ui.planning_dates(runtime)==dates[1:]
