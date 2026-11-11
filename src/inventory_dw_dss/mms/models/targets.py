"""Stockout-risk targets shared by training, backtesting and the UI.

dispensary_stockout: the dispensary balance reaches zero in (T, T+h]. It also reflects how
    promptly staff refilled the shelf, so it partly measures past actions rather than risk.
pharmacy_shortfall: sales in (T, T+h] reach all stock held at T (dispensary + storeroom), so the
    pharmacy would run out without a new receipt. This is the target for purchase decisions.
"""
from ..core.schemas import MMSValidationError

RISK_TARGETS = ("dispensary_stockout", "pharmacy_shortfall")
DEFAULT_TARGET = "dispensary_stockout"  # artifacts trained before targets existed
LABEL_DEFINITIONS = {
    "dispensary_stockout": "any verified stockout in (T,T+horizon]; existing zero/negative balances excluded",
    "pharmacy_shortfall": "sales in (T,T+horizon] >= available stock at T; products without stock excluded",
}


def check_target(target):
    if target not in RISK_TARGETS:
        raise MMSValidationError(f"risk target must be one of {RISK_TARGETS}")
    return target


def model_target(risk_model):
    """Target declared by an artifact manifest; older artifacts predate the field."""
    return check_target(getattr(risk_model, "manifest", {}).get("risk_target", DEFAULT_TARGET))


def target_stock(row, target):
    """Stock whose depletion the target measures; rows at or below zero are not at risk, already out."""
    return row.risk_stock if target == "dispensary_stockout" else row.available_stock


def target_label(row, window, target):
    if target == "dispensary_stockout":
        return int(any(o.stockout for o in window))
    return int(sum(o.sales_quantity for o in window) >= row.available_stock)
