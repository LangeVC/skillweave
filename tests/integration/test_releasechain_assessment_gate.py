"""Integration tests for the releasechain assessment gate (SW-157-REL-001).

Proves that ``AssessmentGate`` blocks on each of the four negative cases:

1. **Missing receipt**: a required ``.json`` file does not exist — blocked.
2. **Stale receipt**: ``provenance.produced_at`` exceeds the staleness threshold
   — blocked.
3. **Mismatched receipt**: the sha256 digest does not match the payload —
   blocked (tamper-evident).
4. **Tampered receipt**: a post-hoc mutation of a digested field raises
   ``AssessmentTamperError`` — blocked.

Also proves the gate has no cleanup authority: it is read-only and never
writes, deletes, or mutates receipts or workspace state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.assessment_contracts import (
    SCHEMA_VERSION,
    RESULT_AVAILABLE,
    seal,
)
from skillweave.release.assessment_gate import AssessmentGate

_SHA = "0ef44d4ae2d41fb608c01b3d729995ffee5c22ae"
_SHA256 = "a" * 64


def _make_valid_receipt() -> dict:
    """Return a sealed, valid available receipt (as a Python dict)."""
    return seal(
        {
            "schema_version": SCHEMA_VERSION,
            "result": {"status": RESULT_AVAILABLE, "summary": "all clear"},
            "subject": {
                "full_sha": _SHA,
                "repo": "skillweave/skillweave",
                "ref": "main",
            },
            "sources": [
                {"path": "src/skillweave/release/assessment_gate.py", "sha256": _SHA256}
            ],
            "commands": [
                {"command": "pytest tests/integration/test_releasechain_assessment_gate.py", "exit": 0}
            ],
            "findings": [
                {"id": "F-1", "severity": "info", "summary": "no issues"}
            ],
            "limits": ["read-only gate; no runtime execution beyond focused tests"],
            "provenance": {
                "assessor": "sw-157-rel-001",
                "run_id": "op-SW-157-REL-001",
                "produced_at": "2026-09-27T00:00:00Z",
                "model": "byteplus-deepseek-flash",
            },
        }
    )


def _write_receipt(receipts_dir: Path, filename: str, data: dict) -> Path:
    """Write a receipt dict as JSON to ``receipts_dir / filename``."""
    receipts_dir.mkdir(parents=True, exist_ok=True)
    path = receipts_dir / filename
    path.write_text(json.dumps(data, sort_keys=True))
    return path


# ── Criterion 1: missing receipt must block ────────────────────────────────


def test_missing_receipt_blocks(tmp_path: Path) -> None:
    """A required receipt that does not exist blocks the gate."""
    gate = AssessmentGate(project_root=tmp_path, receipts_dir=tmp_path / "assessments")
    result = gate.verify(required_ids=["assessment-a"])
    assert not result.passed
    assert result.failed == 1
    assert result.validated == 0
    assert "blocked" in result.detail


# ── Criterion 2: stale receipt must block ──────────────────────────────────


def test_stale_receipt_blocks(tmp_path: Path) -> None:
    """A receipt whose produced_at exceeds max_age_seconds blocks the gate."""
    receipt = _make_valid_receipt()
    receipts_dir = tmp_path / "assessments"
    _write_receipt(receipts_dir, "assessment-a.json", receipt)

    gate = AssessmentGate(
        project_root=tmp_path,
        receipts_dir=receipts_dir,
        max_age_seconds=0,
    )
    result = gate.verify()
    assert not result.passed
    assert result.failed == 1
    assert "stale" in result.receipts[0].detail.lower()


# ── Criterion 3: mismatched receipt must block ─────────────────────────────


def test_mismatched_receipt_blocks(tmp_path: Path) -> None:
    """A receipt whose digest does not match its payload blocks the gate."""
    receipt = _make_valid_receipt()
    # Corrupt the digest so it no longer matches the payload.
    receipt["digest"] = "b" * 64
    receipts_dir = tmp_path / "assessments"
    _write_receipt(receipts_dir, "assessment-a.json", receipt)

    gate = AssessmentGate(project_root=tmp_path, receipts_dir=receipts_dir)
    result = gate.verify()
    assert not result.passed
    assert result.failed == 1
    assert "digest mismatch" in result.receipts[0].detail


# ── Criterion 4: tampered receipt must block ───────────────────────────────


def test_tampered_receipt_blocks(tmp_path: Path) -> None:
    """A receipt whose status is flipped post-seal blocks the gate."""
    receipt = _make_valid_receipt()
    # Flip the status (a digested field) — canonicalize() raises
    # AssessmentTamperError.
    receipt["result"]["status"] = "unavailable"
    receipts_dir = tmp_path / "assessments"
    _write_receipt(receipts_dir, "assessment-a.json", receipt)

    gate = AssessmentGate(project_root=tmp_path, receipts_dir=receipts_dir)
    result = gate.verify()
    assert not result.passed
    assert result.failed == 1
    assert "digest mismatch" in result.receipts[0].detail


# ── No cleanup authority ───────────────────────────────────────────────────


def test_gate_has_no_cleanup_authority(tmp_path: Path) -> None:
    """The gate is read-only: it never writes, deletes, or mutates state."""
    receipt = _make_valid_receipt()
    receipts_dir = tmp_path / "assessments"
    _write_receipt(receipts_dir, "assessment-a.json", receipt)

    # Snapshot directory state before verification.
    before = set(receipts_dir.iterdir())

    gate = AssessmentGate(project_root=tmp_path, receipts_dir=receipts_dir)
    result = gate.verify()
    assert result.passed

    # Snapshot directory state after verification.
    after = set(receipts_dir.iterdir())
    assert before == after, "gate mutated receipt directory"

    # Confirm the receipt content is unchanged.
    content = json.loads((receipts_dir / "assessment-a.json").read_text())
    assert content == receipt


# ── Positive case: valid receipt passes ────────────────────────────────────


def test_valid_receipt_passes(tmp_path: Path) -> None:
    """A valid, non-stale receipt passes the gate."""
    receipt = _make_valid_receipt()
    receipts_dir = tmp_path / "assessments"
    _write_receipt(receipts_dir, "assessment-a.json", receipt)

    gate = AssessmentGate(project_root=tmp_path, receipts_dir=receipts_dir)
    result = gate.verify()
    assert result.passed
    assert result.validated == 1
    assert result.failed == 0
