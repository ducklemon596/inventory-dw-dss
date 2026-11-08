"""Reconciliation must reject loss, double counting and broken anchors."""
import copy
import unittest

from inventory_dw_dss.validation.inventory_history import reconciliation_checks


class InventoryHistoryTests(unittest.TestCase):
    def setUp(self):
        self.metrics = {
            'ledger': dict(movements=3, ledgers=1, transitions=2, continuous=1, gaps=1),
            'segments': dict(movements=3, segments=2, initial_segments=1,
                             additional_segments=1, reconstruction_errors=0),
            'movement': dict(movements=3, distinct_ids=3, receipts=2, issues=1, delta=1),
            'daily': dict(movements=3, observations=2, distinct_grains=2, gaps=1,
                          receipts=2, issues=1, delta=1),
            'diagnostics': [dict(gaps=1)],
            'flows_by_unit': {
                'movement': [dict(stock_unit_id=1, receipts=2, issues=1, delta=1)],
                'daily': [dict(stock_unit_id=1, receipts=2, issues=1, delta=1)],
            },
        }
        self.source = dict(rows=3, ledger=dict(series=1, transitions=2, continuous=1,
                                               discontinuities=1))
        self.baseline = dict(segments=2, fct_inventory_daily_observed_rows=2)

    def checks(self, metrics):
        return reconciliation_checks(metrics, self.source, self.baseline)

    def test_consistent_small_snapshot_passes_without_production_counts(self):
        self.assertTrue(all(self.checks(self.metrics).values()))

    def test_missing_or_duplicated_movements_fail(self):
        for table in ('ledger', 'segments', 'movement', 'daily'):
            metrics = copy.deepcopy(self.metrics)
            metrics[table]['movements'] += 1
            self.assertFalse(self.checks(metrics)['all_movements_preserved'], table)

    def test_gap_delta_must_not_be_added_to_daily_flow(self):
        metrics = copy.deepcopy(self.metrics)
        metrics['flows_by_unit']['daily'][0]['delta'] += 4
        self.assertFalse(self.checks(metrics)['daily_flows_reconcile'])

    def test_flow_comparison_never_cancels_differences_across_units(self):
        metrics = copy.deepcopy(self.metrics)
        metrics['flows_by_unit']['daily'][0]['stock_unit_id'] = 2
        self.assertFalse(self.checks(metrics)['daily_flows_reconcile'])

    def test_reconstruction_errors_and_extra_segments_fail(self):
        metrics = copy.deepcopy(self.metrics)
        metrics['segments'].update(reconstruction_errors=1, segments=3)
        checks = self.checks(metrics)
        self.assertFalse(checks['exact_segment_reconstruction'])
        self.assertFalse(checks['one_anchor_per_segment'])
        self.assertFalse(checks['segments_match_snapshot'])

    def test_snapshot_expectation_is_supplied_not_universal(self):
        baseline = {**self.baseline, 'fct_inventory_daily_observed_rows': 99}
        checks = reconciliation_checks(self.metrics, self.source, baseline)
        self.assertFalse(checks['daily_rows_match_snapshot'])


if __name__ == '__main__':
    unittest.main()
