"""Dashboard views. All inference, evaluation and persistence delegate to services."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from .core.schemas import MMSValidationError, to_dict
from .evaluation.backtesting import Backtester
from .tracking.repository import ManagerAction
from .ui_presenters import (ACTION_LABELS, FLAG_LABELS, PROFILE_LABELS, comparison_rows,
                            config_token, csv_export, item_rows, scenario_label, item_advice)


def show_items(items, key, query="", empty="No items.", simple=False):
    rows=item_rows(items,query)
    if not rows:
        st.info(empty if not query else "No matching items.")
    # Keep an explicit schema so an empty Order List remains a valid empty table.
    columns=["rank","sku_id","risk_score","available_stock","stock_unit","dos","suggested_q","allocated_q","flags"]
    frame=pd.DataFrame(rows,columns=columns)
    if not frame.empty:
        frame["flags"]=frame["flags"].map(lambda flags:
            ", ".join(FLAG_LABELS.get(f,f) for f in flags if f!="sop_excluded_diagnostics") or "—")
    if simple:
        advice={item.sku_id:("Check required" if not item.eligible else
            "No order needed" if item.suggested_q==0 else
            "Limit reached" if item.allocated_q==0 else
            "Partial" if item.allocated_q<item.suggested_q else "Full quantity") for item in items}
        frame["advice"]=frame["sku_id"].map(advice)
        st.dataframe(frame,hide_index=True,width="stretch",key=key,
            column_order=["sku_id","available_stock","stock_unit","dos","allocated_q","advice"],
            column_config={"sku_id":st.column_config.TextColumn("Item",pinned=True),
                "available_stock":st.column_config.NumberColumn("In stock",format="%g"),
                "stock_unit":"Unit", "dos":st.column_config.NumberColumn("Days left",format="%.1f"),
                "allocated_q":st.column_config.NumberColumn("Planned qty",format="%d"),
                "advice":st.column_config.TextColumn("Status",help="Partial / limit reached: quantity is constrained. Open an item in Approve for details.")})
        return
    st.dataframe(frame,hide_index=True,width="stretch",key=key,
        column_config={"rank":st.column_config.NumberColumn("Rank",format="%d",width="small"),
            "sku_id":st.column_config.TextColumn("SKU",pinned=True),
            "risk_score":st.column_config.ProgressColumn("Risk score",min_value=0,max_value=1,format="%.3f"),
            "available_stock":st.column_config.NumberColumn("Stock",format="%.1f"),
            "stock_unit":"Unit","dos":st.column_config.NumberColumn("Days cover",format="%.1f"),
            "suggested_q":st.column_config.NumberColumn("Suggested",format="%d"),
            "allocated_q":st.column_config.NumberColumn("Allocated",format="%d"),"flags":"Diagnostics"})


def result_metrics(result):
    summary=result.summary
    for col,label,value,help_text in zip(st.columns(3),
        ("Review","To order","Total units"),
        (summary["selected_sku_count"],summary["order_sku_count"],summary["units_allocated"]),
        ("Items prioritized for review.","Items with a positive planned quantity.",
         "Total SKU-specific units, not money or an order placed.")):
        col.metric(label,f"{value:,}" if isinstance(value,int) else value,help=help_text)


def comparison_view(comparison):
    st.subheader("Scenario comparison")
    st.caption("All scenarios share one snapshot and risk scores.")
    rows=comparison_rows(comparison)
    st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch",key="comparison_table")
    st.bar_chart(pd.DataFrame(rows).set_index("Scenario")[["Suggested","Allocated"]],stack=False,
                 color=["#b8d9d9","#087f82"],height=260)
    overlap=[]
    for pair in comparison.overlap:
        a,b=pair["scenario_a"],pair["scenario_b"]
        overlap.append({"Scenario pair":f"{chr(65+a)} ↔ {chr(65+b)}",
            "Review overlap":pair["review_jaccard"],"Order overlap":pair["order_jaccard"],
            "Only in first":", ".join(pair["selected_only_a"]) or "—",
            "Only in second":", ".join(pair["selected_only_b"]) or "—"})
    if overlap:
        st.dataframe(overlap,hide_index=True,width="stretch",key="overlap_table",
            column_config={"Review overlap":st.column_config.NumberColumn(format="percent"),
                           "Order overlap":st.column_config.NumberColumn(format="percent")})
    else:
        st.info("Select at least two scenarios to compare overlap.")


def approve_allocated(result, selected):
    drafts=st.session_state.setdefault("_mms_manager_drafts",{})
    for item in result.order_proposal:
        st.session_state[f"action_{selected}_{item.sku_id}"]="accepted"
        st.session_state[f"edit_{selected}_{item.sku_id}"]=item.allocated_q
        draft=drafts.setdefault(str(selected),{}).setdefault(item.sku_id,{})
        draft.update(action="accepted",quantity=item.allocated_q)


def remember_draft(selected,sku):
    drafts=st.session_state.setdefault("_mms_manager_drafts",{})
    drafts.setdefault(str(selected),{})[sku]={
        "action":st.session_state.get(f"action_{selected}_{sku}","pending"),
        "quantity":st.session_state.get(f"edit_{selected}_{sku}",0),
        "note":st.session_state.get(f"note_{selected}_{sku}","")}


def manager_view(result,selected,repository,pending):
    st.subheader("Approve")
    st.caption("Saving does not place an order.")
    st.button("Accept all",key="approve_allocated",disabled=pending or not result.order_proposal,
        on_click=approve_allocated,args=(result,selected))
    actions=[]
    with st.container(border=True):
        if not result.review_list:
            st.info("No items. You can save an empty decision.")
        for item in result.review_list:
            draft=st.session_state.get("_mms_manager_drafts",{}).get(str(selected),{}).get(item.sku_id,{})
            defaults={f"action_{selected}_{item.sku_id}":draft.get("action","pending"),
                f"edit_{selected}_{item.sku_id}":draft.get("quantity",item.allocated_q),
                f"note_{selected}_{item.sku_id}":draft.get("note","")}
            for key,value in defaults.items():
                if key not in st.session_state:
                    st.session_state[key]=value
            with st.expander(f"{item.sku_id} · Qty {item.allocated_q}"):
                st.write(item_advice(item))
                a,b=st.columns([1.2,1])
                action=a.selectbox("Decision",list(ACTION_LABELS),format_func=ACTION_LABELS.get,
                                  key=f"action_{selected}_{item.sku_id}",on_change=remember_draft,args=(selected,item.sku_id))
                quantity=b.number_input("Revised quantity",min_value=0,
                    help="Applies only when Adjust quantity is selected.",
                    key=f"edit_{selected}_{item.sku_id}",on_change=remember_draft,args=(selected,item.sku_id))
                note=st.text_input("Note",key=f"note_{selected}_{item.sku_id}",
                    placeholder="Add a note…",
                    on_change=remember_draft,args=(selected,item.sku_id))
                st.caption(f"In stock {item.available_stock:g} {item.stock_unit} · Average sales {item.vel90:.2f} units/day.")
                if action!="pending" or note.strip():
                    actions.append(ManagerAction(item.sku_id,action,quantity if action=="edited" else None,note))
        save=st.button("Save decision",key="save_decision",type="primary",disabled=pending)
    if save:
        session=repository().save_decision(result,actions)
        st.session_state["_mms_last_saved"]={"config":config_token(result.config),"selected":selected,"id":session["session_id"]}
    last=st.session_state.get("_mms_last_saved")
    if last and last["config"]==config_token(result.config) and last["selected"]==selected:
        st.success(f"Decision saved · {last['id']}")


def evaluation_view(result,runtime,pending):
    st.subheader("Historical backtest")
    st.caption("Features at T; outcomes from T+1. Incomplete and stocktaking windows are reported separately.")
    a,b,c=st.columns([2,1,1])
    dates=a.text_input("Decision dates (comma-separated)",str(result.config.analysis_date),key="evaluation_dates")
    horizon=b.selectbox("Horizon",[7,14,30],format_func=lambda d:f"{d} days",key="evaluation_horizon")
    with c:
        st.write("")
        evaluate=st.button("Run backtest",key="evaluate",disabled=pending,width="stretch")
    if evaluate:
        with st.spinner("Running backtest…"):
            report=Backtester(runtime.service,runtime.load_outcomes()).run(result.config,
                [d.strip() for d in dates.split(",")],horizon)
        st.session_state["_mms_backtest"]={"config":config_token(result.config),"report":report}
    saved=st.session_state.get("_mms_backtest")
    if not saved or saved["config"]!=config_token(result.config):
        st.info("Run a backtest to evaluate this plan.")
        return
    report=saved["report"]
    st.caption(f"Results: {report.horizon_days}-day horizon · {len(report.per_date)} decision dates.")
    aggregate=report.aggregate
    values=[aggregate["demand"]["wape"],aggregate["risk"]["precision_at_k"],aggregate["risk"]["recall_at_k"],aggregate["risk"]["roc_auc"]]
    for col,label,value in zip(st.columns(4),["WAPE ↓","Precision@K ↑","Recall@K ↑","ROC-AUC ↑"],values):
        col.metric(label,"—" if value is None else f"{value:.3f}")
    statuses={"evaluated":"Evaluated","incomplete":"Incomplete observations",
              "excluded_sop":"Excluded: stocktaking","excluded_sop202508":"Excluded: SOP202508"}
    rows=[]
    for day in report.per_date:
        rows.append({"Date":day["analysis_date"],"Status":statuses.get(day["status"],day["status"]),
            "WAPE":day.get("demand",{}).get("wape"),"Bias":day.get("demand",{}).get("bias"),
            "Precision@K":day.get("risk",{}).get("precision_at_k"),"Recall@K":day.get("risk",{}).get("recall_at_k"),
            "ROC-AUC":day.get("risk",{}).get("roc_auc"),"Existing stockouts":day.get("existing_stockout_count"),
            "New stockouts":day.get("new_stockout_count")})
    st.dataframe(rows,hide_index=True,width="stretch",key="evaluation_table")
    st.caption("Blank metrics are undefined. Observational results do not prove policy impact.")
    st.download_button("Download backtest",json.dumps(to_dict(report),indent=2,ensure_ascii=False,allow_nan=False),
        file_name="mms-backtest.json",mime="application/json",key="export_backtest")


def sessions_view(runtime,repository):
    st.subheader("Saved decisions")
    sessions=repository().list_sessions()
    if not sessions:
        st.info("No saved decisions.")
        return
    by_id={s["session_id"]:s for s in sessions}
    def label(session_id):
        s=by_id[session_id]
        timestamp=datetime.fromisoformat(s["created_at"]).astimezone(ZoneInfo("Asia/Bangkok"))
        return f"{s['analysis_date']} · {timestamp:%d/%m %H:%M} · {session_id[:8]}"
    session_id=st.selectbox("Saved session",list(by_id),format_func=label,key="saved_session")
    a,b=st.columns([1,2])
    if a.button("Open",key="reopen_session",width="stretch"):
        st.session_state["reopened_session"]=repository().get_session(session_id)
    if b.button("Update follow-up",key="followup",width="stretch"):
        saved=repository().get_session(session_id)
        current=runtime.service.provider.get_snapshot(saved["analysis_date"])
        if current.data_version!=saved["result"]["metadata"]["data_version"]:
            raise MMSValidationError("Data version differs from the saved decision. Select the matching version.")
        st.session_state["reopened_session"]=repository().add_followups(session_id,runtime.load_outcomes())
    saved=st.session_state.get("reopened_session")
    if saved:
        st.subheader("Saved decision")
        st.caption(f"Session {saved['session_id']} · Analysis date {saved['analysis_date']} · "
                   f"{PROFILE_LABELS[saved['result']['config']['profile']]}")
        st.dataframe(saved["result"]["review_list"],hide_index=True,width="stretch",key="saved_items")
        if saved["actions"]:
            st.dataframe([{ "SKU":a["sku_id"],"Decision":ACTION_LABELS.get(a["action"],a["action"]),
                "Adjustment":a["quantity"],"Note":a["note"]} for a in saved["actions"]],
                hide_index=True,width="stretch",key="saved_actions")
        if saved["followups"]:
            st.dataframe(saved["followups"],hide_index=True,width="stretch",key="saved_followups")
        with st.expander("Saved configuration & versions"):
            st.json({"config":saved["result"]["config"],"metadata":saved["result"]["metadata"]})
        st.download_button("Download decision",json.dumps(saved,ensure_ascii=False,indent=2,allow_nan=False),
            file_name=f"mms-decision-{saved['session_id'][:8]}.json",mime="application/json",key="export_saved")
