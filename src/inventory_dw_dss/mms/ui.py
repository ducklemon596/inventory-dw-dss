"""Run: uv run --extra ui streamlit run src/inventory_dw_dss/mms/ui.py"""
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3

import duckdb
import streamlit as st

from inventory_dw_dss.mms.core.schemas import PROFILES, ScenarioComparison, ScenarioConfig, MMSValidationError, to_dict
from inventory_dw_dss.mms.data.duckdb_adapter import DuckDBDataProvider
from inventory_dw_dss.mms.demo import build_demo_service, demo_outcomes
from inventory_dw_dss.mms.evaluation.backtesting import Backtester, OutcomeProvider
from inventory_dw_dss.mms.models.histgb import HistGBRiskModel
from inventory_dw_dss.mms.service import MMSService
from inventory_dw_dss.mms.tracking.repository import DecisionRepository, ManagerAction


@st.cache_resource
def production_service(database, artifact, manifest):
    return MMSService(DuckDBDataProvider(database), HistGBRiskModel.load(artifact, manifest))


def runtime():
    database = os.getenv("MMS_DUCKDB_PATH")
    if database:
        artifact, manifest = os.getenv("MMS_ARTIFACT_PATH"), os.getenv("MMS_MANIFEST_PATH")
        if not artifact or not manifest:
            raise MMSValidationError("Set MMS_ARTIFACT_PATH and MMS_MANIFEST_PATH for production inference")
        return production_service(database, artifact, manifest), False
    return build_demo_service(), True


def read_outcomes(demo):
    if demo:
        return demo_outcomes()
    import duckdb
    with duckdb.connect(os.environ["MMS_DUCKDB_PATH"], read_only=True) as connection:
        return OutcomeProvider.from_duckdb(connection)


def render():
    st.set_page_config(page_title="Inventory MMS", layout="wide")
    st.title("Inventory decision support")
    try:
        service, demo = runtime()
        if demo:
            st.warning("SYNTHETIC DEMO — fixed scores, not trained HistGB predictions or experimental results.")
        st.caption("Review alerts and proposed units separately. Q is a unit budget; manager review is required.")
        with st.expander("Model catalog"):
            st.json(to_dict(service.list_models()))
        with st.form("scenario_parameters"):
            analysis_date = st.text_input("Analysis date (YYYY-MM-DD)", "2025-06-30")
            count = st.selectbox("Number of scenarios", [2, 3, 4, 1])
            configs = []
            # Render all four slots so changing count does not require a form submit.
            for i in range(4):
                with st.expander(f"Scenario {i+1} (used when count ≥ {i+1})", expanded=i == 0):
                    profile = st.selectbox("Ranking profile", PROFILES, index=i, key=f"profile_{i}")
                    pstar = st.number_input("Risk threshold", min_value=0., max_value=1., value=.3, key=f"pstar_{i}")
                    k = st.number_input("Review slots K", min_value=1, value=50, key=f"k_{i}")
                    tau = st.number_input("Coverage days tau", min_value=.1, value=14., key=f"tau_{i}")
                    unlimited = st.checkbox("No unit budget limit", value=False, key=f"unlimited_{i}")
                    q = st.number_input("Unit budget Q", min_value=0, value=15, key=f"q_{i}")
                    configs.append(dict(analysis_date=analysis_date, profile=profile, pstar=pstar,
                        top_k=k, unit_budget_q=None if unlimited else q, coverage_tau_days=tau))
            run = st.form_submit_button("Run scenarios", key="run_scenarios")
        if run:
            active = configs[:count]
            comparison = (service.compare_scenarios(active) if count > 1 else
                          ScenarioComparison((service.execute_scenario(active[0]),), ()))
            # Manager inputs belong to the exact run, even if SKU IDs are reused.
            for key in list(st.session_state):
                if key.startswith(("action_", "edit_", "note_")):
                    del st.session_state[key]
            st.session_state["comparison"] = comparison
        comparison = st.session_state.get("comparison")
        if comparison:
            for i, result in enumerate(comparison.results):
                st.subheader(f"Scenario {i+1}: {result.config.profile}")
                st.json(result.summary)
                review, orders = st.tabs(["Review List", "Order Proposal"])
                review.dataframe(to_dict(result.review_list), width="stretch")
                orders.dataframe(to_dict(result.order_proposal), width="stretch")
            if comparison.overlap:
                st.subheader("Scenario differences")
                st.json(to_dict(comparison.overlap))
            st.download_button("Download results JSON", json.dumps(to_dict(comparison), indent=2, allow_nan=False),
                               file_name="mms-scenarios.json", mime="application/json")
            selected = st.selectbox("Scenario to save / evaluate", range(len(comparison.results)),
                                    format_func=lambda i: f"Scenario {i+1}")
            result = comparison.results[selected]
            st.subheader("Manager review")
            actions = []
            with st.form("manager_actions"):
                for item in result.review_list:
                    with st.expander(f"{item.sku_id}: {item.explanation}"):
                        action = st.selectbox("Action", ["pending", "accepted", "rejected", "edited"], key=f"action_{selected}_{item.sku_id}")
                        quantity = st.number_input("Edited quantity (used for edited action)", min_value=0,
                            value=item.allocated_q, key=f"edit_{selected}_{item.sku_id}")
                        note = st.text_input("Manager note", key=f"note_{selected}_{item.sku_id}")
                        if action != "pending":
                            actions.append(ManagerAction(item.sku_id, action, quantity if action == "edited" else None, note))
                save = st.form_submit_button("Save decision", key="save_decision")
            if save:
                session = repository().save_decision(result, actions)
                st.success(f"Saved decision {session['session_id']}")
            st.subheader("Historical evaluation")
            evaluation_dates = st.text_input("Decision dates (comma separated)", str(result.config.analysis_date))
            horizon = st.selectbox("Outcome horizon days", [7, 14, 30])
            if st.button("Evaluate", key="evaluate"):
                report = Backtester(service, read_outcomes(demo)).run(result.config,
                    [d.strip() for d in evaluation_dates.split(",")], horizon)
                st.json(to_dict(report))
        st.subheader("Saved sessions")
        sessions = repository().list_sessions()
        if sessions:
            session_id = st.selectbox("Session", [s["session_id"] for s in sessions])
            if st.button("Reopen session", key="reopen_session"):
                st.session_state["reopened_session"] = repository().get_session(session_id)
            if st.button("Observe historical follow-up", key="followup"):
                st.session_state["reopened_session"] = repository().add_followups(session_id, read_outcomes(demo))
            if st.session_state.get("reopened_session"):
                st.subheader("Saved decision — exact configuration and versions")
                st.json(st.session_state["reopened_session"])
    except (MMSValidationError, OSError) as exc:
        st.error(str(exc))
    except (duckdb.Error, sqlite3.Error) as exc:
        st.error(f"Database unavailable or export schema incomplete: {exc}")


def repository():
    path = Path(os.getenv("MMS_DECISIONS_PATH", "reports/mms-decisions.sqlite"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return DecisionRepository(path)


if __name__ == "__main__":
    render()
