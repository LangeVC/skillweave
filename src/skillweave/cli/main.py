"""The unified SkillWeave CLI router.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from skillweave.cli import run
from skillweave.dispatch import cli as dispatch
from skillweave.cli import observe as observe_mod


def main(argv: Optional[Sequence[str]] = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)

    # `--dispatch` flag (Handshake & Observe: non-blocking dispatch)
    if "--dispatch" in args_list:
        return observe_mod.main_dispatch(args_list)

    # `--observe <execution_id>` flag (Handshake & Observe: read-only tailer)
    if "--observe" in args_list:
        return observe_mod.main_observe(args_list)

    parser = argparse.ArgumentParser(
        prog="skillweave",
        description="SkillWeave Multi-agent AI Orchestration",
    )
    subparsers = parser.add_subparsers(title="commands", dest="command")

    # `dispatch` subcommand
    subparsers.add_parser(
        "dispatch",
        help="Execute one wave of a dispatch sequence (experimental)",
        parents=[dispatch.build_parser()],
        add_help=False,
    )

    # `run` subcommand
    subparsers.add_parser(
        "run",
        help="Execute a single authoritative run command",
        parents=[run.build_parser()],
        add_help=False,
    )

    args = parser.parse_args(args_list)

    if args.command == "dispatch":
        return dispatch.main(args_list[1:] if args_list else sys.argv[2:])
    elif args.command == "run":
        return run.main(args_list[1:] if args_list else sys.argv[2:])
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
