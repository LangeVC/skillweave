"""The thin ``skillweave dispatch`` command-line surface (SW138-DISPATCH-001).

This module only parses arguments and hands them to the application service. It
owns no process launch, no SQLite write, no state machine, and no artifact
persistence: those concerns live in the shared runtime / workspace / running
seams the application delegates to.

The command is **experimental and wave-scoped**: it executes exactly one wave
and makes no claim of stable 1.4 transport compatibility. Help text and the
result metadata say both of these explicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from skillweave.dispatch.application import OperatorDispatchApplication

_EXPERIMENTAL_NOTE = "experimental; wave-scoped; no stable 1.4 transport compatibility"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave dispatch",
        description=(
            f"Operator-dispatch experiment ({_EXPERIMENTAL_NOTE}). "
            "Execute one wave of a dispatch sequence against a routing profile."
        ),
        epilog=(
            f"Experimental command ({_EXPERIMENTAL_NOTE}). This command is "
            "wave-scoped and changes without notice across releases."
        ),
    )
    parser.add_argument(
        "--sequence",
        required=True,
        help="path to the dispatch sequence fixture (YAML)",
    )
    parser.add_argument(
        "--wave",
        default="0",
        help="the wave to execute (default: 0)",
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="path to the routing profile fixture (YAML)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "resolve lanes/roles/profile/execution model/parallelism/correction "
            "budget and report without starting any worker"
        ),
    )
    return parser


def _print_result(run: object) -> None:
    """Emit the machine-readable run identifier (and report) to stdout.

    A single JSON object is printed: the ``run_id`` is the first-class field a
    downstream consumer parses, and the resolved report rides beside it. In
    dry-run mode no worker started, yet the same machine-readable shape is
    emitted so tooling treats the two modes uniformly.
    """
    sys.stdout.write(json.dumps(run.to_dict(), sort_keys=True) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    app = OperatorDispatchApplication()

    if args.dry_run:
        run = app.dry_run(args.sequence, args.profile, wave=args.wave)
    else:
        run = app.dispatch(args.sequence, args.profile, wave=args.wave)

    _print_result(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
