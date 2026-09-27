"""The ``skillweave assess`` CLI subcommand.

Usage::

    skillweave assess --root <path> --request <path|->

Reads one declarative assessment request as JSON, runs the read-only
:class:`skillweave.assessment_service.AssessmentService` over it, and writes the
sealed assessment receipt to stdout as a single JSON document. The request is
supplied, never inferred: the subject SHA, ``produced_at`` and every source are
given by the caller, so the same request always seals to the same digest.

Exit semantics (the project convention, plus one deliberate refinement)::

    0  the assessment completed *and* its evidence resolved (``available``)
    1  the assessment produced an ``unavailable`` receipt -- a real outcome,
       not a CLI error; the receipt's ``limits`` say what could not be
       established
    2  user/config error (unreadable request, malformed request) or a system
       error (read-only authority refused)

The receipt status is the authority on *why*: ``1`` only says the assessment
could not establish everything it was asked to, and the emitted document names
the exact shortfall. That mirrors ``planning-sync``'s ``AT RISK`` exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from skillweave.assessment_contracts import RESULT_AVAILABLE, AssessmentError
from skillweave.assessment_service import (
    AssessmentRequest,
    AssessmentService,
    Finding,
    SourceSpec,
)

#: Exit codes.
EXIT_OK = 0
EXIT_UNAVAILABLE = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillweave assess",
        description=(
            "Run a read-only assessment over a declared request and emit the "
            "sealed, tamper-evident assessment receipt as JSON."
        ),
    )
    parser.add_argument(
        "--root",
        default=None,
        metavar="PATH",
        help="Assessment root the evidence is confined to (defaults to cwd).",
    )
    parser.add_argument(
        "--request",
        required=True,
        metavar="PATH",
        help="Path to the JSON assessment request, or '-' to read it from stdin.",
    )
    return parser


def _load_request_document(path: str, stdin: Any) -> Any:
    """Read the request JSON from ``path`` (or stdin when ``'-'``)."""
    if path == "-":
        text = stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def _as_mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object, got {type(value).__name__}")
    return value


def _opt_str(document: dict, key: str) -> Optional[str]:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key!r} must be a string, got {type(value).__name__}")
    return value


def _path_str(entry: dict, key: str, label: str) -> str:
    """Return ``entry[key]`` as a usable path string, or refuse it here.

    ``resolve_source`` joins this value onto the root, so a non-string (or a
    string carrying a NUL byte, which the filesystem layer rejects) would raise
    ``TypeError``/``ValueError`` deep inside the service -- past the CLI's
    ``except AssessmentError`` and out as a raw traceback with an exit code that
    collides with the documented ``unavailable`` outcome. Refusing it at the
    request boundary keeps the promise that a malformed request is exit 2.
    """
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}.{key} must be a non-empty string, got {value!r}")
    if "\x00" in value:
        raise ValueError(f"{label}.{key} must not contain a NUL byte")
    return value


def _build_request(document: Any) -> AssessmentRequest:
    """Turn a JSON request document into a typed :class:`AssessmentRequest`.

    Strict about shape: a malformed request is refused here (exit 2) rather than
    silently dropped into an ``unavailable`` receipt, because an unreadable
    request is not an assessment outcome -- it is a usage error.
    """
    document = _as_mapping(document, "assessment request")

    sources = []
    for index, entry in enumerate(document.get("sources") or []):
        entry = _as_mapping(entry, f"sources[{index}]")
        sources.append(
            SourceSpec(
                path=_path_str(entry, "path", f"sources[{index}]"),
                sha256=entry.get("sha256"),
            )
        )

    findings = []
    for index, entry in enumerate(document.get("findings") or []):
        entry = _as_mapping(entry, f"findings[{index}]")
        findings.append(
            Finding(id=entry["id"], severity=entry["severity"], summary=entry["summary"])
        )

    return AssessmentRequest(
        subject_sha=document["subject_sha"],
        assessor=document["assessor"],
        run_id=document["run_id"],
        produced_at=document["produced_at"],
        sources=tuple(sources),
        findings=tuple(findings),
        model=_opt_str(document, "model"),
        repo=_opt_str(document, "repo"),
        ref=_opt_str(document, "ref"),
        limits=tuple(document.get("limits") or []),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path.cwd().resolve()

    try:
        document = _load_request_document(args.request, sys.stdin)
        request = _build_request(document)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        sys.stderr.write(f"ERROR: could not read the assessment request: {exc}\n")
        return EXIT_ERROR

    try:
        receipt = AssessmentService(root).assess(request)
    except AssessmentError as exc:
        # A malformed request (e.g. a subject that is not a canonical SHA) is a
        # usage error, not an assessment outcome: report it as exit 2 like any
        # other unreadable request rather than letting a service exception
        # escape as a traceback. ReadOnlyViolation is itself an AssessmentError.
        sys.stderr.write(f"ERROR: {exc}\n")
        return EXIT_ERROR

    sys.stdout.write(receipt.to_json() + "\n")
    return EXIT_OK if receipt.payload["result"]["status"] == RESULT_AVAILABLE else EXIT_UNAVAILABLE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
