from datetime import date, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from inventory_dw_dss.mms.core.schemas import InventoryRow, InventorySnapshot, MMSValidationError, ScenarioConfig
from inventory_dw_dss.mms.data.mart_adapter import MART_FEATURES, ReplenishmentMartProvider
from inventory_dw_dss.mms.evaluation.backtesting import Backtester, Observation, OutcomeProvider
from inventory_dw_dss.mms.models.histgb import HistGBRiskModel
from inventory_dw_dss.mms.service import MMSService
from inventory_dw_dss.mms.training import train_histgb

T = date(2025, 6, 2)


def mart_row(product_id, code, dispensary, storeroom, **overrides):
    row = {name: Decimal("1") for name in MART_FEATURES}
    row.update(product_id=product_id, sku_id=code, stock_unit_code="Tab", snapshot_date=T,
        dispensary_on_hand_qty=Decimal(dispensary), storeroom_on_hand_qty=Decimal(storeroom),
        available_qty=Decimal(max(0, dispensary + storeroom)), sold_qty_7d=Decimal(7), sold_qty_30d=Decimal(30),
        sold_qty_90d=Decimal(90), sales_amount_90d=Decimal(900), is_orderable=1, days_since_last_receipt=None,
        dispensary_stockout_days_90d=2, history_days=400, has_stocktake_90d=0,
        dispensary_days_of_supply=float(max(0, dispensary)), days_since_last_stockout=None)
    row.update(overrides)
    return row


class Client:
    """Routes the adapter's SELECTs to in-memory mart rows (clickhouse_connect result shape)."""

    def __init__(self, snapshot_rows, positions):
        self.snapshot_rows, self.positions, self.queries = snapshot_rows, positions, []

    def query(self, sql, parameters=None, **kwargs):
        assert sql.lstrip().upper().startswith("SELECT")
        self.queries.append(sql)
        if "max(snapshot_date)" in sql:
            rows = [{"dataset_name": "fixture", "export_end": date(2025, 12, 31)}]
        elif "fct_product_replenishment_snapshot AS s" in sql:
            rows = self.snapshot_rows
        else:
            rows = [p for p in self.positions if p["sku_id"] in parameters["skus"]
                    and parameters["t"] < p["position_date"] <= parameters["end"]]
        names = list(rows[0]) if rows else []
        return SimpleNamespace(column_names=names, result_rows=[tuple(r[n] for n in names) for r in rows])


def positions(sku, days, stockout_day=None, receipt=Decimal(0)):
    return [{"sku_id": sku, "position_date": T + timedelta(days=d), "sold_qty": Decimal(1),
             "is_dispensary_stockout": int(d == stockout_day), "purchase_received_qty": receipt,
             "has_stocktake": 0} for d in range(1, days + 1)]


def test_snapshot_maps_point_of_sale_stock_missing_features_and_action_flags():
    client = Client([mart_row(1, "A", 0, 40), mart_row(2, "B", 12, 0)], [])
    snapshot = ReplenishmentMartProvider(client, "inventory_dw").get_snapshot(T)
    assert snapshot.data_version == "replenishment-mart-v1:fixture:2025-12-31"
    a, b = snapshot.rows
    # Orderable stock is pharmacy-wide; stockout incidents are judged at the dispensary.
    assert (a.available_stock, a.point_of_sale_stock, a.risk_stock) == (40.0, 0.0, 0.0)
    assert set(a.flags) == {"dispensary_out_of_stock", "transfer_from_storeroom"}
    assert b.risk_stock == 12 and b.flags == ()
    # NULL stays missing for the model's native branch; it is never replaced by zero.
    assert a.features["days_since_last_stockout"] is None and a.days_since_last_receipt is None
    assert "`inventory_dw`" in client.queries[-1]
    assert [r.sku_id for r in ReplenishmentMartProvider(client, "inventory_dw")
            .get_snapshot(T, {"sku_ids": ["B"]}).rows] == ["B"]


def test_outcome_window_requires_every_day_and_floors_net_receipts():
    client = Client([], positions("A", 14, stockout_day=3, receipt=Decimal(-2)) + positions("B", 13))
    outcomes = ReplenishmentMartProvider(client, "inventory_dw").get_outcomes()
    window = outcomes.window(T, ["A"], 14)["A"]
    assert len(window) == 14 and window[2].stockout and window[0].received_quantity == 0
    with pytest.raises(MMSValidationError, match="not complete for B"):
        outcomes.window(T, ["B"], 14)
    with pytest.raises(MMSValidationError, match="data cutoff"):
        outcomes.window(date(2025, 12, 25), ["A"], 14)


class Provider:
    """Weekly snapshots whose dispensary stock alone determines the future stockout."""

    def __init__(self, dates):
        self.snapshots = {}
        for t in dates:
            rows = [InventoryRow(f"S{i:02d}", "Tab", available_stock=20 + i, sales_7d=7, sales_30d=30, sales_90d=90,
                                 revenue_90d=900., point_of_sale_stock=float(i % 10), eligible=True,
                                 features={"dispensary_on_hand_qty": float(i % 10),
                                           "days_since_last_stockout": None if i % 3 else float(i)})
                    for i in range(1, 40)]
            self.snapshots[t] = InventorySnapshot(t, f"s-{t}", "mart-v1", rows)

    def get_snapshot(self, t, filters=None):
        return self.snapshots[t]


