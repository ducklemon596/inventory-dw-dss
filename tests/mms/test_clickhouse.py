from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from inventory_dw_dss.mms.core.schemas import MMSValidationError
from inventory_dw_dss.mms.data.clickhouse_adapter import ClickHouseDataProvider, audit_warehouse
from inventory_dw_dss.mms.data.mock import MockDataProvider
from test_data import records, T


def release():
    return dict(release_id="r1", schema_version="mms-v1", data_version="export-v1",
        location_scope="pharmacy_total", available_stock_verified=1,
        daily_sales_verified=1, units_verified=1, sop_rules_verified=1,
        approved_by="data-owner", approval_reference="review-42",
        outcome_version="labels-v1", data_cutoff=T+timedelta(days=30))


class Client:
    def __init__(self):
        inventory, sales = records()
        self.tables = {"mms_release_metadata": [release()],
            "mms_inventory_daily": [dict(r, release_id="r1") for r in inventory],
            "mms_sales_daily": [dict(r, release_id="r1") for r in sales],
            "mms_outcomes_daily": [dict(release_id="r1", observation_date=T+timedelta(days=d),
                sku_id="A", sales_quantity=1., stockout=0, received_quantity=0., sop_day=0) for d in range(1,31)]}
        self.queries = []
        self.metadata_reads = 0
        self.change_release = False

    def query(self, sql, parameters=None, **kwargs):
        assert sql.lstrip().upper().startswith("SELECT")
        self.queries.append((sql, parameters))
        if "system.columns" in sql:
            rows = [dict(table="fct_sales_line", name="stock_unit_qty", type="Nullable(Float64)")]
        else:
            table = next(name for name in self.tables if f"`{name}`" in sql)
            rows = deepcopy(self.tables[table])
            if table == "mms_release_metadata":
                self.metadata_reads += 1
                if self.change_release and self.metadata_reads > 1:
                    rows[0]["approval_reference"] = "changed"
        names = list(rows[0]) if rows else []
        return SimpleNamespace(column_names=names, result_rows=[tuple(r[n] for n in names) for r in rows])


def test_same_contract_as_mock_and_bound_selects_only():
    client = Client()
    provider = ClickHouseDataProvider(client, "inventory_dw", "r1")
    assert provider.get_snapshot(T) == MockDataProvider(*records()).get_snapshot(T)
    assert client.metadata_reads == 2
    assert all("2025-06-30" not in sql for sql, _ in client.queries)
    assert any(p.get("analysis_date") == T for _, p in client.queries)
    assert all(p["release_id"] == "r1" for _, p in client.queries)


@pytest.mark.parametrize("field,value", [("available_stock_verified", 0), ("units_verified", "true"),
    ("daily_sales_verified", None), ("sop_rules_verified", 0), ("approved_by", ""),
    ("approval_reference", ""), ("location_scope", "Apotek"), ("schema_version", "old")])
def test_unapproved_release_is_rejected(field, value):
    client = Client()
    client.tables["mms_release_metadata"][0][field] = value
    with pytest.raises(MMSValidationError):
        ClickHouseDataProvider(client, "inventory_dw", "r1").get_snapshot(T)


def test_identifier_release_and_version_changes_fail_closed():
    with pytest.raises(MMSValidationError): ClickHouseDataProvider(Client(), "bad;DROP", "r1")
    client = Client()
    client.change_release = True
    with pytest.raises(MMSValidationError, match="changed"):
        ClickHouseDataProvider(client, "inventory_dw", "r1").get_snapshot(T)
    client = Client()
    client.tables["mms_inventory_daily"][0]["data_version"] = "wrong-version"
    with pytest.raises(MMSValidationError, match="version"):
        ClickHouseDataProvider(client, "inventory_dw", "r1").get_snapshot(T)


def test_outcomes_keep_cutoff_sop_flags_and_verified_release():
    client = Client()
    provider = ClickHouseDataProvider(client, "inventory_dw", "r1")
    labels = provider.get_outcomes()
    assert len(labels.window(T, ["A"], 30)["A"]) == 30
    assert labels.version == "labels-v1"
    assert labels.observations[0].stockout is False
    client.tables["mms_outcomes_daily"][0]["stockout"] = 2
    with pytest.raises(MMSValidationError): provider.get_outcomes()


def test_raw_warehouse_audit_never_approves_observed_as_available():
    report = audit_warehouse(Client(), "inventory_dw")
    assert report["production_ready"] is False
    assert report["columns"]["fct_sales_line"]["stock_unit_qty"] == "Nullable(Float64)"
    assert "available_stock_unverified" in report["blockers"]
    assert "missing_days_are_not_zero" in report["blockers"]
