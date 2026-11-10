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
                            config_token, csv_export, item_rows, scenario_label)


def show_items(items, key, query="", empty="Không có SKU trong danh sách này."):
    rows=item_rows(items,query)
    if not rows:
        st.info(empty if not query else "Không có SKU khớp từ khóa tìm kiếm.")
    # Keep an explicit schema so an empty Order List remains a valid empty table.
    columns=["rank","sku_id","risk_score","available_stock","stock_unit","dos","suggested_q","allocated_q","flags"]
    frame=pd.DataFrame(rows,columns=columns)
    if not frame.empty:
        frame["flags"]=frame["flags"].map(lambda flags:
            ", ".join(FLAG_LABELS.get(f,f) for f in flags if f!="sop_excluded_diagnostics") or "—")
    st.dataframe(frame,hide_index=True,width="stretch",key=key,
        column_config={"rank":st.column_config.NumberColumn("Hạng",format="%d",width="small"),
            "sku_id":st.column_config.TextColumn("SKU",pinned=True),
            "risk_score":st.column_config.ProgressColumn("Điểm rủi ro",min_value=0,max_value=1,format="%.3f"),
            "available_stock":st.column_config.NumberColumn("Tồn kho",format="%.1f"),
            "stock_unit":"Đơn vị SKU","dos":st.column_config.NumberColumn("Bao phủ (ngày)",format="%.1f"),
            "suggested_q":st.column_config.NumberColumn("Đề xuất",format="%d"),
            "allocated_q":st.column_config.NumberColumn("Phân bổ",format="%d"),"flags":"Chẩn đoán"})


def result_metrics(result):
    summary=result.summary
    for col,label,value,help_text in zip(st.columns(4),
        ("SKU cần xem xét","SKU có phân bổ","Đơn vị đã phân bổ","Ngân sách còn lại"),
        (summary["selected_sku_count"],summary["order_sku_count"],summary["units_allocated"],
         "Không giới hạn" if summary["budget_remaining"] is None else summary["budget_remaining"]),
        ("Danh sách điều tra có thể gồm q = 0.","SKU đủ điều kiện và có phân bổ lớn hơn 0.",
         "Tổng đơn vị quy ước theo từng SKU, không phải tiền.","Phần còn lại của giới hạn Q.")):
        col.metric(label,f"{value:,}" if isinstance(value,int) else value,help=help_text)


