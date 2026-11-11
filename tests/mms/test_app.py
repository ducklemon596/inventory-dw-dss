"""Headless Streamlit checks with the in-memory reader and model."""
from streamlit.testing.v1 import AppTest


def app_script(path):
    import sys
    sys.path.insert(0, "tests/mms")
    from fixtures import Reader, RiskModel, row
    from inventory_dw_dss.mms.app import render
    from inventory_dw_dss.mms.decisions import DecisionStore
    from inventory_dw_dss.mms.service import MMSService
    rows = tuple(row(f"S{i:02d}", i, std=1.5, abc="A" if i < 5 else "C") for i in range(20))
    render(MMSService(Reader(rows), RiskModel()), DecisionStore(path))


def start(tmp_path):
    return AppTest.from_function(app_script, args=(str(tmp_path / "d.sqlite"),), default_timeout=30).run()


def button(app, label):
    return next(b for b in app.button if b.label == label)


def approved_text(app):
    return next(m.value for m in app.markdown if "Đã duyệt" in m.value)


def test_opens_with_a_default_plan_and_saves_bulk_approval(tmp_path):
    app = start(tmp_path)
    assert not app.exception and app.subheader[0].value == "Kế hoạch đặt hàng"
    plan = app.session_state["plans"][0]   # planned on first load, no click needed
    assert plan.config.policy == "service_level" and plan.items[0].target_level is not None
    assert [m.label for m in app.metric] == ["Sản phẩm cần xem xét", "Dòng có đặt hàng", "Tổng đơn vị phân bổ",
                                             "Giá trị ước tính"]
    assert any("Không giới hạn đơn vị" in c.value for c in app.caption) and "Đã duyệt 0 /" in approved_text(app)
    button(app, "Duyệt các dòng có phân bổ").click().run()
    approved = sum(i.allocated_qty > 0 for i in plan.items)
    assert f"Đã duyệt {approved} / {len(plan.items)}" in approved_text(app)
    button(app, "Lưu quyết định").click().run()
    assert any(f"{approved} dòng duyệt" in s.value for s in app.success)
    assert any(s.label == "Phiên đã lưu" for s in app.selectbox)


def test_filters_keep_decisions(tmp_path):
    app = start(tmp_path)
    button(app, "Duyệt các dòng có phân bổ").click().run()
    app.session_state["row_filter"] = "orders"
    app.run()
    app.text_input(key="query").set_value("S01").run()
    assert not app.exception and len(app.dataframe) >= 1
    assert "Đã duyệt 0 " not in approved_text(app)   # approvals survive filtering


def test_budget_gauge_shows_usage_and_lines_cut(tmp_path):
    app = start(tmp_path)
    app.number_input(key="a_budget").set_value(20).run()
    button(app, "Lập kế hoạch").click().run()
    plan = app.session_state["plans"][0]
    cut = sum(i.allocated_qty < i.suggested_qty for i in plan.items)
    text = app.get("progress")[0].proto.text
    assert f"/ 20 ({plan.summary['units_allocated'] / 20:.0%})" in text and f"{cut} dòng bị cắt" in text and cut > 0


def test_compare_two_policies_and_stale_warning(tmp_path):
    app = start(tmp_path)
    app.toggle(key="compare").set_value(True).run()
    app.radio(key="b_policy").set_value("Theo số ngày bao phủ").run()
    button(app, "Lập kế hoạch").click().run()
    assert [p.config.policy for p in app.session_state["plans"]] == ["service_level", "coverage"]
    assert any("có trong cả hai danh sách" in c.value for c in app.caption)
    app.select_slider(key="a_level").set_value(.9).run()
    assert any("Thiết lập đã thay đổi" in w.value for w in app.warning)
