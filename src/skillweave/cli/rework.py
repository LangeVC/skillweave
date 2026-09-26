"""The ``skillweave rework`` CLI subcommand.

Usage::

    skillweave rework --lane <lane_id> [--project-root <path>] [--output-dir <path>]

Reads the gate log for the named lane, extracts failing criteria, and writes
a structured rework brief to ``.skillweave/rework/<lane_id>-<timestamp>.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave rework",
        description=(
            "Generate a structured rework brief from a failed gate log. "
            "The brief is written to .skillweave/rework/<lane_id>-<timestamp>.md."
        ),
    )
    parser.add_argument(
        "--lane",
        required=True,
        metavar="LANE_ID",
        help="Lane identifier whose gate log will be read (e.g. SW-CLI-001).",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        metavar="PATH",
        help=(
            "Root directory of the SkillWeave project. "
            "Defaults to the current working directory."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="PATH",
        help=(
            "Directory to write the rework brief into. "
            "Defaults to <project-root>/.skillweave/rework/."
        ),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve() if args.project_root else None
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None

    from skillweave.rework.brief import ReworkBriefWriter, ReworkError

    writer = ReworkBriefWriter(project_root=project_root, output_dir=output_dir)

    try:
        brief_path = writer.write(args.lane)
    except ReworkError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(f"Unexpected error: {exc}\n")
        return 2

    # Print the path so callers can pick it up
    print(str(brief_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
