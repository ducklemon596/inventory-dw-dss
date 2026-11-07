"""Publication must preserve previous tables and reverse only completed operations."""
import unittest
from types import SimpleNamespace

from inventory_dw_dss.extraction import identifier, publish, rollback_publication


class FakeClient:
    def __init__(self, existing=(), fail_at=None):
        self.existing = set(existing)
        self.fail_at = fail_at
        self.commands = []

    def query(self, query, parameters):
        return SimpleNamespace(first_row=(int(parameters['table'] in self.existing),))

    def command(self, query):
        if self.fail_at is not None and len(self.commands) == self.fail_at:
            self.fail_at = None
            raise RuntimeError('injected publication failure')
        self.commands.append(query)


class PublicationTests(unittest.TestCase):
    def test_empty_prepared_list_does_not_publish_existing_tables(self):
        client = FakeClient(existing=['sales_line'])
        completed = []
        publish(client, 'raw', '_work', completed, [])
        self.assertEqual(client.commands, [])
        self.assertEqual(completed, [])

    def test_repeated_publish_exchanges_instead_of_appending(self):
        client = FakeClient(existing=['product', 'sales_line'])
        completed = []
        publish(client, 'raw', '_work', completed, ['product', 'sales_line'])
        self.assertEqual(completed, [('product', True), ('sales_line', True)])
        self.assertEqual(client.commands, [
            'EXCHANGE TABLES `raw`.`product` AND `_work`.`product`',
            'EXCHANGE TABLES `raw`.`sales_line` AND `_work`.`sales_line`'])

    def test_failure_restores_existing_and_new_tables_in_reverse_order(self):
        client = FakeClient(existing=['product'], fail_at=2)
        completed = []
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            publish(client, 'raw', '_work', completed, ['product', 'sales_line', 'unit'])
        rollback_publication(client, 'raw', '_work', completed)
        self.assertEqual(completed, [('product', True), ('sales_line', False)])
        self.assertEqual(client.commands[-2:], [
            'RENAME TABLE `raw`.`sales_line` TO `_work`.`sales_line`',
            'EXCHANGE TABLES `raw`.`product` AND `_work`.`product`'])

    def test_rejects_injected_database_names(self):
        for name in ('raw; DROP DATABASE raw', 'raw.name', '', 'raw`'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                identifier(name)


if __name__ == '__main__':
    unittest.main()
