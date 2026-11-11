from datetime import date, timedelta
from decimal import Decimal

import pytest

from inventory_dw_dss.mms.data import MART_FEATURES, MartReader
from inventory_dw_dss.mms.schemas import MMSError

from fixtures import T, Client


def mart_row(product_id, code, dispensary, storeroom, **overrides):
    row = {name: Decimal("1") for name in MART_FEATURES}
    row.update(product_id=product_id, sku_id=code, product_name=f"Product {code}", stock_unit_code="Tab",
               snapshot_date=T, dispensary_on_hand_qty=Decimal(dispensary), storeroom_on_hand_qty=Decimal(storeroom),
               available_qty=Decimal(max(0, dispensary + storeroom)), sold_qty_7d=Decimal(7),
               sold_qty_30d=Decimal(30), sold_qty_90d=Decimal(90), sales_amount_90d=Decimal(900),
               sold_qty_std_90d=1.5, abc_class="B", is_orderable=1, days_since_last_receipt=None,
               has_stocktake_90d=0, dispensary_days_of_supply=float(max(0, dispensary)), days_since_last_stockout=None)
    row.update(overrides)
    return row


def positions(sku, days, stockout_day=None, receipt=Decimal(0)):
    return [{"sku_id": sku, "position_date": T + timedelta(days=d), "sold_qty": Decimal(1),
             "is_dispensary_stockout": int(d == stockout_day), "purchase_received_qty": receipt,
             "has_stocktake": 0} for d in range(1, days + 1)]


def reader(client):
    return MartReader(client_factory=lambda: client)


def test_snapshot_maps_stock_levels_missing_values_and_flags():
    client = Client([mart_row(1, "A", 0, 40), mart_row(2, "B", 12, 0, sold_qty_7d=Decimal(30))])
    snapshot = reader(client).snapshot(T)
    assert snapshot.data_version == "replenishment-mart-v1:fixture:2025-12-31"
    a, b = snapshot.rows
    # Order quantities use pharmacy-wide stock; the dispensary is the shelf.
    assert (a.available_stock, a.dispensary_stock, a.sales_std_90d, a.abc_class) == (40, 0, 1.5, "B")
    assert set(a.flags) == {"dispensary_empty", "transfer_from_storeroom"}
    assert b.flags == ("demand_spike",)          # 30 sold in 7 days vs 7 expected at MA90
    assert a.features["days_since_last_stockout"] is None   # NULL stays missing, never zero
    assert "`inventory_dw`" in client.queries[-1]


def test_outcome_window_requires_every_day_and_floors_net_receipts():
    outcomes = reader(Client([], positions("A", 14, stockout_day=3, receipt=Decimal(-2)) + positions("B", 13))).outcomes()
    window = outcomes.window(T, ["A"], 14)["A"]
    assert len(window) == 14 and window[2].stockout and window[0].received_quantity == 0
    with pytest.raises(MMSError, match="missing days"):
        outcomes.window(T, ["B"], 14)
    with pytest.raises(MMSError, match="not complete"):
        outcomes.window(date(2025, 12, 25), ["A"], 14)
