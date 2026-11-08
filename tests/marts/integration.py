"""Exercise compiled star-schema tests in a disposable ClickHouse database.

Run after the pinned dbt build: uv run --locked python tests/marts/integration.py
"""
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import clickhouse_connect

ROOT = Path(__file__).resolve().parents[2]


def main():
    source = os.environ.get('CLICKHOUSE_DB', 'inventory_dw')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', source):
        raise ValueError('Unsupported DW database name')
    manifest = json.loads((ROOT / 'transform/dbt/target/manifest.json').read_text())
    database = 'test_star_' + uuid4().hex[:12]
    client = clickhouse_connect.get_client(
        host=os.environ.get('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.environ.get('CLICKHOUSE_HTTP_PORT', '8123')),
        username=os.environ.get('CLICKHOUSE_USER', 'dbt'),
        password=os.environ.get('CLICKHOUSE_PASSWORD', 'dbt_local'),
    )

    def test_query(test_name, model, column=None):
        nodes = [node for node in manifest['nodes'].values()
                 if node['resource_type'] == 'test'
                 and node.get('test_metadata', {}).get('name') == test_name
                 and 'model.inventory_dw.' + model in node['depends_on']['nodes']
                 and (column is None or node.get('column_name') == column)]
        if len(nodes) != 1 or not nodes[0].get('compiled_code'):
            raise RuntimeError('Run the pinned full dbt build before this test: ' + test_name)
        return (nodes[0]['compiled_code']
                .replace(f'`{source}`', f'`{database}`')
                .replace(f"'{source}'", f"'{database}'"))

    def failures(test_name, model, column=None):
        return client.query(test_query(test_name, model, column)).row_count

    try:
        client.command(f'CREATE DATABASE `{database}` ENGINE = Atomic')
        for dimension in ('dim_product', 'dim_warehouse', 'dim_unit', 'dim_date'):
            client.command(f'CREATE TABLE `{database}`.{dimension} ENGINE = Memory AS '
                           f'SELECT * FROM `{source}`.{dimension}')
        client.command(f'''CREATE TABLE `{database}`.int_sales_quantity_converted ENGINE = Memory AS
            SELECT * FROM `{source}`.int_sales_quantity_converted
            WHERE sales_invoice_line_id IN (
                SELECT min(sales_invoice_line_id) FROM `{source}`.fct_sales_line
                WHERE conversion_status IN ('approved', 'candidate') AND verified_stock_unit_id != 0
                GROUP BY conversion_status
                UNION ALL SELECT min(sales_invoice_line_id) FROM `{source}`.fct_sales_line
                WHERE verified_stock_unit_id = 0)''')
        client.command(f'CREATE TABLE `{database}`.fct_sales_line ENGINE = Memory AS '
                       f'SELECT * FROM `{source}`.fct_sales_line WHERE sales_invoice_line_id IN '
                       f'(SELECT sales_invoice_line_id FROM `{database}`.int_sales_quantity_converted)')
        assert client.query(f'SELECT count() FROM `{database}`.fct_sales_line').first_row[0] == 3
        for name in ('matches_declared_schema', 'dimensional_join_cardinality', 'preserves_source_rows'):
            assert failures(name, 'fct_sales_line') == 0, name
        assert failures('relationships', 'fct_sales_line', 'product_id') == 0

        client.command(f'TRUNCATE TABLE `{database}`.dim_product')
        assert failures('relationships', 'fct_sales_line', 'product_id') == 3
        assert failures('dimensional_join_cardinality', 'fct_sales_line') == 0
        # An orphan is retained for diagnosis; referential acceptance rejects it.
        client.command(f'INSERT INTO `{database}`.dim_product SELECT * FROM `{source}`.dim_product')
        client.command(f'''INSERT INTO `{database}`.dim_product SELECT * FROM `{source}`.dim_product
            WHERE product_id IN (SELECT product_id FROM `{database}`.fct_sales_line)''')
        assert failures('unique', 'dim_product', 'product_id') > 0
        assert failures('dimensional_join_cardinality', 'fct_sales_line') == 3

        client.command(f'TRUNCATE TABLE `{database}`.dim_product')
        client.command(f'INSERT INTO `{database}`.dim_product SELECT * FROM `{source}`.dim_product')
        assert failures('not_null', 'fct_sales_line', 'verified_stock_unit_id') == 0
        assert failures('relationships', 'fct_sales_line', 'verified_stock_unit_id') == 0

        # The special member is required exactly once and cannot collide with source units.
        client.command(f'CREATE TABLE `{database}`.stg_units ENGINE = Memory AS '
                       f'SELECT * FROM `{source}`.stg_units')
        for fact in ('fct_inventory_movement', 'fct_inventory_daily_observed'):
            client.command(f'CREATE TABLE `{database}`.{fact} ENGINE = Memory AS '
                           f'SELECT * FROM `{source}`.{fact} LIMIT 0')
        special = next(node['compiled_code'] for node in manifest['nodes'].values()
                       if node['name'] == 'unit_special_member_contract')
        special = special.replace(f'`{source}`', f'`{database}`')
        assert client.query(special).row_count == 0
        client.command(f"INSERT INTO `{database}`.stg_units VALUES (0, 'Untrusted source unit')")
        assert client.query(special).row_count == 1
        client.command(f'TRUNCATE TABLE `{database}`.stg_units')
        client.command(f'INSERT INTO `{database}`.stg_units SELECT * FROM `{source}`.stg_units')
        client.command(f'INSERT INTO `{database}`.dim_unit SELECT * FROM `{source}`.dim_unit WHERE unit_id = 0')
        assert client.query(special).row_count == 1
        assert failures('dimensional_join_cardinality', 'fct_sales_line') > 0
        client.command(f'TRUNCATE TABLE `{database}`.dim_unit')
        client.command(f'INSERT INTO `{database}`.dim_unit SELECT * FROM `{source}`.dim_unit WHERE unit_id != 0')
        assert client.query(special).row_count == 1
        assert failures('relationships', 'fct_sales_line', 'verified_stock_unit_id') == 1
        client.command(f'INSERT INTO `{database}`.dim_unit SELECT * FROM `{source}`.dim_unit WHERE unit_id = 0')

        columns = client.query(f'DESCRIBE TABLE `{database}`.fct_sales_line').result_rows
        null_count = client.query(f'SELECT countIf(stock_unit_qty IS NULL) FROM `{database}`.int_sales_quantity_converted').first_row[0]
        projection = ', '.join(
            'ifNull(stock_unit_qty, toDecimal128(0, 12)) as stock_unit_qty'
            if column[0] == 'stock_unit_qty' else
            'ifNull(verified_stock_unit_id, toUInt32(0)) as verified_stock_unit_id'
            if column[0] == 'verified_stock_unit_id' else f'`{column[0]}`' for column in columns)
        client.command(f'TRUNCATE TABLE `{database}`.fct_sales_line')
        client.command(f'INSERT INTO `{database}`.fct_sales_line SELECT {projection} '
                       f'FROM `{database}`.int_sales_quantity_converted')
        assert failures('preserves_source_rows', 'fct_sales_line') == null_count

        # Neither a real verified unit changed to zero nor missing evidence changed to a real unit is valid.
        for replacement in ('toUInt32(0)', '(SELECT min(unit_id) FROM `' + database + '`.stg_units)'):
            projection = ', '.join(f'{replacement} AS verified_stock_unit_id'
                                   if column[0] == 'verified_stock_unit_id' else f'`{column[0]}`'
                                   for column in columns)
            client.command(f'TRUNCATE TABLE `{database}`.fct_sales_line')
            client.command(f'INSERT INTO `{database}`.fct_sales_line SELECT {projection} '
                           f'FROM `{database}`.int_sales_quantity_converted')
            assert failures('preserves_source_rows', 'fct_sales_line') > 0

        client.command(f'ALTER TABLE `{database}`.fct_sales_line ADD COLUMN warehouse_id UInt32')
        assert failures('matches_declared_schema', 'fct_sales_line') == 1
        print('PASS: valid joins/schema/exact FK projection; orphan, fan-out, reserved-key collision, missing/duplicate special member, fabricated FK/quantity and extra warehouse field rejected')
    finally:
        client.command(f'DROP DATABASE IF EXISTS `{database}` SYNC')
        client.close()


if __name__ == '__main__':
    main()