def comparison_view(comparison):
    st.subheader("Tác động của từng phương án")
    st.caption("Mọi phương án trong lần chạy này dùng cùng snapshot và cùng điểm rủi ro.")
    rows=comparison_rows(comparison)
    st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch",key="comparison_table")
    st.bar_chart(pd.DataFrame(rows).set_index("Phương án")[["Đề xuất","Phân bổ"]],stack=False,
                 color=["#b8d9d9","#087f82"],height=260)
    overlap=[]
    for pair in comparison.overlap:
        a,b=pair["scenario_a"],pair["scenario_b"]
        overlap.append({"Cặp phương án":f"{chr(65+a)} ↔ {chr(65+b)}",
            "Trùng SKU xem xét":pair["review_jaccard"],"Trùng SKU đặt hàng":pair["order_jaccard"],
            "Chỉ ở phương án đầu":", ".join(pair["selected_only_a"]) or "—",
            "Chỉ ở phương án sau":", ".join(pair["selected_only_b"]) or "—"})
    if overlap:
        st.dataframe(overlap,hide_index=True,width="stretch",key="overlap_table",
            column_config={"Trùng SKU xem xét":st.column_config.NumberColumn(format="percent"),
                           "Trùng SKU đặt hàng":st.column_config.NumberColumn(format="percent")})
    else:
        st.info("Chọn từ hai phương án để xem mức giao nhau của danh sách.")


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
    st.subheader("Ghi nhận quyết định của người quản lý")
    st.caption("Duyệt, điều chỉnh hoặc ghi chú từng SKU. Lưu phiên không phát hành đơn mua hàng.")
    st.button("Chấp nhận các dòng có phân bổ",key="approve_allocated",disabled=pending or not result.order_proposal,
        on_click=approve_allocated,args=(result,selected))
    actions=[]
    with st.container(border=True):
        if not result.review_list:
            st.info("Phương án không có SKU cần xem xét. Bạn vẫn có thể lưu một phiên trống.")
        for item in result.review_list:
            draft=st.session_state.get("_mms_manager_drafts",{}).get(str(selected),{}).get(item.sku_id,{})
            defaults={f"action_{selected}_{item.sku_id}":draft.get("action","pending"),
                f"edit_{selected}_{item.sku_id}":draft.get("quantity",item.allocated_q),
                f"note_{selected}_{item.sku_id}":draft.get("note","")}
            for key,value in defaults.items():
                if key not in st.session_state:
                    st.session_state[key]=value
            with st.expander(f"#{item.rank} · {item.sku_id} · Đề xuất {item.suggested_q} / Phân bổ {item.allocated_q}"):
                a,b=st.columns([1.2,1])
                action=a.selectbox("Quyết định",list(ACTION_LABELS),format_func=ACTION_LABELS.get,
                                  key=f"action_{selected}_{item.sku_id}",on_change=remember_draft,args=(selected,item.sku_id))
                quantity=b.number_input("Số lượng điều chỉnh",min_value=0,
                    help="Chỉ được áp dụng khi chọn Điều chỉnh số lượng; đây là ghi nhận của quản lý.",
                    key=f"edit_{selected}_{item.sku_id}",on_change=remember_draft,args=(selected,item.sku_id))
                note=st.text_input("Ghi chú",key=f"note_{selected}_{item.sku_id}",
                    placeholder="Lý do điều chỉnh, kiểm đếm hoặc trao đổi với nhà cung cấp…",
                    on_change=remember_draft,args=(selected,item.sku_id))
                st.caption(f"Điểm {item.risk_score:.3f} · Tồn {item.available_stock:g} {item.stock_unit} · "
                           f"Tốc độ bán {item.vel90:.2f} đơn vị/ngày. Cần người quản lý xem xét trước khi đặt hàng.")
                if action!="pending" or note.strip():
                    actions.append(ManagerAction(item.sku_id,action,quantity if action=="edited" else None,note))
        save=st.button("Lưu quyết định",key="save_decision",type="primary",disabled=pending)
    if save:
        session=repository().save_decision(result,actions)
        st.session_state["_mms_last_saved"]={"config":config_token(result.config),"selected":selected,"id":session["session_id"]}
    last=st.session_state.get("_mms_last_saved")
    if last and last["config"]==config_token(result.config) and last["selected"]==selected:
        st.success(f"Đã lưu quyết định · {last['id']}")


def evaluation_view(result,runtime,pending):
    st.subheader("Kiểm định trên dữ liệu lịch sử")
    st.caption("Đặc trưng lấy tại T; kết quả quan sát lấy từ T+1. Cửa sổ thiếu dữ liệu hoặc bị kiểm kê được báo riêng.")
    a,b,c=st.columns([2,1,1])
    dates=a.text_input("Các ngày quyết định (phân cách bằng dấu phẩy)",str(result.config.analysis_date),key="evaluation_dates")
    horizon=b.selectbox("Cửa sổ quan sát",[7,14,30],format_func=lambda d:f"{d} ngày",key="evaluation_horizon")
    with c:
        st.write("")
        evaluate=st.button("Chạy kiểm định",key="evaluate",disabled=pending,width="stretch")
    if evaluate:
        with st.spinner("Đang kiểm định các cửa sổ lịch sử…"):
            report=Backtester(runtime.service,runtime.load_outcomes()).run(result.config,
                [d.strip() for d in dates.split(",")],horizon)
        st.session_state["_mms_backtest"]={"config":config_token(result.config),"report":report}
    saved=st.session_state.get("_mms_backtest")
    if not saved or saved["config"]!=config_token(result.config):
        st.info("Chạy kiểm định để xem độ chính xác dự báo và mức bao phủ rủi ro của phương án.")
        return
    report=saved["report"]
    st.caption(f"Kết quả đã chạy: cửa sổ {report.horizon_days} ngày · {len(report.per_date)} ngày quyết định.")
    aggregate=report.aggregate
    values=[aggregate["demand"]["wape"],aggregate["risk"]["precision_at_k"],aggregate["risk"]["recall_at_k"],aggregate["risk"]["roc_auc"]]
    for col,label,value in zip(st.columns(4),["WAPE ↓","Precision@K ↑","Recall@K ↑","ROC-AUC ↑"],values):
        col.metric(label,"—" if value is None else f"{value:.3f}")
    statuses={"evaluated":"Đã đánh giá","incomplete":"Thiếu cửa sổ quan sát",
              "excluded_sop":"Loại do kiểm kê","excluded_sop202508":"Loại do SOP202508"}
    rows=[]
    for day in report.per_date:
        rows.append({"Ngày":day["analysis_date"],"Trạng thái":statuses.get(day["status"],day["status"]),
            "WAPE":day.get("demand",{}).get("wape"),"Bias":day.get("demand",{}).get("bias"),
            "Precision@K":day.get("risk",{}).get("precision_at_k"),"Recall@K":day.get("risk",{}).get("recall_at_k"),
            "ROC-AUC":day.get("risk",{}).get("roc_auc"),"Hết hàng sẵn tại T":day.get("existing_stockout_count"),
            "Hết hàng mới":day.get("new_stockout_count")})
    st.dataframe(rows,hide_index=True,width="stretch",key="evaluation_table")
    st.caption("Ô trống là chỉ số chưa xác định. Kết quả quan sát không chứng minh tác động nhân quả của chính sách.")
    st.download_button("Tải báo cáo kiểm định",json.dumps(to_dict(report),indent=2,ensure_ascii=False,allow_nan=False),
        file_name="mms-backtest.json",mime="application/json",key="export_backtest")


