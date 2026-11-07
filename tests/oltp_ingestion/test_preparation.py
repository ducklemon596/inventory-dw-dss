import csv
from collections import Counter
from datetime import date
import json
import contextlib
import io
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from inventory_dw_dss.oltp_ingestion.loading import selected_inputs
from inventory_dw_dss.oltp_ingestion.preprocessing import RAW_COLUMNS, checksum, period_bounds, prepare, transform


def sample(dataset):
    with (Path(__file__).parent / 'fixtures' / f'{dataset}_raw.csv').open(newline='') as f:
        return next(csv.DictReader(f))


def frame(dataset, **changes):
    return pd.DataFrame([{**sample(dataset), **changes}], columns=RAW_COLUMNS[dataset], dtype='string')


class ParsingTests(unittest.TestCase):
    def test_shift_batch_and_percent(self):
        out = transform(frame('sales', Shift='20230102-Pagi-Cashier_009', DiscountPct='2,86%'), 'sales')
        self.assertEqual(out.loc[0, 'shift_period'], 'PAGI')
        self.assertEqual(out.loc[0, 'batch_number'], '20229')
        self.assertEqual(out.loc[0, 'expiry_date'], '2024-09-01')
        self.assertEqual(out.loc[0, 'discount_pct_value'], '2.86')
        self.assertEqual(out.loc[0, 'BatchAndExpiryDate'], sample('sales')['BatchAndExpiryDate'])

    def test_optional_errors_preserve_rows(self):
        warnings = Counter()
        out = transform(frame('sales', Shift='?', BatchAndExpiryDate='ABC (ED : bad)', DiscountPct='bad'), 'sales', warnings)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.loc[0, 'batch_number'], '')
        self.assertEqual(out.loc[0, 'shift_period'], '')
        self.assertEqual(warnings['batch_unparsed'], 1)
        self.assertEqual(warnings['shift_unparsed'], 1)
        self.assertEqual(warnings['discount_pct_value_unparsed'], 1)
        self.assertEqual(transform(frame('sales', BatchAndExpiryDate=''), 'sales').loc[0, 'batch_number'], '')
        self.assertEqual(transform(frame('sales', BatchAndExpiryDate='LOT01'), 'sales').loc[0, 'batch_number'], 'LOT01')

    def test_stock_signed_thousands_and_decimal(self):
        out = transform(frame('stock', InitialStock='-1.260,5 Tab', RemainingStock='-1.261,5 Tab'), 'stock')
        self.assertEqual(out.loc[0, 'initial_stock_quantity'], '-1260.5')
        self.assertEqual(out.loc[0, 'initial_stock_unit'], 'Tab')
        self.assertEqual(out.loc[0, 'remaining_stock_quantity'], '-1261.5')

    def test_transaction_rules(self):
        cases = {
            'Penjualan dengan No Faktur :PJ001,Pasien :Patient_002': 'SALE',
            'Pembelian Dari Supplier PT dengan no faktur :INV001': 'PURCHASE',
            'MUTASI ANTAR GUDANG': 'TRANSFER', 'mts': 'TRANSFER', 'm': 'TRANSFER',
            'Import Stokopname': 'IMPORT_STOCKTAKE', 'Stokopname': 'STOCKTAKE',
            'Import Data Obat': 'IMPORT_PRODUCT', 'Tambah Master Obat': 'CREATE_PRODUCT',
            'Retur': 'RETURN', 'Test Entry': 'TEST_ENTRY', 'unfamiliar note': 'UNKNOWN',
        }
        for description, expected in cases.items():
            out = transform(frame('stock', TransactionDescription=description), 'stock')
            self.assertEqual(out.loc[0, 'transaction_type'], expected)
        out = transform(frame('stock', TransactionDescription='Pembelian Dari Supplier PT dengan no faktur :INV001'), 'stock')
        self.assertEqual(out.loc[0, 'supplier_name'], 'Supplier PT')
        self.assertEqual(out.loc[0, 'referenced_invoice_number'], 'INV001')

    def test_required_errors(self):
        for change in [{'DateTime': 'bad'}, {'RowNumber': ''}, {'Quantity': 'x'}, {'DrugCode': ''}]:
            with self.assertRaises(ValueError):
                transform(frame('sales', **change), 'sales')
        with self.assertRaises(ValueError):
            transform(frame('stock', StockIn='1.2 Tab'), 'stock')

    def test_cli_rejects_ambiguous_selection(self):
        from inventory_dw_dss.oltp_ingestion.cli import main
        for argv in [
            ['oltp-bootstrap', 'load'],
            ['oltp-bootstrap', 'load', '--from', '2023-01-01'],
            ['oltp-bootstrap', 'load', '--all', '--from', '2023-01-01'],
            ['oltp-bootstrap', 'load', '--from', '2023-02-01', '--to', '2023-01-01'],
        ]:
            with patch('sys.argv', argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)

    def test_boundaries(self):
        dates = pd.Series(['2023-01-01', '2023-01-02', '2024-02-29', '2024-03-01'])
        start, end = period_bounds(dates, '1mo')
        self.assertEqual(end.tolist(), ['2023-01-31', '2023-01-31', '2024-02-29', '2024-03-31'])
        start, end = period_bounds(dates, '1w')
        self.assertEqual((start[0], end[0]), ('2022-12-26', '2023-01-01'))
        self.assertEqual((start[1], end[1]), ('2023-01-02', '2023-01-08'))
        start, end = period_bounds(pd.Series(['2023-01-01', '2023-01-03', '2023-01-04']), '3d')
        self.assertEqual(start.tolist(), ['2023-01-01', '2023-01-01', '2023-01-04'])
        start, end = period_bounds(dates, '1d')
        self.assertEqual(start.tolist(), dates.tolist())
        self.assertEqual(start.tolist(), end.tolist())


class FilePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'data/raw').mkdir(parents=True)
        for dataset in ('sales', 'stock'):
            rows = []
            for number, timestamp in [(3, '01 Feb 2023 08:00:00'), (2, '03 Jan 2023 08:00:00'), (1, '02 Jan 2023 08:00:00')]:
                rows.append({**sample(dataset), 'RowNumber': str(number), 'DateTime': timestamp})
            with (self.root / 'data/raw' / f'{dataset}_raw.csv').open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS[dataset]); writer.writeheader(); writer.writerows(rows)

    def tearDown(self):
        self.temp.cleanup()

    def test_partition_totals_order_and_repeat(self):
        for interval in ('1d', '3d', '1w', '1mo'):
            manifest = prepare(self.root, interval, chunksize=1)
            first = {(p['path'], p['sha256']) for p in manifest['partitions']}
            self.assertEqual(sum(p['rows'] for p in manifest['partitions']), 6)
            for part in manifest['partitions']:
                data = pd.read_csv(self.root / 'data/processed' / interval / part['path'])
                self.assertEqual(data['RowNumber'].tolist(), sorted(data['RowNumber'].tolist()))
            again = prepare(self.root, interval, chunksize=2)
            self.assertEqual(first, {(p['path'], p['sha256']) for p in again['partitions']})

    def test_selection_mid_partition_and_dataset(self):
        prepare(self.root)
        with tempfile.TemporaryDirectory() as target:
            _, files, counts = selected_inputs(self.root, '1mo', 'sales', date(2023, 1, 3), date(2023, 1, 3), Path(target))
            self.assertEqual(counts, {'sales': 1, 'stock': 0})
            self.assertEqual(len(files), 1)
            self.assertEqual(pd.read_csv(Path(target) / 'sales.csv')['RowNumber'].tolist(), [2])

    def test_failure_keeps_previous_publication(self):
        prepare(self.root)
        manifest = self.root / 'data/processed/1mo/manifest.json'
        digest = checksum(manifest)
        source = self.root / 'data/raw/sales_raw.csv'
        source.write_text(source.read_text().replace('01 Feb 2023 08:00:00', 'bad timestamp'))
        with self.assertRaises(ValueError):
            prepare(self.root)
        self.assertEqual(checksum(manifest), digest)

    def test_incomplete_manifest_and_empty_selection(self):
        prepare(self.root)
        with tempfile.TemporaryDirectory() as target:
            with self.assertRaises(ValueError):
                selected_inputs(self.root, '1mo', 'both', date(2025, 1, 1), date(2025, 1, 2), Path(target))
            path = self.root / 'data/processed/1mo/manifest.json'
            manifest = json.loads(path.read_text())
            del manifest['partitions'][0]['sha256']
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                selected_inputs(self.root, '1mo', 'both', None, None, Path(target))

    def test_duplicate_key_and_modified_partition_rejected(self):
        prepare(self.root)
        manifest = json.loads((self.root / 'data/processed/1mo/manifest.json').read_text())
        path = self.root / 'data/processed/1mo' / manifest['partitions'][0]['path']
        with path.open('a') as f:
            f.write('corrupt\n')
        with tempfile.TemporaryDirectory() as target:
            with self.assertRaises(ValueError):
                selected_inputs(self.root, '1mo', 'both', None, None, Path(target))
        source = self.root / 'data/raw/sales_raw.csv'
        data = pd.read_csv(source, dtype='string', keep_default_na=False)
        data.loc[1, 'RowNumber'] = data.loc[0, 'RowNumber']
        data.to_csv(source, index=False)
        with self.assertRaises(ValueError):
            prepare(self.root, chunksize=1)


if __name__ == '__main__':
    unittest.main()
