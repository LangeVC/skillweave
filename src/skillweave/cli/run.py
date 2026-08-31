"""The thin ``skillweave run`` command-line surface.

This module parses arguments and delegates execution to the Run Application Service.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from skillweave.dispatch.application import generate_run_id

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave run",
        description="Execute a single authoritative run command.",
    )
    parser.add_argument(
        "--tool",
        required=True,
        help="The tool being executed",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="The model identifier",
    )
    parser.add_argument(
        "--subject-repo",
        required=True,
        help="The repository the run operates on",
    )
    parser.add_argument(
        "--subject-commit",
        required=True,
        help="The exact commit SHA the run operates on",
    )
    parser.add_argument(
        "--db-path",
        default=":memory:",
        help="Path to the SQLite store (default: :memory:)",
    )
    parser.add_argument(
        "--artifacts-path",
        default=".skillweave/artifacts",
        help="Path to the raw artifact store directory",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The actual command to run (use -- to separate)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]

    if not command:
        parser.error("A command to run is required.")

    from skillweave.runtime.store import SQLiteRunStore
    from skillweave.runtime.journal import EventJournal
    from skillweave.runtime.registry import RawArtifactStore
    from skillweave.runsvc.service import RunApplicationService

    store = SQLiteRunStore(args.db_path)
    journal = EventJournal(args.db_path)
    raw_artifacts = RawArtifactStore(args.artifacts_path)

    svc = RunApplicationService(store, journal, raw_artifacts)
    run_id = generate_run_id()

    try:
        execution = svc.execute(
            command=command,
            run_id=run_id,
            tool=args.tool,
            model=args.model,
            subject_repo=args.subject_repo,
            subject_commit=args.subject_commit,
        )

        result_dict = {
            "run_id": execution.run.run_id,
            "state": execution.run.state,
            "gate_state": execution.gate_state,
            "raw_digest": execution.raw_digest,
            "verification": execution.verification,
        }
        sys.stdout.write(json.dumps(result_dict, sort_keys=True) + "\n")
        return 0

    except Exception as exc:
        error_dict = {
            "error": str(exc),
            "run_id": run_id,
        }
        sys.stderr.write(json.dumps(error_dict, sort_keys=True) + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
