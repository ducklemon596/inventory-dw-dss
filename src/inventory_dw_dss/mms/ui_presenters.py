"""Presentation/export transformations; model decisions remain in MMSService."""
import csv
from dataclasses import fields
import io
import json

from .core.schemas import DecisionItem, to_dict


PROFILE_LABELS = {"RiskFirst":"Ưu tiên rủi ro", "LowStock":"Tồn kho thấp",
                  "DOS":"Độ bao phủ thấp", "RevenueAtRisk":"Doanh thu có rủi ro"}
TARGET_LABELS = {
    "pharmacy_shortfall":"khả năng nhà thuốc hết hàng (quầy + kho) nếu không nhập thêm",
    "dispensary_stockout":"khả năng quầy bán bị trống hàng (đã tính việc chuyển hàng từ kho)"}
POLICY_LABELS = {"coverage":"Theo số ngày bao phủ", "service_level":"Theo mức phục vụ"}
ACTION_LABELS = {"pending":"Chờ xem xét", "accepted":"Chấp nhận", "rejected":"Từ chối", "edited":"Điều chỉnh số lượng"}
FLAG_LABELS = {"negative_stock":"Tồn âm", "stagnant_inventory":"Tồn chậm luân chuyển",
    "chronic_stockout":"Hết hàng kéo dài", "demand_spike_informational":"Biến động bán hàng",
    "sop_excluded_diagnostics":"Đã loại ngày kiểm kê", "stocktake_last_90d":"Kiểm kê trong 90 ngày",
    "dispensary_out_of_stock":"Quầy đã hết hàng", "transfer_from_storeroom":"Chuyển từ kho sau"}


def scenario_label(index, config):
    return f"{chr(65+index)} · {PROFILE_LABELS[config.profile]}"


def config_matches(comparison, configs):
    return comparison is not None and tuple(r.config for r in comparison.results) == tuple(configs)


def config_token(config):
    return json.dumps(to_dict(config),sort_keys=True)


def risk_caption(manifest):
    """What the risk score measures, from the artifact manifest."""
    target=manifest.get("risk_target","dispensary_stockout")
    horizon=manifest.get("label_horizon_days")
    window=f" trong {horizon} ngày tới" if horizon else ""
    return (f"Điểm rủi ro 0–1: {TARGET_LABELS[target]}{window}. "
            "Cảnh báo có thể có đề xuất bằng 0 và cần được điều tra thêm.")


def quantity_note(item):
    """Vietnamese one-line reason for the suggested quantity."""
    if item.target_level is None:
        return (f"Bao phủ theo MA90 ({item.vel90:.2f} {item.stock_unit}/ngày); tồn {item.available_stock:g} "
                f"→ đề xuất {item.suggested_q}.")
    return (f"Mức phục vụ {item.service_level:.0%}: mức mục tiêu S = {item.target_level:g} {item.stock_unit} "
            f"(trong đó tồn an toàn {item.safety_stock:.1f}); tồn {item.available_stock:g} → đề xuất {item.suggested_q}.")


def item_rows(items, query=""):
    query=query.strip().casefold()
    return [to_dict(item) for item in items if not query or query in item.sku_id.casefold()]


def csv_export(items):
    stream=io.StringIO(newline="")
    writer=csv.DictWriter(stream,fieldnames=[f.name for f in fields(DecisionItem)])
    writer.writeheader()
    for item in items:
        row=to_dict(item)
        row["flags"]="; ".join(row["flags"])
        for key,value in row.items():
            if isinstance(value,str) and value.lstrip().startswith(("=","+","-","@")):
                row[key]="'"+value
        writer.writerow(row)
    return stream.getvalue().encode("utf-8-sig")


def comparison_rows(comparison):
    return [{"Phương án":scenario_label(i,r.config),"SKU xem xét":r.summary["selected_sku_count"],
        "SKU đặt hàng":r.summary["order_sku_count"],"Đề xuất":r.summary["units_suggested"],
        "Phân bổ":r.summary["units_allocated"],"Còn lại":r.summary["budget_remaining"],
        "Ngưỡng rủi ro":r.config.pstar,"K":r.config.top_k,"Q":r.config.unit_budget_q,
        "Chính sách":POLICY_LABELS[r.config.policy],
        "Mức phục vụ":("ABC" if r.config.abc_service else r.config.service_level) if r.config.policy=="service_level" else None,
        "Số ngày bao phủ / chu kỳ":r.config.coverage_tau_days,
        "Chờ hàng (ngày)":r.config.lead_time_days if r.config.policy=="service_level" else None}
        for i,r in enumerate(comparison.results)]
