"""Run: uv run --extra ui streamlit run src/inventory_dw_dss/mms/ui.py"""
import json
import os
from pathlib import Path
import sqlite3
import hashlib
from datetime import date

import duckdb
import streamlit as st

from inventory_dw_dss.mms.core.schemas import PROFILES, ScenarioComparison, ScenarioConfig, MMSValidationError, as_date
from inventory_dw_dss.mms.runtime import SourceSettings, build_runtime
from inventory_dw_dss.mms.tracking.repository import DecisionRepository
from inventory_dw_dss.mms.ui_theme import apply_theme
from inventory_dw_dss.mms.ui_presenters import (PROFILE_LABELS, config_matches, csv_export, scenario_label)
from inventory_dw_dss.mms.ui_views import (show_items, result_metrics, comparison_view,
    manager_view, evaluation_view, sessions_view)


@st.cache_resource
def configured_runtime(settings):
    return build_runtime(settings)


def reset_manager_inputs():
    st.session_state.pop("_mms_manager_drafts",None)
    for key in list(st.session_state):
        if key.startswith(("action_", "edit_", "note_")):
            del st.session_state[key]


def bind_runtime(active_runtime):
    settings = active_runtime.settings
    model = active_runtime.service.executor.risk_model
    manifest = getattr(model,"manifest",{})
    # Credentials are deliberately omitted from retained UI provenance.
    identity = {name:getattr(settings,name) for name in ("source","duckdb_path","host","port",
        "database","username","secure","release_id","artifact_path","manifest_path")}
    identity.update(artifact_version=getattr(model,"version",None), artifact_sha256=manifest.get("sha256"),
                    data_kind=manifest.get("data_kind"))
    token=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    if st.session_state.get("_mms_runtime_identity") != token:
        st.session_state.pop("comparison",None)
        st.session_state.pop("reopened_session",None)
        for key in ("_mms_backtest","_mms_overview","_mms_last_saved","evaluation_dates","_mms_plan_dates","analysis_date"):
            st.session_state.pop(key,None)
        reset_manager_inputs()
        st.session_state["_mms_runtime_identity"]=token


def planning_dates(runtime):
    if '_mms_plan_dates' not in st.session_state:
        provider=runtime.service.provider
        if not hasattr(provider,'snapshot_dates'):
            return None
        dates=provider.snapshot_dates()
        manifest=getattr(runtime.service.executor.risk_model,'manifest',{})
        cutoff=manifest.get('supervised_data_cutoff')
        if cutoff:
            dates=tuple(t for t in dates if t>=as_date(cutoff))
        st.session_state['_mms_plan_dates']=dates
    return st.session_state['_mms_plan_dates']


def sidebar_controls(runtime):
    with st.sidebar:
        st.html('<div class="mms-brand">Inventory Studio</div>')
        st.divider()
        dates=planning_dates(runtime)
        if dates is not None:
            if not dates:
                raise MMSValidationError("No snapshot dates are compatible with this model.")
            default=date(2025,6,30) if date(2025,6,30) in dates else dates[-1]
            analysis_date=st.date_input("Plan date",value=default,min_value=dates[0],max_value=dates[-1],
                key="analysis_date",format="DD/MM/YYYY",
                help="Choose a date within the available data range.")
        else:
            analysis_date=st.date_input("Plan date",date(2025,6,30),key="analysis_date")
        configs=[]
        tau=st.number_input("Stock cover (days)",min_value=.1,value=14.,key="tau_0")
        q=st.number_input("Quantity limit",min_value=0,help="Total SKU-specific units, not money.",
            value=15 if runtime.settings.source=="demo" else 150,key="q_0",
            disabled=st.session_state.get("unlimited_0",False))
        if st.session_state.get("unlimited_0",False):
            st.info("Unlimited quantity")
        run=st.button("View plan",key="run_scenarios",type="primary",width="stretch",
            disabled=dates is not None and analysis_date not in dates)
        with st.expander("Advanced",expanded=False):
            count=st.selectbox("Scenarios",[1,2,3,4],key="scenario_count")
            st.caption("Defaults work for most plans.")
            for i in range(count):
                st.markdown(f"**Scenario {chr(65+i)}**")
                profile=st.selectbox("Ranking",PROFILES,index=i,key=f"profile_{i}",format_func=PROFILE_LABELS.get)
                pstar=st.number_input("Risk threshold",min_value=0.,max_value=1.,value=.3,step=.05,key=f"pstar_{i}")
                k=st.number_input("Maximum items",min_value=1,value=50,key=f"k_{i}")
                target=tau if i==0 else st.number_input("Stock cover (days)",min_value=.1,value=14.,key=f"tau_{i}")
                unlimited=st.checkbox("Unlimited quantity",key=f"unlimited_{i}")
                budget=q if i==0 else st.number_input("Quantity limit",min_value=0,
                    value=15 if runtime.settings.source=="demo" else 150,key=f"q_{i}",disabled=unlimited)
                configs.append(ScenarioConfig(analysis_date,profile=profile,pstar=pstar,top_k=k,
                    unit_budget_q=None if unlimited else budget,coverage_tau_days=target))
    return configs,run


