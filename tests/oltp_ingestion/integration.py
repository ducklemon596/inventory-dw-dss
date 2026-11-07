"""Explicit Docker integration check using a disposable database in the existing container.
Run: uv run --group bootstrap python tests/oltp_ingestion/integration.py
"""
import csv
from datetime import date
import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

import pandas as pd

from inventory_dw_dss.oltp_ingestion.loading import database, run_upsert, selected_inputs
from inventory_dw_dss.oltp_ingestion.preprocessing import RAW_COLUMNS, prepare

ROOT = Path(__file__).resolve().parents[2]


def sql(psql, statement):
    return subprocess.run(psql + ['-c', statement], check=True, text=True, capture_output=True).stdout.strip()


def main():
    checks = []
    with database(ROOT) as admin:
        name = 'inventory_test_' + uuid4().hex[:12]
        sql(admin, f'CREATE DATABASE {name}')
        psql = admin.copy()
        psql[psql.index('-d') + 1] = name
        try:
            with tempfile.TemporaryDirectory(prefix='inventory-test-') as temp:
                root = Path(temp)
                (root / 'data/raw').mkdir(parents=True)
                frames = {}
                for kind in ('sales', 'stock'):
                    with (Path(__file__).parent / 'fixtures' / f'{kind}_raw.csv').open(newline='') as handle:
                        first = next(csv.DictReader(handle))
                    rows = [first, {**first, 'RowNumber': '2', 'DateTime': '03 Jan 2023 09:00:00'}]
                    for row in rows:
                        row['DrugClass'] = 'TEST_CLASS'
                        row['Category'] = 'Patent'
                        if kind == 'sales':
                            row['Manufacturer'] = 'TEST_MANUFACTURER'
                    frames[kind] = pd.DataFrame(rows, columns=RAW_COLUMNS[kind], dtype='string')
                    frames[kind].to_csv(root / 'data/raw' / f'{kind}_raw.csv', index=False)
                prepare(root, chunksize=1)
                inputs = root / 'input'; inputs.mkdir()
                # Apply the complete schema, seed an older row, then run embedded catalog enrichment twice.
                sql(psql, (ROOT / 'sql/oltp/schema.sql').read_text())
                sql(psql, '''INSERT INTO oltp.product(drug_code) VALUES ('SW2106000281');
                INSERT INTO oltp.unit(unit_code) VALUES ('Fls');
                INSERT INTO oltp.cashier(source_code) VALUES ('Cashier_009');
                INSERT INTO oltp.sales_invoice(invoice_number) VALUES ('PJ2301020001');
                INSERT INTO oltp.sales_line(source_row_number,invoice_id,product_id,unit_id,cashier_id,sold_at,drug_name,manufacturer,drug_class,category,quantity,unit_price)
                VALUES (1,1,1,1,1,'2023-01-02 07:55:43','Fasidol Forte Syr 60ml','TEST_MANUFACTURER','TEST_CLASS','Patent',1,8000);
                DELETE FROM staging.schema_migration WHERE version='consolidated_catalog_backfill';''')
                sql(psql, (ROOT / 'sql/oltp/schema.sql').read_text())
                sql(psql, (ROOT / 'sql/oltp/schema.sql').read_text())
                assert sql(psql, "SELECT manufacturer_name FROM oltp.product JOIN oltp.manufacturer USING(manufacturer_id) WHERE drug_code='SW2106000281'") == 'TEST_MANUFACTURER'
                selected_inputs(root, '1mo', 'both', None, None, inputs)
                first = run_upsert(psql, ROOT, inputs)
                assert first['datasets']['sales']['updated'] == 1
                assert first['datasets']['stock']['inserted'] == 2
                assert sql(psql, 'SELECT sales_line_id FROM oltp.sales_line WHERE source_row_number=1') == '1'
                checks.append('complete schema is repeatable; upsert enriches existing row without changing PK')
                second = run_upsert(psql, ROOT, inputs)
                assert all(v['unchanged'] == 2 and v['inserted'] == v['updated'] == 0 for v in second['datasets'].values())
                checks.append('repeat upsert changes neither rows nor payload')
                assert sql(psql, """SELECT drug_name || ':' || manufacturer_name || ':' || drug_class_name || ':' || category_name
                    FROM oltp.product JOIN oltp.manufacturer USING(manufacturer_id)
                    JOIN oltp.drug_class USING(drug_class_id) JOIN oltp.category USING(category_id)
                    WHERE drug_code='SW2106000281'""") == 'Fasidol Forte Syr 60ml:TEST_MANUFACTURER:TEST_CLASS:Patent'
                assert sql(psql, 'SELECT count(*) FROM oltp.manufacturer') == '1'
                checks.append('catalog attributes resolve to deduplicated master FKs')
                conflict = pd.read_csv(inputs / 'sales.csv', dtype='string', keep_default_na=False)
                conflict.loc[0, 'Manufacturer'] = 'CONFLICTING_MANUFACTURER'
                conflict.to_csv(inputs / 'sales.csv', index=False)
                try:
                    run_upsert(psql, ROOT, inputs)
                    raise AssertionError('Expected conflicting product attributes to fail')
                except RuntimeError:
                    pass
                assert sql(psql, "SELECT count(*) FROM oltp.manufacturer WHERE manufacturer_name='CONFLICTING_MANUFACTURER'") == '0'
                selected_inputs(root, '1mo', 'both', None, None, inputs)
                checks.append('contradictory product labels reject load and roll back without arbitrary assignment')
                assert sql(psql, "SELECT count(*) FROM oltp.product_batch") == '1'
                # Re-prepare after modifying a source value, rather than editing checksummed partitions.
                frames['sales'].loc[0, 'Quantity'] = '9.0'
                frames['sales'].to_csv(root / 'data/raw/sales_raw.csv', index=False)
                prepare(root)
                selected_inputs(root, '1mo', 'sales', None, None, inputs)
                updated = run_upsert(psql, ROOT, inputs)
                assert updated['datasets']['sales']['updated'] == 1 and updated['datasets']['stock']['rows_read'] == 0
                assert sql(psql, "SELECT sales_line_id::text || ':' || quantity::text FROM oltp.sales_line WHERE source_row_number=1") == '1:9.0'
                checks.append('changed source updates payload and preserves identity; sales-only selection')
                selected_inputs(root, '1mo', 'stock', None, None, inputs)
                stock = run_upsert(psql, ROOT, inputs)
                assert stock['datasets']['sales']['rows_read'] == 0 and stock['datasets']['stock']['unchanged'] == 2
                checks.append('stock-only selection leaves sales unchanged')
                selected_inputs(root, '1mo', 'both', date(2023, 1, 3), date(2023, 1, 3), inputs)
                subset = run_upsert(psql, ROOT, inputs)
                assert all(v['rows_read'] == 1 and v['unchanged'] == 1 for v in subset['datasets'].values())
                checks.append('inclusive date filter inside monthly partition')
                # A late stock error must roll back a valid preceding sales update and new product.
                selected_inputs(root, '1mo', 'both', None, None, inputs)
                good = pd.read_csv(inputs / 'sales.csv', dtype='string', keep_default_na=False)
                good.loc[0, 'DrugCode'] = 'ROLLBACK_PRODUCT'
                good.loc[0, 'Quantity'] = '99'
                good.to_csv(inputs / 'sales.csv', index=False)
                bad = pd.read_csv(inputs / 'stock.csv', dtype='string', keep_default_na=False)
                bad.loc[0, 'remaining_stock_quantity'] = 'not-a-number'
                bad.to_csv(inputs / 'stock.csv', index=False)
                try:
                    run_upsert(psql, ROOT, inputs)
                    raise AssertionError('Expected rollback')
                except RuntimeError:
                    pass
                assert sql(psql, "SELECT count(*) FROM oltp.product WHERE drug_code='ROLLBACK_PRODUCT'") == '0'
                assert sql(psql, 'SELECT quantity FROM oltp.sales_line WHERE source_row_number=1') == '9.0'
                checks.append('late failure rolls back preceding sales changes and dimension insert')
                # DB, not just Python, enforces matching product/batch.
                sql(psql, "INSERT INTO oltp.product(drug_code) VALUES ('OTHER_PRODUCT')")
                invalid = subprocess.run(psql + ['-c', "UPDATE oltp.sales_line SET product_id=(SELECT product_id FROM oltp.product WHERE drug_code='OTHER_PRODUCT') WHERE source_row_number=1"], capture_output=True, text=True)
                assert invalid.returncode and 'sales_line_batch_product_fk' in invalid.stderr
                checks.append('composite FK rejects product/batch mismatch')
                # Overlapping RowNumber in a different source namespace remains independent.
                selected_inputs(root, '1mo', 'sales', None, None, inputs)
                other = run_upsert(psql, ROOT, inputs, source_dataset='fixture_second_source')
                assert other['datasets']['sales']['inserted'] == 2
                checks.append('source dataset namespaces prevent RowNumber collision')
                # A different partition interval still identifies the same rows.
                prepare(root, '1d')
                selected_inputs(root, '1d', 'both', None, None, inputs)
                overlap = run_upsert(psql, ROOT, inputs)
                assert all(v['unchanged'] == 2 for v in overlap['datasets'].values())
                checks.append('daily/monthly partition overlap reuses the same source keys')
                # A plain batch number has an unknown expiry, and must remain unique.
                frames['sales']['BatchAndExpiryDate'] = 'NO_EXPIRY'
                frames['sales'].to_csv(root / 'data/raw/sales_raw.csv', index=False)
                prepare(root)
                selected_inputs(root, '1mo', 'sales', None, None, inputs)
                run_upsert(psql, ROOT, inputs)
                run_upsert(psql, ROOT, inputs)
                assert sql(psql, "SELECT count(*) FROM oltp.product_batch WHERE batch_number='NO_EXPIRY' AND expiry_date IS NULL") == '1'
                checks.append('NULL expiry natural key does not duplicate batches on repeat')
            report = {'status': 'passed', 'checks': checks, 'isolated_database_removed': True}
            print(json.dumps(report, indent=2))
        finally:
            sql(admin, f'DROP DATABASE {name} WITH (FORCE)')


if __name__ == '__main__':
    main()
