"""Reconcile historical inventory with the verified export, using SELECT only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import clickhouse_connect

from .source_sequence import (
    ROOT, Statistics, ch_records, clickhouse_query, file_sha256, identifier,
)


def collect_metrics(client, database: str, dataset: str) -> dict:
    """Collect scoped measures and physical costs without creating audit relations."""
    database = identifier(database)
    queries = {
        'ledger': '''SELECT count() AS movements,
            uniqExact(tuple(product_id, warehouse_id)) AS ledgers,
            countIf(NOT is_ledger_start) AS transitions,
            countIf(is_continuous) AS continuous, countIf(is_discontinuity) AS gaps
            FROM {db}.int_inventory_ledger_ordered WHERE dataset_name={{dataset:String}}''',
        'segments': '''SELECT count() AS movements, uniqExact(segment_id) AS segments,
            countIf(is_ledger_start) AS initial_segments,
            countIf(is_discontinuity) AS additional_segments,
            countIf(reconstructed_closing_quantity != closing_stock_quantity) AS reconstruction_errors
            FROM {db}.int_inventory_segments WHERE dataset_name={{dataset:String}}''',
        'movement': '''SELECT count() AS movements, uniqExact(inventory_movement_id) AS distinct_ids,
            countIf(is_unknown_movement) AS unknown_movements,
            countIf(transaction_type='RETURN' AND received_quantity>0) AS inbound_returns,
            countIf(transaction_type='RETURN' AND issued_quantity>0) AS outbound_returns,
            countIf(has_negative_closing_stock) AS negative_closings,
            countIf(received_quantity=0 AND issued_quantity=0) AS zero_flow
            FROM {db}.fct_inventory_movement WHERE dataset_name={{dataset:String}}''',
        'daily': '''SELECT count() AS observations,
            uniqExact(tuple(product_id, warehouse_id, observation_date)) AS distinct_grains,
            sum(movement_count) AS movements,
            countIf(has_ambiguous_latest_timestamp) AS ambiguous_latest_timestamp_days,
            countIf(has_negative_closing_stock) AS negative_closing_days,
            sum(discontinuity_count) AS gaps
            FROM {db}.fct_inventory_daily_observed WHERE dataset_name={{dataset:String}}''',
    }
    result = {
        name: next(client.query(query.format(db=database), parameters={'dataset': dataset}).named_results())
        for name, query in queries.items()
    }
    result['diagnostics'] = list(client.query(f'''
        SELECT diagnostic_class, count() AS gaps
        FROM {database}.diag_inventory_ledger_discontinuities
        WHERE dataset_name={{dataset:String}}
        GROUP BY diagnostic_class ORDER BY diagnostic_class
    ''', parameters={'dataset': dataset}).named_results())
    result['storage'] = list(client.query('''
        SELECT table, sum(rows) AS rows, sum(bytes_on_disk) AS bytes_on_disk
        FROM system.parts WHERE database={database:String} AND active
        AND table IN ('int_inventory_ledger_ordered', 'int_inventory_segments',
                      'fct_inventory_movement', 'fct_inventory_daily_observed')
        GROUP BY table ORDER BY table
    ''', parameters={'database': database.strip('"')}).named_results())
    # Compare flows per unit; quantities in different units are never pooled.
    result['flows_by_unit'] = {}
    for name, table, unit, received, issued in (
        ('movement', 'fct_inventory_movement', 'closing_stock_unit_id', 'received_quantity', 'issued_quantity'),
        ('daily', 'fct_inventory_daily_observed', 'stock_unit_id', 'recorded_received_quantity', 'recorded_issued_quantity'),
    ):
        result['flows_by_unit'][name] = list(client.query(f'''
            SELECT {unit} AS stock_unit_id, sum({received}) AS receipts,
                sum({issued}) AS issues, sum(recorded_delta_qty) AS delta
            FROM {database}.{table} WHERE dataset_name={{dataset:String}}
            GROUP BY {unit} ORDER BY {unit}
        ''', parameters={'dataset': dataset}).named_results())
    return result


def reconciliation_checks(metrics: dict, source: dict, baseline: dict) -> dict:
    """Snapshot expectations are inputs from the passport, never universal tests."""
    ledger, segments = metrics['ledger'], metrics['segments']
    movement, daily = metrics['movement'], metrics['daily']
    flows = metrics['flows_by_unit']
    return {
        'all_movements_preserved': all(m['movements'] == source['rows'] for m in (ledger, segments, movement, daily)),
        'movement_ids_unique': movement['distinct_ids'] == movement['movements'],
        'ledger_count_matches_source': ledger['ledgers'] == source['ledger']['series'],
        'transitions_match_source': ledger['transitions'] == source['ledger']['transitions'],
        'gaps_match_source': ledger['gaps'] == source['ledger']['discontinuities'],
        'continuous_match_source': ledger['continuous'] == source['ledger']['continuous'],
        'one_anchor_per_segment': segments['segments'] == segments['initial_segments'] + segments['additional_segments'],
        'segments_match_snapshot': segments['segments'] == baseline['segments'],
        'exact_segment_reconstruction': segments['reconstruction_errors'] == 0,
        'daily_grains_unique': daily['observations'] == daily['distinct_grains'],
        'daily_rows_match_snapshot': daily['observations'] == baseline['fct_inventory_daily_observed_rows'],
        'diagnostics_cover_gaps': sum(d['gaps'] for d in metrics['diagnostics']) == ledger['gaps'] == daily['gaps'],
        'daily_flows_reconcile': flows['daily'] == flows['movement'],
        'flow_direction_preserved': all(row['delta'] == row['receipts'] - row['issues'] for row in flows['movement']),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--passport', type=Path, default=ROOT / 'data/reference/sequence_passport_v2.json')
    parser.add_argument('--dataset-name', default='pharmacy_2023_2025')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    passport = json.loads(args.passport.read_text())
    if passport.get('version') != 2:
        parser.error('A verified version-2 export passport is required')
    database = os.environ.get('CLICKHOUSE_DB', 'inventory_dw')
    raw = os.environ.get('CLICKHOUSE_RAW_SCHEMA', 'raw')
    client = clickhouse_connect.get_client(
        host=os.environ.get('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.environ.get('CLICKHOUSE_HTTP_PORT', '8123')),
        username=os.environ.get('CLICKHOUSE_USER', 'dbt'),
        password=os.environ.get('CLICKHOUSE_PASSWORD', 'dbt_local'),
        settings={'readonly': 2, 'max_execution_time': 180},
    )
    try:
        statistics = Statistics('stock')
        for record in ch_records(client, clickhouse_query('stock', 'staging', raw, database), 'stock', args.dataset_name):
            statistics.add(record)
        source = statistics.result()
        fingerprint_checks = {
            key: source[key] == expected
            for key, expected in passport['stock_inventory'].items() if key != 'row_field_order'
        }
        if not all(fingerprint_checks.values()):
            raise ValueError('Current stock differs from the passport vintage; investigate before comparing snapshot baselines')
        metrics = collect_metrics(client, database, args.dataset_name)
        checks = reconciliation_checks(metrics, source, passport['checkpoint2_baselines_snapshot'])
    finally:
        client.close()
    report = {
        'validated_at_utc': datetime.now(timezone.utc).isoformat(),
        'dataset_name': args.dataset_name,
        'passport_sha256': file_sha256(args.passport),
        'source_fingerprint_checks': fingerprint_checks,
        'metrics': metrics,
        'checks': checks,
        'status': 'PASS' if all(checks.values()) else 'FAIL',
        'scope': 'Verified export only. Internal segment reconciliation does not certify physical or available stock.',
    }
    text = json.dumps(report, default=str, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        print(f'{report["status"]}: {args.output}')
    else:
        print(text, end='')
    if report['status'] != 'PASS':
        raise SystemExit(1)
