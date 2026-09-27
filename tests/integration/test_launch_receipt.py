"""Integration tests for the launch receipt contract (SW-157-LAUNCH-001).

Tests the focused positive case (seal/canonicalize round-trip) and the
negative cases:

1. **Missing digest**: canonicalize raises ``LaunchReceiptError``.
2. **Tampered digest**: a post-hoc mutation of a digested field raises
   ``LaunchReceiptTamperError``.
3. **Unavailable without limits**: an unavailable receipt with no limits is
   rejected.
4. **Unavailable with success outcome**: an unavailable result cannot have
   a success outcome.
5. **Available without commands**: an available receipt with no commands is
   rejected.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.launch.deployment import (
    SCHEMA_VERSION,
    RESULT_AVAILABLE,
    RESULT_UNAVAILABLE,
    OUTCOME_SUCCESS,
    OUTCOME_FAILURE,
    OUTCOME_UNAVAILABLE,
    LaunchReceipt,
    LaunchReceiptError,
    LaunchReceiptTamperError,
    compute_digest,
    seal,
    canonicalize,
)

_SHA256 = "a" * 64


def _make_valid_receipt() -> dict:
    """Return a sealed, valid available receipt (as a Python dict)."""
    return seal(
        {
            "schema_version": SCHEMA_VERSION,
            "result": {"status": RESULT_AVAILABLE, "summary": "deployment complete"},
            "target": {
                "environment": "staging",
                "version": "1.5.5",
                "host": "staging.skillweave.dev",
            },
            "artifact": {
                "artifact_id": "skillweave-v1.5.5",
                "sha256": _SHA256,
            },
            "commands": [
                {"command": "gh workflow run deploy.yml", "exit": 0},
                {"command": "health_check staging.skillweave.dev/health", "exit": 0},
            ],
            "outcome": {
                "status": OUTCOME_SUCCESS,
                "health": {"status": "ok", "response_time_ms": 142},
            },
            "provenance": {
                "launcher": "skillweave-launch",
                "run_id": "run-001",
                "produced_at": "2026-09-27T12:00:00Z",
                "model": "byteplus-deepseek-flash",
            },
            "limits": [],
        }
    )


# ---------------------------------------------------------------------------
# Positive: seal → canonicalize round-trip
# ---------------------------------------------------------------------------


def test_launch_receipt_seal_canonicalize_round_trip():
    """A sealed receipt canonicalizes successfully and the digest matches."""
    sealed = _make_valid_receipt()
    receipt = canonicalize(sealed)
    assert isinstance(receipt, LaunchReceipt)
    assert receipt.digest == sealed["digest"]
    assert receipt.digest == compute_digest(sealed)
    assert receipt.payload["schema_version"] == SCHEMA_VERSION
    assert receipt.payload["result"]["status"] == RESULT_AVAILABLE
    assert receipt.payload["outcome"]["status"] == OUTCOME_SUCCESS


def test_launch_receipt_to_dict_includes_digest():
    """to_dict() round-trips through canonicalize."""
    sealed = _make_valid_receipt()
    d = sealed  # already a dict
    receipt = canonicalize(d)
    restored = receipt.to_dict()
    assert "digest" in restored
    assert restored["digest"] == sealed["digest"]


def test_launch_receipt_to_json_is_valid_json():
    """to_json() produces parseable JSON with digest."""
    sealed = _make_valid_receipt()
    receipt = canonicalize(sealed)
    parsed = json.loads(receipt.to_json())
    assert parsed["digest"] == sealed["digest"]


# ---------------------------------------------------------------------------
# Negative: missing digest
# ---------------------------------------------------------------------------


def test_receipt_without_digest_raises_error():
    """canonicalize() raises LaunchReceiptError when digest is missing."""
    sealed = _make_valid_receipt()
    del sealed["digest"]
    with pytest.raises(LaunchReceiptError, match="missing 'digest'"):
        canonicalize(sealed)


# ---------------------------------------------------------------------------
# Negative: tampered digest
# ---------------------------------------------------------------------------


def test_tampered_digest_raises_tamper_error():
    """A post-hoc mutation of a digested field raises LaunchReceiptTamperError."""
    sealed = _make_valid_receipt()
    sealed["outcome"] = {"status": OUTCOME_FAILURE, "health": {"status": "down", "response_time_ms": 999}}
    with pytest.raises(LaunchReceiptTamperError, match="digest mismatch"):
        canonicalize(sealed)


# ---------------------------------------------------------------------------
# Negative: unavailable without limits
# ---------------------------------------------------------------------------


def test_unavailable_receipt_without_limits_raises_error():
    """An unavailable receipt must declare at least one limit."""
    with pytest.raises(LaunchReceiptError, match="unavailable receipt must declare at least one limit"):
        seal(
            {
                "schema_version": SCHEMA_VERSION,
                "result": {"status": RESULT_UNAVAILABLE, "summary": "could not deploy"},
                "target": {
                    "environment": "staging",
                    "version": "1.5.5",
                },
                "artifact": {
                    "artifact_id": "skillweave-v1.5.5",
                    "sha256": _SHA256,
                },
                "commands": [],
                "outcome": {"status": OUTCOME_UNAVAILABLE},
                "provenance": {
                    "launcher": "skillweave-launch",
                    "run_id": "run-002",
                    "produced_at": "2026-09-27T12:00:00Z",
                },
                "limits": [],
            }
        )


# ---------------------------------------------------------------------------
# Negative: unavailable with success outcome
# ---------------------------------------------------------------------------


def test_unavailable_result_with_success_outcome_raises_error():
    """An unavailable result cannot have a success outcome."""
    with pytest.raises(LaunchReceiptError, match="unavailable result cannot have a success outcome"):
        seal(
            {
                "schema_version": SCHEMA_VERSION,
                "result": {"status": RESULT_UNAVAILABLE, "summary": "could not deploy"},
                "target": {
                    "environment": "staging",
                    "version": "1.5.5",
                },
                "artifact": {
                    "artifact_id": "skillweave-v1.5.5",
                    "sha256": _SHA256,
                },
                "commands": [],
                "outcome": {"status": OUTCOME_SUCCESS},
                "provenance": {
                    "launcher": "skillweave-launch",
                    "run_id": "run-003",
                    "produced_at": "2026-09-27T12:00:00Z",
                },
                "limits": ["deployment target unreachable"],
            }
        )


# ---------------------------------------------------------------------------
# Negative: available without commands
# ---------------------------------------------------------------------------


def test_available_receipt_without_commands_raises_error():
    """An available receipt must declare at least one command."""
    with pytest.raises(LaunchReceiptError, match="available receipt must declare at least one command"):
        seal(
            {
                "schema_version": SCHEMA_VERSION,
                "result": {"status": RESULT_AVAILABLE, "summary": "deployment ok"},
                "target": {
                    "environment": "staging",
                    "version": "1.5.5",
                },
                "artifact": {
                    "artifact_id": "skillweave-v1.5.5",
                    "sha256": _SHA256,
                },
                "commands": [],
                "outcome": {"status": OUTCOME_SUCCESS},
                "provenance": {
                    "launcher": "skillweave-launch",
                    "run_id": "run-004",
                    "produced_at": "2026-09-27T12:00:00Z",
                },
                "limits": [],
            }
        )
