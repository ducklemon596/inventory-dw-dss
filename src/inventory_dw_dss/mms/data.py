"""Read-only access to the dbt replenishment marts in ClickHouse.

fct_product_replenishment_snapshot gives one row per product and day with point-in-time
features; fct_product_daily_position gives the daily outcomes used for labels and backtests.
Each call opens a short-lived client, so the Streamlit app never shares a session.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
import os
import re

from .schemas import InventoryRow, InventorySnapshot, MMSError, Observation, as_date

SCHEMA_VERSION = "replenishment-mart-v1"

# Mart columns passed to the risk model as extra features. Columns that equal an InventoryRow
# field (sold_qty_90d, sales_amount_90d, available_qty) are mapped to that field instead.
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
    """ClickHouse Decimal/int to float; NULL stays None so the model sees a missing value."""
    return float(value) if isinstance(value, (Decimal, int, float)) and not isinstance(value, bool) else value


@dataclass(frozen=True)
class WarehouseSettings:
    host: str = "localhost"
    port: int = 8123
    database: str = "inventory_dw"
    username: str = "dbt"
    password: str = field(default="dbt_local", repr=False)
    secure: bool = False

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        database = env.get("CLICKHOUSE_DB", cls.database)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", database):
            raise MMSError("CLICKHOUSE_DB must be a plain identifier")
        try:
            port = int(env.get("CLICKHOUSE_HTTP_PORT", cls.port))
        except ValueError:
            raise MMSError("CLICKHOUSE_HTTP_PORT must be an integer") from None
        return cls(env.get("CLICKHOUSE_HOST", cls.host), port, database,
                   env.get("CLICKHOUSE_USER", cls.username), env.get("CLICKHOUSE_PASSWORD", cls.password),
                   env.get("CLICKHOUSE_SECURE", "false").lower() in ("1", "true"))


class MartReader:
    """Snapshots, outcome windows and raw queries against the replenishment marts."""

    def __init__(self, settings=None, client_factory=None):
        self.settings = settings or WarehouseSettings.from_env()
        self._client_factory = client_factory  # tests inject an in-memory client

    @contextmanager
    def _client(self):
        if self._client_factory:
            yield self._client_factory()
            return
        import clickhouse_connect
        s = self.settings
        try:
            client = clickhouse_connect.get_client(host=s.host, port=s.port, username=s.username, password=s.password,
                                                   database=s.database, secure=s.secure, connect_timeout=3,
                                                   send_receive_timeout=30, autogenerate_session_id=False)
        except Exception as exc:
            raise MMSError(f"ClickHouse is unavailable at {s.host}:{s.port} ({type(exc).__name__})") from exc
        try:
            yield client
        finally:
            client.close()

    def query(self, sql, parameters=None):
        """Run a SELECT; `{db}` is replaced by the database (binds use {name:Type})."""
        sql = sql.replace("{db}", f"`{self.settings.database}`")
        with self._client() as client:
            try:
                result = client.query(sql, parameters=parameters or {})
            except Exception as exc:
                raise MMSError(f"Mart query failed: {exc}") from exc
        return [dict(zip(result.column_names, row)) for row in result.result_rows]

    def data_version(self):
        """'replenishment-mart-v1:<dataset>:<export end>' and the export end date."""
        rows = self.query("SELECT dataset_name, max(snapshot_date) AS export_end "
                          "FROM {db}.fct_product_replenishment_snapshot GROUP BY dataset_name")
        if len(rows) != 1:
            raise MMSError("The replenishment mart must contain exactly one dataset; run dbt first")
        end = as_date(rows[0]["export_end"])
        return f"{SCHEMA_VERSION}:{rows[0]['dataset_name']}:{end}", end

    def snapshot(self, analysis_date):
        """Products sold in the 90 days up to the analysis date, with their stock at day end."""
        t = as_date(analysis_date)
        version, _ = self.data_version()
        rows = self.query(
            "SELECT s.*, p.product_code AS sku_id, p.product_name, u.unit_code AS stock_unit_code "
            "FROM {db}.fct_product_replenishment_snapshot AS s "
            "LEFT JOIN {db}.dim_product AS p ON p.product_id = s.product_id "
            "LEFT JOIN {db}.dim_unit AS u ON u.unit_id = s.stock_unit_id "
            "WHERE s.snapshot_date = {t:Date} AND s.is_active_90d = 1", {"t": t})
        if not rows:
            raise MMSError(f"No replenishment snapshot for {t}")
        return InventorySnapshot(t, version, tuple(_row(r) for r in rows))

    def outcomes(self):
        version, end = self.data_version()
        return MartOutcomes(self, version, end)


def _row(raw):
    flags = []
    if raw["has_stocktake_90d"]:
        flags.append("stocktake_90d")
    if raw["dispensary_on_hand_qty"] <= 0:
        flags.append("dispensary_empty")
    # Storeroom stock can refill a thin shelf: a transfer, not a purchase, fixes it.
    if raw["storeroom_on_hand_qty"] > 0 and (raw["dispensary_days_of_supply"] or 0) < 7:
        flags.append("transfer_from_storeroom")
    if raw["sold_qty_90d"] and raw["sold_qty_7d"] > 2 * raw["sold_qty_90d"] / 90 * 7:
        flags.append("demand_spike")
    return InventoryRow(
        sku_id=raw["sku_id"], stock_unit=raw["stock_unit_code"] or "?", product_name=raw.get("product_name"),
        available_stock=_number(raw["available_qty"]), dispensary_stock=_number(raw["dispensary_on_hand_qty"]),
        sales_7d=_number(raw["sold_qty_7d"]), sales_30d=_number(raw["sold_qty_30d"]),
        sales_90d=_number(raw["sold_qty_90d"]), revenue_90d=_number(raw["sales_amount_90d"]),
        sales_std_90d=_number(raw["sold_qty_std_90d"]), abc_class=raw.get("abc_class"),
        eligible=bool(raw["is_orderable"]), days_since_last_receipt=raw["days_since_last_receipt"],
        features={name: _number(raw[name]) for name in MART_FEATURES}, flags=tuple(flags))


class MartOutcomes:
    """Daily outcomes after a decision date, read per window instead of loading every day."""

    def __init__(self, reader, version, data_cutoff):
        self.reader, self.version, self.data_cutoff = reader, version, as_date(data_cutoff)

    def window(self, t, sku_ids, horizon):
        """{sku: (Observation for day t+1 .. t+horizon)}; every day must be present."""
        t = as_date(t)
        if self.data_cutoff < t + timedelta(days=horizon):
            raise MMSError(f"Outcomes after {t} are not complete for {horizon} days at the data cutoff")
        rows = self.reader.query(
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
                raise MMSError(f"Outcomes for {sku} after {t} are missing days")
            result[sku] = tuple(observed)
        return result
