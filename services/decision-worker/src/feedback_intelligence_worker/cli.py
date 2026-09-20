"""Command-line entry point for the decision-worker foundation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from feedback_intelligence_worker import __version__
from feedback_intelligence_worker.service import WorkerSettings, run

WORKER_STATUS = "Feedback Intelligence decision worker is ready."


def build_parser() -> argparse.ArgumentParser:
    """Build the worker command-line parser."""
    parser = argparse.ArgumentParser(
        prog="decision-worker",
        description="Start the Feedback Intelligence decision worker.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subcommands = parser.add_subparsers(dest="command")
    run_parser = subcommands.add_parser("run", help="Consume processing jobs continuously.")
    run_parser.add_argument(
        "--once",
        action="store_true",
        help="Claim at most one job and one projection event, then exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Report readiness or run the continuous worker."""
    arguments = build_parser().parse_args(argv)
    if arguments.command != "run":
        print(WORKER_STATUS)
        return 0
    try:
        return run(WorkerSettings.from_environment(), once=arguments.once)
    except (OSError, ValueError) as error:
        print(json.dumps({"event": "worker.start_failed", "error": str(error)}), file=sys.stderr)
        return 2
