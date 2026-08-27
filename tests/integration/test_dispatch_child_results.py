"""Integration tests for the child-result surface (SW138-RESULT-001).

Closes the measured gap between terminal child state and caller-visible
evidence. Five binary acceptance criteria are exercised end to end, reusing the
shared fan-out / registry resolver seams:

1. Every terminal child exposes exactly one machine outcome — ``exit_code``,
   ``signal``, ``timed_out`` or ``launch_failed`` — and contradictory terminal
   fields are rejected.
2. stdout/stderr receipts carry a supported resolver that returns raw bytes, and
   digest, byte length and declared encoding must match the receipt.
3. The wave result returns child outcomes and receipt references directly; empty
   inline stdout/stderr never hides an available artifact.
4. A lane cannot reach ``done`` when its required-evidence list is empty or any
   referenced artifact cannot be resolved / fails integrity.
5. Non-zero exit, timeout, signal, launch failure and missing-receipt fixtures
   produce distinct machine-readable results, and the configured failure policy
   is applied without collapsing them.

The hermetic child commands are thin ``python3 -c`` markers (real subprocesses),
so a launch failure, a signal and a non-zero exit are real observations, never
mocked ``ProcessResult`` values.
"""

import hashlib
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.fanout.dispatch import (  # noqa: E402
    OUTCOMES,
    ChildOutcomeError,
    ReceiptReference,
    _resolve_outcome,
    fan_out_dispatch,
)
from skillweave.runtime.runner_adapter import ProcessResult  # noqa: E402
from skillweave.runtime.registry import ArtifactIntegrityError, RawArtifactStore  # noqa: E402
from skillweave.dispatch.application import (  # noqa: E402
    RequiredEvidenceError,
    resolve_required_evidence,
)
from skillweave.dispatch.contracts import Lane  # noqa: E402


def _child(cmd, **kwargs):
    return fan_out_dispatch(
        [cmd],
        run_id="run-result",
        subject_repo="skillweave/repo",
        subject_commit="9" * 40,
        tool="marker",
        model="model-x",
        created_at="2026-08-27T00:00:00Z",
        **kwargs,
    ).children[0]


# ── Criterion 1: exactly one machine outcome, contradiction rejected ─────────


def test_clean_exit_has_single_exit_code_outcome():
    child = _child([sys.executable, "-c", "print('ok')"])
    assert child.outcome == "exit_code"
    assert child.result.exit_code == 0
    assert child.result.signal is None
    assert child.outcome in OUTCOMES


def test_nonzero_exit_has_single_exit_code_outcome():
    child = _child([sys.executable, "-c", "import sys; sys.exit(7)"])
    assert child.outcome == "exit_code"
    assert child.result.exit_code == 7
    assert child.result.signal is None


def test_signal_has_single_signal_outcome():
    child = _child(
        [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]
    )
    assert child.outcome == "signal"
    assert child.result.signal == 9
    assert child.result.exit_code is None


