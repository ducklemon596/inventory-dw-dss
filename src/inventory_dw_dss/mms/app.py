"""Replenishment planning app.

    uv run --locked --extra ui streamlit run src/inventory_dw_dss/mms/app.py

Needs the marts in ClickHouse and a trained risk model (see the MMS README for variables).
"""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from inventory_dw_dss.mms.decisions import Decision, DecisionStore
from inventory_dw_dss.mms.schemas import MMSError, ScenarioConfig, as_date

PROFILES = {"RiskFirst": "Rủi ro cao nhất", "RevenueAtRisk": "Doanh thu có rủi ro", "DaysOfSupply": "Ít ngày đủ bán nhất"}
STATUS = {"pending": "Chờ", "approved": "Duyệt", "rejected": "Bỏ qua"}
STATUS_KEY = {v: k for k, v in STATUS.items()}
# Colours carry meaning and always come with a text label: red = act now, orange = watch, blue = info.
# Stocktake flags matter for evaluation, not for the order decision, so they are not shown.
FLAGS = {"dispensary_empty": "Quầy đã hết", "demand_spike": "Bán tăng đột biến",
         "transfer_from_storeroom": "Chuyển từ kho được"}
FLAG_COLORS = ["red", "orange", "blue"]
RISK_LEVELS = ["Cao", "Trung bình", "Thấp"]
RISK_COLORS = ["red", "orange", "gray"]


def risk_level(score):
    return "Cao" if score >= .6 else "Trung bình" if score >= .3 else "Thấp"
TARGETS = {"pharmacy_shortfall": "khả năng nhà thuốc hết hàng nếu không nhập thêm",
           "dispensary_stockout": "khả năng quầy bán bị trống"}
EDITABLE = ("Quyết định", "SL duyệt", "Ghi chú")

HELP = """
- **Mức / Rủi ro**: điểm 0–1 của mô hình về {target} trong kỳ dự báo. Cao ≥ 0,6, trung bình ≥ 0,3. Điểm dùng để xếp hạng, không phải xác suất chính xác.
- **Tồn**: tồn toàn nhà thuốc (quầy + kho) cuối ngày phân tích. **Tồn quầy** là phần đang ở quầy bán.
- **Bán/ngày**: lượng bán trung bình mỗi ngày trong 90 ngày gần nhất (MA90).
- **Đủ bán**: số ngày tồn hiện có đủ bán với tốc độ đó.
- **Mức mục tiêu S**: lượng cần có để đủ bán trong chu kỳ xem xét + thời gian chờ hàng ở mức phục vụ đã chọn.
  **Tồn an toàn** là phần S vượt nhu cầu trung bình, lớn hơn với hàng bán thất thường.
- **Đề xuất** = S − tồn (theo mức phục vụ) hoặc số ngày bao phủ × bán/ngày − tồn.
- **Phân bổ**: phần đề xuất được cấp trong giới hạn tổng đơn vị, lần lượt theo hạng.
- **Cách tính số lượng**: *mức phục vụ* đặt đủ để không thiếu hàng với xác suất đã chọn;
  *số ngày bao phủ* đặt đủ bán trung bình trong N ngày. **Giá trị ước tính** = phân bổ × giá bán trung bình 90 ngày.
"""


def number(value, digits=0):
    """Vietnamese thousands separator: 12.408.186 / 1,5."""
    text = f"{value:,.{digits}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


# ---------------------------------------------------------------- inputs

