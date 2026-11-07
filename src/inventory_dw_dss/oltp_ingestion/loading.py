"""Select prepared partitions and upsert them transactionally into PostgreSQL."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

import pandas as pd

from .preprocessing import SCHEMA_VERSION, SOURCE_DATASET, checksum, columns_for, partition_lock


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@contextmanager
def database(root: Path):
    with tempfile.TemporaryDirectory(prefix='inventory-docker-') as config:
        Path(config, 'config.json').write_text('{}')
        base = ['docker', '--config', config, 'compose', '-p', 'inventory-dw-dss',
                '-f', str(root / 'infra/docker-compose.oltp.yml')]
        subprocess.run(base + ['up', '-d', '--wait'], check=True)
        yield base + ['exec', '-T', 'db', 'psql', '-X', '-qAt', '-U', 'inventory',
                      '-d', 'inventory', '-v', 'ON_ERROR_STOP=1']


def selected_inputs(root: Path, interval: str, dataset: str, start: date | None,
                    end: date | None, output: Path) -> tuple[dict, list[dict], dict[str, int]]:
    directory = root / 'data' / 'processed' / interval
    manifest_path = directory / 'manifest.json'
    if not manifest_path.is_file():
        raise ValueError(f'Missing prepared data. Run: uv run --group bootstrap inventory-dw-dss bootstrap prepare --interval {interval}')
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict):
        raise ValueError('Invalid manifest structure. Run prepare again.')
    if manifest.get('schema_version') != SCHEMA_VERSION or manifest.get('interval') != interval or manifest.get('source_dataset') != SOURCE_DATASET:
        raise ValueError('Incompatible manifest. Run prepare again.')
    if not isinstance(manifest.get('partitions'), list) or not isinstance(manifest.get('sources'), dict) or not isinstance(manifest.get('warnings'), dict):
        raise ValueError('Invalid manifest structure. Run prepare again.')
    selected = []
    counts = {'sales': 0, 'stock': 0}
    seen_files = set()
    for kind in ('sales', 'stock'):
        source = manifest['sources'].get(kind)
        if not isinstance(source, dict) or source.get('columns') != columns_for(kind):
            raise ValueError(f'{kind}: incompatible prepared column schema; run prepare again')
        # Even an unselected dataset gets an empty incoming table/file.
        pd.DataFrame(columns=columns_for(kind)).to_csv(output / f'{kind}.csv', index=False)
    for entry in manifest['partitions']:
        required = {'dataset', 'path', 'start', 'end', 'rows', 'sha256'}
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise ValueError('Incomplete partition manifest. Run prepare again.')
        if not all(isinstance(entry[key], str) for key in ('dataset', 'path', 'start', 'end', 'sha256')) or not isinstance(entry['rows'], int) or entry['rows'] < 1:
            raise ValueError('Invalid partition metadata. Run prepare again.')
        try:
            lower, upper = date.fromisoformat(entry['start']), date.fromisoformat(entry['end'])
        except ValueError as error:
            raise ValueError('Invalid partition date bounds') from error
        if lower > upper:
            raise ValueError('Reversed partition date bounds')
        kind = entry['dataset']
        if kind not in counts:
            raise ValueError('Unknown dataset in manifest')
        if dataset != 'both' and dataset != kind:
            continue
        if start and (entry['end'] < start.isoformat() or entry['start'] > end.isoformat()):
            continue
        path = (directory / entry['path']).resolve()
        if not path.is_relative_to(directory.resolve()) or path in seen_files:
            raise ValueError('Invalid/duplicate partition path in manifest')
        seen_files.add(path)
        if not path.is_file() or checksum(path) != entry['sha256']:
            raise ValueError(f'Partition missing/modified: {entry["path"]}. Run prepare again.')
        file_rows = kept = 0
        with pd.read_csv(path, dtype="string", keep_default_na=False, chunksize=100_000) as reader:
            for chunk in reader:
                if list(chunk.columns) != columns_for(kind):
                    raise ValueError(f'{path.name}: incompatible CSV header')
                file_rows += len(chunk)
                if start:
                    chunk = chunk[chunk['event_date'].between(start.isoformat(), end.isoformat())]
                if not chunk.empty:
                    chunk.to_csv(output / f'{kind}.csv', mode='a', index=False, header=False, lineterminator='\n')
                    kept += len(chunk)
        if file_rows != entry['rows']:
            raise ValueError(f'{path.name}: manifest row count mismatch')
        counts[kind] += kept
        selected.append({**entry, 'selected_rows': kept})
    if not sum(counts.values()):
        raise ValueError('No rows match the requested dataset/date range')
    return manifest, selected, counts


def transaction_prefix(root: Path, source_dataset: str = SOURCE_DATASET) -> str:
    text = "BEGIN;\nSET standard_conforming_strings = on;\nSET TIME ZONE 'UTC';\nSELECT pg_advisory_xact_lock(731906);\n"
    text += (root / 'sql/oltp/schema.sql').read_text() + '\n'
    text += f"SET LOCAL inventory.source_dataset = {literal(source_dataset)};\n"
    for kind in ('sales', 'stock'):
        cols = ', '.join('"' + col + '" text' for col in columns_for(kind))
        text += f'CREATE TEMP TABLE incoming_{kind} ({cols}) ON COMMIT DROP;\n'
    return text


def run_upsert(psql: list[str], root: Path, files: Path, *, source_dataset: str = SOURCE_DATASET) -> dict:
    """One all-or-nothing database transaction, also used by integration checks."""
    with tempfile.TemporaryFile() as stdout:
        process = subprocess.Popen(psql, stdin=subprocess.PIPE, stdout=stdout)
        assert process.stdin is not None
        try:
            process.stdin.write(transaction_prefix(root, source_dataset).encode())
            for kind in ('sales', 'stock'):
                process.stdin.write(f'COPY incoming_{kind} FROM STDIN WITH (FORMAT csv, HEADER true);\n'.encode())
                with (files / f'{kind}.csv').open('rb') as handle:
                    while chunk := handle.read(1024 * 1024):
                        process.stdin.write(chunk)
                process.stdin.write(b'\\.\n')
            process.stdin.write((root / 'sql/oltp/load.sql').read_bytes() + b'\n')
            process.stdin.write(b'COMMIT;\n')
            process.stdin.close()
            returncode = process.wait()
        except BaseException as error:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
            process.wait()
            raise RuntimeError('Load failed; database transaction rolled back') from error
        if returncode:
            raise RuntimeError('Load failed; database transaction rolled back')
        stdout.seek(0)
        lines = [line for line in stdout.read().decode().splitlines() if line.startswith('{')]
        if len(lines) != 1:
            raise RuntimeError('Database committed but did not return an unambiguous load report')
        return json.loads(lines[0])


def load(root: Path, interval: str, dataset: str, start: date | None, end: date | None) -> dict:
    with tempfile.TemporaryDirectory(prefix='inventory-load-') as temporary:
        directory = Path(temporary)
        # Hold a shared lock only while validating/copying partitions locally.
        with partition_lock(root, interval, exclusive=False):
            manifest, selected, counts = selected_inputs(root, interval, dataset, start, end, directory)
        print(f'Selected rows: {counts}', flush=True)
        with database(root) as psql:
            result = run_upsert(psql, root, directory)
    report = {'run_id': uuid4().hex, 'loaded_at_utc': datetime.now(timezone.utc).isoformat(),
              'schema_version': SCHEMA_VERSION, 'source_dataset': SOURCE_DATASET, 'interval': interval,
              'selection': {'dataset': dataset, 'from': start.isoformat() if start else None, 'to': end.isoformat() if end else None},
              'files': selected, 'preparation_warnings_all_source_rows': manifest['warnings'],
              'reconciliation': 'passed', **result}
    for kind, expected in counts.items():
        if result['datasets'][kind]['rows_read'] != expected:
            raise RuntimeError('Database committed but returned unexpected input row counts')
    reports = root / 'reports/oltp_ingestion'
    content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    try:
        reports.mkdir(parents=True, exist_ok=True)
        (reports / f'load_{report["run_id"]}.json').write_text(content)
        latest = reports / f'.load_summary.{report["run_id"]}.tmp'
        latest.write_text(content)
        latest.replace(reports / 'load_summary.json')
    except OSError as error:
        raise RuntimeError('Database committed successfully, but writing the load report failed') from error
    print(json.dumps({key: report[key] for key in ('run_id', 'datasets', 'totals', 'reconciliation')}, indent=2))
    return report
