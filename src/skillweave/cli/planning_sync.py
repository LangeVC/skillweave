"""The ``skillweave planning-sync`` CLI subcommand.

Usage::

    skillweave planning-sync [--project-root <path>] [--planning-root <path>]
                             [--area <name> ...]

Resolves the workspace's backing store from its configuration (``sync.yaml``
and/or the ``SKILLWEAVE_PLANNING_ROOT`` environment variable), then carries each
durable area's payload into the planning repository and prints, per area, the
destination it synced and the names of the files it carried. Areas whose
durable payload cannot reach a store are printed as ``AT RISK`` rather than
silently claimed carried.

Exit codes mirror the project convention: 0 success, 1 user/config error,
2 system error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from skillweave.persistence import Durability, get_area_declaration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave planning-sync",
        description=(
            "Carry durable substrate areas from a non-git workspace into the "
            "configured planning repository, reporting what was synced."
        ),
    )
    parser.add_argument(
        "--project-root",
        default=None,
        metavar="PATH",
        help="Root directory of the workspace (defaults to current directory).",
    )
    parser.add_argument(
        "--planning-root",
        default=None,
        metavar="PATH",
        help=(
            "Local checkout of the planning repository to sync into. "
            "Defaults to the SKILLWEAVE_PLANNING_ROOT environment variable or "
            "the planning_root key of <project-root>/sync.yaml."
        ),
    )
    parser.add_argument(
        "--area",
        action="append",
        default=None,
        metavar="NAME",
        help="Only sync the named area (repeatable). Defaults to every declared durable area.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    import importlib

    runtime = importlib.import_module("skillweave.runtime")
    PlanningSyncBackingStore = runtime.PlanningSyncBackingStore
    classify_runtime = runtime.classify_runtime
    resolve_runtime_store = runtime.resolve_runtime_store

    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = str(Path(args.project_root).resolve()) if args.project_root else None
    planning_root = str(Path(args.planning_root).resolve()) if args.planning_root else None

    if project_root is None:
        project_root = str(Path.cwd().resolve())

    store = resolve_runtime_store(
        project_root=project_root,
        planning_root=planning_root,
    )

    if not isinstance(store, PlanningSyncBackingStore):
        sys.stderr.write(
            "ERROR: workspace has no configured planning repository to sync into "
            "(no git repo and no planning_repository configured).\n"
        )
        return 1

    classified = classify_runtime(project_root=project_root, planning_root=planning_root)
    areas = args.area if args.area else [
        name for name, resolved in classified.items()
        if get_area_declaration(name).durability is Durability.DURABLE
    ]

    exit_code = 0
    for name in areas:
        report = store.sync(name, project_root)
        if report.at_risk:
            exit_code = 1
            print(f"{name}: AT RISK — {report.reason}")
            continue
        names = report.names()
        print(f"{name}: synced {len(names)} file(s) -> {report.destination}")
        for carried in names:
            print(f"  {carried}")

    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
