"""Optional OLTP bootstrap: prepare source CSVs and initialize PostgreSQL. Not a DW command."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .preprocessing import INTERVALS, prepare


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='inventory-dw-dss bootstrap', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('prepare', 'load'):
        sub = commands.add_parser(command)
        sub.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
        sub.add_argument('--interval', choices=INTERVALS, default='1mo')
        if command == 'prepare':
            sub.add_argument('--chunksize', type=int, default=100_000)
        else:
            sub.add_argument('--dataset', choices=['sales', 'stock', 'both'], default='both')
            sub.add_argument('--all', action='store_true')
            sub.add_argument('--from', dest='start', type=date.fromisoformat)
            sub.add_argument('--to', dest='end', type=date.fromisoformat)
    args = parser.parse_args(arguments)
    if args.command == 'load':
        if args.all and (args.start or args.end):
            parser.error('--all cannot be combined with --from/--to')
        if not args.all and (args.start is None or args.end is None):
            parser.error('load requires --all or both --from and --to')
        if args.start and args.start > args.end:
            parser.error('--from must not be after --to')
    try:
        if args.command == 'prepare':
            prepare(args.root.resolve(), args.interval, args.chunksize)
        else:
            from .loading import load
            load(args.root.resolve(), args.interval, args.dataset, args.start, args.end)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
