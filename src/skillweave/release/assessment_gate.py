"""Release assessment gate (SW-157-REL-001).

Validates assessment receipts before release — a read-only gate that checks
for missing, stale, mismatched, and tampered receipts. Fails closed.

The gate loads receipt JSON files from ``.skillweave/assessments/``, validates
each through ``skillweave.assessment_contracts.canonicalize()`` (which verifies
the sha256 content digest), and optionally enforces a staleness policy based on
``provenance.produced_at``.

The gate has **no cleanup authority**: it reads and validates only. It never
writes, deletes, or mutates receipts or workspace state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skillweave.assessment_contracts import (
    AssessmentError,
    AssessmentReceipt,
    AssessmentTamperError,
    canonicalize,
)


@dataclass
class ReceiptResult:
    """Validation result for a single receipt file."""

    path: str
    passed: bool = False
    detail: str = ""
    receipt: AssessmentReceipt | None = None


@dataclass
class AssessmentGateResult:
    """Aggregate result of the assessment gate check.

    ``passed`` is ``True`` only when every receipt validates and none are
    missing, stale, mismatched or tampered.
    """

    passed: bool = False
    total: int = 0
    validated: int = 0
    failed: int = 0
    receipts: list[ReceiptResult] = field(default_factory=list)
    detail: str = ""


class AssessmentGate:
    """Read-only release gate over assessment receipts.

    Loads ``.json`` receipt files from ``receipts_dir`` (default:
    ``<project_root>/.skillweave/assessments/``), validates each via the
    tamper-evident contract, and rejects any that are missing, stale,
    mismatched, or tampered.

    Parameters
    ----------
    project_root:
        Project root directory. Defaults to ``Path.cwd()``.
    receipts_dir:
        Explicit path to receipts directory. Defaults to
        ``<project_root>/.skillweave/assessments/``.
    max_age_seconds:
        If set, any receipt whose ``provenance.produced_at`` is older than
        this threshold (relative to the current UTC time) is rejected as stale.
    """

    def __init__(
        self,
        project_root: str | Path | None = None,
        receipts_dir: str | Path | None = None,
        max_age_seconds: int | None = None,
    ) -> None:
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self._receipts_dir = (
            Path(receipts_dir)
            if receipts_dir
            else self.project_root / ".skillweave" / "assessments"
        )
        self._max_age_seconds = max_age_seconds

    def verify(self, required_ids: list[str] | None = None) -> AssessmentGateResult:
        """Load and validate all assessment receipts.

        Returns fail-closed: any missing, stale, mismatched, or tampered
        receipt sets ``passed`` to ``False``.

        Parameters
        ----------
        required_ids:
            Optional list of receipt file stems (without ``.json``) that must
            exist. Missing required IDs are reported as failures.
        """
        required = set(required_ids or [])
        result = AssessmentGateResult()

        found_ids: set[str] = set()

        if self._receipts_dir.is_dir():
            receipt_files = sorted(self._receipts_dir.glob("*.json"))
            result.total = len(receipt_files)

            for rf in receipt_files:
                receipt_result = self._validate_receipt(rf)
                result.receipts.append(receipt_result)
                if receipt_result.passed and receipt_result.receipt is not None:
                    found_ids.add(rf.stem)
                    result.validated += 1
                else:
                    result.failed += 1

        # Check for missing required IDs that were not found among validated
        # receipt files — this runs even when the directory does not exist.
        missing = required - found_ids
        for mid in sorted(missing):
            result.receipts.append(
                ReceiptResult(
                    path=f"(required) {mid}",
                    passed=False,
                    detail=f"Required assessment receipt not found: {mid}",
                )
            )
            result.failed += 1

        result.passed = result.failed == 0
        if not result.passed:
            failures = [r for r in result.receipts if not r.passed]
            result.detail = (
                f"Assessment gate blocked: {len(failures)} failure(s)"
            )
        else:
            result.detail = f"All {result.validated} receipt(s) valid"

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_receipt(self, path: Path) -> ReceiptResult:
        """Validate a single receipt file, returning a ``ReceiptResult``."""
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return ReceiptResult(path=str(path), passed=False, detail=str(exc))

        # canonicalize() validates structure AND verifies the sha256 digest.
        # A digest mismatch raises AssessmentTamperError; a structural
        # problem raises AssessmentError.
        try:
            receipt = canonicalize(raw)
        except AssessmentTamperError as exc:
            return ReceiptResult(path=str(path), passed=False, detail=str(exc))
        except AssessmentError as exc:
            return ReceiptResult(path=str(path), passed=False, detail=str(exc))

        # Optional staleness check: compare produced_at to current time.
        if self._max_age_seconds is not None:
            produced_at: str = (
                receipt.payload.get("provenance", {}).get("produced_at", "")
            )
            try:
                produced = datetime.fromisoformat(produced_at)
                age = (datetime.now(timezone.utc) - produced).total_seconds()
                if age > self._max_age_seconds:
                    return ReceiptResult(
                        path=str(path),
                        passed=False,
                        detail=(
                            f"Stale receipt: produced_at={produced_at}, "
                            f"age={age:.0f}s > "
                            f"max_age={self._max_age_seconds}s"
                        ),
                    )
            except (ValueError, TypeError) as exc:
                return ReceiptResult(
                    path=str(path),
                    passed=False,
                    detail=f"Cannot parse produced_at: {produced_at!r}: {exc}",
                )

        return ReceiptResult(
            path=str(path), passed=True, detail="valid", receipt=receipt
        )


__all__ = [
    "AssessmentGate",
    "AssessmentGateResult",
    "ReceiptResult",
]
