"""The unified SkillWeave CLI router.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from skillweave.cli import run
from skillweave.cli import rework
from skillweave.dispatch import cli as dispatch


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skillweave",
        description="SkillWeave Multi-agent AI Orchestration",
    )
    subparsers = parser.add_subparsers(title="commands", dest="command")

    # `dispatch` subcommand
    parser_dispatch = subparsers.add_parser(
        "dispatch",
        help="Execute one wave of a dispatch sequence (experimental)",
        # Inherit the exact arguments from the existing dispatch parser
        parents=[dispatch.build_parser()],
        add_help=False,
    )

    # `run` subcommand
    parser_run = subparsers.add_parser(
        "run",
        help="Execute a single authoritative run command",
        parents=[run.build_parser()],
        add_help=False,
    )

    # `rework` subcommand
    parser_rework = subparsers.add_parser(
        "rework",
        help="Generate a structured rework brief from a failed gate log",
        parents=[rework.build_parser()],
        add_help=False,
    )

    args = parser.parse_args(argv)

    if args.command == "dispatch":
        return dispatch.main(argv[1:] if argv else sys.argv[2:])
    elif args.command == "run":
        return run.main(argv[1:] if argv else sys.argv[2:])
    elif args.command == "rework":
        return rework.main(argv[1:] if argv else sys.argv[2:])
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