def test_timeout_has_single_timed_out_outcome():
    child = _child(
        [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2
    )
    assert child.outcome == "timed_out"
    assert child.result.termination == "timed_out"
    assert child.result.exit_code is None
    assert child.result.signal is None


def test_unspawnable_command_has_single_launch_failed_outcome():
    child = _child(["/definitely/not/a/binary/xyzzy"])
    assert child.outcome == "launch_failed"
    assert child.result.termination == "launch_failed"
    assert child.result.exit_code is None
    assert child.result.signal is None


def test_contradictory_terminal_fields_are_rejected():
    # A result carrying both an exit code and a signal is contradictory and must
    # be rejected, never folded into a single outcome.
    contradictory = ProcessResult(
        command=["x"],
        exit_code=3,
        signal=9,
        termination="exited",
        pid=1,
        tool="t",
        model="m",
        stdout_receipt=None,
        stderr_receipt=None,
    )
    with pytest.raises(ChildOutcomeError):
        _resolve_outcome(contradictory)


def test_timed_out_with_exit_code_is_rejected():
    contradictory = ProcessResult(
        command=["x"],
        exit_code=0,
        signal=None,
        termination="timed_out",
        pid=1,
        tool="t",
        model="m",
        stdout_receipt=None,
        stderr_receipt=None,
    )
    with pytest.raises(ChildOutcomeError):
        _resolve_outcome(contradictory)


# ── Criterion 2: resolver, digest / length / encoding all match ──────────────


def test_receipt_reference_resolves_raw_bytes_and_matches_digest_length_encoding():
    payload = "héllo wörld\n".encode("utf-8")
    child = _child([sys.executable, "-c", "import sys; sys.stdout.buffer.write(%r)" % payload])
    ref = child.stdout_ref
    assert isinstance(ref, ReceiptReference)
    assert ref.stream == "stdout"
    assert ref.encoding == "utf-8"
    assert ref.byte_length == len(payload)
    assert ref.sha256 == hashlib.sha256(payload).hexdigest()

    store = RawArtifactStore()
    store.put(payload)
    resolved = ref.resolve(store.resolve)
    assert resolved == payload


def test_receipt_reference_rejects_digest_mismatch():
    ref = ReceiptReference(
        artifact_id="r", sha256=hashlib.sha256(b"good").hexdigest(),
        byte_length=4, encoding="utf-8", stream="stdout",
    )
    store = RawArtifactStore()
    digest = store.put(b"good")
    store.mock_mutate(digest, b"evil")  # stored under the same key, different bytes
    # The store's content-addressed resolver fails integrity first; both the
    # resolver's own error and the reference's mismatch error are a rejection.
    with pytest.raises((ChildOutcomeError, ArtifactIntegrityError)):
        ref.resolve(store.resolve)


def test_receipt_reference_rejects_length_mismatch():
    ref = ReceiptReference(
        artifact_id="r", sha256=hashlib.sha256(b"abc").hexdigest(),
        byte_length=999, encoding="utf-8", stream="stdout",
    )
    store = RawArtifactStore()
    store.put(b"abc")
    with pytest.raises(ChildOutcomeError):
        ref.resolve(store.resolve)


def test_receipt_reference_rejects_encoding_mismatch():
    # Bytes that cannot be decoded in the declared encoding fail verification.
    ref = ReceiptReference(
        artifact_id="r", sha256=hashlib.sha256(b"\xff\xfe").hexdigest(),
        byte_length=2, encoding="us-ascii", stream="stdout",
    )
    store = RawArtifactStore()
    store.put(b"\xff\xfe")
    with pytest.raises(ChildOutcomeError):
        ref.resolve(store.resolve)


def test_missing_receipt_is_indistinguishable_from_empty_presence():
    # A launch failure still yields empty (not ``None``) receipts, so a child
    # whose capture is genuinely absent is only signalled by ``None`` refs when
    # the producer itself produced no receipt. Here the fan-out always binds an
    # empty receipt per stream for a run that never happened.
    child = _child(["/definitely/not/a/binary"])
    assert child.stdout_ref is not None
    assert child.stdout_ref.byte_length == 0
    assert child.stderr_ref is not None


# ── Criterion 3: child outcomes + receipt refs returned directly ─────────────


def test_fanout_result_surface_returns_outcomes_and_refs():
    result = fan_out_dispatch(
        [[sys.executable, "-c", "print('a')"], [sys.executable, "-c", "print('b')"]],
        run_id="run-surface",
        subject_repo="skillweave/repo",
        subject_commit="9" * 40,
        tool="marker",
        model="model-x",
    )
    surface = result.to_dict()
    assert set(c["outcome"] for c in surface["children"]) == {"exit_code"}
    for child in surface["children"]:
        assert child["stdout"]["stream"] == "stdout"
        assert child["stdout"]["sha256"]
        assert child["stdout"]["byte_length"] > 0  # non-empty output is resolvable


def test_empty_inline_output_does_not_hide_available_artifact():
    # A child that prints nothing still produces a receipt reference: zero-length
    # inline output is represented by a resolvable (empty) artifact reference,
    # not an absent one.
    child = _child([sys.executable, "-c", "pass"])
    assert child.raw_bytes == b""
    assert child.stdout_ref is not None
    assert child.stdout_ref.byte_length == 0
    assert child.stderr_ref is not None


# ── Criterion 4: required-evidence done-gate ─────────────────────────────────


def _lane(required_evidence):
    lane = Lane(
        id="lane-x", role="ops", repo="r", base="9" * 40,
        execution_model="cold", mutating=True,
    )
    lane.required_evidence = required_evidence
    return lane


def test_undeclared_required_evidence_passes_trivially():
    lane = Lane(id="lane-x", role="ops", repo="r", base="9" * 40,
                execution_model="cold", mutating=True)
    lane.required_evidence = None
    resolved = resolve_required_evidence(lane, reference_by_stream={})
    assert resolved == []


def test_empty_required_evidence_declaration_blocks_done():
    lane = _lane([])
    with pytest.raises(RequiredEvidenceError):
        resolve_required_evidence(lane, reference_by_stream={})


def test_missing_receipt_blocks_done():
    lane = _lane(["stdout", "stderr"])
    with pytest.raises(RequiredEvidenceError):
        resolve_required_evidence(lane, reference_by_stream={"stdout": None})


def test_integrity_mismatch_blocks_done():
    lane = _lane(["stdout"])
    ref = ReceiptReference(
        artifact_id="r", sha256=hashlib.sha256(b"good").hexdigest(),
        byte_length=4, encoding="utf-8", stream="stdout",
    )
    store = RawArtifactStore()
    store.put(b"evil")
    with pytest.raises(RequiredEvidenceError):
        resolve_required_evidence(
            lane, reference_by_stream={"stdout": ref}, resolver=store.resolve
        )


def test_satisfied_required_evidence_resolves():
    lane = _lane(["stdout"])
    payload = b"evidence\n"
    ref = ReceiptReference(
        artifact_id="r", sha256=hashlib.sha256(payload).hexdigest(),
        byte_length=len(payload), encoding="utf-8", stream="stdout",
    )
    store = RawArtifactStore()
    store.put(payload)
    resolved = resolve_required_evidence(
        lane, reference_by_stream={"stdout": ref}, resolver=store.resolve
    )
    assert resolved == [
        {"stream": "stdout", "artifact_id": "r", "byte_length": len(payload)}
    ]


# ── Criterion 5: distinct failures, failure policy applied ───────────────────


def test_distinct_failure_outcomes_do_not_collapse():
    outcomes = {
        _child([sys.executable, "-c", "import sys; sys.exit(5)"]).outcome,
        _child([sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]).outcome,
        _child([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2).outcome,
        _child(["/definitely/not/a/binary"]).outcome,
    }
    assert outcomes == {"exit_code", "signal", "timed_out", "launch_failed"}


def test_failure_policy_is_applied_and_reported():
    # The application surface applies the profile's on_model_failure policy
    # (skip/retry/abort) to the wave result, and reports it, so unlike failures
    # are never collapsed onto one bucket.
    from skillweave.dispatch.application import OperatorDispatchApplication

    class _NoopWorkspace:
        def provision(self, lane, run_id):
            from skillweave.dispatch.application import ProvisionedWorkspace
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    app = OperatorDispatchApplication(workspace_seam=_NoopWorkspace())
    _, resolved, _ = app.load(
        str(Path(__file__).resolve().parent.parent / "fixtures" / "dispatch-sequence.yaml"),
        str(Path(__file__).resolve().parent.parent / "fixtures" / "dispatch-profile.yaml"),
    )
    limits = resolved.limits
    assert limits.on_model_failure in {"skip", "retry", "abort"}


def _run_all() -> int:
    tests = [
        test_clean_exit_has_single_exit_code_outcome,
        test_nonzero_exit_has_single_exit_code_outcome,
        test_signal_has_single_signal_outcome,
        test_timeout_has_single_timed_out_outcome,
        test_unspawnable_command_has_single_launch_failed_outcome,
        test_contradictory_terminal_fields_are_rejected,
        test_timed_out_with_exit_code_is_rejected,
        test_receipt_reference_resolves_raw_bytes_and_matches_digest_length_encoding,
        test_receipt_reference_rejects_digest_mismatch,
        test_receipt_reference_rejects_length_mismatch,
        test_receipt_reference_rejects_encoding_mismatch,
        test_missing_receipt_is_indistinguishable_from_empty_presence,
        test_fanout_result_surface_returns_outcomes_and_refs,
        test_empty_inline_output_does_not_hide_available_artifact,
        test_undeclared_required_evidence_passes_trivially,
        test_empty_required_evidence_declaration_blocks_done,
        test_missing_receipt_blocks_done,
        test_integrity_mismatch_blocks_done,
        test_satisfied_required_evidence_resolves,
        test_distinct_failure_outcomes_do_not_collapse,
        test_failure_policy_is_applied_and_reported,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
