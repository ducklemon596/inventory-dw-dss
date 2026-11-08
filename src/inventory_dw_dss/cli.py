"""Public operations: load PostgreSQL, load ClickHouse raw, and run dbt."""
from __future__ import annotations

import argparse
from datetime import date
import importlib.util
import json
from pathlib import Path
import re


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def calendar_date(value: str) -> date:
    """Accept an explicit calendar date rather than compact or ISO-week forms."""
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise argparse.ArgumentTypeError('use YYYY-MM-DD, for example 2023-01-31')
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f'{value!r} is not a valid calendar date') from error


def mapping_version(value: str) -> str:
    if not re.fullmatch(r'uom_mapping_v[1-9][0-9]*_\d{4}-\d{2}-\d{2}', value):
        raise argparse.ArgumentTypeError('use a published version such as uom_mapping_v2_2026-11-08')
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='inventory-dw-dss',
        description='Load PostgreSQL → ClickHouse raw → dbt marts for DSS.',
    )
    commands = parser.add_subparsers(dest='command', required=True)
    load = commands.add_parser('load', help='Load a destination without deleting unmatched transactions.')
    destinations = load.add_subparsers(dest='destination', required=True)
    for destination, description in (
        ('postgres', 'Choose --full or --start/--end. Prepare the supported CSV export if needed and upsert PostgreSQL.'),
        ('raw', 'Copy PostgreSQL into ClickHouse raw. Default: inclusive event-time watermarks. Reference/header tables always refresh fully.'),
    ):
        sub = destinations.add_parser(destination, help=description, description=description)
        sub.add_argument('--full', action='store_true', help=(
            'Read all CSV transactions and upsert; retain unmatched existing rows.' if destination == 'postgres' else
            'Read all transactions and refresh references; merge transaction PKs without truncating.'))
        sub.add_argument('--start', type=calendar_date, metavar='YYYY-MM-DD', help='First event date to load, inclusive; requires --end.')
        sub.add_argument('--end', type=calendar_date, metavar='YYYY-MM-DD', help='Last event date to load, inclusive; requires --start.')
        if destination == 'postgres':
            sub.add_argument('--dataset', choices=('sales', 'stock', 'both'), default='both',
                             help='CSV transactions to load (default: both). Requires the bootstrap dependency group.')
    transform = commands.add_parser('transform', help='Build all dbt models and tests using project defaults.',
                                    description='Build all dbt models, the governed seed and tests. Project/profile paths and the pinned UOM version come from the repository.')
    transform.add_argument('--select', nargs='+', metavar='MODEL_OR_LAYER', help='Model or layer: staging, intermediate, marts, dimensions. Include ancestors with +MODEL.')
    transform.add_argument('--test', action='store_true', help='Run tests against existing models instead of rebuilding them.')
    transform.add_argument('--uom-version', type=mapping_version, metavar='VERSION',
                           help='Override the published UOM version pinned in dbt_project.yml; rebuild before testing another version.')
    return parser


def validate_scope(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.full and (args.start is not None or args.end is not None):
        parser.error('--full cannot be combined with --start/--end')
    if (args.start is None) != (args.end is None):
        parser.error('provide both --start and --end')
    if args.start is not None and args.start > args.end:
        parser.error('--start must be on or before --end')
    if args.end == date.max:
        parser.error('--end must be before 9999-12-31 so its inclusive day can be represented')
    if args.destination == 'postgres' and not args.full and args.start is None:
        parser.error('load postgres requires --full or both --start and --end')


def run_transform(root: Path, *, selection: list[str] | None = None,
                  tests_only: bool = False, uom_version: str | None = None) -> None:
    """Delegate execution, graph selection and exit status to the installed dbt."""
    from dbt.cli.main import dbtRunner

    action = 'test' if tests_only else 'build'
    project = root / 'transform/dbt'
    arguments = [action, '--project-dir', str(project), '--profiles-dir', str(project)]
    if selection:
        # Paths make layer selection stable even when dbt assigns a different FQN grouping.
        layer_paths = {
            'staging': 'models/staging', 'intermediate': 'models/intermediate',
            'marts': 'models/marts', 'dimensions': 'models/marts/dimensions',
        }
        resolved = []
        for expression in selection:
            layer = re.fullmatch(r'(\+?)(staging|intermediate|marts|dimensions)(\+?)', expression)
            resolved.append(f'{layer[1]}path:{layer_paths[layer[2]]}{layer[3]}' if layer else expression)
        arguments += ['--select', *resolved]
    if uom_version is not None:
        arguments += ['--vars', json.dumps({'uom_mapping_version': uom_version})]
    result = dbtRunner().invoke(arguments)
    if not result.success:
        raise RuntimeError(f'dbt {action} failed: {result.exception or "see the dbt failures above"}')
    if selection and not getattr(result.result, 'results', []):
        raise RuntimeError('No dbt nodes matched --select; check the model or layer names.')


def main(arguments: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(arguments)
    if args.command == 'load':
        validate_scope(parser, args)
    try:
        if args.command == 'transform':
            run_transform(project_root(), selection=args.select, tests_only=args.test,
                          uom_version=args.uom_version)
        elif args.destination == 'raw':
            from .extraction import load_raw
            load_raw(full=args.full, start=args.start, end=args.end)
        else:
            if importlib.util.find_spec('pandas') is None:
                scope = '--full' if args.full else f'--start {args.start} --end {args.end}'
                raise RuntimeError('CSV loading requires pandas. Run:\n'
                                   '  uv run --locked --group bootstrap inventory-dw-dss '
                                   f'load postgres {scope} --dataset {args.dataset}')
            from .oltp_ingestion.loading import load_source
            load_source(project_root(), dataset=args.dataset, start=args.start, end=args.end)
    except KeyboardInterrupt:
        parser.exit(130, 'Cancelled.\n')
    except Exception as error:
        parser.exit(1, f'Error: {error}\n')
