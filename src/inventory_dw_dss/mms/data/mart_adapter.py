"""Read the dbt replenishment marts (fct_product_replenishment_snapshot / fct_product_daily_position).

The marts already apply the documented ledger rules (carried-forward balances, ledger
sales in the stock unit, dispensary stockouts), so this adapter only maps columns.
"""
from datetime import timedelta
from decimal import Decimal

from ..core.schemas import InventoryRow, InventorySnapshot, MMSValidationError, as_date
from ..evaluation.backtesting import Observation
from .clickhouse_adapter import identifier, query_rows

SCHEMA_VERSION = "replenishment-mart-v1"

# Mart columns passed to models as extra features. Columns that equal a canonical InventoryRow
# field (sold_qty_90d, sales_amount_90d, pharmacy_days_of_supply) are mapped there instead.
MART_FEATURES = (
    "dispensary_on_hand_qty", "storeroom_on_hand_qty", "sale_days_90d",
    "unit_sales_value_90d", "dispensary_days_of_supply",
    "days_since_last_sale", "purchase_receipt_days_90d", "transfer_to_dispensary_qty_30d",
    "dispensary_stockout_days_90d", "history_days", "has_stocktake_90d", "has_full_history",
    "sold_qty_std_90d", "sold_qty_max_90d", "demand_cv_90d", "demand_trend_7_90", "dispensary_peak_cover_days",
    "sold_qty_365d", "sale_days_365d", "purchase_receipt_days_365d", "avg_purchase_receipt_qty_365d",
    "transfer_days_90d", "days_since_last_transfer", "dispensary_avg_on_hand_30d", "dispensary_min_on_hand_30d",
    "days_since_last_stockout", "dispensary_stockout_days_365d",
)


def _number(value):
    """ClickHouse Decimal/int to float; NULL stays None so models see a missing value."""
    if value is None:
        return None
    return float(value) if isinstance(value, (Decimal, int, float)) else value


class ReplenishmentMartProvider:
    """Snapshot and outcome reads; the caller owns the ClickHouse client."""

    def __init__(self, client, database):
        self.client = client
        self.database = identifier(database)

    def _query(self, sql, parameters=None):
        # Plain replace: ClickHouse binds use {name:Type}, which str.format would consume.
        return query_rows(self.client, sql.replace("{db}", self.database), parameters or {})

    def data_version(self):
        rows = self._query("SELECT dataset_name, max(snapshot_date) AS export_end "
                           "FROM {db}.fct_product_replenishment_snapshot GROUP BY dataset_name")
        if len(rows) != 1:
            raise MMSValidationError("Replenishment mart must contain exactly one dataset")
        return f"{SCHEMA_VERSION}:{rows[0]['dataset_name']}:{rows[0]['export_end']}", as_date(rows[0]["export_end"])

    def get_snapshot(self, analysis_date, filters=None):
        t = as_date(analysis_date)
        filters = filters or {}
        if set(filters) - {"sku_ids"}:
            raise MMSValidationError("Unsupported snapshot filter")
        data_version, _ = self.data_version()
        # Active products only: a product without sales in 90 days has no demand to protect.
        rows = self._query(
            "SELECT s.*, p.product_code AS sku_id, u.unit_code AS stock_unit_code "
            "FROM {db}.fct_product_replenishment_snapshot AS s "
            "LEFT JOIN {db}.dim_product AS p ON p.product_id = s.product_id "
            "LEFT JOIN {db}.dim_unit AS u ON u.unit_id = s.stock_unit_id "
            "WHERE s.snapshot_date = {t:Date} AND s.is_active_90d = 1", {"t": t})
        if not rows:
            raise MMSValidationError(f"No replenishment snapshot for {t}")
        selected = filters.get("sku_ids")
        items = []
        for raw in rows:
            if selected is not None and raw["sku_id"] not in selected:
                continue
            flags = ["stocktake_last_90d"] if raw["has_stocktake_90d"] else []
            # Already empty at the point of sale: an incident in progress, not a forecast.
            if raw["dispensary_on_hand_qty"] <= 0:
                flags.append("dispensary_out_of_stock")
            # Storeroom stock can cover the dispensary: a transfer, not a purchase, resolves it.
            if raw["storeroom_on_hand_qty"] > 0 and (raw["dispensary_days_of_supply"] or 0) < 7:
                flags.append("transfer_from_storeroom")
            items.append(InventoryRow(
                sku_id=raw["sku_id"], stock_unit=raw["stock_unit_code"] or "UNKNOWN_UNIT",
                available_stock=_number(raw["available_qty"]),
                point_of_sale_stock=_number(raw["dispensary_on_hand_qty"]),
                sales_std_90d=_number(raw["sold_qty_std_90d"]), abc_class=raw.get("abc_class"),
                sales_7d=_number(raw["sold_qty_7d"]), sales_30d=_number(raw["sold_qty_30d"]),
                sales_90d=_number(raw["sold_qty_90d"]), revenue_90d=_number(raw["sales_amount_90d"]),
                eligible=bool(raw["is_orderable"]),
                days_since_last_receipt=raw["days_since_last_receipt"],
                features={name: _number(raw[name]) for name in MART_FEATURES},
                flags=tuple(flags),
                observed_stockout_days=int(raw["dispensary_stockout_days_90d"]),
                diagnostic_observed_days=min(int(raw["history_days"]) + 1, 90),
            ))
        return InventorySnapshot(t, f"{data_version}:{t}", data_version, tuple(items))

    def get_outcomes(self):
        version, export_end = self.data_version()
        return MartOutcomeProvider(self, version, export_end)


class MartOutcomeProvider:
    """OutcomeProvider interface backed by per-window queries instead of an in-memory export.

    Daily outcomes: stockout is a dispensary closing at or below zero; sop_day marks stocktake
    postings; receipts are net supplier quantities floored at zero.
    """

    def __init__(self, provider, version, data_cutoff):
        self.provider = provider
        self.version = version
        self.data_cutoff = data_cutoff

    def window(self, t, sku_ids, horizon):
        t = as_date(t)
        if self.data_cutoff < t + timedelta(days=horizon):
            raise MMSValidationError("Observation window is not complete at the data cutoff")
        rows = self.provider._query(
            "SELECT p.product_code AS sku_id, d.position_date, d.sold_qty, d.is_dispensary_stockout, "
            "d.purchase_received_qty, d.has_stocktake "
            "FROM {db}.fct_product_daily_position AS d "
            "INNER JOIN {db}.dim_product AS p ON p.product_id = d.product_id "
            "WHERE d.position_date > {t:Date} AND d.position_date <= {end:Date} "
            "AND p.product_code IN {skus:Array(String)}",
            {"t": t, "end": t + timedelta(days=horizon), "skus": list(sku_ids)})
        days = {}
        for r in rows:
            days.setdefault(r["sku_id"], []).append(Observation(
                as_date(r["position_date"]), r["sku_id"], max(0.0, float(r["sold_qty"])),
                bool(r["is_dispensary_stockout"]), max(0.0, float(r["purchase_received_qty"])),
                bool(r["has_stocktake"])))
        result = {}
        for sku in sku_ids:
            observed = sorted(days.get(sku, ()), key=lambda o: o.observation_date)
            if len(observed) != horizon:
                raise MMSValidationError(f"Observation window is not complete for {sku}")
            result[sku] = tuple(observed)
        return result
