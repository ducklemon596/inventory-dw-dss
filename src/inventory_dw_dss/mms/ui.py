"""Run: uv run --extra ui streamlit run src/inventory_dw_dss/mms/ui.py"""
import json
import os
from pathlib import Path
import sqlite3
import hashlib
from datetime import date

import duckdb
import pandas as pd
import streamlit as st

from inventory_dw_dss.mms.core.schemas import POLICIES, PROFILES, ScenarioComparison, ScenarioConfig, MMSValidationError, to_dict
from inventory_dw_dss.mms.runtime import SourceSettings, build_runtime
from inventory_dw_dss.mms.tracking.repository import DecisionRepository
from inventory_dw_dss.mms.ui_theme import apply_theme
from inventory_dw_dss.mms.ui_presenters import (POLICY_LABELS, PROFILE_LABELS, config_matches, risk_caption, csv_export, scenario_label)
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
        for key in ("_mms_backtest","_mms_overview","_mms_last_saved","evaluation_dates"):
            st.session_state.pop(key,None)
        reset_manager_inputs()
        st.session_state["_mms_runtime_identity"]=token


def sidebar_controls(runtime):
    with st.sidebar:
        st.html('<div class="mms-brand">Inventory Studio</div>')
        st.caption("MODEL MANAGEMENT · DECISION SUPPORT")
        st.divider()
        analysis_date=st.date_input("Ngày phân tích",date(2025,6,30),key="analysis_date")
        count=st.selectbox("Số phương án",[2,3,4,1],key="scenario_count")
        st.caption("Mỗi phương án dùng chung một snapshot tại ngày đã chọn.")
        run=st.button("Chạy phương án",key="run_scenarios",type="primary",width="stretch")
        configs=[]
        for i in range(count):
            with st.expander(f"Phương án {chr(65+i)}",expanded=i==0):
                profile=st.selectbox("Ưu tiên xếp hạng",PROFILES,index=i,key=f"profile_{i}",format_func=PROFILE_LABELS.get)
                pstar=st.number_input("Ngưỡng điểm rủi ro",min_value=0.,max_value=1.,value=.3,step=.05,key=f"pstar_{i}")
                k=st.number_input("Số SKU xem xét · K",min_value=1,value=50,key=f"k_{i}")
                policy=st.selectbox("Chính sách đặt hàng",POLICIES,key=f"policy_{i}",format_func=POLICY_LABELS.get,
                    help="Mức phục vụ: đặt đủ để đáp ứng nhu cầu trong chu kỳ xem xét + thời gian chờ hàng "
                         "với xác suất đã chọn, dựa trên độ biến động bán 90 ngày.")
                service=policy=="service_level"
                tau=st.number_input("Chu kỳ xem xét (ngày) · tau" if service else "Số ngày bao phủ · tau",
                    min_value=.1,value=7. if service else 14.,key=f"tau_{i}_{policy}")
                level,lead,abc=.95,2.,False
                if service:
                    abc=st.checkbox("Mức phục vụ theo nhóm ABC",key=f"abc_{i}",
                        help="A 98% · B 95% · C 90%; nhóm theo giá trị bán 90 ngày.")
                    level=st.slider("Mức phục vụ",min_value=.80,max_value=.99,value=.95,step=.01,key=f"level_{i}",
                        disabled=abc,help="Áp dụng cho SKU chưa có nhóm ABC khi bật phân nhóm.")
                    lead=st.number_input("Thời gian chờ hàng (ngày)",min_value=0.,value=2.,step=1.,key=f"lead_{i}")
                unlimited=st.checkbox("Không giới hạn Q",key=f"unlimited_{i}")
                q=st.number_input("Giới hạn đơn vị · Q",min_value=0,
                    value=15 if runtime.settings.source=="demo" else 150,key=f"q_{i}",disabled=unlimited)
                configs.append(ScenarioConfig(analysis_date,profile=profile,pstar=pstar,top_k=k,
                    unit_budget_q=None if unlimited else q,coverage_tau_days=tau,
                    policy=policy,service_level=level,lead_time_days=lead,abc_service=abc))
        st.caption("Q là tổng đơn vị quy ước theo từng SKU, không phải ngân sách tiền tệ.")
        st.divider()
        with st.expander("Thông tin nguồn và mô hình"):
            settings=runtime.settings
            model=runtime.service.executor.risk_model
            st.caption("Nguồn mô phỏng" if runtime.is_demo else "Nguồn dữ liệu vận hành")
            st.text(f"Mô hình: {getattr(model,'version','Chưa cấu hình')}")
            st.text(f"Nguồn: {settings.source}")
            if settings.release_id:
                st.text(f"Release: {settings.release_id}")
            st.caption("Thứ tự xử lý: ngưỡng rủi ro → xếp hạng → K → chính sách đặt hàng → phân bổ Q.")
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
        st.warning(f"Chưa đọc được snapshot cho ngày này: {cached['error']}")
        return
    rows=cached['snapshot'].rows
    for col,label,value in zip(st.columns(3),
        ['SKU trong snapshot','SKU có tồn dương','SKU không phát sinh bán 90 ngày'],
        [len(rows),sum(r.available_stock>0 for r in rows),sum(r.sales_90d==0 for r in rows)]):
        col.metric(label,f"{value:,}")


