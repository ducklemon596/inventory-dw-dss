"""Serialization and ordering checks that do not require either database."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import unittest

from inventory_dw_dss.validation.source_sequence import (
    Record, Statistics, identifier, ordered, passport_row, stock_quantity, timestamp,
)


class SourceSequenceTests(unittest.TestCase):
    def test_stock_fingerprint_uses_labels_and_exact_decimal_serialization(self):
        record = Record(7, ('2024-02-29 10:00:00.123456', '  SKU  01 ', 'Apotek',
                            'Stock\n count', Decimal('12.000000'), Decimal('0.100000'),
                            Decimal('2.10'), Decimal('10.000000')))
        expected = b'2024-02-29 10:00:00|SKU 01|Apotek|Stock count|12|0.1|2.1|10'
        self.assertEqual(passport_row('stock', record), expected)

    def test_sequence_set_and_identity_hashes_include_exact_separators(self):
        records = [Record(n, ('2024-02-29 10:00:00.000000', 'INV', 'SKU', Decimal('1.5'), 'Tab'))
                   for n in (1, 3)]
        statistics = Statistics('sales')
        for record in records:
            statistics.add(record)
        result = statistics.result()
        row_hash = hashlib.md5(passport_row('sales', records[0])).hexdigest()
        self.assertEqual(result['S1_seq_set_md5_sorted'], hashlib.md5(b'1,3').hexdigest())
        self.assertEqual(result['S2_content_set_md5_sorted'], hashlib.md5(row_hash.encode()).hexdigest())
        self.assertEqual(result['S2_content_multiset_sum64'],
                         (2 * int.from_bytes(bytes.fromhex(row_hash)[:8], 'big')) % 2**64)
        self.assertEqual(result['S3_identity_ordered_md5'],
                         hashlib.md5(f'1:{row_hash}\n3:{row_hash}'.encode()).hexdigest())
        self.assertEqual(result['missing_sequence_ranges'], [[2, 2]])

    def test_duplicate_sequences_are_detected(self):
        statistics = Statistics('sales')
        row = Record(1, ('2024-02-29 10:00:00.000000', 'INV', 'SKU', Decimal('1'), 'Tab'))
        statistics.add(row)
        statistics.add(row)
        self.assertEqual(statistics.result()['duplicate_sequence_rows'], 1)

    def test_unordered_stream_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'not ordered'):
            list(ordered([Record(2, ()), Record(1, ())]))

    def test_signed_source_quantities_keep_exact_units_and_precision(self):
        self.assertEqual(stock_quantity('-1.260,5 Tab'), (Decimal('-1260.5'), 'Tab'))
        with self.assertRaises(ValueError):
            stock_quantity('1.2 Tab')

    def test_wall_clock_time_must_not_gain_an_inferred_timezone(self):
        self.assertEqual(timestamp(datetime(2024, 2, 29)), '2024-02-29 00:00:00.000000')
        with self.assertRaises(ValueError):
            timestamp(datetime(2024, 2, 29, tzinfo=timezone.utc))

    def test_sql_identifier_rejects_query_fragments(self):
        with self.assertRaises(ValueError):
            identifier('inventory_dw; DROP DATABASE raw')


if __name__ == '__main__':
    unittest.main()
