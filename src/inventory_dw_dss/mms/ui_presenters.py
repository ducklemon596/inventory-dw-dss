"""Presentation/export transformations; model decisions remain in MMSService."""
import csv
from dataclasses import fields
import io
import json

from .core.schemas import DecisionItem, to_dict


PROFILE_LABELS = {"RiskFirst":"Risk first", "LowStock":"Low stock",
                  "DOS":"Low cover", "RevenueAtRisk":"Revenue at risk"}
ACTION_LABELS = {"pending":"Pending", "accepted":"Accept", "rejected":"Reject", "edited":"Adjust quantity"}
FLAG_LABELS = {"negative_stock":"Negative stock", "stagnant_inventory":"No sales in 90 days",
    "chronic_stockout":"Chronic stockout", "demand_spike_informational":"Sales spike",
    "sop_excluded_diagnostics":"Stocktaking days excluded"}


def scenario_label(index, config):
    return f"{chr(65+index)} · {PROFILE_LABELS[config.profile]}"


def config_matches(comparison, configs):
    return comparison is not None and tuple(r.config for r in comparison.results) == tuple(configs)


def config_token(config):
    return json.dumps(to_dict(config),sort_keys=True)


def item_rows(items, query=""):
    query=query.strip().casefold()
    return [to_dict(item) for item in items if not query or query in item.sku_id.casefold()]


def item_advice(item, include_coverage=True):
    """Explain observed coverage and allocation without inventing model attribution."""
    parts=[]
    if include_coverage and item.dos is not None:
        parts.append(f"About {item.dos:.1f} days of stock")
    elif include_coverage:
        parts.append("Stock cover unavailable")
    flags=[FLAG_LABELS.get(f,f) for f in item.flags if f!="sop_excluded_diagnostics"]
    parts.extend(flags)
    if not item.eligible:
        parts.append("Check eligibility before ordering")
    elif item.suggested_q == 0:
        parts.append("No replenishment needed for this target")
    elif item.allocated_q == 0:
        parts.append("Not allocated: quantity limit reached")
    elif item.allocated_q < item.suggested_q:
        parts.append(f"Needs {item.suggested_q}; limited to {item.allocated_q}")
    else:
        parts.append("Full suggested quantity")
    return "; ".join(parts)


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
    return [{"Scenario":scenario_label(i,r.config),"Review items":r.summary["selected_sku_count"],
        "Order items":r.summary["order_sku_count"],"Suggested":r.summary["units_suggested"],
        "Allocated":r.summary["units_allocated"],"Remaining":r.summary["budget_remaining"],
        "Risk threshold":r.config.pstar,"K":r.config.top_k,"Q":r.config.unit_budget_q,
        "Stock cover days":r.config.coverage_tau_days} for i,r in enumerate(comparison.results)]
