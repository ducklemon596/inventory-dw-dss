"""Load the repository's raw CSV files into its PostgreSQL container."""
import argparse
import csv
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['load'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    # Isolate the local deployment from host Docker credential helper settings.
    with tempfile.TemporaryDirectory(prefix='inventory-docker-') as config:
        Path(config, 'config.json').write_text('{}')
        base = ['docker', '--config', config, 'compose', '-p', 'inventory-dw-dss',
                '-f', str(root / 'compose.yaml')]
        subprocess.run(base + ['up', '-d', '--wait'], check=True)
        psql = base + ['exec', '-T', 'db', 'psql', '-X', '-U', 'inventory',
                       '-d', 'inventory', '-v', 'ON_ERROR_STOP=1']
        schema = (root / 'sql/001_schema.sql').read_bytes()
        transform = (root / 'sql/002_load.sql').read_bytes()
        process = subprocess.Popen(psql, stdin=subprocess.PIPE)
        assert process.stdin is not None
        try:
            process.stdin.write(b'BEGIN;\nSELECT pg_advisory_xact_lock(731906);\n')
            process.stdin.write(schema + b'\n')
            process.stdin.write(b'TRUNCATE staging.sales_raw, staging.stock_raw;\n')
            for name in ['sales', 'stock']:
                source = root / 'data' / f'{name}_raw.csv'
                with source.open(encoding='utf-8-sig', newline='') as handle:
                    columns = next(csv.reader(handle))
                quoted = ','.join('"' + col.replace('"', '""') + '"' for col in columns)
                process.stdin.write(
                    f'COPY staging.{name}_raw ({quoted}) FROM STDIN WITH (FORMAT csv, HEADER true);\n'.encode())
                print(f'Loading {source.name} ...', flush=True)
                ending = b''
                with source.open('rb') as handle:
                    while chunk := handle.read(1024 * 1024):
                        process.stdin.write(chunk)
                        ending = chunk[-2:]
                newline = b'\r\n' if ending.endswith(b'\r\n') else b'\n'
                if not ending.endswith(b'\n'):
                    process.stdin.write(newline)
                process.stdin.write(b'\\.' + newline)
            process.stdin.write(transform + b'\nCOMMIT;\n')
            process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError('Load failed; the database transaction was rolled back.')
        except BaseException:
            if not process.stdin.closed:
                process.stdin.close()
            process.wait()
            raise
        query = """SELECT json_build_object(
          'sales_raw', (SELECT count(*) FROM staging.sales_raw),
          'stock_raw', (SELECT count(*) FROM staging.stock_raw),
          'sales_lines', (SELECT count(*) FROM oltp.sales_line),
          'inventory_movements', (SELECT count(*) FROM oltp.inventory_movement),
          'products', (SELECT count(*) FROM oltp.product),
          'invoices', (SELECT count(*) FROM oltp.sales_invoice),
          'warehouses', (SELECT count(*) FROM oltp.warehouse));"""
        result = subprocess.run(psql + ['-At', '-c', query], check=True, capture_output=True, text=True)
        report = {'loaded_at_utc': datetime.now(timezone.utc).isoformat(),
                  'counts': json.loads(result.stdout)}
        output = root / 'reports' / 'load_summary.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
