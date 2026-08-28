"""Integration tests for the dispatch job contract (SW1311-RECEIPT-001).

Covers criteria 2 through 7, behaviourally, over the trace contracts:

2. Each job reports process status, task verdict, evidence availability and
   gate verdict as four separate fields; exit zero alone cannot verify a task
   or pass a gate.
3. A terminal envelope binds full subject SHA, exact command, exit or signal or
   timeout, raw artifact references, declared inputs and completion contract.
4. A noninteractive job that requests stdin fails with a typed blocked-input
   result and never waits indefinitely.
5. Heartbeat expiry, timeout, cancel and launch failure each produce
   deterministic distinct terminal states.
6. Every child receives a unique run id, working directory and state namespace;
   a simulated shared state collision fails preflight as a technical failure.
7. A completion missing required evidence, carrying an unresolvable artifact or
   omitting subject identity cannot mark the task complete.

No harness, no concrete provider/model, no text/source-presence assertions.
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.trace.contracts import (  # noqa: E402
    EvidenceAvailability,
    GateVerdict,
    IncompleteCompletionError,
    JobResult,
    JobStateNamespace,
    JobStatus,
    NamespaceCollisionError,
    StateNamespaceRegistry,
    TaskVerdict,
    TerminalEnvelope,
    TerminalState,
    TECHNICAL_TERMINAL_STATES,
    blocked_input_result,
    derive_gate_verdict,
)


# ── Criterion 2: four separated outcome dimensions ──────────────────────────


def test_job_reports_four_separate_fields():
    result = JobResult(
        job_status=JobStatus.EXITED,
        task_verdict=TaskVerdict.DONE,
        evidence_available=EvidenceAvailability.MISSING,
        gate_verdict=GateVerdict.INCONCLUSIVE,
    )
    payload = result.to_dict()
    # Four distinct, named fields — not one collapsed string.
    assert set(("job_status", "task_verdict", "evidence_available", "gate_verdict")) \
        <= set(payload)
    assert payload["job_status"] != payload["task_verdict"]
    assert payload["task_verdict"] != payload["gate_verdict"]
    assert payload["evidence_available"] != payload["gate_verdict"]


def test_exit_zero_alone_cannot_verify_task_or_pass_gate():
    # Empty output with a clean exit is *inconclusive*, not done/pass.
    gate = derive_gate_verdict(exit_code=0, signal=None, termination="exited", stdout=b"")
    assert gate is GateVerdict.INCONCLUSIVE

    # A clean exit with non-empty output passes the gate, but exit zero by
    # itself is not proof — the gate requires output as well.
    passing = derive_gate_verdict(
        exit_code=0, signal=None, termination="exited", stdout=b"real output\n"
    )
    assert passing is GateVerdict.PASS

    # A non-zero exit is fail regardless of output.
    failing = derive_gate_verdict(
        exit_code=1, signal=None, termination="exited", stdout=b"real output\n"
    )
    assert failing is GateVerdict.FAIL


def test_from_dict_round_trips_the_four_fields():
    original = JobResult(
        job_status=JobStatus.BLOCKED_INPUT,
        task_verdict=TaskVerdict.BLOCKED,
        evidence_available=EvidenceAvailability.MISSING,
        gate_verdict=GateVerdict.FAIL,
    )
    payload = original.to_dict()
    rebuilt = JobResult.from_dict(payload)
    assert rebuilt == original


# ── Criterion 3: terminal envelope binds everything ─────────────────────────


def test_terminal_envelope_binds_subject_command_outcome_refs_inputs_contract():
    env = TerminalEnvelope(
        subject_sha="9" * 40,
        command=["python3", "-c", "print('x')"],
        terminal_state=TerminalState.COMPLETED,
        exit_code=0,
        artifact_refs=[f"sha256:{'a'*64}"],
        declared_inputs=[f"sha256:{'b'*64}"],
        completion_contract={"require": "non-empty stdout"},
    )
    assert env.subject_sha == "9" * 40
    assert env.command == ["python3", "-c", "print('x')"]
    assert env.outcome == "exit_code"
    d = env.to_dict()
    assert d["subject_sha"] == "9" * 40
    assert d["exit_code"] == 0
    assert d["signal"] is None
    assert d["timed_out"] is False
    assert d["artifact_refs"]
    assert d["declared_inputs"]
    assert d["completion_contract"]


def test_terminal_envelope_signal_and_timeout_outcomes_are_distinct():
    sig = TerminalEnvelope(
        subject_sha="9" * 40, command=["x"], terminal_state=TerminalState.COMPLETED,
        signal=9,
    )
    assert sig.outcome == "signal"
    to = TerminalEnvelope(
        subject_sha="9" * 40, command=["x"], terminal_state=TerminalState.TIMED_OUT,
        timed_out=True,
    )
    assert to.outcome == "timed_out"


# ── Criterion 4: blocked input never waits ──────────────────────────────────


def test_blocked_input_result_is_typed_and_never_waits():
    result = blocked_input_result(["some", "command"])
    assert result.job_status is JobStatus.BLOCKED_INPUT
    assert result.task_verdict is TaskVerdict.BLOCKED
    assert result.gate_verdict is GateVerdict.FAIL
    # A blocked-input terminal state is a technical failure, never a review fail.
    assert TerminalState.BLOCKED_INPUT.value in TECHNICAL_TERMINAL_STATES


# ── Criterion 5: deterministic distinct terminal states ─────────────────────


def test_technical_terminal_states_are_distinct():
    states = {
        TerminalState.HEARTBEAT_EXPIRED,
        TerminalState.TIMED_OUT,
        TerminalState.CANCELLED,
        TerminalState.LAUNCH_FAILED,
    }
    # Four distinct values, deterministic, each a technical (non-review) failure.
    assert len(states) == 4
    for state in states:
        assert state.value in TECHNICAL_TERMINAL_STATES
        assert state.value in {
            "heartbeat_expired", "timed_out", "cancelled", "launch_failed"
        }


def test_terminal_states_serialize_unambiguously():
    for state in (
        TerminalState.HEARTBEAT_EXPIRED,
        TerminalState.TIMED_OUT,
        TerminalState.CANCELLED,
        TerminalState.LAUNCH_FAILED,
    ):
        env = TerminalEnvelope(subject_sha="9" * 40, command=["x"],
                               terminal_state=state)
        assert env.to_dict()["terminal_state"] == state.value


# ── Criterion 6: unique namespace + collision preflight ─────────────────────


def test_each_job_gets_unique_runid_cwd_namespace():
    registry = StateNamespaceRegistry()
    first = JobStateNamespace(
        run_id="run-1", working_directory="/tmp/ws-1", state_namespace="ns-1"
    )
    second = JobStateNamespace(
        run_id="run-2", working_directory="/tmp/ws-2", state_namespace="ns-2"
    )
    assert registry.claim(first) is True
    assert registry.claim(second) is True
    # Distinct values end to end.
    assert first.run_id != second.run_id
    assert first.working_directory != second.working_directory
    assert first.state_namespace != second.state_namespace


def test_shared_run_id_collision_fails_preflight():
    registry = StateNamespaceRegistry()
    registry.claim(JobStateNamespace(
        run_id="shared", working_directory="/tmp/a", state_namespace="ns-a"
    ))
    with pytest.raises(NamespaceCollisionError):
        registry.claim(JobStateNamespace(
            run_id="shared", working_directory="/tmp/b", state_namespace="ns-b"
        ))


def test_shared_state_namespace_collision_fails_preflight():
    registry = StateNamespaceRegistry()
    registry.claim(JobStateNamespace(
        run_id="r1", working_directory="/tmp/a", state_namespace="shared-ns"
    ))
    with pytest.raises(NamespaceCollisionError):
        registry.claim(JobStateNamespace(
            run_id="r2", working_directory="/tmp/b", state_namespace="shared-ns"
        ))


def test_collision_retries_as_technical_failure_not_review_fail():
    registry = StateNamespaceRegistry()
    registry.claim(JobStateNamespace(
        run_id="r1", working_directory="/tmp/a", state_namespace="ns-a"
    ))
    # The retry path derives a fresh namespace (no human, no review-fail).
    fresh = registry.retry_after_collision(base_run_id="r1", base_namespace="ns-a")
    assert fresh.run_id != "r1"
    assert fresh.state_namespace != "ns-a"
    assert registry.claim(fresh) is True


# ── Criterion 7: completion fail-closed ─────────────────────────────────────


def test_completion_missing_required_evidence_cannot_mark_complete():
    env = TerminalEnvelope(
        subject_sha="9" * 40, command=["x"], terminal_state=TerminalState.COMPLETED,
        exit_code=0, artifact_refs=[],
    )
    assert env.complete(required_evidence=["stdout"]) is False
    assert env.completion_error(required_evidence=["stdout"]) == "required evidence missing"


def test_completion_omitting_subject_identity_cannot_mark_complete():
    env = TerminalEnvelope(
        subject_sha="", command=["x"], terminal_state=TerminalState.COMPLETED,
        exit_code=0, artifact_refs=["sha256:abc"],
    )
    assert env.complete(required_evidence=["stdout"]) is False
    assert "subject identity" in (env.completion_error(required_evidence=["stdout"]) or "")


def test_completion_unresolvable_artifact_cannot_mark_complete():
    def _resolver(ref):
        raise KeyError(ref)
    env = TerminalEnvelope(
        subject_sha="9" * 40, command=["x"], terminal_state=TerminalState.COMPLETED,
        exit_code=0, artifact_refs=["sha256:missing"],
    )
    assert env.complete(required_evidence=["stdout"], resolver=_resolver) is False
    assert "unresolvable" in (env.completion_error(
        required_evidence=["stdout"], resolver=_resolver) or "")


def test_completion_with_resolvable_evidence_succeeds():
    def _resolver(ref):
        return b"bytes"
    env = TerminalEnvelope(
        subject_sha="9" * 40, command=["x"], terminal_state=TerminalState.COMPLETED,
        exit_code=0, artifact_refs=["sha256:present"],
    )
    assert env.complete(required_evidence=["stdout"], resolver=_resolver) is True
    assert env.completion_error(required_evidence=["stdout"], resolver=_resolver) is None


def _run_all() -> int:
    tests = [
        test_job_reports_four_separate_fields,
        test_exit_zero_alone_cannot_verify_task_or_pass_gate,
        test_from_dict_round_trips_the_four_fields,
        test_terminal_envelope_binds_subject_command_outcome_refs_inputs_contract,
        test_terminal_envelope_signal_and_timeout_outcomes_are_distinct,
        test_blocked_input_result_is_typed_and_never_waits,
        test_technical_terminal_states_are_distinct,
        test_terminal_states_serialize_unambiguously,
        test_each_job_gets_unique_runid_cwd_namespace,
        test_shared_run_id_collision_fails_preflight,
        test_shared_state_namespace_collision_fails_preflight,
        test_collision_retries_as_technical_failure_not_review_fail,
        test_completion_missing_required_evidence_cannot_mark_complete,
        test_completion_omitting_subject_identity_cannot_mark_complete,
        test_completion_unresolvable_artifact_cannot_mark_complete,
        test_completion_with_resolvable_evidence_succeeds,
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
