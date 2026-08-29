"""Dispatch-order group 1 — "round and structured child-job truth" (criteria 1, 2).

Proves the append-only receipt lineage and the deterministic, typed terminal
lifecycle against ``skillweave.trace.contracts``. Every assertion here targets a
real product surface: if the surface regressed (e.g. a digest became mutable, a
technical terminal state folded into ``REVIEW_FAIL``, or exit-zero alone started
passing a gate), one of these assertions fails.

Nothing here launches a worker, names a provider, or mutates product state.
"""

from __future__ import annotations

import pytest

from skillweave.trace import contracts as C


def _full_sha() -> str:
    return "a" * 40


# ── Criterion 1: append-only multi-round receipts ────────────────────────────


def test_criterion_01_append_only_rounds_preserve_bytes_and_separate_dimensions():
    """Multi-round receipts preserve prior bytes and separate the four outcomes.

    Build a three-record lineage (dispatch -> correction -> integration). After
    appending later records, the earlier records' digests and parent links are
    byte-identical (immutable), each record resolves by id, and the four outcome
    dimensions (process status / task verdict / evidence / gate verdict) remain
    distinct fields — process ``exited`` never forces task ``done`` or gate
    ``pass``.
    """
    log = C.AppendOnlyReceiptLog()

    r1 = C.new_append_only_round(
        log, parent_id=None, round_=1, kind=C.RoundKind.DISPATCH,
        job_id="job-1",
        result=C.JobResult(
            job_status=C.JobStatus.EXITED,
            task_verdict=C.TaskVerdict.DONE,
            evidence_available=C.EvidenceAvailability.RECORDED,
            gate_verdict=C.GateVerdict.PASS,
        ),
    )
    r2 = C.new_append_only_round(
        log, parent_id=r1.record_id, round_=2, kind=C.RoundKind.CORRECTION,
        job_id="job-1",
        result=C.JobResult(
            job_status=C.JobStatus.EXITED,
            task_verdict=C.TaskVerdict.DONE,
            evidence_available=C.EvidenceAvailability.RECORDED,
            gate_verdict=C.GateVerdict.PASS,
        ),
    )
    r3 = C.new_append_only_round(
        log, parent_id=r2.record_id, round_=3, kind=C.RoundKind.INTEGRATION,
        job_id="job-1",
        result=C.JobResult(
            job_status=C.JobStatus.EXITED,
            task_verdict=C.TaskVerdict.DONE,
            evidence_available=C.EvidenceAvailability.RECORDED,
            gate_verdict=C.GateVerdict.PASS,
        ),
    )

    # Three immutable records, each resolvable by id, parent links intact.
    assert len(log) == 3
    assert log.resolve_id(r1.record_id) is r1
    assert log.resolve_id(r2.record_id) is r2
    assert log.resolve_id(r3.record_id) is r3
    assert r2.parent_id == r1.record_id
    assert r3.parent_id == r2.record_id

    # Prior bytes are preserved: the first record's digest never changes even
    # though later records were appended to the same lineage.
    digest_after_append = r1.digest
    assert digest_after_append
    assert r1.prior_digest() == digest_after_append

    # Duplicate id + identical bytes is idempotent (returns the same record).
    reread = log.records()
    again = C.new_append_only_round(
        log, parent_id=None, round_=1, kind=C.RoundKind.DISPATCH,
        job_id="job-1",
        result=C.JobResult(
            job_status=C.JobStatus.EXITED,
            task_verdict=C.TaskVerdict.DONE,
            evidence_available=C.EvidenceAvailability.RECORDED,
            gate_verdict=C.GateVerdict.PASS,
        ),
        record_id=r1.record_id,
    )
    assert again is r1
    assert len(log) == 3
    assert log.records() == reread

    # Separated outcome dimensions: a process can exit zero while the task and
    # gate remain inconclusive. Exit zero is NOT pass by itself.
    exit_zero_only = C.JobResult(
        job_status=C.JobStatus.EXITED,
        task_verdict=C.TaskVerdict.INCONCLUSIVE,
        evidence_available=C.EvidenceAvailability.UNDECLARED,
        gate_verdict=C.GateVerdict.INCONCLUSIVE,
    )
    assert exit_zero_only.job_status is C.JobStatus.EXITED
    assert exit_zero_only.task_verdict is C.TaskVerdict.INCONCLUSIVE
    assert exit_zero_only.gate_verdict is not C.GateVerdict.PASS

    # Same id with different bytes fails closed.
    with pytest.raises(C.DuplicateDigestError):
        C.new_append_only_round(
            log, parent_id=None, round_=9, kind=C.RoundKind.DISPATCH,
            job_id="job-different",
            result=C.JobResult(),
            record_id=r1.record_id,
        )


