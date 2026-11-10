"""Presentation/export transformations; model decisions remain in MMSService."""
import csv
from dataclasses import fields
import io
import json

from .core.schemas import DecisionItem, to_dict


PROFILE_LABELS = {"RiskFirst":"Ưu tiên rủi ro", "LowStock":"Tồn kho thấp",
                  "DOS":"Độ bao phủ thấp", "RevenueAtRisk":"Doanh thu có rủi ro"}
ACTION_LABELS = {"pending":"Chờ xem xét", "accepted":"Chấp nhận", "rejected":"Từ chối", "edited":"Điều chỉnh số lượng"}
FLAG_LABELS = {"negative_stock":"Tồn âm", "stagnant_inventory":"Tồn chậm luân chuyển",
    "chronic_stockout":"Hết hàng kéo dài", "demand_spike_informational":"Biến động bán hàng",
    "sop_excluded_diagnostics":"Đã loại ngày kiểm kê"}


def scenario_label(index, config):
    return f"{chr(65+index)} · {PROFILE_LABELS[config.profile]}"


def config_matches(comparison, configs):
    return comparison is not None and tuple(r.config for r in comparison.results) == tuple(configs)


def config_token(config):
    return json.dumps(to_dict(config),sort_keys=True)


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
        "Số ngày bao phủ":r.config.coverage_tau_days} for i,r in enumerate(comparison.results)]
