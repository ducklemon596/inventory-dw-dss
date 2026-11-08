"""Public CLI scope validation, dispatch and dbt delegation without databases."""
import contextlib
from datetime import date
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from inventory_dw_dss.cli import main, run_transform
from inventory_dw_dss.extraction import load_raw


class CommandTests(unittest.TestCase):
    def test_invalid_selection_is_rejected_before_execution(self):
        cases = [[], ['load'], ['bootstrap'], ['extract'],
                 ['load', 'postgres'], ['load', 'postgres', '--all'],
                 ['load', 'raw', '--start', '2023-01-01'],
                 ['load', 'postgres', '--end', '2023-01-01'],
                 ['load', 'raw', '--full', '--start', '2023-01-01', '--end', '2023-01-02'],
                 ['load', 'raw', '--start', '2023-02-01', '--end', '2023-01-01'],
                 ['load', 'raw', '--start', '2023-02-29', '--end', '2023-03-01'],
                 ['load', 'raw', '--start', '20230101', '--end', '2023-01-01'],
                 ['load', 'raw', '--start', '9999-12-31', '--end', '9999-12-31'],
                 ['transform', '--select'], ['transform', '--uom-version', 'bad;version']]
        for arguments in cases:
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(arguments)
                self.assertEqual(error.exception.code, 2)

    def test_help_does_not_require_bootstrap_dependencies(self):
        for arguments in [['--help'], ['load', '--help'], ['load', 'postgres', '--help'],
                          ['load', 'raw', '--help'], ['transform', '--help']]:
            with self.subTest(arguments=arguments), patch('inventory_dw_dss.cli.importlib.util.find_spec', return_value=None), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(arguments)
                self.assertEqual(error.exception.code, 0)

    def test_raw_defaults_and_explicit_scopes(self):
        with patch('inventory_dw_dss.extraction.load_raw') as load:
            main(['load', 'raw'])
            load.assert_called_with(full=False, start=None, end=None)
            main(['load', 'raw', '--full'])
            load.assert_called_with(full=True, start=None, end=None)
            main(['load', 'raw', '--start', '2024-02-29', '--end', '2024-02-29'])
            load.assert_called_with(full=False, start=date(2024, 2, 29), end=date(2024, 2, 29))

    def test_postgres_dispatch_and_optional_dependency_message(self):
        with patch('inventory_dw_dss.oltp_ingestion.loading.load_source') as load, patch('inventory_dw_dss.cli.project_root', return_value=Path('/checkout')):
            main(['load', 'postgres', '--full'])
            load.assert_called_with(Path('/checkout'), dataset='both', start=None, end=None)
            main(['load', 'postgres', '--start', '2023-01-01', '--end', '2023-01-03', '--dataset', 'sales'])
            load.assert_called_with(Path('/checkout'), dataset='sales', start=date(2023, 1, 1), end=date(2023, 1, 3))
        error_text = io.StringIO()
        with patch('inventory_dw_dss.cli.importlib.util.find_spec', return_value=None), contextlib.redirect_stderr(error_text):
            with self.assertRaises(SystemExit) as error:
                main(['load', 'postgres', '--full'])
            self.assertEqual(error.exception.code, 1)
        self.assertIn('uv run --locked --group bootstrap inventory-dw-dss load postgres --full', error_text.getvalue())

    def test_transform_delegates_selection_and_version_to_dbt(self):
        with patch('dbt.cli.main.dbtRunner') as runner:
            runner.return_value.invoke.return_value = SimpleNamespace(success=True, result=SimpleNamespace(results=[object()]))
            run_transform(Path('/checkout'))
            runner.return_value.invoke.assert_called_with([
                'build', '--project-dir', '/checkout/transform/dbt', '--profiles-dir', '/checkout/transform/dbt'])
            run_transform(Path('/checkout'), selection=['staging', '+fct_sales_line'], tests_only=True,
                          uom_version='uom_mapping_v1_2026-11-08')
            arguments = runner.return_value.invoke.call_args.args[0]
            self.assertEqual(arguments[0], 'test')
            self.assertEqual(arguments[arguments.index('--select') + 1:arguments.index('--vars')], ['path:models/staging', '+fct_sales_line'])
            self.assertIn('uom_mapping_v1_2026-11-08', arguments[-1])
            run_transform(Path('/checkout'), selection=['dimensions', '+intermediate', 'marts+'])
            forwarded = runner.return_value.invoke.call_args.args[0]
            self.assertEqual(forwarded[forwarded.index('--select') + 1:],
                             ['path:models/marts/dimensions', '+path:models/intermediate', 'path:models/marts+'])

    def test_failures_return_nonzero_without_hiding_dbt_failure(self):
        with patch('dbt.cli.main.dbtRunner') as runner, contextlib.redirect_stderr(io.StringIO()):
            runner.return_value.invoke.return_value = SimpleNamespace(success=False, exception=RuntimeError('connection failed'))
            with self.assertRaises(SystemExit) as error:
                main(['transform'])
            self.assertEqual(error.exception.code, 1)
        with patch('inventory_dw_dss.extraction.load_raw', side_effect=RuntimeError('source unavailable')), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(['load', 'raw'])
            self.assertEqual(error.exception.code, 1)

    def test_empty_model_selection_fails_clearly(self):
        with patch('dbt.cli.main.dbtRunner') as runner:
            runner.return_value.invoke.return_value = SimpleNamespace(success=True, result=SimpleNamespace(results=[]))
            with self.assertRaisesRegex(RuntimeError, 'No dbt nodes matched'):
                run_transform(Path('/checkout'), selection=['missing_model'])

    def test_raw_api_rejects_invalid_scope_without_connections(self):
        for arguments in [dict(full=True, start=date(2023, 1, 1)), dict(start=date(2023, 1, 1)),
                          dict(start=date(2023, 2, 1), end=date(2023, 1, 1)), dict(batch_size=0)]:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                load_raw(**arguments)


if __name__ == '__main__':
    unittest.main()
