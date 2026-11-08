"""Watermark-based extraction from PostgreSQL OLTP into ClickHouse raw.

Raw stores canonical PostgreSQL text and true NULLs. dbt owns analytical typing.
No CSV, pandas, bootstrap import, or write to OLTP is involved.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import clickhouse_connect
import psycopg
from psycopg import sql

TABLES = (
    'manufacturer', 'drug_class', 'category', 'product', 'warehouse', 'unit',
    'cashier', 'sales_invoice', 'product_batch', 'sales_line',
    'inventory_document', 'inventory_movement',
)

EVENT_TIMES = {'sales_line': 'sold_at', 'inventory_movement': 'occurred_at'}


def identifier(name: str) -> str:
    """Reject unsafe configured ClickHouse identifiers before quoting them."""
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
        raise ValueError(f'Unsupported database/table identifier: {name!r}')
    return f'`{name}`'


def publish(client, raw_db: str, work_db: str, completed: list[tuple[str, bool]],
            tables: list[str]) -> None:
    """Publish tables individually; caller must reverse completed steps on failure.

    EXCHANGE is atomic for each table, not for the whole set of 12 tables.
    Coordinate readers: run dbt only after extraction completes.
    """
    for table in tables:
        raw, work = f'{identifier(raw_db)}.{identifier(table)}', f'{identifier(work_db)}.{identifier(table)}'
        exists = bool(client.query('SELECT count() FROM system.tables WHERE database = {db:String} AND name = {table:String}',
                                   parameters={'db': raw_db, 'table': table}).first_row[0])
        client.command(f'EXCHANGE TABLES {raw} AND {work}' if exists else f'RENAME TABLE {work} TO {raw}')
        completed.append((table, exists))


def rollback_publication(client, raw_db: str, work_db: str, completed: list[tuple[str, bool]]) -> None:
    for table, existed in reversed(completed):
        raw, work = f'{identifier(raw_db)}.{identifier(table)}', f'{identifier(work_db)}.{identifier(table)}'
        client.command(f'EXCHANGE TABLES {raw} AND {work}' if existed else f'RENAME TABLE {raw} TO {work}')


def prepare_table(pg, client, raw_db, work_db, table, columns, keys, batch_size, *,
                  full=False, start=None, end=None):
    """Read a bounded source window and prepare one reconciled replacement table."""
    raw = f'{identifier(raw_db)}.{identifier(table)}'
    target = f'{identifier(work_db)}.{identifier(table)}'
    event_time = EVENT_TIMES.get(table)
    exists = bool(client.query('SELECT count() FROM system.tables WHERE database = {db:String} AND name = {table:String}',
                              parameters={'db': raw_db, 'table': table}).first_row[0])
    expected_types = [(c, 'Nullable(String)' if nullable == 'YES' else 'String') for c, nullable, _ in columns]
    fields = ', '.join(identifier(c) for c, _, _ in columns)
    key_sql = 'tuple(' + ', '.join(identifier(k) for k in keys) + ')'
    definitions = ', '.join(f'{identifier(c)} {typ}' for c, typ in expected_types)
    previous_count = 0
    if exists:
        actual_types = [(r[0], r[1]) for r in client.query(f'DESCRIBE TABLE {raw}').result_rows]
        if dict(actual_types) != dict(expected_types):
            raise RuntimeError(f'Raw schema differs from source for {table}; review the mapping before loading')
        previous_count, previous_unique = client.query(f'SELECT count(), uniqExact({key_sql}) FROM {raw}').first_row
        if previous_unique != previous_count:
            raise RuntimeError(f'Existing raw primary keys are not unique in {table}')
    watermark = None
    if event_time and previous_count and not full and start is None:
        watermark = client.query(f'SELECT maxOrNull(CAST({identifier(event_time)} AS DateTime64(6))) FROM {raw}').first_row[0]
        # PostgreSQL transaction columns represent wall-clock times without a timezone.
        watermark = watermark.replace(tzinfo=None)
    where = sql.SQL('')
    params = ()
    if event_time and start is not None:
        where = sql.SQL(' WHERE {} >= %s AND {} < %s').format(
            sql.Identifier(event_time), sql.Identifier(event_time))
        params = (datetime.combine(start, datetime.min.time()),
                  datetime.combine(end + timedelta(days=1), datetime.min.time()))
    elif watermark is not None:
        where = sql.SQL(' WHERE {} >= %s').format(sql.Identifier(event_time))
        params = (watermark,)
    delta_table = f'delta_{table}' if event_time else table
    delta = f'{identifier(work_db)}.{identifier(delta_table)}'
    client.command(f'CREATE TABLE {delta} ({definitions}) ENGINE = MergeTree ORDER BY {key_sql}')
    source_count = pg.execute(sql.SQL('SELECT count(*) FROM oltp.{}').format(sql.Identifier(table)) + where,
                              params).fetchone()[0]
    projection = sql.SQL(', ').join(sql.SQL('{}::text').format(sql.Identifier(c)) for c, _, _ in columns)
    read_count = 0
    with pg.cursor(name=f'extract_{table}') as cursor:
        cursor.execute(sql.SQL('SELECT {} FROM oltp.{}').format(projection, sql.Identifier(table)) + where, params)
        while rows := cursor.fetchmany(batch_size):
            client.insert(f'{work_db}.{delta_table}', rows, column_names=[c for c, _, _ in columns])
            read_count += len(rows)
    delta_count, delta_unique = client.query(f'SELECT count(), uniqExact({key_sql}) FROM {delta}').first_row
    if not source_count == read_count == delta_count == delta_unique:
        raise RuntimeError(f'Delta count/key reconciliation failed for {table}')
    overlap = client.query(f'SELECT count() FROM {delta} WHERE {key_sql} IN (SELECT {key_sql} FROM {raw})').first_row[0] if exists and delta_count else 0
    ready = True
    if event_time:
        if exists and not delta_count:
            ready = False
            final_count = previous_count
            final_unique = previous_count
        else:
            client.command(f'CREATE TABLE {target} ({definitions}) ENGINE = MergeTree ORDER BY {key_sql}')
            if exists:
                client.command(f'INSERT INTO {target} ({fields}) SELECT {fields} FROM {raw} '
                               f'WHERE {key_sql} NOT IN (SELECT {key_sql} FROM {delta})')
            client.command(f'INSERT INTO {target} ({fields}) SELECT {fields} FROM {delta}')
            final_count, final_unique = client.query(f'SELECT count(), uniqExact({key_sql}) FROM {target}').first_row
            if not final_count == final_unique == previous_count + delta_count - overlap:
                raise RuntimeError(f'Merged count/key reconciliation failed for {table}')
    else:
        final_count, final_unique = delta_count, delta_unique
    return {
        'mode': ('full' if full else 'range' if start is not None else 'incremental') if event_time else 'refresh',
        'watermark': watermark.isoformat(timespec='microseconds') if watermark else None,
        'watermark_column': event_time, 'selected_rows': source_count, 'rows_read': read_count,
        'new_keys': delta_count - overlap, 'reread_keys': overlap,
        'raw_rows_before': previous_count, 'raw_rows': final_count,
        'unique_primary_keys': final_unique, 'primary_key': keys,
        'reconciliation': 'passed', 'publication_required': ready,
        'columns': [{'name': c, 'postgres_type': typ,
                     'raw_type': 'Nullable(String)' if nullable == 'YES' else 'String'}
                    for c, nullable, typ in columns],
    }, ready


def load_raw(*, full: bool = False, start: date | None = None,
             end: date | None = None, batch_size: int = 20000) -> dict:
    if batch_size < 1:
        raise ValueError('batch_size must be positive')
    if full and (start is not None or end is not None):
        raise ValueError('full cannot be combined with start/end')
    if (start is None) != (end is None):
        raise ValueError('provide both start and end')
    if start is not None and start > end:
        raise ValueError('start must be on or before end')
    if end == date.max:
        raise ValueError('end must be before 9999-12-31')
    mode = 'full' if full else 'range' if start is not None else 'incremental'
    raw_db = os.environ.get('CLICKHOUSE_RAW_SCHEMA', 'raw')
    identifier(raw_db)
    if raw_db in {'system', 'information_schema', 'INFORMATION_SCHEMA', os.environ.get('CLICKHOUSE_DB', 'inventory_dw')}:
        raise ValueError('Raw database must be separate from system databases and the dbt destination')
    work_db = f'_extract_{uuid4().hex}'
    report_path = Path('reports/raw_extraction.json')
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'mode': mode,
              'selection': {'start': start.isoformat() if start else None, 'end': end.isoformat() if end else None},
              'raw_database': raw_db, 'work_database': work_db, 'status': 'failed',
              'batch_size': batch_size, 'tables': {}}
    client = None
    cleanup_allowed = True
    completed: list[tuple[str, bool]] = []
    prepared: list[str] = []
    try:
        client = clickhouse_connect.get_client(host=os.environ.get('CLICKHOUSE_HOST', 'localhost'),
            port=int(os.environ.get('CLICKHOUSE_HTTP_PORT', '8123')),
            username=os.environ.get('CLICKHOUSE_USER', 'dbt'),
            password=os.environ.get('CLICKHOUSE_PASSWORD', 'dbt_local'))
        # PostgreSQL libpq environment variables are standard, including PGPASSWORD.
        with psycopg.connect(host=os.environ.get('PGHOST', 'localhost'),
                port=int(os.environ.get('PGPORT', '5433')), dbname=os.environ.get('PGDATABASE', 'inventory'),
                user=os.environ.get('PGUSER', 'inventory'), password=os.environ.get('PGPASSWORD', 'inventory_local'),
                autocommit=True) as pg:
            # Session lock serializes this pipeline's writers for a raw destination.
            locked = pg.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
                                (f'inventory_dw_dss.raw.{raw_db}',)).fetchone()[0]
            if not locked:
                raise RuntimeError('Another raw extraction is running for this destination')
            client.command(f'CREATE DATABASE IF NOT EXISTS {identifier(raw_db)} ENGINE = Atomic')
            engine = client.query('SELECT engine FROM system.databases WHERE name = {db:String}',
                                  parameters={'db': raw_db}).first_row[0]
            if engine != 'Atomic':
                raise RuntimeError(f'{raw_db} must use the Atomic database engine')
            client.command(f'CREATE DATABASE {identifier(work_db)} ENGINE = Atomic')
            with pg.transaction():
                pg.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                pg.execute("SET LOCAL DateStyle = 'ISO, YMD'")
                pg.execute("SET LOCAL TIME ZONE 'UTC'")
                report['source_snapshot'] = pg.execute('SELECT pg_current_snapshot()::text').fetchone()[0]
                for table in TABLES:
                    columns = pg.execute('''SELECT column_name, is_nullable, data_type
                        FROM information_schema.columns WHERE table_schema = 'oltp' AND table_name = %s
                        ORDER BY ordinal_position''', (table,)).fetchall()
                    if not columns:
                        raise RuntimeError(f'Missing source table oltp.{table}')
                    keys = [r[0] for r in pg.execute('''SELECT a.attname FROM pg_index i
                        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                        WHERE i.indrelid = %s::regclass AND i.indisprimary ORDER BY a.attnum''',
                        (f'oltp.{table}',)).fetchall()]
                    if not keys:
                        raise RuntimeError(f'No verified primary key for oltp.{table}')
                    result, ready = prepare_table(pg, client, raw_db, work_db, table,
                                                  columns, keys, batch_size, full=full, start=start, end=end)
                    report['tables'][table] = result
                    if ready:
                        prepared.append(table)
                    print(f"{table}: read={result['rows_read']:,}, new={result['new_keys']:,}, "
                          f"reread={result['reread_keys']:,}, raw={result['raw_rows']:,}", flush=True)
            # Leave the PostgreSQL snapshot transaction before publishing; retain session lock.
            # Keep old tables in work_db until all exchanges have succeeded.
            cleanup_allowed = False
            try:
                publish(client, raw_db, work_db, completed, prepared)
            except Exception:
                rollback_publication(client, raw_db, work_db, completed)
                # A timed-out exchange may have executed despite a missing reply.
                # Retain work tables even after reversing all acknowledged steps.
                report['acknowledged_publications_rolled_back'] = True
                raise
            cleanup_allowed = True
            report['status'] = 'passed'
    except Exception as exc:
        report['error'] = str(exc)
        if not cleanup_allowed:
            report['recovery_required'] = f'Inspect {work_db}; previous tables retained. Completed exchanges: {completed}'
        raise
    finally:
        if client is not None:
            try:
                if cleanup_allowed:
                    client.command(f'DROP DATABASE IF EXISTS {identifier(work_db)} SYNC')
            except Exception as exc:
                report['cleanup_warning'] = str(exc)
            finally:
                client.close()
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Published {len(prepared)} tables to {raw_db}. Report: {report_path}', flush=True)
    return report