def scenario_inputs(prefix, analysis_date):
    """Widgets for one plan. Common choices first; the rest under 'Tuỳ chọn nâng cao'."""
    policy = st.radio("Cách tính số lượng", ["Theo mức phục vụ", "Theo số ngày bao phủ"], key=f"{prefix}_policy")
    service = policy == "Theo mức phục vụ"
    level, days, lead, abc = .95, 7, 2, False
    if service:
        level = st.select_slider("Mức phục vụ", [.80, .85, .90, .95, .98, .99], .95, key=f"{prefix}_level",
                                 format_func=lambda v: f"{v:.0%}")
    else:
        days = st.number_input("Số ngày bao phủ", 1, 90, 14, key=f"{prefix}_days")
    budget = st.number_input("Giới hạn tổng đơn vị", 0, value=0, step=100, key=f"{prefix}_budget",
                             help="0 là không giới hạn. Đơn vị của các sản phẩm được cộng như số đếm.")
    with st.expander("Tuỳ chọn nâng cao"):
        if service:
            days = st.number_input("Chu kỳ xem xét (ngày)", 1, 60, 7, key=f"{prefix}_review")
            lead = st.number_input("Thời gian chờ hàng (ngày)", 0, 30, 2, key=f"{prefix}_lead")
            abc = st.checkbox("Mức phục vụ theo nhóm ABC", key=f"{prefix}_abc",
                              help="A 98%, B 95%, C 90%, theo giá trị bán 90 ngày. Thay cho mức chọn ở trên.")
        profile = st.selectbox("Xếp hạng theo", list(PROFILES), format_func=PROFILES.get, key=f"{prefix}_profile")
        pstar = st.slider("Ngưỡng rủi ro tối thiểu", 0., 1., .3, .05, key=f"{prefix}_pstar")
        top_k = st.number_input("Số dòng tối đa", 1, 500, 50, key=f"{prefix}_k")
    return ScenarioConfig(analysis_date, profile=profile, pstar=pstar, top_k=int(top_k),
                          unit_budget=int(budget) or None, policy="service_level" if service else "coverage",
                          coverage_days=float(days), service_level=level, lead_time_days=float(lead), abc_service=abc)


def plan_label(plan):
    c = plan.config
    if c.policy == "coverage":
        return f"Bao phủ {c.coverage_days:g} ngày"
    return "Mức phục vụ theo ABC" if c.abc_service else f"Mức phục vụ {c.service_level:.0%}"


def date_bounds(service):
    """First date the model may score and the last date in the mart."""
    if "date_bounds" not in st.session_state:
        _, end = service.reader.data_version()
        start = as_date(service.risk_model.manifest["supervised_data_cutoff"])
        st.session_state["date_bounds"] = (start, end)
    return st.session_state["date_bounds"]


# ---------------------------------------------------------------- decisions held while editing

def decision_state(plan_key, plan):
    """Per-plan decisions {sku: {status, qty, note}}, kept across reruns until the plan changes."""
    store = st.session_state.setdefault("decisions", {})
    if plan_key not in store:
        store[plan_key] = {i.sku_id: {"status": "pending", "qty": i.allocated_qty, "note": ""} for i in plan.items}
    return store[plan_key]


# Button callbacks run before the page is drawn, so the counters above the table are current.
def _refresh_editor():
    st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1


def approve_allocated(plan_key, plan):
    decisions = decision_state(plan_key, plan)
    for i in plan.items:
        if i.allocated_qty > 0:
            decisions[i.sku_id].update(status="approved", qty=i.allocated_qty)
    _refresh_editor()


def reset_decisions(plan_key):
    st.session_state["decisions"].pop(plan_key, None)
    _refresh_editor()


def plan_frame(plan, decisions):
    return pd.DataFrame([{
        "Hạng": i.rank, "Sản phẩm": i.product_name or i.sku_id, "Mã": i.sku_id, "Rủi ro": i.risk_score,
        "Mức": [risk_level(i.risk_score)],
        "Tồn": i.available_stock, "Tồn quầy": i.dispensary_stock, "Đơn vị": i.stock_unit,
        "Bán/ngày": i.daily_demand, "Đủ bán": i.days_of_supply,
        "Mức mục tiêu S": i.target_level, "Tồn an toàn": i.safety_stock,
        "Đề xuất": i.suggested_qty, "Phân bổ": i.allocated_qty,
        "Quyết định": STATUS[decisions[i.sku_id]["status"]], "SL duyệt": decisions[i.sku_id]["qty"],
        "Ghi chú": decisions[i.sku_id]["note"], "Lưu ý": [FLAGS[f] for f in FLAGS if f in i.flags],
    } for i in plan.items])