def overview(runtime,analysis_date):
    token=(st.session_state['_mms_runtime_identity'],str(analysis_date))
    cached=st.session_state.get('_mms_overview')
    if not cached or cached['token']!=token:
        try:
            snapshot=runtime.service.provider.get_snapshot(analysis_date)
            cached={'token':token,'snapshot':snapshot}
        except MMSValidationError as exc:
            cached={'token':token,'error':str(exc)}
        st.session_state['_mms_overview']=cached
    if cached.get('error'):
        st.warning(f"Snapshot unavailable for this date: {cached['error']}")
        return
    rows=cached['snapshot'].rows
    for col,label,value in zip(st.columns(3),
        ['Items','In stock','No recent sales'],
        [len(rows),sum(r.available_stock>0 for r in rows),sum(r.sales_90d==0 for r in rows)]):
        col.metric(label,f"{value:,}")


def model_catalog(service):
    with st.expander("Model components"):
        names={"MB1":("MA90","Sales velocity and demand forecast."),
            "MB2":("HistGB","Stockout risk ranking."),
            "MB3":("Replenishment","Quantity for target stock cover."),
            "MB4":("Allocation","Planning with item and quantity limits.")}
        for col,model in zip(st.columns(4),service.list_models()):
            name,description=names[model.model_id]
            col.markdown(f"**{model.model_id} · {name}**")
            col.caption(description)


def render(configure_page=True,application_runtime=None):
    if configure_page:
        st.set_page_config(page_title="Inventory Studio",page_icon="▦",layout="wide")
    apply_theme()
    try:
        runtime=application_runtime or configured_runtime(SourceSettings.from_env())
        bind_runtime(runtime)
        configs,run=sidebar_controls(runtime)
        st.title("Replenishment")
        dates=planning_dates(runtime)
        if dates is not None and configs[0].analysis_date not in dates:
            st.info("No snapshot for this date. Choose another date.")
            return
        if not st.session_state.get('comparison') and not run:
            overview(runtime,configs[0].analysis_date)
            with st.container(border=True):
                st.html('<div class="mms-start-icon" aria-hidden="true">▦</div>')
                st.subheader("Your next order")
                run=st.button("Create plan",key="create_plan",type="primary")
        if run:
            with st.spinner("Building plan…"):
                comparison=(runtime.service.compare_scenarios(configs) if len(configs)>1 else
                    ScenarioComparison((runtime.service.execute_scenario(configs[0]),),()))
            reset_manager_inputs()
            for key in ('_mms_backtest','_mms_last_saved','evaluation_dates'):
                st.session_state.pop(key,None)
            if st.session_state.get('active_scenario',0)>=len(comparison.results):
                st.session_state.pop('active_scenario',None)
            st.session_state['comparison']=comparison
        comparison=st.session_state.get('comparison')
        if not comparison:
            with st.expander("Saved decisions",expanded=False):
                sessions_view(runtime,repository)
            return
        pending=not config_matches(comparison,configs)
        if pending:
            st.warning("Settings changed. Select View plan to update.")
        a,b=st.columns([2,1])
        if len(comparison.results)>1:
            selected=a.selectbox("Current scenario",range(len(comparison.results)),key='active_scenario',
                format_func=lambda i:scenario_label(i,comparison.results[i].config))
        else:
            selected=0
        result=comparison.results[selected]
        b.caption(f"As of {result.config.analysis_date:%d/%m/%Y}")
        result_metrics(result)
        st.write("")
        budget=result.config.unit_budget_q
        if budget is not None:
            st.caption(f"{result.summary['units_allocated']:,} / {budget:,} units · {result.config.coverage_tau_days:g} days · Not ordered")
        else:
            st.caption("Unlimited quantity · Not ordered")
        review,manage,sessions=st.tabs(["Review","Approve","History"])
        with review:
            top,search=st.columns([2,1])
            top.subheader("Items")
            query=search.text_input("Search items",key='sku_search',placeholder="Search items…",label_visibility='collapsed')
            show_items(result.review_list,'review_table',query,simple=True)
            st.download_button("Download CSV",csv_export(result.review_list),
                file_name=f'mms-review-{result.config.analysis_date}-{result.config.profile}.csv',
                mime='text/csv',key='export_review')
        with manage:
            show_items(result.order_proposal,'order_table',empty='No items to order. Check quantity limit and stock cover.',simple=True)
            st.download_button("Download order CSV",csv_export(result.order_proposal),
                file_name=f'mms-orders-{result.config.analysis_date}-{result.config.profile}.csv',mime='text/csv',key='export_orders')
            manager_view(result,selected,repository,pending)
        with sessions:
            sessions_view(runtime,repository)
        with st.expander("Analysis",expanded=False):
            compare,evaluate,details=st.tabs(["Compare scenarios","Backtest","Model details"])
            with compare:
                comparison_view(comparison)
            with evaluate:
                evaluation_view(result,runtime,pending)
            with details:
                st.caption("Risk scores rank items; they are not calibrated probabilities.")
                show_items(result.review_list,'technical_table')
                model_catalog(runtime.service)
    except (MMSValidationError,OSError) as exc:
        st.error(str(exc))
    except (duckdb.Error,sqlite3.Error) as exc:
        st.error(f"Database unavailable or export schema incomplete: {exc}")


def repository():
    path = Path(os.getenv("MMS_DECISIONS_PATH", "reports/mms-decisions.sqlite"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return DecisionRepository(path)


if __name__ == "__main__":
    render()
