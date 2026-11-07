"""Project command line; ingestion dependencies are loaded only on request."""
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
    _, arguments = parser.parse_known_args()
    if importlib.util.find_spec('pandas') is None:
        parser.exit(1, 'OLTP ingestion requires its optional dependencies. Run:\n'
                    '  uv run --group bootstrap inventory-dw-dss bootstrap --help\n')
    from .oltp_ingestion.cli import main as ingestion_main
    ingestion_main(arguments)
