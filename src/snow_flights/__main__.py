"""Command line: ``python -m snow_flights alerts --config alerts.yaml [--dry-run]``."""

import argparse
import sys

from .alerts import run as alerts_run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="snow_flights")
    sub = parser.add_subparsers(dest="command", required=True)
    alerts = sub.add_parser("alerts", help="Check watched resorts and send a powder digest")
    alerts_run.add_arguments(alerts)
    args = parser.parse_args(argv)
    if args.command == "alerts":
        return alerts_run.run(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
