"""Read-only validation of one POS export vintage across the existing pipeline.

Run from the repository root:
  uv run --locked python scripts/validation/validate_source_sequence.py \
    --passport data/reference/sequence_passport_v2.json --output /tmp/source-sequence-validation.json

No preprocessing, loading, dbt build, DDL or database writes are performed.
Only the optional local JSON result is written. Existing connection environment
variables are supported. Original CSVs are validation evidence, not DW inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import heapq
from itertools import groupby
import json
import os
from pathlib import Path
import re

import clickhouse_connect
import psycopg

ROOT = Path(__file__).resolve().parents[3]
LAYERS = ('csv', 'prepared', 'postgresql', 'raw', 'staging', 'intermediate')
MONTHS = {month: f'{i:02}' for i, month in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), 1)}
FIELDS = {
    'stock': ('movement_at', 'product_code', 'warehouse_name', 'transaction_description',
              'opening_stock_quantity', 'received_quantity', 'issued_quantity', 'closing_stock_quantity',
              'inventory_document_number', 'product_name', 'opening_unit', 'received_unit', 'issued_unit', 'closing_unit'),
    'sales': ('sold_at', 'sales_invoice_number', 'product_code', 'sold_quantity', 'unit_code'),
}


def identifier(value):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', value):
        raise ValueError(f'Unsupported SQL identifier: {value!r}')
    return f'"{value}"'


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def decimal_text(value):
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def timestamp(value):
    if isinstance(value, datetime):
        # Source timestamps are wall-clock values; never infer or convert a timezone.
        if value.tzinfo is not None:
            raise ValueError('Unexpected timezone-aware source event time')
        return value.isoformat(sep=' ', timespec='microseconds')
    return datetime.fromisoformat(value).isoformat(sep=' ', timespec='microseconds')


def csv_timestamp(value):
    day, month, year, clock = value.split()
    return f'{year}-{MONTHS[month]}-{day} {clock}.000000'


def stock_quantity(value):
    matched = re.fullmatch(r'([+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?)\s+(.+)', value.strip())
    if not matched:
        raise ValueError(f'Unsupported stock quantity: {value!r}')
    return Decimal(matched[1].replace('.', '').replace(',', '.')), matched[2].strip()


@dataclass
class Record:
    sequence: int
    payload: tuple
    identifiers: tuple = ()


def csv_records(path, kind, prepared=False):
    with path.open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            when = timestamp(row['event_datetime']) if prepared else csv_timestamp(row['DateTime'])
            if kind == 'stock':
                if prepared:
                    names = ('initial_stock', 'stock_in', 'stock_out', 'remaining_stock')
                    quantities = tuple(Decimal(row[f'{name}_quantity']) for name in names)
                    units = tuple(row[f'{name}_unit'] for name in names)
                else:
                    parts = [stock_quantity(row[name]) for name in ('InitialStock', 'StockIn', 'StockOut', 'RemainingStock')]
                    quantities, units = tuple(p[0] for p in parts), tuple(p[1] for p in parts)
                payload = (when, row['DrugCode'], row['Warehouse'], row['TransactionDescription'],
                           *quantities, row['DocumentNumber'], row['DrugName'], *units)
            else:
                payload = (when, row['InvoiceNumber'], row['DrugCode'], Decimal(row['Quantity'].replace(',', '.')), row['Unit'])
            yield Record(int(row['RowNumber']), payload)


def ordered(records):
    previous = None
    for record in records:
        if previous is not None and record.sequence < previous:
            raise ValueError(f'Input stream is not ordered by source sequence: {previous} -> {record.sequence}')
        previous = record.sequence
        yield record


def normalized_payload(payload):
    """Only the trimming/blank-to-NULL normalization used by staging text fields."""
    return tuple((value.strip() or None) if isinstance(value, str) and i else value
                 for i, value in enumerate(payload))


def passport_row(kind, record):
    # Passport product_id/warehouse_id are source business labels, not OLTP IDs.
    values = record.payload[:8] if kind == 'stock' else record.payload
    fields = []
    for i, value in enumerate(values):
        if i == 0:
            value = value[:19]  # ISO seconds, a space between date and clock.
        elif isinstance(value, Decimal):
            value = decimal_text(value)
        fields.append(' '.join(str(value or '').split()))
    return '|'.join(fields).encode('utf-8')


class Statistics:
    def __init__(self, kind):
        self.kind = kind
        self.rows = self.distinct = self.total = self.squares = 0
        self.minimum = self.maximum = None
        self.seq_digest, self.identity_digest = hashlib.md5(), hashlib.md5()
        self.content_hashes = bytearray()
        self.content_sum = 0
        self.missing = []
        self.duplicates = 0
        self.previous_sequence = None
        self.previous_time = None
        self.inversions = self.equal_time_pairs = 0
        self.ledgers = {}
        self.transitions = self.gaps = self.same_time_gaps = self.unit_changes = self.line_balance_errors = 0
        self.gap_patterns = Counter()
        self.gap_samples, self.other_gaps = [], []

    def add(self, record):
        seq, payload = record.sequence, record.payload
        if seq < 1:
            raise ValueError(f'Nonpositive source sequence: {seq}')
        if self.rows:
            self.identity_digest.update(b'\n')
        self.rows += 1
        self.total += seq
        self.squares += seq * seq
        self.minimum = seq if self.minimum is None else min(self.minimum, seq)
        self.maximum = seq if self.maximum is None else max(self.maximum, seq)
        if seq == self.previous_sequence:
            self.duplicates += 1
        else:
            if self.distinct:
                self.seq_digest.update(b',')
            self.seq_digest.update(str(seq).encode('ascii'))
            self.distinct += 1
            first_missing = 1 if self.previous_sequence is None else self.previous_sequence + 1
            if seq > first_missing:
                self.missing.append([first_missing, seq - 1])
        self.previous_sequence = seq
        digest = hashlib.md5(passport_row(self.kind, record)).digest()
        self.content_hashes.extend(digest)
        self.content_sum = (self.content_sum + int.from_bytes(digest[:8], 'big')) % (2**64)
        self.identity_digest.update(f'{seq}:{digest.hex()}'.encode('ascii'))
        when = payload[0]
        if self.previous_time is not None:
            self.inversions += when < self.previous_time
            self.equal_time_pairs += when == self.previous_time
        self.previous_time = when
        if self.kind == 'stock':
            key = (payload[1], payload[2])
            previous = self.ledgers.get(key)
            self.line_balance_errors += payload[4] + payload[5] - payload[6] != payload[7]
            if previous is not None:
                self.transitions += 1
                self.unit_changes += previous.payload[13] != payload[10]
                if previous.payload[7] != payload[4]:
                    self.gaps += 1
                    self.same_time_gaps += previous.payload[0] == when
                    before = 'stokopname' in (previous.payload[3] or '').lower()
                    after = 'stokopname' in (payload[3] or '').lower()
                    self.gap_patterns[f'previous_stocktake={before},current_stocktake={after}'] += 1
                    sample = dict(product_code=key[0], warehouse=key[1], previous_sequence=previous.sequence,
                                  sequence=seq, previous_time=previous.payload[0], movement_at=when,
                                  previous_closing=previous.payload[7], opening=payload[4], closing=payload[7],
                                  offset=payload[4] - previous.payload[7], previous_description=previous.payload[3],
                                  description=payload[3], document=payload[8])
                    if len(self.gap_samples) < 5:
                        self.gap_samples.append(sample)
                    if not (before and after) and len(self.other_gaps) < 10:
                        self.other_gaps.append(sample)
            self.ledgers[key] = record

    def result(self):
        hashes = sorted(set(bytes(self.content_hashes[i:i+16]) for i in range(0, len(self.content_hashes), 16)))
        digest = hashlib.md5()
        for i, value in enumerate(hashes):
            if i:
                digest.update(b',')
            digest.update(value.hex().encode('ascii'))
        result = dict(rows=self.rows, nonnull_sequence=self.rows, seq_distinct=self.distinct,
                      seq_min=self.minimum, seq_max=self.maximum, seq_sum=self.total, seq_sumsq=self.squares,
                      missing_sequence_ranges=self.missing, duplicate_sequence_rows=self.duplicates,
                      S1_seq_set_md5_sorted=self.seq_digest.hexdigest(), S2_content_multiset_sum64=self.content_sum,
                      S2_content_set_md5_sorted=digest.hexdigest(), S3_identity_ordered_md5=self.identity_digest.hexdigest(),
                      distinct_content_rows=len(hashes), timestamp_inversions=self.inversions,
                      adjacent_equal_timestamp_pairs=self.equal_time_pairs)
        if self.kind == 'stock':
            result['ledger'] = dict(series=len(self.ledgers), transitions=self.transitions,
                                    continuous=self.transitions-self.gaps, discontinuities=self.gaps,
                                    same_timestamp_discontinuities=self.same_time_gaps,
                                    discontinuity_rate=self.gaps/self.transitions if self.transitions else None,
                                    adjacent_unit_changes=self.unit_changes, line_balance_errors=self.line_balance_errors,
                                    gap_description_patterns=dict(self.gap_patterns), examples=self.gap_samples,
                                    other_discontinuities=self.other_gaps)
        return result


def postgres_query(kind):
    if kind == 'stock':
        return '''SELECT m.source_row_number,p.drug_code,w.warehouse_name,m.occurred_at,m.description,
            m.initial_stock,m.stock_in,m.stock_out,m.remaining_stock,d.document_number,m.drug_name,
            a.unit_code,b.unit_code,c.unit_code,e.unit_code,
            m.movement_id,m.product_id,m.warehouse_id,m.document_id,m.initial_unit_id,m.in_unit_id,m.out_unit_id,m.remaining_unit_id
            FROM oltp.inventory_movement m LEFT JOIN oltp.product p USING(product_id)
            LEFT JOIN oltp.warehouse w USING(warehouse_id) LEFT JOIN oltp.inventory_document d USING(document_id)
            LEFT JOIN oltp.unit a ON m.initial_unit_id=a.unit_id LEFT JOIN oltp.unit b ON m.in_unit_id=b.unit_id
            LEFT JOIN oltp.unit c ON m.out_unit_id=c.unit_id LEFT JOIN oltp.unit e ON m.remaining_unit_id=e.unit_id
            WHERE m.source_dataset=%s ORDER BY m.source_row_number'''
    return '''SELECT m.source_row_number,i.invoice_number,p.drug_code,m.sold_at,m.quantity,u.unit_code,
        m.sales_line_id,m.product_id,m.invoice_id,m.unit_id,m.cashier_id,m.batch_id
        FROM oltp.sales_line m LEFT JOIN oltp.product p USING(product_id)
        LEFT JOIN oltp.sales_invoice i USING(invoice_id) LEFT JOIN oltp.unit u USING(unit_id)
        WHERE m.source_dataset=%s ORDER BY m.source_row_number'''


def database_record(kind, values):
    if kind == 'stock':
        seq, product, warehouse, when, description, opening, received, issued, closing, document, name, *rest = values
        units, ids = rest[:4], rest[4:]
        payload = (timestamp(when),product,warehouse,description,*(Decimal(q) for q in (opening,received,issued,closing)),document,name,*units)
    else:
        seq, invoice, product, when, quantity, unit, *ids = values
        payload = (timestamp(when),invoice,product,Decimal(quantity),unit)
    return Record(int(seq), payload, tuple(int(value) if value is not None else None for value in ids))


def pg_records(pg, kind, dataset):
    with pg.cursor(name=f'validate_sequence_{kind}') as cursor:
        cursor.execute(postgres_query(kind), (dataset,))
        while rows := cursor.fetchmany(10_000):
            for row in rows:
                yield database_record(kind, row)


def clickhouse_query(kind, layer, raw_db, dw_db):
    raw, dw = identifier(raw_db), identifier(dw_db)
    if layer == 'raw':
        if kind == 'stock':
            return f'''SELECT m.source_row_number,p.drug_code,w.warehouse_name,m.occurred_at,m.description,
                m.initial_stock,m.stock_in,m.stock_out,m.remaining_stock,d.document_number,m.drug_name,
                a.unit_code,b.unit_code,c.unit_code,e.unit_code,
                m.movement_id,m.product_id,m.warehouse_id,m.document_id,m.initial_unit_id,m.in_unit_id,m.out_unit_id,m.remaining_unit_id
                FROM {raw}.inventory_movement m LEFT JOIN {raw}.product p ON m.product_id=p.product_id
                LEFT JOIN {raw}.warehouse w ON m.warehouse_id=w.warehouse_id
                LEFT JOIN {raw}.inventory_document d ON m.document_id=d.document_id
                LEFT JOIN {raw}.unit a ON m.initial_unit_id=a.unit_id LEFT JOIN {raw}.unit b ON m.in_unit_id=b.unit_id
                LEFT JOIN {raw}.unit c ON m.out_unit_id=c.unit_id LEFT JOIN {raw}.unit e ON m.remaining_unit_id=e.unit_id
                WHERE m.source_dataset={{dataset:String}} ORDER BY toUInt64(m.source_row_number) SETTINGS join_use_nulls=1'''
        return f'''SELECT m.source_row_number,i.invoice_number,p.drug_code,m.sold_at,m.quantity,u.unit_code,
            m.sales_line_id,m.product_id,m.invoice_id,m.unit_id,m.cashier_id,m.batch_id
            FROM {raw}.sales_line m LEFT JOIN {raw}.product p ON m.product_id=p.product_id
            LEFT JOIN {raw}.sales_invoice i ON m.invoice_id=i.invoice_id LEFT JOIN {raw}.unit u ON m.unit_id=u.unit_id
            WHERE m.source_dataset={{dataset:String}} ORDER BY toUInt64(m.source_row_number) SETTINGS join_use_nulls=1'''
    if layer == 'intermediate':
        if kind == 'stock':
            return f'''SELECT dataset_row_number,product_code,warehouse_name,movement_at,transaction_description,
                opening_stock_quantity,received_quantity,issued_quantity,closing_stock_quantity,
                inventory_document_number,product_name,opening_stock_unit_code,received_unit_code,issued_unit_code,closing_stock_unit_code,
                inventory_movement_id,product_id,warehouse_id,inventory_document_id,
                opening_stock_unit_id,received_unit_id,issued_unit_id,closing_stock_unit_id
                FROM {dw}.int_inventory_movements_enriched WHERE dataset_name={{dataset:String}}
                ORDER BY dataset_row_number'''
        return f'''SELECT dataset_row_number,sales_invoice_number,product_code,sold_at,sold_quantity,unit_code,
            sales_invoice_line_id,product_id,sales_invoice_id,unit_id,cashier_id,product_batch_id
            FROM {dw}.int_sales_lines_enriched WHERE dataset_name={{dataset:String}} ORDER BY dataset_row_number'''
    if kind == 'stock':
        table = 'stg_inventory_movements' if layer == 'staging' else 'int_inventory_movements_enriched'
        return f'''SELECT m.dataset_row_number,p.product_code,w.warehouse_name,m.movement_at,m.transaction_description,
            m.opening_stock_quantity,m.received_quantity,m.issued_quantity,m.closing_stock_quantity,
            d.inventory_document_number,m.product_name,a.unit_code,b.unit_code,c.unit_code,e.unit_code,
            m.inventory_movement_id,m.product_id,m.warehouse_id,m.inventory_document_id,
            m.opening_stock_unit_id,m.received_unit_id,m.issued_unit_id,m.closing_stock_unit_id
            FROM {dw}.{table} m LEFT JOIN {dw}.stg_products p ON m.product_id=p.product_id
            LEFT JOIN {dw}.stg_warehouses w ON m.warehouse_id=w.warehouse_id
            LEFT JOIN {dw}.stg_inventory_documents d ON m.inventory_document_id=d.inventory_document_id
            LEFT JOIN {dw}.stg_units a ON m.opening_stock_unit_id=a.unit_id LEFT JOIN {dw}.stg_units b ON m.received_unit_id=b.unit_id
            LEFT JOIN {dw}.stg_units c ON m.issued_unit_id=c.unit_id LEFT JOIN {dw}.stg_units e ON m.closing_stock_unit_id=e.unit_id
            WHERE m.dataset_name={{dataset:String}} ORDER BY m.dataset_row_number SETTINGS join_use_nulls=1'''
    table = 'stg_sales_invoice_lines' if layer == 'staging' else 'int_sales_lines_enriched'
    return f'''SELECT m.dataset_row_number,i.sales_invoice_number,p.product_code,m.sold_at,m.sold_quantity,u.unit_code,
        m.sales_invoice_line_id,m.product_id,m.sales_invoice_id,m.unit_id,m.cashier_id,m.product_batch_id
        FROM {dw}.{table} m LEFT JOIN {dw}.stg_products p ON m.product_id=p.product_id
        LEFT JOIN {dw}.stg_sales_invoices i ON m.sales_invoice_id=i.sales_invoice_id
        LEFT JOIN {dw}.stg_units u ON m.unit_id=u.unit_id
        WHERE m.dataset_name={{dataset:String}} ORDER BY m.dataset_row_number SETTINGS join_use_nulls=1'''


def ch_records(client, query, kind, dataset):
    with client.query_rows_stream(query, parameters={'dataset':dataset}) as stream:
        for row in stream:
            yield database_record(kind, row)


def compare_layers(kind, streams, expected):
    statistics = {layer:Statistics(kind) for layer in LAYERS}
    comparisons = {f'{a}->{b}':dict(missing_left=0,missing_right=0,mismatched_records=0,
                                   identifier_mismatches=0,field_mismatches=Counter(),examples=[])
                   for a,b in zip(LAYERS,LAYERS[1:])}
    def tagged(layer, stream):
        for record in ordered(stream):
            yield record.sequence, layer, record
    merged = heapq.merge(*(tagged(layer, stream) for layer,stream in streams.items()), key=lambda value:value[:2])
    for sequence, group in groupby(merged, key=lambda value:value[0]):
        records = {}
        for _,layer,record in group:
            statistics[layer].add(record)
            records.setdefault(layer,record)
        for left,right in zip(LAYERS,LAYERS[1:]):
            result = comparisons[f'{left}->{right}']
            a,b = records.get(left),records.get(right)
            if a is None:
                result['missing_left'] += b is not None
            elif b is None:
                result['missing_right'] += 1
            else:
                expected_payload = normalized_payload(a.payload) if right=='staging' else a.payload
                different = [field for field,x,y in zip(FIELDS[kind],expected_payload,b.payload,strict=True) if x!=y]
                ids_differ = bool(a.identifiers and b.identifiers and a.identifiers!=b.identifiers)
                result['mismatched_records'] += bool(different)
                result['identifier_mismatches'] += ids_differ
                result['field_mismatches'].update(different)
                if (different or ids_differ) and len(result['examples'])<5:
                    result['examples'].append(dict(sequence=sequence,fields=different,left=a.payload,right=b.payload,
                                                   left_ids=a.identifiers,right_ids=b.identifiers))
        if sequence % 100_000 == 0:
            print(f'{kind}: compared through source sequence {sequence:,}',flush=True)
    layers = {}
    baseline_fields = ('rows','seq_min','seq_max','seq_distinct','seq_sum','seq_sumsq',
                       'S1_seq_set_md5_sorted','S2_content_multiset_sum64','S2_content_set_md5_sorted','S3_identity_ordered_md5')
    for layer,statistic in statistics.items():
        result = statistic.result()
        result['passport_checks'] = {key:result[key]==expected[key] for key in baseline_fields}
        result['missing_from_expected_range'] = expected['rows']-result['seq_distinct'] if result['seq_min']==1 and result['seq_max']==expected['seq_max'] else None
        layers[layer] = result
        print(f'{kind}/{layer}: rows={result["rows"]:,}, passport={all(result["passport_checks"].values())}',flush=True)
    return dict(layers=layers,comparisons=comparisons)


def ordered_ledger_checks(client, database, dataset):
    table=f'{identifier(database)}.stg_inventory_movements'
    results={}
    for name,order in [('source_sequence','dataset_row_number'),('event_then_source','movement_at,dataset_row_number'),('event_then_identity','movement_at,inventory_movement_id')]:
        query=f'''SELECT countIf(previous_sequence!=0) AS transitions,
            countIf(previous_sequence!=0 AND opening_stock_quantity!=previous_closing) AS discontinuities,
            countIf(previous_sequence!=0 AND opening_stock_quantity!=previous_closing AND movement_at=previous_time) AS same_timestamp_discontinuities
            FROM (SELECT *,lagInFrame(dataset_row_number) OVER ledger AS previous_sequence,
                lagInFrame(closing_stock_quantity) OVER ledger AS previous_closing,
                lagInFrame(movement_at) OVER ledger AS previous_time
                FROM {table} WHERE dataset_name={{dataset:String}}
                WINDOW ledger AS (PARTITION BY product_id,warehouse_id ORDER BY {order} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW))'''
        results[name]=next(client.query(query,parameters={'dataset':dataset}).named_results())
    query=f'''SELECT count() AS rows,countIf(dataset_row_number=inventory_movement_id) AS equal_values,
        countIf(sequence_rank!=identity_rank) AS different_ledger_ranks,
        uniqExactIf(tuple(product_id,warehouse_id),sequence_rank!=identity_rank) AS affected_ledgers,
        countIf(source_predecessor!=identity_predecessor) AS different_predecessors,
        countIf(source_predecessor!=event_identity_predecessor) AS different_event_identity_predecessors
        FROM (SELECT product_id,warehouse_id,dataset_row_number,inventory_movement_id,
            row_number() OVER (PARTITION BY product_id,warehouse_id ORDER BY dataset_row_number) AS sequence_rank,
            row_number() OVER (PARTITION BY product_id,warehouse_id ORDER BY inventory_movement_id) AS identity_rank,
            lagInFrame(dataset_row_number) OVER (PARTITION BY product_id,warehouse_id ORDER BY dataset_row_number ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS source_predecessor,
            lagInFrame(dataset_row_number) OVER (PARTITION BY product_id,warehouse_id ORDER BY inventory_movement_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS identity_predecessor,
            lagInFrame(dataset_row_number) OVER (PARTITION BY product_id,warehouse_id ORDER BY movement_at,inventory_movement_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS event_identity_predecessor
            FROM {table} WHERE dataset_name={{dataset:String}})'''
    results['identifier_equivalence']=next(client.query(query,parameters={'dataset':dataset}).named_results())
    query=f'''SELECT count() AS tied_ledger_timestamp_groups,sum(n) AS rows_in_ties,
        countIf(balances>1) AS different_closing_groups
        FROM (SELECT product_id,warehouse_id,movement_at,count() AS n,uniqExact(closing_stock_quantity) AS balances
            FROM {table} WHERE dataset_name={{dataset:String}} GROUP BY product_id,warehouse_id,movement_at HAVING n>1)'''
    results['timestamp_ties']=next(client.query(query,parameters={'dataset':dataset}).named_results())
    results['daily_closing_conflicts']=daily_closing_checks(client,database,dataset)
    return results


def daily_closing_checks(client, database, dataset):
    """Diagnose tied final observations; do not build a daily inventory model."""
    table=f'{identifier(database)}.stg_inventory_movements'
    query=f'''WITH scoped AS (
        SELECT * FROM {table} WHERE dataset_name={{dataset:String}}
    ), following AS (
        SELECT dataset_row_number,closing_stock_quantity,
            leadInFrame(dataset_row_number,1,0) OVER ledger AS next_sequence,
            leadInFrame(opening_stock_quantity,1,toDecimal64(0,6)) OVER ledger AS next_opening
        FROM scoped WINDOW ledger AS (PARTITION BY product_id,warehouse_id ORDER BY dataset_row_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
    ), conflicts AS (
        SELECT product_id,warehouse_id,toDate32(movement_at) AS day,max(dataset_row_number) AS last_sequence
        FROM scoped WHERE (product_id,warehouse_id,movement_at) IN (
            SELECT product_id,warehouse_id,max(movement_at) FROM scoped
            GROUP BY product_id,warehouse_id,toDate32(movement_at))
        GROUP BY product_id,warehouse_id,day HAVING uniqExact(closing_stock_quantity)>1
    )
    SELECT count() AS latest_day_conflict_groups,countIf(next_sequence>0) AS with_next_observation,
        countIf(next_sequence=0) AS without_next_observation,
        countIf(next_sequence>0 AND closing_stock_quantity=next_opening) AS last_sequence_closing_matches_next,
        countIf(next_sequence>0 AND closing_stock_quantity!=next_opening) AS last_sequence_closing_mismatches_next
    FROM conflicts LEFT JOIN following ON conflicts.last_sequence=following.dataset_row_number'''
    result=next(client.query(query,parameters={'dataset':dataset}).named_results())
    result['observed_product_warehouse_dates']=client.query(f'''SELECT uniqExact(tuple(product_id,warehouse_id,toDate32(movement_at)))
        FROM {table} WHERE dataset_name={{dataset:String}}''',parameters={'dataset':dataset}).first_row[0]
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--passport',type=Path,default=ROOT/'data/reference/sequence_passport_v2.json')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--dataset-name',default='pharmacy_2023_2025')
    args=parser.parse_args()
    passport=json.loads(args.passport.read_text())
    if passport.get('version')!=2:
        raise ValueError('This validator implements the documented version-2 passport serialization')
    raw_db,dw_db=os.environ.get('CLICKHOUSE_RAW_SCHEMA','raw'),os.environ.get('CLICKHOUSE_DB','inventory_dw')
    identifier(raw_db),identifier(dw_db)
    manifest_path=ROOT/'data/processed/1mo/manifest.json'
    manifest=json.loads(manifest_path.read_text())
    if manifest['source_dataset']!=args.dataset_name:
        raise ValueError('Prepared manifest and requested dataset differ')
    report=dict(validated_at_utc=datetime.now(timezone.utc).isoformat(),dataset_name=args.dataset_name,
                passport_path=str(args.passport),passport_sha256=file_sha256(args.passport),datasets={})
    report['fingerprint_serialization']={
        'row':'UTF-8; passport field order; trim and collapse whitespace; ISO seconds with space; minimal decimal; pipe separator',
        'S1':'MD5 of sorted distinct integer sequences joined by comma; no trailing separator',
        'S2_sum64':'sum of first eight row-MD5 bytes interpreted big-endian, modulo 2^64',
        'S2_set':'MD5 of sorted distinct lowercase row-MD5 hex strings joined by comma; no trailing separator',
        'S3':'MD5 of sequence:row_MD5_hex lines in ascending sequence order, LF between lines; no final LF',
        'identifier_mapping':'passport product_id and warehouse_id map to DrugCode and Warehouse business labels, not generated OLTP IDs',
    }
    with psycopg.connect(host=os.environ.get('PGHOST','localhost'),port=int(os.environ.get('PGPORT','5433')),
                        dbname=os.environ.get('PGDATABASE','inventory'),user=os.environ.get('PGUSER','inventory'),
                        password=os.environ.get('PGPASSWORD','inventory_local'),options='-c default_transaction_read_only=on') as pg:
        pg.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        pg.execute("SET LOCAL DateStyle='ISO,YMD'")
        report['postgresql_snapshot']=pg.execute('SELECT pg_current_snapshot()::text').fetchone()[0]
        report['postgresql_read_only']=pg.execute('SHOW transaction_read_only').fetchone()[0]
        client=clickhouse_connect.get_client(host=os.environ.get('CLICKHOUSE_HOST','localhost'),port=int(os.environ.get('CLICKHOUSE_HTTP_PORT','8123')),
            username=os.environ.get('CLICKHOUSE_USER','dbt'),password=os.environ.get('CLICKHOUSE_PASSWORD','dbt_local'),
            autogenerate_session_id=False,
            # ClickHouse readonly=2 rejects writes while allowing SELECT settings,
            # including NULL-preserving joins. readonly=1 also forbids that setting.
            settings={'readonly':2,'max_execution_time':180,'max_block_size':10000})
        try:
            def raw_uuids():
                return client.query('SELECT name,toString(uuid) FROM system.tables WHERE database={database:String} ORDER BY name',parameters={'database':raw_db}).result_rows
            before=raw_uuids()
            for kind,key in [('stock','stock_inventory'),('sales','sales')]:
                source=ROOT/f'data/raw/{kind}_raw.csv'
                source_hash=file_sha256(source)
                entries=[p for p in manifest['partitions'] if p['dataset']==kind]
                paths=[manifest_path.parent/p['path'] for p in entries]
                if not entries or any(not path.resolve().is_relative_to(manifest_path.parent.resolve()) for path in paths):
                    raise ValueError('Missing or unsafe prepared partition paths')
                partition_checks=[file_sha256(path)==entry['sha256'] for path,entry in zip(paths,entries,strict=True)]
                if not all(partition_checks):
                    raise ValueError('A prepared partition differs from its existing manifest; no preparation was rerun')
                streams={'csv':csv_records(source,kind),
                         'prepared':heapq.merge(*(ordered(csv_records(path,kind,True)) for path in paths),key=lambda r:r.sequence),
                         'postgresql':pg_records(pg,kind,args.dataset_name)}
                streams.update({layer:ch_records(client,clickhouse_query(kind,layer,raw_db,dw_db),kind,args.dataset_name)
                                for layer in ('raw','staging','intermediate')})
                with ExitStack() as stack:
                    for stream in streams.values():
                        stack.callback(stream.close)
                    report['datasets'][kind]=compare_layers(kind,streams,passport[key])
                report['datasets'][kind]['files']=dict(source_sha256=source_hash,
                    source_matches_manifest=source_hash==manifest['sources'][kind]['sha256'],
                    source_unchanged_during_read=file_sha256(source)==source_hash,
                    prepared_partitions=len(entries),prepared_checksums_passed=sum(partition_checks),
                    manifest_source_path=manifest['sources'][kind]['path'],actual_source_path=str(source.relative_to(ROOT)))
            report['ordering']=ordered_ledger_checks(client,dw_db,args.dataset_name)
            report['raw_table_uuids_unchanged']=before==raw_uuids()
        finally:
            client.close()
    failed=[]
    for kind,dataset in report['datasets'].items():
        for layer,values in dataset['layers'].items():
            if not all(values['passport_checks'].values()) or values['duplicate_sequence_rows'] or values['missing_sequence_ranges'] or values['timestamp_inversions']:
                failed.append(f'{kind}/{layer}: passport, sequence or chronology')
        for hop,values in dataset['comparisons'].items():
            if any(values[key] for key in ('missing_left','missing_right','mismatched_records','identifier_mismatches')):
                failed.append(f'{kind}/{hop}: source record association')
        if not all(dataset['files'][key] for key in ('source_matches_manifest','source_unchanged_during_read')):
            failed.append(f'{kind}: source file changed or manifest scope differs')
    if not report['raw_table_uuids_unchanged']:
        failed.append('Raw tables were exchanged during validation')
    report['failed_checks']=failed
    source_ledger=report['datasets']['stock']['layers']['csv']['ledger']
    for layer,values in report['datasets']['stock']['layers'].items():
        ledger=values['ledger']
        if any(ledger[key]!=source_ledger[key] for key in ('series','transitions','continuous','discontinuities')):
            failed.append(f'stock/{layer}: ledger statistics differ from original CSV')
    for ordering in ('source_sequence','event_then_source'):
        if any(report['ordering'][ordering][key]!=source_ledger[key] for key in ('transitions','discontinuities')):
            failed.append(f'stock/{ordering}: SQL ledger statistics differ from original CSV')
    report['sequence_integrity']='PASS' if not failed else 'FAIL'
    report['scope']='This export vintage only; no native transaction order, CDC or incremental-watermark guarantee.'
    if args.output:
        args.output.write_text(json.dumps(report,default=str,indent=2)+'\n')
        print(f'Result: {report["sequence_integrity"]}. Local report: {args.output}',flush=True)
    else:
        print(json.dumps(report,default=str,indent=2))
    if failed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
