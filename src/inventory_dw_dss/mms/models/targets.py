"""What the risk score predicts. Training and backtests use the same definitions.

pharmacy_shortfall (recommended): sales over the next h days reach all stock held at T
    (dispensary + storeroom), so the pharmacy runs out unless it buys. This is the event a
    purchase decision prevents.
dispensary_stockout: the dispensary balance reaches zero within h days. It also depends on how
    quickly staff refilled the shelf from the storeroom, so it partly measures past actions.
"""
from ..schemas import MMSError

RISK_TARGETS = ("pharmacy_shortfall", "dispensary_stockout")
LABEL_DEFINITIONS = {
    "pharmacy_shortfall": "sales in (T, T+h] >= available stock at T; products without stock excluded",
    "dispensary_stockout": "dispensary balance <= 0 on a day in (T, T+h]; products with an empty shelf excluded",
}


def check_target(target):
    if target not in RISK_TARGETS:
        raise MMSError(f"risk target must be one of {RISK_TARGETS}")
    return target


def target_stock(row, target):
    """Stock whose depletion the target measures. Products at or below zero are already out."""
    return row.available_stock if target == "pharmacy_shortfall" else row.dispensary_stock


def target_label(row, window, target):
    """1 if the event happened in the observed window (sequence of Observation), else 0."""
    if target == "pharmacy_shortfall":
        return int(sum(o.sales_quantity for o in window) >= row.available_stock)
    return int(any(o.stockout for o in window))
