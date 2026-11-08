"""Published mapping bytes and exact evidence values must survive seed assembly."""
import csv
from collections import Counter
from decimal import Decimal
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / 'data/reference/uom/uom_conversion_mapping_v2.csv'
SEED = ROOT / 'transform/dbt/seeds/uom_conversion_mapping.csv'


def records(path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


class PublishedMappingTests(unittest.TestCase):
    def test_v1_snapshot_bytes_are_immutable(self):
        path = REFERENCE.with_name('uom_conversion_mapping_v1.csv')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         'a9b4655cc04113bc1605fc06694ea43efa827032ddd7a3910a30ee83324f787c')

    def test_v2_snapshot_bytes_are_immutable(self):
        self.assertEqual(hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
                         '7e2e0c0e51dda3e96e5466af664d40ae4a4129d10171eb60af46bc0c55ba0aa2')

    def test_seed_is_exact_union_of_available_snapshots(self):
        reference_rows = []
        for path in REFERENCE.parent.glob('uom_conversion_mapping_v*.csv'):
            reference_rows.extend(records(path))
        key = lambda row: tuple(sorted(row.items()))
        self.assertEqual(Counter(map(key, records(SEED))), Counter(map(key, reference_rows)))

    def test_v2_counts_and_governance(self):
        rows = records(REFERENCE)
        self.check_governance(rows, 'uom_mapping_v2_2026-11-08', 207, 197,
                              {'approved': 87, 'candidate': 89, 'quarantined': 31})

    def test_v1_counts_and_governance(self):
        rows = records(REFERENCE.with_name('uom_conversion_mapping_v1.csv'))
        self.check_governance(rows, 'uom_mapping_v1_2026-11-08', 190, 182,
                              {'approved': 73, 'candidate': 87, 'quarantined': 30})

    def test_v2_preserves_all_v1_pair_decisions_and_adds_17_pairs(self):
        first = {(r['product_id'], r['sales_unit']): r for r in records(REFERENCE.with_name('uom_conversion_mapping_v1.csv'))}
        second = {(r['product_id'], r['sales_unit']): r for r in records(REFERENCE)}
        self.assertTrue(first.keys() <= second.keys())
        added = second.keys() - first.keys()
        self.assertEqual(len(added), 17)
        self.assertEqual(len({key[0] for key in added}), 15)
        for key, row in first.items():
            self.assertEqual({k: v for k, v in row.items() if k != 'mapping_version'},
                             {k: v for k, v in second[key].items() if k != 'mapping_version'})

    def check_governance(self, rows, version, pair_count, sku_count, status_counts):
        self.assertEqual(len(rows), pair_count)
        self.assertEqual(len({row['product_id'] for row in rows}), sku_count)
        self.assertEqual(Counter(row['approval_status'] for row in rows),
                         status_counts)
        self.assertEqual(len({(r['mapping_version'], r['product_id'], r['sales_unit']) for r in rows}), pair_count)
        for row in rows:
            self.assertEqual(row['mapping_version'], version)
            self.assertEqual(row['approval_status'], {'A': 'approved', 'B': 'candidate', 'C': 'quarantined'}[row['tier']])
            self.assertEqual(bool(row['factor_approved']), row['approval_status'] == 'approved')
            self.assertTrue(row['evidence_source'].strip())
            for name in ('product_id', 'sales_unit', 'stock_unit'):
                self.assertEqual(row[name], row[name].strip())
                self.assertTrue(row[name])
            for name in ('factor_approved', 'factor_candidate'):
                if row[name]:
                    factor = Decimal(row[name])
                    self.assertGreater(factor, 0)
                    self.assertEqual(factor * 10**6, (factor * 10**6).to_integral_value())
                    self.assertLess(factor, Decimal('1000000000000'))


if __name__ == '__main__':
    unittest.main()