def sessions_view(runtime,repository):
    st.subheader("Tra cứu các quyết định đã lưu")
    sessions=repository().list_sessions()
    if not sessions:
        st.info("Chưa có phiên được lưu. Sau khi chạy phương án, mở tab Quyết định để ghi chú và lưu.")
        return
    by_id={s["session_id"]:s for s in sessions}
    def label(session_id):
        s=by_id[session_id]
        timestamp=datetime.fromisoformat(s["created_at"]).astimezone(ZoneInfo("Asia/Bangkok"))
        return f"{s['analysis_date']} · {timestamp:%d/%m %H:%M} · {session_id[:8]}"
    session_id=st.selectbox("Phiên quyết định",list(by_id),format_func=label,key="saved_session")
    a,b=st.columns([1,2])
    if a.button("Mở lại phiên",key="reopen_session",width="stretch"):
        st.session_state["reopened_session"]=repository().get_session(session_id)
    if b.button("Cập nhật quan sát sau quyết định",key="followup",width="stretch"):
        saved=repository().get_session(session_id)
        current=runtime.service.provider.get_snapshot(saved["analysis_date"])
        if current.data_version!=saved["result"]["metadata"]["data_version"]:
            raise MMSValidationError("Nguồn quan sát hiện tại không khớp phiên đã lưu; chọn đúng phiên bản dữ liệu.")
        st.session_state["reopened_session"]=repository().add_followups(session_id,runtime.load_outcomes())
    saved=st.session_state.get("reopened_session")
    if saved:
        st.subheader("Quyết định đã lưu")
        st.caption(f"Phiên {saved['session_id']} · Ngày phân tích {saved['analysis_date']} · "
                   f"{PROFILE_LABELS[saved['result']['config']['profile']]}")
        st.dataframe(saved["result"]["review_list"],hide_index=True,width="stretch",key="saved_items")
        if saved["actions"]:
            st.dataframe([{ "SKU":a["sku_id"],"Quyết định":ACTION_LABELS.get(a["action"],a["action"]),
                "Điều chỉnh":a["quantity"],"Ghi chú":a["note"]} for a in saved["actions"]],
                hide_index=True,width="stretch",key="saved_actions")
        if saved["followups"]:
            st.dataframe(saved["followups"],hide_index=True,width="stretch",key="saved_followups")
        with st.expander("Cấu hình và phiên bản của phiên đã lưu"):
            st.json({"config":saved["result"]["config"],"metadata":saved["result"]["metadata"]})
        st.download_button("Tải phiên quyết định",json.dumps(saved,ensure_ascii=False,indent=2,allow_nan=False),
            file_name=f"mms-decision-{saved['session_id'][:8]}.json",mime="application/json",key="export_saved")
