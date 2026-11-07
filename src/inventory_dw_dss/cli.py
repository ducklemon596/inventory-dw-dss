"""Project CLI; CSV bootstrap and operational extraction are separate commands."""
import argparse
import importlib.util


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='inventory-dw-dss',
        description='Inventory DW DSS. PostgreSQL OLTP is the warehouse source.',
    )
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('bootstrap', add_help=False,
                        help='CSV preparation and OLTP ingestion (requires --group bootstrap).')
    extract = commands.add_parser('extract', help='Load transactions since the raw watermark and refresh reference data.')
    extract.add_argument('--batch-size', type=int, default=20000)
    args, arguments = parser.parse_known_args()
    if args.command == 'extract':
        if arguments:
            parser.error('unrecognized arguments: ' + ' '.join(arguments))
        if args.batch_size < 1:
            parser.error('--batch-size must be positive')
        from .extraction import extract_incremental
        try:
            extract_incremental(batch_size=args.batch_size)
        except Exception as exc:
            parser.exit(1, f'Extraction failed: {exc}\n')
        return
    if importlib.util.find_spec('pandas') is None:
        parser.exit(1, 'OLTP ingestion requires its optional dependencies. Run:\n'
                    '  uv run --group bootstrap inventory-dw-dss bootstrap --help\n')
    from .oltp_ingestion.cli import main as ingestion_main
    ingestion_main(arguments)
