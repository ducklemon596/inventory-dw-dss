"""Optional OLTP bootstrap: deterministic preparation of source CSVs."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import pandas as pd

SCHEMA_VERSION = 2
INTERVALS = ('1d', '3d', '1w', '1mo')
SOURCE_DATASET = 'pharmacy_2023_2025'
RAW_COLUMNS = {
    'sales': 'RowNumber DateTime Shift CashierID InvoiceNumber Manufacturer DrugClass Category DrugCode DrugName BatchAndExpiryDate PrescriptionNumber PatientID DoctorID SalespersonID Quantity Unit PriceTier UnitPrice SalesPromo PromoName DiscountPct DiscountAmount ServiceFee PackagingFee TaxInvoiceNumber Subtotal InvoiceDiscountPct IsMember PromoDiscountPct TaxAmount AdditionalFee PaymentType PrintCount TotalPrice'.split(),
    'stock': 'RowNumber DateTime Warehouse DrugCode DrugName DocumentNumber TransactionDescription InitialStock StockIn StockOut RemainingStock DrugClass Category DrugType Status'.split(),
}
DATE_COLUMNS = ['event_datetime', 'event_date', 'event_time', 'year', 'month', 'day', 'day_of_week', 'hour']
PERCENT_COLUMNS = {
    'DiscountPct': 'discount_pct_value', 'InvoiceDiscountPct': 'invoice_discount_pct_value',
    'PromoDiscountPct': 'promo_discount_pct_value', 'TaxAmount': 'tax_pct_value',
}
STOCK_COLUMNS = {'InitialStock': 'initial_stock', 'StockIn': 'stock_in', 'StockOut': 'stock_out', 'RemainingStock': 'remaining_stock'}
EXTRA_COLUMNS = {
    'sales': DATE_COLUMNS + ['shift_date', 'shift_period', 'shift_cashier_code', 'batch_number', 'expiry_date', 'price_tier_number'] + list(PERCENT_COLUMNS.values()),
    'stock': DATE_COLUMNS + [f'{name}_{suffix}' for name in STOCK_COLUMNS.values() for suffix in ('quantity', 'unit')] + ['transaction_type', 'supplier_name', 'referenced_invoice_number', 'patient_code'],
}


def columns_for(dataset: str) -> list[str]:
    return RAW_COLUMNS[dataset] + EXTRA_COLUMNS[dataset]


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def partition_lock(root: Path, interval: str, *, exclusive: bool):
    directory = root / 'data' / 'processed'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f'.{interval}.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def warn(warnings: Counter, key: str, mask: pd.Series) -> None:
    count = int(mask.sum())
    if count:
        warnings[key] += count


def numeric(series: pd.Series, field: str, *, required: bool = False, integer: bool = False) -> pd.Series:
    """Validate numeric strings without rounding source monetary values via float."""
    value = series.str.strip().str.replace(',', '.', regex=False)
    present = value.ne('')
    pattern = r'[+-]?\d+' if integer else r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
    invalid = present & ~value.str.fullmatch(pattern, na=False)
    if required:
        invalid |= ~present
    if invalid.any():
        raise ValueError(f'{field}: {int(invalid.sum())} invalid/missing numeric values')
    return value.mask(~present, '')


def transform(frame: pd.DataFrame, dataset: str, warnings: Counter | None = None) -> pd.DataFrame:
    warnings = warnings if warnings is not None else Counter()
    if list(frame.columns) != RAW_COLUMNS[dataset]:
        raise ValueError(f'{dataset}: CSV columns do not match expected raw schema')
    frame = frame.copy().fillna('').astype('string')
    numeric(frame['RowNumber'], 'RowNumber', required=True, integer=True)
    ids = pd.to_numeric(frame['RowNumber'], errors='raise')
    if (ids <= 0).any() or (ids > 9223372036854775807).any():
        raise ValueError('RowNumber must be a positive bigint')
    required = ['DrugCode', 'DrugName'] + (['InvoiceNumber', 'CashierID', 'Unit'] if dataset == 'sales' else ['DocumentNumber', 'Warehouse'])
    for name in required:
        if frame[name].str.strip().eq('').any():
            raise ValueError(f'{dataset}.{name}: missing mandatory value')
    times = pd.to_datetime(frame['DateTime'], format='%d %b %Y %H:%M:%S', errors='coerce')
    if times.isna().any():
        raise ValueError(f'{dataset}.DateTime: {int(times.isna().sum())} invalid timestamps')
    frame['event_datetime'] = times.dt.strftime('%Y-%m-%d %H:%M:%S')
    frame['event_date'] = times.dt.strftime('%Y-%m-%d')
    frame['event_time'] = times.dt.strftime('%H:%M:%S')
    for name, values in [('year', times.dt.year), ('month', times.dt.month), ('day', times.dt.day), ('day_of_week', times.dt.day_of_week + 1), ('hour', times.dt.hour)]:
        frame[name] = values.astype('string')
    if dataset == 'sales':
        shift = frame['Shift'].str.strip().str.extract(r'^(\d{8})-([^-]+)-(Cashier_\d+)$')
        shift_date = pd.to_datetime(shift[0], format='%Y%m%d', errors='coerce')
        period = shift[1].str.upper()
        valid = shift_date.notna() & period.isin(['PAGI', 'SORE']) & shift[2].notna()
        warn(warnings, 'shift_unparsed', ~valid)
        frame['shift_date'] = shift_date.dt.strftime('%Y-%m-%d').where(valid, '')
        frame['shift_period'] = period.where(valid, '')
        frame['shift_cashier_code'] = shift[2].where(valid, '')
        warn(warnings, 'shift_date_mismatch', valid & frame['shift_date'].ne(frame['event_date']))
        warn(warnings, 'shift_cashier_mismatch', valid & frame['shift_cashier_code'].ne(frame['CashierID']))
        raw_batch = frame['BatchAndExpiryDate'].str.strip()
        batch = raw_batch.str.extract(r'^(.*?)\s*\(ED\s*:\s*(\d{4}-\d{2}-\d{2})\)$')
        expiry = pd.to_datetime(batch[1], format='%Y-%m-%d', errors='coerce')
        # Plain batch numbers can be kept without inventing an expiry date.
        plain = raw_batch.ne('') & ~raw_batch.str.contains(r'\(|\)|ED\s*:', case=False, regex=True)
        frame['batch_number'] = batch[0].str.strip().fillna('').where(~plain, raw_batch)
        frame['expiry_date'] = expiry.dt.strftime('%Y-%m-%d').fillna('')
        warn(warnings, 'batch_unparsed', raw_batch.ne('') & frame['batch_number'].eq(''))
        warn(warnings, 'expiry_unparsed', batch[1].notna() & expiry.isna())
        tier = frame['PriceTier'].str.extract(r'(?i)^\s*Harga\s+Jual\s+(\d+)\s*$')[0]
        frame['price_tier_number'] = tier.fillna('')
        warn(warnings, 'price_tier_unparsed', frame['PriceTier'].str.strip().ne('') & tier.isna())
        for source, target in PERCENT_COLUMNS.items():
            raw = frame[source].str.strip().str.removesuffix('%').str.strip().str.replace(',', '.', regex=False)
            valid_pct = raw.str.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', na=False)
            frame[target] = raw.where(valid_pct, '')
            warn(warnings, f'{target}_unparsed', raw.ne('') & ~valid_pct)
        for name in ['Quantity', 'UnitPrice', 'DiscountAmount', 'ServiceFee', 'PackagingFee', 'Subtotal', 'AdditionalFee', 'TotalPrice', 'PrintCount']:
            numeric(frame[name], name, required=name in ['Quantity', 'UnitPrice'], integer=name == 'PrintCount')
    else:
        for source, target in STOCK_COLUMNS.items():
            parts = frame[source].str.strip().str.extract(r'^([+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?)\s+(.+?)\s*$')
            if parts.isna().any(axis=1).any():
                raise ValueError(f'{source}: invalid stock quantity/unit')
            frame[f'{target}_quantity'] = parts[0].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            frame[f'{target}_unit'] = parts[1].str.strip()
        description = frame['TransactionDescription'].str.strip()
        normalized = description.str.casefold().str.replace(r'\s+', ' ', regex=True)
        frame['transaction_type'] = 'UNKNOWN'
        rules = [
            ('SALE', r'^penjualan dengan no faktur\s*:'),
            ('PURCHASE', r'^pembelian dari .+ dengan no faktur\s*:'),
            ('TRANSFER', r'^(?:mutasi(?: antar gudang)?|mts|m)$'),
            ('IMPORT_STOCKTAKE', r'^import stok\s*opname\b'),
            ('STOCKTAKE', r'^stok\s*opname\b'),
            ('IMPORT_PRODUCT', r'^import data obat\b'),
            ('CREATE_PRODUCT', r'^tambah master obat\b'),
            ('RETURN', r'^retur\b'),
            ('TEST_ENTRY', r'^test entry\b'),
        ]
        for label, pattern in rules:
            frame.loc[normalized.str.match(pattern, na=False), 'transaction_type'] = label
        supplier = description.str.extract(r'(?i)^pembelian\s+dari\s+(.+?)\s+dengan\s+no\s+faktur\s*:')[0]
        invoice = description.str.extract(r'(?i)\bno\s+faktur\s*:\s*([^,\s]+)')[0]
        patient = description.str.extract(r'(?i)\bpasien\s*:\s*(Patient_\d+)\b')[0]
        frame['supplier_name'] = supplier.fillna('')
        frame['referenced_invoice_number'] = invoice.fillna('')
        frame['patient_code'] = patient.fillna('')
        warn(warnings, 'transaction_type_unknown', frame['transaction_type'].eq('UNKNOWN'))
    return frame[columns_for(dataset)].fillna('')


def period_bounds(dates: pd.Series, interval: str) -> tuple[pd.Series, pd.Series]:
    dates = pd.to_datetime(dates).dt.normalize()
    if interval == '1mo':
        start = dates.dt.to_period('M').dt.start_time
        end = dates.dt.to_period('M').dt.end_time.dt.normalize()
    elif interval == '1w':
        start = dates - pd.to_timedelta(dates.dt.day_of_week, unit='D')
        end = start + pd.Timedelta(days=6)
    elif interval == '3d':
        anchor = pd.Timestamp('2023-01-01')
        start = anchor + pd.to_timedelta(((dates - anchor).dt.days // 3) * 3, unit='D')
        end = start + pd.Timedelta(days=2)
    elif interval == '1d':
        start = end = dates
    else:
        raise ValueError(f'Unsupported interval: {interval}')
    return start.dt.strftime('%Y-%m-%d'), end.dt.strftime('%Y-%m-%d')


def prepare(root: Path, interval: str = '1mo', chunksize: int = 100_000) -> dict:
    if chunksize <= 0:
        raise ValueError('chunksize must be positive')
    with partition_lock(root, interval, exclusive=True):
        parent = root / 'data' / 'processed'
        work = Path(tempfile.mkdtemp(prefix=f'.{interval}-', dir=parent))
        target = parent / interval
        backup = parent / f'.{interval}-previous'
        # Recover an interrupted directory swap before starting a new preparation.
        if backup.exists() and not target.exists():
            backup.rename(target)
        elif backup.exists():
            shutil.rmtree(backup)
        manifest = {'schema_version': SCHEMA_VERSION, 'interval': interval,
                    'source_dataset': SOURCE_DATASET, 'prepared_at_utc': datetime.now(timezone.utc).isoformat(),
                    'day_of_week_convention': 'ISO: Monday=1, Sunday=7', 'sources': {}, 'partitions': [], 'warnings': {}}
        try:
            for dataset in ('sales', 'stock'):
                source = root / 'data/raw' / f'{dataset}_raw.csv'
                source_hash = checksum(source)
                warnings = Counter()
                seen = set()
                row_count = 0
                paths: dict[str, tuple[str, str]] = {}
                (work / dataset).mkdir()
                with pd.read_csv(source, dtype="string", keep_default_na=False, chunksize=chunksize) as reader:
                    for chunk in reader:
                        processed = transform(chunk, dataset, warnings)
                        ids = processed['RowNumber'].astype('int64')
                        if ids.duplicated().any() or seen.intersection(ids):
                            raise ValueError(f'{dataset}: duplicate source RowNumber')
                        seen.update(ids)
                        row_count += len(processed)
                        start, end = period_bounds(processed['event_date'], interval)
                        processed['_partition'] = dataset + '_' + start + '_' + end + '.csv'
                        for filename, group in processed.groupby('_partition', sort=True):
                            path = work / dataset / filename
                            group.drop(columns='_partition').to_csv(path, mode='a', header=not path.exists(), index=False, lineterminator='\n')
                            paths[filename] = (str(start.loc[group.index[0]]), str(end.loc[group.index[0]]))
                if checksum(source) != source_hash:
                    raise ValueError(f'{source.name} changed during preparation')
                total = 0
                for filename, (start, end) in sorted(paths.items()):
                    path = work / dataset / filename
                    part = pd.read_csv(path, dtype='string', keep_default_na=False)
                    part['_row_order'] = part['RowNumber'].astype('int64')
                    part = part.sort_values(['event_datetime', '_row_order'], kind='stable').drop(columns='_row_order')
                    part.to_csv(path, index=False, lineterminator='\n')
                    total += len(part)
                    manifest['partitions'].append({'dataset': dataset, 'path': f'{dataset}/{filename}', 'start': start, 'end': end,
                                                   'rows': len(part), 'sha256': checksum(path)})
                if total != row_count:
                    raise ValueError(f'{dataset}: partition row count mismatch')
                manifest['sources'][dataset] = {'path': f'data/raw/{dataset}_raw.csv', 'sha256': source_hash, 'rows': row_count,
                                                'columns': columns_for(dataset)}
                manifest['warnings'][dataset] = dict(warnings)
                print(f'{dataset}: {row_count:,} rows, {len(paths)} partitions, warnings={dict(warnings)}', flush=True)
            (work / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            if target.exists():
                target.rename(backup)
            try:
                work.rename(target)
            except BaseException:
                if backup.exists():
                    backup.rename(target)
                raise
            if backup.exists():
                shutil.rmtree(backup)
            return manifest
        finally:
            if work.exists():
                shutil.rmtree(work)
