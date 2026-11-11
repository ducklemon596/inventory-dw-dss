from datetime import date, timedelta

import duckdb
import pytest

from inventory_dw_dss.mms.data.duckdb_adapter import DuckDBDataProvider
from inventory_dw_dss.mms.data.mock import MockDataProvider
from inventory_dw_dss.mms.core.schemas import MMSValidationError


T = date(2025, 6, 30)


def records():
    inventory = [dict(analysis_date=T, sku_id="A", available_stock=30,
                      stock_unit="tablet", location_scope="pharmacy_total",
                      snapshot_version="fixture-v1", data_version="export-v1",
                      feature_as_of=T, eligible=True, features={})]
    sales = [dict(sku_id="A", sales_date=T - timedelta(days=i),
                  quantity=1, revenue=2) for i in range(90)]
    return inventory, sales


def test_snapshot_lookback_boundaries_and_frozen_input():
    inventory, sales = records()
    sales += [dict(sku_id="A", sales_date=T-timedelta(days=90), quantity=999, revenue=0),
              dict(sku_id="A", sales_date=T+timedelta(days=1), quantity=999, revenue=0)]
    provider = MockDataProvider(inventory, sales)
    snapshot = provider.get_snapshot(T)
    row = snapshot.rows[0]
    assert (row.sales_7d, row.sales_30d, row.sales_90d) == (7, 30, 90)
    assert row.vel90 == 1 and row.dos == 30 and row.revenue_90d == 180
    inventory[0]["available_stock"] = 500
    assert provider.get_snapshot(T) == snapshot
    with pytest.raises((TypeError, AttributeError)):
        row.features["future"] = 1


@pytest.mark.parametrize("fault", ["missing", "duplicate", "negative_sales", "future_feature", "scope"])
def test_invalid_or_incomplete_data_is_not_silently_imputed(fault):
    inventory, sales = records()
    if fault == "missing": sales.pop()
    if fault == "duplicate": sales.append(sales[0].copy())
    if fault == "negative_sales": sales[0]["quantity"] = -1
    if fault == "future_feature": inventory[0]["feature_as_of"] = T+timedelta(days=1)
    if fault == "scope": inventory[0]["location_scope"] = "Apotek"
    with pytest.raises(MMSValidationError):
        MockDataProvider(inventory, sales).get_snapshot(T)


def test_zero_demand_negative_stock_and_filters():
    inventory, sales = records()
    inventory[0]["available_stock"] = -3
    for s in sales: s["quantity"] = 0
    snapshot = MockDataProvider(inventory, sales).get_snapshot(T, {"sku_ids": ["A"]})
    assert snapshot.rows[0].dos is None
    assert snapshot.rows[0].eligible is False
    assert "negative_stock" in snapshot.rows[0].flags
    assert not MockDataProvider(inventory, sales).get_snapshot(T, {"sku_ids": ["B"]}).rows


def test_duckdb_reads_only_requested_date_and_uses_same_contract():
    inventory, sales = records()
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE mms_inventory_daily (analysis_date DATE, sku_id VARCHAR, available_stock DOUBLE, stock_unit VARCHAR, location_scope VARCHAR, snapshot_version VARCHAR, data_version VARCHAR, feature_as_of DATE, eligible BOOLEAN, features JSON)")
        connection.execute("INSERT INTO mms_inventory_daily VALUES (?, 'A', 30, 'tablet', 'pharmacy_total', 'fixture-v1', 'export-v1', ?, true, '{}')", [T, T])
        connection.execute("CREATE TABLE mms_sales_daily (sku_id VARCHAR, sales_date DATE, quantity DOUBLE, revenue DOUBLE)")
        connection.executemany("INSERT INTO mms_sales_daily VALUES (?, ?, ?, ?)",
                               [(s['sku_id'], s['sales_date'], s['quantity'], s['revenue']) for s in sales])
        provider = DuckDBDataProvider(connection)
        assert provider.get_snapshot(T) == MockDataProvider(inventory, sales).get_snapshot(T)
        with pytest.raises(MMSValidationError, match="snapshot"):
            provider.get_snapshot(T + timedelta(days=1))


@pytest.mark.parametrize("key,value", [("eligible", "false"), ("eligible", 1),
    ("days_since_last_receipt", -1), ("observed_stockout_days", -1),
    ("diagnostic_observed_days", 1.5)])
def test_optional_quality_fields_and_eligibility_are_strict(key, value):
    inventory, sales = records()
    inventory[0][key] = value
    with pytest.raises(MMSValidationError):
        MockDataProvider(inventory, sales).get_snapshot(T)


def test_missing_database_tables_are_service_validation_errors():
    with duckdb.connect() as connection:
        with pytest.raises(MMSValidationError, match="normalized"):
            DuckDBDataProvider(connection).get_snapshot(T)


def test_missing_database_file_is_service_validation_error(tmp_path):
    with pytest.raises(MMSValidationError, match="normalized"):
        DuckDBDataProvider(tmp_path / "missing.duckdb").get_snapshot(T)
