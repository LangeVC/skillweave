"""CLI surface for the async run lifecycle.

Provides three subcommands:

- ``skillweave start --async <command>`` — start a durable background run.
- ``skillweave inspect <run-id>`` — snapshot or follow run state/events.
- ``skillweave kill <run-id> <pid>`` — graceful-then-forced kill.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .handle import start_async, inspect_run, kill_run, InspectMode
from .store import StalePidError, RunStateError


def build_start_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave start",
        description="Start a command, optionally as a durable background run.",
    )
    parser.add_argument(
        "--async",
        action="store_true",
        dest="async_run",
        help="Start the command in a non-blocking detached subprocess.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run ID (default: auto-generated uuid hex).",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The command to run (use -- to separate).",
    )
    return parser


def build_inspect_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave inspect",
        description="Inspect a run's state and events.  Supports snapshot or follow mode.",
    )
    parser.add_argument(
        "run_id",
        help="The run ID to inspect (returned by `skillweave start --async`).",
    )
    parser.add_argument(
        "--follow", "-f",
        action="store_true",
        help="Keep tailing events until the run finishes (like tail -f).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.25,
        help="Seconds between poll cycles in follow mode (default: 0.25).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Maximum seconds to wait in follow mode (default: no timeout).",
    )
    return parser


def build_kill_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave kill",
        description="Kill a run by its ID and recorded PID.  "
                     "Idempotent: graceful (SIGTERM) then forced (SIGKILL).",
    )
    parser.add_argument(
        "run_id",
        help="The run ID to kill.",
    )
    parser.add_argument(
        "pid",
        type=int,
        help="The PID to kill.  Must match the recorded PID.",
    )
    return parser


def main_start(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_start_parser()
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]

    if not command:
        parser.error("A command to run is required.")

    if not args.async_run:
        # Without --async, delegate to subprocess.run synchronously
        import subprocess
        result = subprocess.run(command)
        return result.returncode

    handle = start_async(
        command=command,
        run_id=args.run_id,
    )
    sys.stdout.write(json.dumps(handle.to_dict(), sort_keys=True) + "\n")
    return 0


def main_inspect(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_inspect_parser()
    args = parser.parse_args(argv)

    mode = InspectMode.FOLLOW if args.follow else InspectMode.SNAPSHOT

    return inspect_run(
        run_id=args.run_id,
        mode=mode,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
    )


def main_kill(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_kill_parser()
    args = parser.parse_args(argv)

    try:
        result = kill_run(
            run_id=args.run_id,
            pid=args.pid,
        )
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
        return 0
    except StalePidError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except RunStateError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