def labels(dates, horizon, sop_sku=None):
    observations = []
    for t in dates:
        for i in range(1, 40):
            for d in range(1, horizon + 1):
                observations.append(Observation(t + timedelta(days=d), f"S{i:02d}", 1., stockout=(i % 10 < 3 and d == 2),
                                                sop_day=(f"S{i:02d}" == sop_sku and d == 1)))
    return OutcomeProvider(observations, max(dates) + timedelta(days=horizon), "labels-v1")


def test_mart_training_keeps_missing_values_and_excludes_stocktake_windows_per_sku(tmp_path, monkeypatch):
    import inventory_dw_dss.mms.training as training
    features = ("available_stock", "vel90", "dispensary_on_hand_qty", "days_since_last_stockout")
    monkeypatch.setattr(training, "feature_set", lambda name: (features, training.MART_PARAMS | {"max_iter": 20,
                        "min_samples_leaf": 5}, True, "sku"))
    dates = [T]
    info = train_histgb(Provider(dates), labels(dates, 7, sop_sku="S05"), dates, tmp_path / "bundle", "mart-test",
                        data_kind="verified", features_name="mart")
    manifest = json.loads((tmp_path / "bundle/manifest.json").read_text())
    # S10, S20 and S30 have zero dispensary stock and leave the incident cohort.
    assert manifest["excluded_sop_rows"] == 1 and info["training_samples"] == 39 - 3 - 1
    assert manifest["missing_values"] == "native" and manifest["sop_scope"] == "sku"
    model = HistGBRiskModel.load(tmp_path / "bundle/histgb.joblib", tmp_path / "bundle/manifest.json")
    later = date(2025, 7, 7)
    scores = model.score(Provider([later]).get_snapshot(later).rows)
    assert len(scores) == 39 and all(0 <= s <= 1 for s in scores)


def test_backtest_sku_scope_drops_only_stocktake_windows():
    dates = [T]

    class Model:
        version, calibrated, manifest = "fixture", False, {}

        def score(self, rows):
            return [1 - r.risk_stock / 10 for r in rows]

    service = MMSService(Provider(dates), Model())
    outcomes = labels(dates, 7, sop_sku="S01")
    config = ScenarioConfig(T, pstar=0, top_k=5)
    by_date = Backtester(service, outcomes).run(config, dates, 7).per_date[0]
    assert by_date["status"] == "excluded_sop"
    by_sku = Backtester(service, outcomes).run(config, dates, 7, sop_scope="sku").per_date[0]
    assert by_sku["status"] == "evaluated" and by_sku["sop_excluded_sku_count"] == 1
    assert by_sku["risk"]["cohort_size"] == 39 - 3 - 1
    assert by_sku["existing_stockout_count"] == 3


class StockProvider:
    """Pharmacy stock i (dispensary half of it) for S01..S39; every product sells one unit a day."""

    def get_snapshot(self, t, filters=None):
        rows = [InventoryRow(f"S{i:02d}", "Tab", available_stock=float(i), sales_7d=7, sales_30d=30, sales_90d=90,
                             revenue_90d=900., point_of_sale_stock=float(i // 2), eligible=True,
                             features={"dispensary_on_hand_qty": float(i // 2), "days_since_last_stockout": None})
                for i in range(0, 40)]
        return InventorySnapshot(t, f"s-{t}", "mart-v1", rows)


def sales_outcomes(t, horizon):
    days = [Observation(t + timedelta(days=d), f"S{i:02d}", 1., stockout=(i // 2 < d)) for i in range(40)
            for d in range(1, horizon + 1)]
    return OutcomeProvider(days, t + timedelta(days=horizon), "labels-v1")


def test_pharmacy_shortfall_target_labels_sales_against_all_stock(tmp_path, monkeypatch):
    import inventory_dw_dss.mms.training as training
    monkeypatch.setattr(training, "feature_set", lambda name: (("available_stock", "dispensary_on_hand_qty"),
                        training.MART_PARAMS | {"max_iter": 20, "min_samples_leaf": 2}, True, "sku"))
    info = train_histgb(StockProvider(), sales_outcomes(T, 7), [T], tmp_path / "bundle", "target-test",
                        data_kind="verified", features_name="mart", horizon_days=7, risk_target="pharmacy_shortfall")
    manifest = json.loads((tmp_path / "bundle/manifest.json").read_text())
    # S00 holds no stock; 7 units sold reach the stock of S01..S07 only.
    assert info["training_samples"] == 39 and manifest["positive_samples"] == 7
    assert manifest["risk_target"] == "pharmacy_shortfall" and "available stock" in manifest["label_definition"]
    with pytest.raises(MMSValidationError, match="risk target"):
        train_histgb(StockProvider(), sales_outcomes(T, 7), [T], tmp_path / "other", "x", data_kind="verified",
                     features_name="mart", horizon_days=7, risk_target="shelf")


# Pharmacy: S01..S39 hold stock, S01..S07 sell out. Dispensary (stock i // 2): S02..S39 hold stock,
# S02..S13 empty within 7 days.
@pytest.mark.parametrize("target, cohort, positives", [("pharmacy_shortfall", 39, 7), ("dispensary_stockout", 38, 12)])
def test_backtest_labels_follow_the_artifact_target(target, cohort, positives):
    class Model:
        version, calibrated, manifest = "fixture", False, {"risk_target": target}

        def score(self, rows):
            return [1 / (1 + r.available_stock) for r in rows]

    service = MMSService(StockProvider(), Model())
    day = Backtester(service, sales_outcomes(T, 7)).run(ScenarioConfig(T, pstar=0, top_k=5), [T], 7,
                                                         sop_scope="sku").per_date[0]
    assert day["risk"]["cohort_size"] == cohort and day["new_stockout_count"] == positives
