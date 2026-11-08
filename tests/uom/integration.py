"""Exercise compiled conversion SQL against copies in a disposable ClickHouse DB.

uv run --locked python tests/uom/integration.py
No live OLTP, raw, reference seed or historical relations are modified.
"""
from pathlib import Path
import os
import subprocess
import tempfile
from uuid import uuid4

import clickhouse_connect
from clickhouse_connect.driver.exceptions import DatabaseError

ROOT = Path(__file__).resolve().parents[2]


def main():
    client = clickhouse_connect.get_client(
        host=os.environ.get('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.environ.get('CLICKHOUSE_HTTP_PORT', '8123')),
        username=os.environ.get('CLICKHOUSE_USER', 'dbt'),
        password=os.environ.get('CLICKHOUSE_PASSWORD', 'dbt_local'),
    )
    database = 'test_uom_' + uuid4().hex[:12]
    source = os.environ.get('CLICKHOUSE_DB', 'inventory_dw')
    if not source.replace('_', '').isalnum():
        raise ValueError('Unsupported DW database name')
    try:
        client.command(f'CREATE DATABASE `{database}` ENGINE = Atomic')
        client.command(f'''CREATE TABLE `{database}`.int_sales_lines_enriched ENGINE = Memory AS
            SELECT sales.* FROM `{source}`.int_sales_lines_enriched AS sales
            INNER JOIN `{source}`.uom_conversion_mapping AS mapping
                ON sales.product_code=mapping.product_id AND sales.unit_code=mapping.sales_unit
            WHERE mapping.mapping_version='uom_mapping_v2_2026-11-08'
                AND mapping.approval_status='approved' AND mapping.factor_approved>1
            LIMIT 1''')
        client.command(f'''CREATE TABLE `{database}`.int_product_stock_units ENGINE = Memory AS
            SELECT * FROM `{source}`.int_product_stock_units
            WHERE (dataset_name,product_id) IN (
                SELECT dataset_name,product_id FROM `{database}`.int_sales_lines_enriched)''')
        client.command(f'''CREATE TABLE `{database}`.uom_conversion_mapping ENGINE = Memory AS
            SELECT * FROM `{source}`.uom_conversion_mapping''')
        with tempfile.TemporaryDirectory(prefix='uom-integration-') as temp:
            env = {**os.environ, 'CLICKHOUSE_DB': database, 'DBT_TARGET_PATH': temp + '/target',
                   'DBT_LOG_PATH': temp + '/logs'}
            subprocess.run(['uv', 'run', '--locked', '--project', str(ROOT), 'dbt', 'compile',
                            '--select', 'int_sales_quantity_converted',
                            '--vars', '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}', '--project-dir', str(ROOT / 'transform/dbt'),
                            '--profiles-dir', str(ROOT / 'transform/dbt')], env=env, check=True)
            query = Path(temp, 'target/compiled/inventory_dw/models/intermediate/sales/int_sales_quantity_converted.sql').read_text()
            assert client.query(f'SELECT count() FROM `{database}`.int_sales_lines_enriched').first_row[0] == 1
            assert next(client.query(query).named_results())['conversion_status'] == 'approved'

            def must_reject(sql, message):
                try:
                    client.query(sql)
                except DatabaseError as error:
                    assert message in str(error), str(error)
                else:
                    raise AssertionError('Invalid mapping was accepted: ' + message)

            must_reject(query.replace("'uom_mapping_v2_2026-11-08'", "'uom_mapping_v999_2099-01-01'"),
                        'Selected UOM mapping version is not published')
            client.command(f'TRUNCATE TABLE `{database}`.uom_conversion_mapping')
            client.command(f'''INSERT INTO `{database}`.uom_conversion_mapping
                SELECT product_id,sales_unit,stock_unit,'B','candidate',NULL,toDecimal64(999,6),
                       n_supporting_invoices,share_at_mode,price_ratio,price_check_within_15pct,
                       evidence_source,mapping_version FROM `{source}`.uom_conversion_mapping''')
            row = next(client.query(query).named_results())
            assert row['conversion_status'] == 'candidate' and row['stock_unit_qty'] is None
            assert row['applied_conversion_factor'] is None

            client.command(f'TRUNCATE TABLE `{database}`.uom_conversion_mapping')
            client.command(f'INSERT INTO `{database}`.uom_conversion_mapping SELECT * FROM `{source}`.uom_conversion_mapping')
            # A contradictory identity must raise rather than override an explicit factor.
            client.command(f'TRUNCATE TABLE `{database}`.int_product_stock_units')
            client.command(f'''INSERT INTO `{database}`.int_product_stock_units
                SELECT dataset_name,product_id,product_code,toNullable(unit_id),unit_code,toUInt64(1),toUInt64(0)
                FROM `{database}`.int_sales_lines_enriched''')
            must_reject(query, 'Explicit UOM factor conflicts with verified identity')
        print('PASS: compiled SQL rejects unpublished versions/identity conflicts and never applies candidate factors')
    finally:
        client.command(f'DROP DATABASE IF EXISTS `{database}` SYNC')
        client.close()


if __name__ == '__main__':
    main()