def model_catalog(service):
    with st.expander("Bốn thành phần mô hình đang sử dụng"):
        names={"MB1":("MA90","Ước lượng tốc độ bán và dự báo nhu cầu."),
            "MB2":("HistGB","Chấm điểm và xếp hạng rủi ro hết hàng."),
            "MB3":("Bổ sung tồn kho","Tính số lượng theo số ngày bao phủ mục tiêu."),
            "MB4":("Phân bổ nguồn lực","Lập phương án theo K, Q và chính sách ưu tiên.")}
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
        st.html('<div class="mms-eyebrow">INVENTORY / DECISION WORKSPACE</div>')
        st.title("Lập kế hoạch tồn kho")
        st.caption("Ưu tiên SKU cần kiểm tra, so sánh phương án và ghi nhận quyết định của người quản lý.")
        if runtime.is_demo:
            detail=("điểm cố định để minh họa" if runtime.settings.source=="demo"
                    else "HistGB được huấn luyện trên dữ liệu tổng hợp")
            st.warning(f"DỮ LIỆU MÔ PHỎNG · SYNTHETIC DEMO — {detail}. Kết quả không đại diện cho dữ liệu nhà thuốc thật.")
        if run:
            with st.spinner("Đang đọc snapshot và so sánh phương án…"):
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
            overview(runtime,configs[0].analysis_date)
            st.write("")
            st.html('<div class="mms-empty"><h3>Sẵn sàng tạo kế hoạch đầu tiên</h3><p>Chọn ngày phân tích và điều kiện ở thanh bên, sau đó bấm <b>Chạy phương án</b> để xem danh sách ưu tiên và phân bổ.</p></div>')
            model_catalog(runtime.service)
            with st.expander("Các phiên đã lưu",expanded=False):
                sessions_view(runtime,repository)
            return
        pending=not config_matches(comparison,configs)
        if pending:
            st.warning("Tham số đã thay đổi. Kết quả bên dưới vẫn thuộc lần chạy trước; chạy lại phương án để lưu hoặc kiểm định.")
        a,b=st.columns([2,1])
        selected=a.selectbox("Phương án làm việc",range(len(comparison.results)),key='active_scenario',
            format_func=lambda i:scenario_label(i,comparison.results[i].config))
        result=comparison.results[selected]
        b.caption(f"Snapshot ngày {result.config.analysis_date:%d/%m/%Y} · {len(comparison.results)} phương án")
        result_metrics(result)
        st.write("")
        review,order,compare,manage,evaluate,sessions=st.tabs([
            "Danh sách xem xét","Đề xuất đặt hàng","So sánh","Quyết định","Kiểm định","Phiên đã lưu"])
        with review:
            top,search=st.columns([2,1])
            top.subheader("SKU cần người quản lý xem xét")
            query=search.text_input("Tìm SKU",key='sku_search',placeholder="Nhập mã SKU…",label_visibility='collapsed')
            st.caption(risk_caption(getattr(runtime.service.executor.risk_model,"manifest",{})))
            show_items(result.review_list,'review_table',query)
            st.download_button("Tải danh sách đầy đủ CSV",csv_export(result.review_list),
                file_name=f'mms-review-{result.config.analysis_date}-{result.config.profile}.csv',
                mime='text/csv',key='export_review')
            if result.review_list:
                chart=pd.DataFrame([{'SKU':r.sku_id,'Điểm rủi ro':r.risk_score} for r in result.review_list[:12]]).set_index('SKU')
                st.bar_chart(chart,color='#087f82',height=220)
        with order:
            st.subheader("Đề xuất đã được phân bổ")
            st.caption("Chỉ gồm SKU đủ điều kiện với đề xuất và phân bổ lớn hơn 0. Đây là phương án để duyệt, chưa phải đơn mua hàng.")
            if result.config.unit_budget_q is not None:
                budget=result.config.unit_budget_q
                spent=result.summary['units_allocated']
                st.progress(spent/budget if budget else 0,text=f"Đã dùng {spent:,} / {budget:,} đơn vị")
            show_items(result.order_proposal,'order_table',empty='Không có dòng được phân bổ. Kiểm tra Q, mức tồn và mục tiêu bao phủ.')
            st.download_button("Tải đề xuất CSV",csv_export(result.order_proposal),
                file_name=f'mms-orders-{result.config.analysis_date}-{result.config.profile}.csv',mime='text/csv',key='export_orders')
        with compare:
            comparison_view(comparison)
        with manage:
            manager_view(result,selected,repository,pending)
        with evaluate:
            evaluation_view(result,runtime,pending)
        with sessions:
            sessions_view(runtime,repository)
        with st.expander("Chi tiết tái lập và tải toàn bộ kết quả"):
            st.json({'config':to_dict(result.config),'metadata':result.metadata})
            st.download_button("Tải toàn bộ phương án JSON",json.dumps(to_dict(comparison),indent=2,ensure_ascii=False,allow_nan=False),
                file_name='mms-scenarios.json',mime='application/json',key='export_comparison')
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
