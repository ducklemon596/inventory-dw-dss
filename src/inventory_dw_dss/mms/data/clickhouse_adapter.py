"""Read approved immutable MMS releases; never reinterpret observed marts."""
from datetime import timedelta
import re

from clickhouse_connect.driver.exceptions import ClickHouseError

from ..core.schemas import MMSValidationError, as_date
from ..evaluation.backtesting import Observation, OutcomeProvider
from .mock import MockDataProvider


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value):
        raise MMSValidationError("Invalid ClickHouse database identifier")
    return f"`{value}`"


def explicit_bool(value, name):
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    raise MMSValidationError(f"{name} must be an explicit Bool/UInt8 0 or 1")


def query_rows(client, sql, parameters):
    try:
        result = client.query(sql, parameters=parameters)
        return [dict(zip(result.column_names, row)) for row in result.result_rows]
    except ClickHouseError as exc:
        # Credentials/URLs from client exceptions are not copied into reports.
        raise MMSValidationError(f"ClickHouse read failed ({type(exc).__name__}); check connection, read grants and normalized schema") from exc


class ClickHouseDataProvider:
    def __init__(self, client, database, release_id):
        self.client = client
        self.database = identifier(database)
        if not isinstance(release_id, str) or not release_id.strip():
            raise MMSValidationError("An immutable ClickHouse release_id is required")
        self.release_id = release_id

    def _rows(self, table, clause="", parameters=None):
        return query_rows(self.client,
            f"SELECT * FROM {self.database}.`{table}` WHERE release_id = {{release_id:String}} {clause}",
            {"release_id": self.release_id, **(parameters or {})})

    def _release(self):
        rows = self._rows("mms_release_metadata")
        if len(rows) != 1:
            raise MMSValidationError("Expected exactly one approved release metadata row")
        metadata = rows[0]
        if (metadata.get("release_id") != self.release_id or metadata.get("schema_version") != "mms-v1"
                or metadata.get("location_scope") != "pharmacy_total"):
            raise MMSValidationError("Unsupported release, schema version or pharmacy scope")
        for field in ("data_version", "approved_by", "approval_reference"):
            if not isinstance(metadata.get(field), str) or not metadata[field].strip():
                raise MMSValidationError(f"Release requires {field}")
        for field in ("available_stock_verified", "daily_sales_verified", "units_verified", "sop_rules_verified"):
            if not explicit_bool(metadata.get(field), field):
                raise MMSValidationError(f"Release approval missing: {field}")
        return metadata

    def _unchanged(self, metadata):
        if self._release() != metadata:
            raise MMSValidationError("ClickHouse release metadata changed while reading; retry with an immutable release")

    def _check_release_rows(self, rows):
        if any(r.get("release_id") != self.release_id for r in rows):
            raise MMSValidationError("Mixed ClickHouse release rows")

    def get_snapshot(self, analysis_date, filters=None):
        t = as_date(analysis_date)
        metadata = self._release()
        inventory = self._rows("mms_inventory_daily", "AND analysis_date = {analysis_date:Date}", {"analysis_date": t})
        sales = self._rows("mms_sales_daily", "AND sales_date BETWEEN {start:Date} AND {end:Date}",
                           {"start": t-timedelta(days=89), "end": t})
        self._check_release_rows(inventory)
        self._check_release_rows(sales)
        if any(r.get("data_version") != metadata["data_version"] for r in inventory):
            raise MMSValidationError("Snapshot data version disagrees with approved release")
        try:
            for row in inventory:
                row["eligible"] = explicit_bool(row.get("eligible"), "eligible")
            result = MockDataProvider(inventory, sales).get_snapshot(t, filters)
        except (KeyError, TypeError) as exc:
            raise MMSValidationError("Incomplete normalized ClickHouse snapshot schema") from exc
        self._unchanged(metadata)
        return result

    def get_outcomes(self):
        metadata = self._release()
        if not isinstance(metadata.get("outcome_version"), str) or not metadata["outcome_version"]:
            raise MMSValidationError("Release has no approved outcome version")
        cutoff = as_date(metadata.get("data_cutoff"))
        rows = self._rows("mms_outcomes_daily", "AND observation_date <= {cutoff:Date}", {"cutoff": cutoff})
        self._check_release_rows(rows)
        try:
            observations = [Observation(as_date(r["observation_date"]), r["sku_id"],
                r["sales_quantity"], explicit_bool(r["stockout"], "stockout"), r["received_quantity"],
                explicit_bool(r["sop_day"], "sop_day")) for r in rows]
        except (KeyError, TypeError) as exc:
            raise MMSValidationError("Incomplete normalized ClickHouse outcome schema") from exc
        result = OutcomeProvider(observations, cutoff, metadata["outcome_version"])
        self._unchanged(metadata)
        return result


def audit_warehouse(client, database):
    """Inspect source schema without granting semantic approval or creating views."""
    identifier(database)
    rows = query_rows(client, "SELECT table, name, type FROM system.columns WHERE database = {database:String} "
        "AND table IN ('fct_sales_line', 'fct_inventory_daily_observed', 'fct_inventory_movement', 'dim_warehouse', 'dim_unit')",
        {"database": database})
    columns = {}
    for row in rows:
        columns.setdefault(row["table"], {})[row["name"]] = row["type"]
    required = {"fct_sales_line", "fct_inventory_daily_observed", "fct_inventory_movement"}
    blockers = ["available_stock_unverified", "missing_days_are_not_zero", "pharmacy_scope_requires_approval",
                "sop_rules_require_approval", "units_require_approval"]
    blockers += [f"missing_mart:{table}" for table in sorted(required-columns.keys())]
    return {"database": database, "production_ready": False, "columns": columns, "blockers": blockers,
            "next_step": "Publish an approved immutable normalized MMS release; raw observations alone do not prove readiness"}