COLUMNS = {
    "Rủi ro": st.column_config.NumberColumn(format="%.2f", width="small"),
    "Mức": st.column_config.MultiselectColumn(options=RISK_LEVELS, color=RISK_COLORS, width="small"),
    "Lưu ý": st.column_config.MultiselectColumn(options=list(FLAGS.values()), color=FLAG_COLORS, width="medium"),
    "Tồn": st.column_config.NumberColumn(format="%.0f", width="small"),
    "Tồn quầy": st.column_config.NumberColumn(format="%.0f", width="small"),
    "Bán/ngày": st.column_config.NumberColumn(format="%.2f", width="small"),
    "Đủ bán": st.column_config.NumberColumn(format="%.0f ngày", width="small"),
    "Mức mục tiêu S": st.column_config.NumberColumn(format="%.0f", width="small"),
    "Tồn an toàn": st.column_config.NumberColumn(format="%.0f", width="small"),
    "Đề xuất": st.column_config.NumberColumn(format="%d", width="small"),
    "Phân bổ": st.column_config.NumberColumn(format="%d", width="small"),
    "Quyết định": st.column_config.SelectboxColumn(options=list(STATUS.values()), required=True, width=100),
    "SL duyệt": st.column_config.NumberColumn(min_value=0, step=1, format="%d", width=90),
    "Ghi chú": st.column_config.TextColumn(width="medium"),
    "Sản phẩm": st.column_config.TextColumn(width="large"),
    "Hạng": st.column_config.NumberColumn(width="small"),
}


# ---------------------------------------------------------------- tabs

def compact_value(value):
    """13.678.030 -> '13,7 tr'; the full figure is in the metric tooltip."""
    for size, unit in ((1e9, "tỉ"), (1e6, "tr"), (1e3, "k")):
        if abs(value) >= size:
            return f"{number(value / size, 1)} {unit}"
    return number(value)


def summary(plan):
    s, budget = plan.summary, plan.config.unit_budget
    a, b, c, d = st.columns(4)
    a.metric("Sản phẩm cần xem xét", s["review_items"])
    b.metric("Dòng có đặt hàng", s["order_lines"])
    c.metric("Tổng đơn vị phân bổ", number(s["units_allocated"]))
    d.metric("Giá trị ước tính", compact_value(s["allocated_value"]))
    if budget:
        used = s["units_allocated"] / budget
        cut = sum(i.allocated_qty < i.suggested_qty for i in plan.items)
        st.progress(min(used, 1.), text=f"Giới hạn đơn vị: đã dùng {number(s['units_allocated'])} / {number(budget)} "
                                        f"({used:.0%}) · {cut} dòng bị cắt bớt")
    else:
        st.caption(f"Không giới hạn đơn vị: phân bổ đủ {number(s['units_suggested'])} đơn vị đề xuất.")


# Quick filters double as the "needs attention" counts.
FILTERS = {
    "all": ("Tất cả", lambda i: True),
    "orders": ("Có đặt hàng", lambda i: i.allocated_qty > 0),
    "high": ("Rủi ro cao", lambda i: i.risk_score >= .6),
    "empty": ("Quầy đã hết", lambda i: "dispensary_empty" in i.flags),
    "spike": ("Bán tăng đột biến", lambda i: "demand_spike" in i.flags),
}


