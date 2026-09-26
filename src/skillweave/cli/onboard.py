"""The ``skillweave onboard`` CLI subcommand.

Usage::

    skillweave onboard [--preview] [--role <role>] [--purpose <purpose>]
                       [--autonomy <autonomy>] [--risk-boundary <boundary>]

Runs operator onboarding through :class:`OnboardingService`. Without
``--preview``, persists the durable profile to ``skillweave.config/`` and the
generated state to ``.skillweave/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from skillweave.onboarding import OnboardingService


def build_onboard_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave onboard",
        description=(
            "Run operator onboarding — collect role, purpose, autonomy and "
            "risk boundary; detect phase; persist durable and generated state."
        ),
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview the result without persisting anything",
    )
    parser.add_argument(
        "--role",
        default=None,
        choices=["operator", "developer", "reviewer", "researcher"],
        help="Operator role (default: developer)",
    )
    parser.add_argument(
        "--purpose",
        default=None,
        choices=["build", "review", "research", "operate"],
        help="Onboarding purpose (default: build)",
    )
    parser.add_argument(
        "--autonomy",
        default=None,
        choices=["guided", "supervised", "autonomous"],
        help="Desired autonomy (default: guided)",
    )
    parser.add_argument(
        "--risk-boundary",
        "--risk_boundary",
        dest="risk_boundary",
        default=None,
        choices=["conservative", "medium", "unicorn"],
        help="Risk boundary (default: conservative)",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        metavar="PATH",
        help="Project root directory (defaults to current directory)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_onboard_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return 2

    overrides: dict[str, str] = {}
    for field in ("role", "purpose", "autonomy", "risk_boundary"):
        value = getattr(args, field, None)
        if value is not None:
            overrides[field] = value

    service = OnboardingService(args.project_root)

    try:
        if args.preview:
            result = service.preview(**overrides)
        else:
            result = service.apply(**overrides)
    except Exception as exc:
        print(f"Onboarding failed: {exc}", file=sys.stderr)
        return 1

    payload = result.to_payload()
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0
