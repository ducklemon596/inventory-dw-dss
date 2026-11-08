"""Exercise watermark loading and dbt in disposable PostgreSQL/ClickHouse databases.

Run from the repository root: uv run --locked python tests/extraction/integration.py
Requires the existing servers. Only the uniquely named test databases are modified.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
from uuid import uuid4

import clickhouse_connect
import psycopg
from psycopg import sql

from inventory_dw_dss import extraction as pipeline

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class FaultClient:
    """Inject failures around real ClickHouse operations, including lost replies."""
    def __init__(self, client, fault):
        self.client, self.fault, self.exchanges = client, fault, 0
        self.ambiguous_table = None

    def __getattr__(self, key):
        return getattr(self.client, key)

    def close(self):
        pass  # The test owns this connection.

    def insert(self, table, *args, **kwargs):
        if self.fault == 'insert' and table.endswith('.delta_sales_line'):
            raise RuntimeError('injected insert failure')
        return self.client.insert(table, *args, **kwargs)

    def query(self, query, *args, **kwargs):
        if self.fault == 'validation' and query.startswith('SELECT count(), uniqExact') and '.`delta_sales_line`' in query:
            raise RuntimeError('injected validation failure')
        return self.client.query(query, *args, **kwargs)

    def command(self, query, *args, **kwargs):
        if query.startswith('EXCHANGE TABLES'):
            self.exchanges += 1
            if self.exchanges == 2:
                if self.fault == 'publish':
                    raise RuntimeError('injected publication failure')
                if self.fault == 'ambiguous':
                    self.client.command(query, *args, **kwargs)
                    self.ambiguous_table = query
                    raise TimeoutError('injected lost exchange reply')
        return self.client.command(query, *args, **kwargs)


def main():
    suffix = uuid4().hex[:12]
    pgdb, rawdb, dwdb = (f'test_incremental_{label}_{suffix}' for label in ('pg', 'raw', 'dw'))
    connection = dict(host=os.environ.get('PGHOST', 'localhost'), port=int(os.environ.get('PGPORT', '5433')),
                      user=os.environ.get('PGUSER', 'inventory'), password=os.environ.get('PGPASSWORD', 'inventory_local'))
    admin = psycopg.connect(**connection, dbname=os.environ.get('PGDATABASE', 'inventory'), autocommit=True)
    client = clickhouse_connect.get_client(host=os.environ.get('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.environ.get('CLICKHOUSE_HTTP_PORT', '8123')), username=os.environ.get('CLICKHOUSE_USER', 'dbt'),
        password=os.environ.get('CLICKHOUSE_PASSWORD', 'dbt_local'))
    work_databases = set()
    try:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(pgdb)))
        with psycopg.connect(**connection, dbname=pgdb, autocommit=True) as source:
            with source.transaction():
                source.execute((ROOT / 'sql/oltp/schema.sql').read_text())
            for statement in (
                "INSERT INTO oltp.manufacturer(manufacturer_name) VALUES ('Maker')",
                "INSERT INTO oltp.drug_class(drug_class_name) VALUES ('Class')",
                "INSERT INTO oltp.category(category_name) VALUES ('Category'), ('Unused')",
                "INSERT INTO oltp.product(drug_code,drug_name,manufacturer_id,drug_class_id,category_id) VALUES ('0001','Drug',1,1,1)",
                "INSERT INTO oltp.unit(unit_code) VALUES ('Tab')",
                "INSERT INTO oltp.cashier(source_code) VALUES ('Cashier_001')",
                "INSERT INTO oltp.warehouse(warehouse_name) VALUES ('Pharmacy')",
                "INSERT INTO oltp.sales_invoice(invoice_number) VALUES ('INV001')",
                "INSERT INTO oltp.inventory_document(document_number) VALUES ('DOC001')",
                "INSERT INTO oltp.product_batch(product_id,batch_number) VALUES (1,'00001')",
            ):
                source.execute(statement)

            def sale(row, when):
                return source.execute('''INSERT INTO oltp.sales_line
                    (source_row_number,invoice_id,product_id,unit_id,cashier_id,sold_at,drug_name,quantity,unit_price,batch_id)
                    VALUES (%s,1,1,1,1,%s,'Drug',1.234567,12.345678,1) RETURNING sales_line_id''', (row, when)).fetchone()[0]

            def movement(row, when):
                source.execute('''INSERT INTO oltp.inventory_movement
                    (source_row_number,document_id,product_id,warehouse_id,occurred_at,drug_name,
                     initial_stock,stock_in,stock_out,remaining_stock,initial_unit_id,in_unit_id,out_unit_id,remaining_unit_id)
                    VALUES (%s,1,1,1,%s,'Drug',-1.234567,0,1,-2.234567,1,1,1,1)''', (row, when))

            first = sale(1, '2024-01-01 10:00:00.123456')
            boundary = sale(2, '2024-01-02 10:00:00.123456')
            movement(1, '2024-02-01 11:00:00.654321')
            with tempfile.TemporaryDirectory(prefix='inventory-incremental-test-') as temp, working_directory(temp), patch.dict(os.environ, {
                'PGDATABASE': pgdb, 'CLICKHOUSE_RAW_SCHEMA': rawdb, 'CLICKHOUSE_DB': dwdb,
            }):
                def run():
                    result = pipeline.extract_incremental(batch_size=1)
                    assert result['status'] == 'passed'
                    return result['tables']

                def fingerprint():
                    return [client.query(f'SELECT count(), groupBitXor(cityHash64(tuple(*))) FROM `{rawdb}`.`{t}`').first_row
                            for t in pipeline.TABLES]

                initial = run()
                assert initial['sales_line']['rows_read'] == 2 and initial['sales_line']['watermark'] is None
                assert initial['inventory_movement']['raw_rows'] == 1
                before = fingerprint()
                client.command(f'TRUNCATE TABLE `{rawdb}`.sales_line')
                client.command(f'TRUNCATE TABLE `{rawdb}`.inventory_movement')
                empty_raw = run()
                assert empty_raw['sales_line']['watermark'] is None and empty_raw['sales_line']['rows_read'] == 2
                assert empty_raw['inventory_movement']['watermark'] is None
                assert fingerprint() == before
                repeated = run()
                assert fingerprint() == before
                assert repeated['sales_line']['rows_read'] == 1 and repeated['sales_line']['new_keys'] == 0
                assert repeated['sales_line']['watermark'].endswith('123456')
                sale(3, '2024-01-02 10:00:00.123456')  # Equal watermark.
                sale(4, '2024-01-03 10:00:00.123456')  # Newer, but still earlier than movement watermark.
                source.execute('UPDATE oltp.sales_line SET unit_price=99 WHERE sales_line_id=%s', (boundary,))
                source.execute("UPDATE oltp.manufacturer SET manufacturer_name='Updated maker'")
                source.execute("UPDATE oltp.sales_invoice SET invoice_number='INV002'")
                source.execute("DELETE FROM oltp.category WHERE category_name='Unused'")
                movement(2, '2024-02-01 11:00:00.654321')
                changed = run()
                assert changed['sales_line']['new_keys'] == 2 and changed['sales_line']['reread_keys'] == 1
                assert changed['sales_line']['raw_rows'] == 4 and changed['inventory_movement']['raw_rows'] == 2
                assert client.query(f"SELECT unit_price FROM `{rawdb}`.sales_line WHERE sales_line_id = '{boundary}'").first_row[0] == '99'
                assert client.query(f'SELECT manufacturer_name FROM `{rawdb}`.manufacturer').first_row[0] == 'Updated maker'
                assert client.query(f'SELECT count() FROM `{rawdb}`.category').first_row[0] == 1
                assert client.query(f'SELECT invoice_number FROM `{rawdb}`.sales_invoice').first_row[0] == 'INV002'
                assert run()['sales_line']['raw_rows'] == 4

                # A second writer cannot extract against the same destination.
                source.execute('SELECT pg_advisory_lock(hashtextextended(%s,0))', (f'inventory_dw_dss.raw.{rawdb}',))
                try:
                    try:
                        run()
                        raise AssertionError('Concurrent writer was not blocked')
                    except RuntimeError as exc:
                        assert 'Another raw extraction' in str(exc)
                finally:
                    source.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', (f'inventory_dw_dss.raw.{rawdb}',))

                # Older inserts/updates and deletions are explicitly outside the watermark contract.
                late = sale(5, '2024-01-01 10:00:00.123456')
                source.execute('UPDATE oltp.sales_line SET unit_price=123 WHERE sales_line_id=%s', (first,))
                source.execute('DELETE FROM oltp.sales_line WHERE sales_line_id=%s', (first,))
                assert run()['sales_line']['raw_rows'] == 4
                assert client.query(f"SELECT count() FROM `{rawdb}`.sales_line WHERE sales_line_id='{late}'").first_row[0] == 0
                assert client.query(f"SELECT count() FROM `{rawdb}`.sales_line WHERE sales_line_id='{first}'").first_row[0] == 1

                # Make the next reference refresh visibly different, then fail before/during publication.
                source.execute("UPDATE oltp.manufacturer SET manufacturer_name='Unpublished maker'")
                before = fingerprint()
                original_fetch = psycopg.ServerCursor.fetchmany
                for fault in ('read', 'insert', 'validation', 'publish', 'ambiguous'):
                    proxy = FaultClient(client, fault)
                    def failing_fetch(cursor, *args, **kwargs):
                        if fault == 'read' and cursor.name == 'extract_sales_line':
                            raise RuntimeError('injected read failure')
                        return original_fetch(cursor, *args, **kwargs)
                    with patch.object(pipeline.clickhouse_connect, 'get_client', return_value=proxy), patch.object(psycopg.ServerCursor, 'fetchmany', failing_fetch):
                        try:
                            run()
                            raise AssertionError(f'{fault} did not fail')
                        except (RuntimeError, TimeoutError) as exc:
                            assert 'injected' in str(exc), str(exc)
                    report = json.loads(Path('reports/raw_extraction.json').read_text())
                    assert report['status'] == 'failed'
                    work = report['work_database']
                    if fault in ('publish', 'ambiguous'):
                        work_databases.add(work)
                        assert 'recovery_required' in report
                        assert client.query('SELECT count() FROM system.databases WHERE name={db:String}', parameters={'db':work}).first_row[0] == 1
                    else:
                        assert client.query('SELECT count() FROM system.databases WHERE name={db:String}', parameters={'db':work}).first_row[0] == 0
                    if fault == 'ambiguous':
                        # Undo the unacknowledged exchange only in our disposable test database.
                        client.command(proxy.ambiguous_table)
                    assert fingerprint() == before, fault
                run()
                source.execute("DELETE FROM oltp.sales_line WHERE sold_at >= '2024-01-03'")
                empty = run()['sales_line']
                assert empty['rows_read'] == 0 and not empty['publication_required'] and empty['raw_rows'] == 4

                # Build and execute actual dbt tests against these fixture raw tables.
                env = {**os.environ, 'DBT_PROFILES_DIR': str(ROOT / 'transform/dbt'),
                       'DBT_TARGET_PATH': f'{temp}/dbt-target', 'DBT_LOG_PATH': f'{temp}/dbt-logs'}
                subprocess.run(['uv', 'run', '--locked', '--directory', str(ROOT / 'transform/dbt'),
                                'dbt', 'build', '--select', 'path:models/staging',
                                '--exclude', 'path:tests/intermediate', 'path:tests/marts',
                                '--indirect-selection', 'cautious'], env=env, check=True)
                results = json.loads(Path(temp, 'dbt-target/run_results.json').read_text())['results']
                manifest = json.loads(Path(temp, 'dbt-target/manifest.json').read_text())
                # This command validates staging only, even as downstream layers grow.
                expected = {
                    key for key, node in manifest['nodes'].items()
                    if node['resource_type'] in ('model', 'test')
                    and node['original_file_path'].startswith(('models/staging/', 'tests/staging/'))
                }
                assert {r['unique_id'] for r in results} == expected
                assert all(r['status'] in ('pass', 'success') for r in results)
        print('PASS: initial load, rerun, independent watermarks, boundary updates, refresh, empty delta, failure recovery and dbt.')
    finally:
        for database in (dwdb, rawdb, *work_databases):
            client.command(f'DROP DATABASE IF EXISTS `{database}` SYNC')
        client.close()
        admin.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(pgdb)))
        admin.close()


if __name__ == '__main__':
    main()