def proposal_tab(plans, store):
    index = 0
    if len(plans) > 1:
        index = st.segmented_control("Phương án", range(len(plans)), default=0, key="active_plan",
                                     format_func=lambda i: f"{'AB'[i]} · {plan_label(plans[i])}") or 0
    plan = plans[index]
    plan_key = f"{st.session_state['run_id']}_{index}"
    decisions = decision_state(plan_key, plan)
    summary(plan)
    if not plan.items:
        st.info("Không có sản phẩm nào vượt ngưỡng rủi ro. Hạ ngưỡng trong Tuỳ chọn nâng cao hoặc chọn ngày khác.")
        return

    counts = {k: sum(map(test, plan.items)) for k, (_, test) in FILTERS.items()}
    shown = st.segmented_control("Lọc", [k for k in FILTERS if counts[k] or k == "all"], default="all",
                                 key="row_filter", label_visibility="collapsed",
                                 format_func=lambda k: f"{FILTERS[k][0]} {counts[k]}") or "all"
    search, details = st.columns([3, 1], vertical_alignment="bottom")
    query = search.text_input("Tìm sản phẩm", placeholder="Tên hoặc mã sản phẩm", key="query",
                              label_visibility="collapsed").strip().casefold()
    show_details = details.toggle("Cột chi tiết", key="show_details")

    approved = sum(d["status"] == "approved" for d in decisions.values())
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("Duyệt các dòng có phân bổ", disabled=st.session_state["stale"], on_click=approve_allocated,
                  args=(plan_key, plan))
        st.button("Đặt lại quyết định", on_click=reset_decisions, args=(plan_key,))
        st.space("stretch")
        st.markdown(f"Đã duyệt {approved} / {len(plan.items)}", width="content")

    table = plan_frame(plan, decisions)
    if query:
        table = table[table["Sản phẩm"].str.casefold().str.contains(query, regex=False)
                      | table["Mã"].str.casefold().str.contains(query, regex=False)]
    if shown != "all":
        keep = {i.sku_id for i in plan.items if FILTERS[shown][1](i)}
        table = table[table["Mã"].isin(keep)]
    detail = ["Rủi ro", "Tồn quầy", "Đơn vị", "Mức mục tiêu S", "Tồn an toàn", "Lưu ý"] if show_details else ["Lưu ý"]
    if plan.config.policy == "coverage":
        detail = [c for c in detail if c not in ("Mức mục tiêu S", "Tồn an toàn")]
    order = ["Hạng", "Sản phẩm", "Mức", "Tồn", "Bán/ngày", "Đủ bán", *detail[:-1], "Đề xuất", "Phân bổ",
             *EDITABLE, detail[-1], "Mã"]
    # A new key whenever the visible rows change, so edits never land on a shifted row.
    key = f"editor_{plan_key}_{st.session_state.get('editor_version', 0)}_{query}_{shown}"
    edited = st.data_editor(table, key=key, hide_index=True, width="stretch", height=min(38 + 35 * len(table), 640),
                            column_order=order, column_config=COLUMNS,
                            disabled=[c for c in table.columns if c not in EDITABLE])
    for row in edited.to_dict("records"):
        decisions[row["Mã"]] = {"status": STATUS_KEY[row["Quyết định"]], "note": row["Ghi chú"] or "",
                                "qty": int(row["SL duyệt"]) if pd.notna(row["SL duyệt"]) else 0}

    save, download, _ = st.columns([2, 2, 5])
    if save.button("Lưu quyết định", type="primary", disabled=st.session_state["stale"]):
        saved = [Decision(sku, d["status"], d["qty"] if d["status"] == "approved" else None, d["note"])
                 for sku, d in decisions.items()]
        store.save(plan, saved)
        st.success(f"Đã lưu: {sum(d.status == 'approved' for d in saved)} dòng duyệt, "
                   f"{sum(d.status == 'rejected' for d in saved)} dòng bỏ qua. Xem lại ở tab Lịch sử.")
    export = plan_frame(plan, decisions)
    export[["Mức", "Lưu ý"]] = export[["Mức", "Lưu ý"]].map(", ".join)
    download.download_button("Tải CSV", export.to_csv(index=False).encode("utf-8-sig"),
                             file_name=f"de-xuat-{plan.config.analysis_date}.csv", mime="text/csv")
    with st.expander("Ý nghĩa các cột"):
        st.markdown(HELP.replace("{target}", TARGETS.get(plan.metadata.get("risk_target"), TARGETS["pharmacy_shortfall"])))


def compare_tab(plans):
    if len(plans) < 2:
        st.info("Bật “So sánh với phương án B” ở thanh bên để so sánh hai cách đặt hàng trên cùng dữ liệu.")
        return
    st.dataframe(pd.DataFrame([{
        "Phương án": f"{'AB'[i]} · {plan_label(p)}", "Xếp hạng": PROFILES[p.config.profile],
        "Sản phẩm xem xét": p.summary["review_items"], "Dòng đặt hàng": p.summary["order_lines"],
        "Đơn vị đề xuất": p.summary["units_suggested"], "Đơn vị phân bổ": p.summary["units_allocated"],
        "Giá trị ước tính": number(p.summary["allocated_value"]),
    } for i, p in enumerate(plans)]), hide_index=True, width="stretch")
    a, b = ({i.sku_id: i for i in p.items} for p in plans)
    shared = sorted(a.keys() & b.keys())
    st.caption(f"{len(shared)} sản phẩm có trong cả hai danh sách · {len(a.keys() - b.keys())} chỉ có ở A · "
               f"{len(b.keys() - a.keys())} chỉ có ở B")
    diff = pd.DataFrame([{"Sản phẩm": a[s].product_name or s, "Mã": s, "Phân bổ A": a[s].allocated_qty,
                          "Phân bổ B": b[s].allocated_qty, "B − A": b[s].allocated_qty - a[s].allocated_qty}
                         for s in shared])
    if not diff.empty:
        st.markdown("**Chênh lệch phân bổ trên các sản phẩm chung**")
        st.dataframe(diff.sort_values("B − A", key=abs, ascending=False), hide_index=True, width="stretch")