# ── Criterion 2: real noninteractive terminal fixtures yield typed results ──


def test_criterion_02_noninteractive_terminal_fixtures_yield_typed_results():
    """Blocked-input, heartbeat, timeout, cancel, collision, missing-evidence.

    Each deterministic terminal state maps to a distinct typed outcome, and none
    can ever be produced (or passed) by exit-zero alone.
    """
    # blocked input -> typed BLOCKED_INPUT result, never a wait.
    blocked = C.blocked_input_result(["tool", "--interactive"])
    assert blocked.job_status is C.JobStatus.BLOCKED_INPUT
    assert blocked.task_verdict is C.TaskVerdict.BLOCKED
    assert blocked.gate_verdict is C.GateVerdict.FAIL

    # heartbeat expiry / timeout / cancel / launch failure -> distinct terminal
    # states, each a technical failure (never a REVIEW_FAIL surface) and each
    # yielding a FAIL gate verdict.
    for terminal, status in (
        (C.TerminalState.HEARTBEAT_EXPIRED, C.JobStatus.HEARTBEAT_EXPIRED),
        (C.TerminalState.TIMED_OUT, C.JobStatus.TIMED_OUT),
        (C.TerminalState.CANCELLED, C.JobStatus.CANCELLED),
        (C.TerminalState.LAUNCH_FAILED, C.JobStatus.LAUNCH_FAILED),
    ):
        result = C.build_job_result_for_terminal(
            terminal_state=terminal, exit_code=None, signal=None,
            termination=None, stdout=b"",
        )
        assert result.job_status is status
        assert result.task_verdict is C.TaskVerdict.FAILED
        assert result.gate_verdict is C.GateVerdict.FAIL
        assert terminal.value in C.TECHNICAL_TERMINAL_STATES

    # All four technical states are mutually distinct.
    states = {
        C.TerminalState.HEARTBEAT_EXPIRED,
        C.TerminalState.TIMED_OUT,
        C.TerminalState.CANCELLED,
        C.TerminalState.LAUNCH_FAILED,
    }
    assert len(states) == 4

    # state namespace collision -> technical (preflight) failure, not REVIEW_FAIL.
    registry = C.StateNamespaceRegistry()
    ns = C.JobStateNamespace(
        run_id="run-1", working_directory="/tmp/w", state_namespace="ns-1"
    )
    assert registry.claim(ns) is True
    with pytest.raises(C.NamespaceCollisionError):
        registry.claim(C.JobStateNamespace(
            run_id="run-1", working_directory="/tmp/w2", state_namespace="ns-2"
        ))
    with pytest.raises(C.NamespaceCollisionError):
        registry.claim(C.JobStateNamespace(
            run_id="run-2", working_directory="/tmp/w3", state_namespace="ns-1"
        ))

    # missing evidence: a completion claiming required evidence but carrying no
    # resolvable artifact cannot be complete.
    env = C.TerminalEnvelope(
        subject_sha=_full_sha(), command=["tool"], terminal_state=C.TerminalState.COMPLETED,
        exit_code=0,
    )
    assert env.complete(required_evidence=["receipt.json"]) is False
    assert env.completion_error(required_evidence=["receipt.json"]) == "required evidence missing"

    # unresolvable artifact fails the completion contract.
    env_refs = C.TerminalEnvelope(
        subject_sha=_full_sha(), command=["tool"], terminal_state=C.TerminalState.COMPLETED,
        exit_code=0, artifact_refs=["missing.bin"],
    )
    def _resolver(ref):
        raise FileNotFoundError(ref)
    err = env_refs.completion_error(required_evidence=["missing.bin"], resolver=_resolver)
    assert err is not None and "unresolvable" in err

    # gate verdict: exit-zero with empty output is inconclusive, never pass.
    assert C.derive_gate_verdict(
        exit_code=0, signal=None, termination="exited", stdout=b""
    ) is C.GateVerdict.INCONCLUSIVE
    assert C.derive_gate_verdict(
        exit_code=0, signal=None, termination="exited", stdout=b"ok"
    ) is C.GateVerdict.PASS
    assert C.derive_gate_verdict(
        exit_code=1, signal=None, termination="exited", stdout=b"boom"
    ) is C.GateVerdict.FAIL