def history_tab(store):
    sessions = store.sessions()
    if not sessions:
        st.info("Chưa có quyết định nào được lưu. Lưu ở tab Đề xuất để xem lại tại đây.")
        return
    labels = {s["session_id"]: f"Ngày {s['analysis_date']} · lưu lúc {s['created_at'][:16].replace('T', ' ')} UTC · "
                               f"{s['approved']} dòng duyệt" for s in sessions}
    session_id = st.selectbox("Phiên đã lưu", list(labels), format_func=labels.get)
    plan, decisions = store.load(session_id)
    rows = []
    for item in plan["items"]:
        d = decisions.get(item["sku_id"])
        rows.append({"Hạng": item["rank"], "Sản phẩm": item["product_name"] or item["sku_id"], "Mã": item["sku_id"],
                     "Đề xuất": item["suggested_qty"], "Phân bổ": item["allocated_qty"],
                     "Quyết định": STATUS[d.status] if d else STATUS["pending"],
                     "SL duyệt": d.quantity if d else None, "Ghi chú": d.note if d else ""})
    table = pd.DataFrame(rows)
    table["SL duyệt"] = table["SL duyệt"].astype("Int64")  # blank, not "None", for undecided lines
    st.dataframe(table, hide_index=True, width="stretch")


# ---------------------------------------------------------------- page

def render(service, store):
    model = service.risk_model
    first, last = date_bounds(service)
    with st.sidebar:
        st.header("Thiết lập")
        analysis_date = st.date_input("Ngày phân tích", last, min_value=first, max_value=last, key="analysis_date",
                                      format="DD/MM/YYYY",
                                      help=f"Từ {first:%d/%m/%Y} (sau dữ liệu huấn luyện) đến {last:%d/%m/%Y}.")
        configs = [scenario_inputs("a", analysis_date)]
        st.divider()
        if st.toggle("So sánh với phương án B", key="compare"):
            st.subheader("Phương án B")
            configs.append(scenario_inputs("b", analysis_date))
        run = st.button("Lập kế hoạch", type="primary", width="stretch")

    st.subheader("Kế hoạch đặt hàng")
    st.caption(f"Ngày {analysis_date:%d/%m/%Y} · rủi ro {model.horizon_days or '?'} ngày tới · mô hình {model.version}")

    # The first visit plans with the defaults, so the page opens with results.
    if run or "plans" not in st.session_state:
        try:
            with st.spinner("Đang đọc dữ liệu và chấm điểm…"):
                st.session_state["plans"] = service.compare(configs)
            st.session_state["run_id"] = st.session_state.get("run_id", 0) + 1
        except MMSError as exc:
            st.session_state["plans"] = None
            st.error(str(exc))
    plans = st.session_state.get("plans")
    st.session_state["stale"] = bool(plans) and [p.config for p in plans] != configs
    if st.session_state["stale"]:
        st.warning("Thiết lập đã thay đổi. Bấm “Lập kế hoạch” để cập nhật; kết quả dưới đây là của lần chạy trước.")

    proposal, compare, history = st.tabs(["Đề xuất", "So sánh", "Lịch sử"])
    with proposal:
        if plans:
            proposal_tab(plans, store)
    with compare:
        if plans:
            compare_tab(plans)
    with history:
        history_tab(store)


@st.cache_resource
def _service():
    from inventory_dw_dss.mms.service import MMSService
    return MMSService.from_env()


def main():
    st.set_page_config(page_title="Kế hoạch đặt hàng", layout="wide")
    path = Path(os.getenv("MMS_DECISIONS_PATH", "reports/mms-decisions.sqlite"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        service = _service()
    except MMSError as exc:
        st.error(str(exc))
        return
    render(service, DecisionStore(path))


if __name__ == "__main__":
    main()
