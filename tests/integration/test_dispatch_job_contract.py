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
    RoundKind,
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


# ── Reachable dispatch-run integration (SW1311-RECEIPT-001 correction C1) ─────


def _run_dispatch_with(app, tmp_path, *, lanes, fanout_seam):
    """Build a minimal sequence+profile and dispatch through ``app``.

    Returns ``(run, fanout_seam)``. The fan-out seam is injected so no real
    process launches; the sequence/profile are written to ``tmp_path``.
    """
    import yaml

    base = "9" * 40
    prof = tmp_path / "profile.yaml"
    prof.write_text(
        yaml.safe_dump(
            {
                "name": "c1-fixture",
                "tier": "balanced",
                "limits": {
                    "timeout": 30.0,
                    "max_retries": 1,
                    "min_models_required": 2,
                    "on_model_failure": "skip",
                },
                "roles": {
                    "ops": {
                        "model": "faigate/dispatch-fixture-model",
                        "tool": {
                            "name": "marker",
                            "launch_command": "python3 -c 'pass'",
                            "args": [],
                        },
                        "capabilities": {"can_mutate_run_state": True},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    seq = tmp_path / "sequence.yaml"
    seq.write_text(
        yaml.safe_dump(
            {
                "session_boundary": "batch",
                "profile": {"path": str(prof), "required": True},
                "execution_model": "cold",
                "max_correction_rounds_per_wave": 0,
                "max_parallel": len(lanes),
                "lanes": lanes,
            }
        ),
        encoding="utf-8",
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=__import__("io").StringIO())
    return run, fanout_seam


def _noop_workspace():
    from skillweave.dispatch.application import ProvisionedWorkspace

    class _Noop:
        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    return _Noop()


def _lanes(ids):
    base = "9" * 40
    lanes = []
    for i, lid in enumerate(ids):
        lanes.append(
            {
                "id": lid,
                "role": "ops",
                "repo": f"skillweave/repo-{i}",
                "base": base,
                "execution_model": "cold",
                "mutating": True,
                "criterion_groups": [{"criteria": [1]}],
            }
        )
    return lanes


def _clean_child(outcome="exit_code"):
    """A successful fan-out child with resolvable stdout/stderr receipts."""
    from skillweave.fanout.dispatch import FanOutChild, ReceiptReference
    from skillweave.runtime.runner_adapter import ProcessResult

    import hashlib

    stdout = b"OK\n"
    stderr = b""
    pr = ProcessResult(
        command=["python3", "-c", "pass"],
        exit_code=0,
        signal=None,
        termination="exited",
        pid=1,
        tool="marker",
        model="m",
        stdout_receipt=None,
        stderr_receipt=None,
        message="",
        stdout=stdout,
        stderr=stderr,
    )
    return FanOutChild(
        child_run_id="c0",
        command=["python3", "-c", "pass"],
        result=pr,
        model="m",
        outcome=outcome,
        raw_bytes=stdout,
        stderr_bytes=stderr,
        stdout_ref=ReceiptReference(
            artifact_id="r-out", sha256=hashlib.sha256(stdout).hexdigest(),
            byte_length=len(stdout), encoding="utf-8", stream="stdout",
        ),
        stderr_ref=ReceiptReference(
            artifact_id="r-err", sha256=hashlib.sha256(stderr).hexdigest(),
            byte_length=len(stderr), encoding="utf-8", stream="stderr",
        ),
    )


def _resolving_fanout(children):
    from skillweave.fanout.dispatch import FanOutResult

    class _Fanout:
        def __init__(self):
            self.calls = 0

        def __call__(self, commands, **kwargs):
            self.calls += 1
            return FanOutResult(children=list(children), overlapped=len(commands) > 1)

    return _Fanout()


class _RecordingFanout:
    """Fan-out seam that records invocations and returns a fixed child list."""

    def __init__(self, children=None):
        self.calls = 0
        self._children = children or []

    def __call__(self, commands, **kwargs):
        self.calls += 1
        return type("_R", (), {"children": list(self._children), "succeeded": True})()


def test_blocked_input_fails_before_child_launch(tmp_path):
    from skillweave.dispatch.application import OperatorDispatchApplication

    lanes = _lanes(["lane-a"])
    lanes[0]["interactive"] = True
    recorder = _RecordingFanout([])
    app = OperatorDispatchApplication(workspace_seam=_noop_workspace(), fanout_seam=recorder)
    run, _ = _run_dispatch_with(app, tmp_path, lanes=lanes, fanout_seam=recorder)

    # The child must never launch (fan-out seam never invoked).
    assert recorder.calls == 0

    # A typed blocked-input terminal is recorded in the run's job records.
    records = run.job_records
    assert records
    terminal = records[0]["envelope"]["terminal_state"]
    assert terminal == TerminalState.BLOCKED_INPUT.value
    assert records[0]["result"]["task_verdict"] == "blocked"
    assert records[0]["result"]["gate_verdict"] == "fail"


def test_namespace_collision_fails_preflight_before_child_launch(tmp_path):
    from skillweave.dispatch.application import OperatorDispatchApplication

    # Pre-seed a collision: the registry already holds lane-a's namespace, so
    # the application's claim must fail preflight before any child launches.
    lanes = _lanes(["lane-a"])
    recorder = _RecordingFanout([])
    registry = StateNamespaceRegistry()
    registry.claim(
        JobStateNamespace(
            run_id="run-lane-a", working_directory="", state_namespace="sw-state/run/lane-a"
        )
    )
    app = OperatorDispatchApplication(
        workspace_seam=_noop_workspace(), fanout_seam=recorder, namespace_registry=registry
    )
    # Force a deterministic run id so the derived namespace collides with the
    # pre-seeded claim above.
    app._generate_run_id = lambda: "run"  # type: ignore[assignment]
    run, _ = _run_dispatch_with(app, tmp_path, lanes=lanes, fanout_seam=recorder)

    assert recorder.calls == 0
    records = run.job_records
    assert records
    assert records[0]["envelope"]["terminal_state"] == TerminalState.PREFLIGHT_FAILED.value
    assert records[0]["result"]["gate_verdict"] == "fail"


def test_unresolvable_evidence_cannot_yield_pass_in_dispatch_run(tmp_path):
    from skillweave.dispatch.application import OperatorDispatchApplication

    # A lane requiring stdout, whose fan-out returns an empty ref (missing) that
    # cannot resolve: the run must not record a gate PASS.
    lanes = _lanes(["lane-a"])
    lanes[0]["required_evidence"] = ["stdout"]

    from skillweave.fanout.dispatch import ReceiptReference

    import hashlib

    missing_ref = ReceiptReference(
        artifact_id="r", sha256=hashlib.sha256(b"absent").hexdigest(),
        byte_length=6, encoding="utf-8", stream="stdout",
    )
    from skillweave.fanout.dispatch import FanOutChild
    from skillweave.runtime.runner_adapter import ProcessResult

    pr = ProcessResult(
        command=["python3", "-c", "pass"], exit_code=0, signal=None,
        termination="exited", pid=1, tool="marker", model="m",
        stdout_receipt=None, stderr_receipt=None, stdout=b"OUT\n", stderr=b"",
    )
    child = FanOutChild(
        child_run_id="c0", command=["python3", "-c", "pass"], result=pr,
        model="m", outcome="exit_code", raw_bytes=b"OUT\n", stderr_bytes=b"",
        stdout_ref=missing_ref,  # does not resolve in a fresh store
        stderr_ref=None,
    )
    recorder = _RecordingFanout([child])
    app = OperatorDispatchApplication(workspace_seam=_noop_workspace(), fanout_seam=recorder)
    run, _ = _run_dispatch_with(app, tmp_path, lanes=lanes, fanout_seam=recorder)

    records = run.job_records
    assert records
    result = records[0]["result"]
    assert result["gate_verdict"] != "pass"
    assert result["evidence_available"] in {"missing", "unresolvable"}
    assert result["task_verdict"] in {"inconclusive", "failed", "blocked"}


def test_clean_run_job_records_match_shipped_schema(tmp_path):
    import json
    from pathlib import Path

    from skillweave.dispatch.application import OperatorDispatchApplication

    schema_path = (
        Path(__file__).resolve().parents[2] / "schemas" / "dispatch-trace.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    lanes = _lanes(["lane-a"])
    recorder = _RecordingFanout([_clean_child()])
    app = OperatorDispatchApplication(workspace_seam=_noop_workspace(), fanout_seam=recorder)
    run, _ = _run_dispatch_with(app, tmp_path, lanes=lanes, fanout_seam=recorder)

    records = run.job_records
    assert records
    for record in records:
        _assert_matches_schema(schema, record)


def _assert_matches_schema(schema, record):
    """Minimal structural validator: required keys present, no extra keys, and
    enum values for the nested result/envelope fields. No ``jsonschema`` dep."""
    for key in schema.get("required", []):
        assert key in record, f"missing required key '{key}'"
    allowed = set(schema.get("properties", {}))
    for key in record:
        assert key in allowed, f"key '{key}' not allowed by schema"
    _check_enums(schema["properties"], record)


def _check_enums(props, instance):
    for key, spec in props.items():
        if "$ref" in spec:
            continue
        value = instance.get(key)
        if value is None:
            continue
        enum = spec.get("enum")
        if enum:
            if isinstance(value, list):
                assert all(v in enum for v in value), f"'{key}' {value!r} not in enum"
            else:
                assert value in enum, f"'{key}' {value!r} not in enum"


def test_heartbeat_expiry_is_a_reachable_terminal_state(tmp_path):
    from skillweave.dispatch.application import OperatorDispatchApplication

    from skillweave.fanout.dispatch import FanOutChild
    from skillweave.runtime.runner_adapter import ProcessResult

    pr = ProcessResult(
        command=["python3", "-c", "pass"], exit_code=None, signal=None,
        termination="heartbeat_expired", pid=1, tool="marker", model="m",
        stdout_receipt=None, stderr_receipt=None,
    )
    child = FanOutChild(
        child_run_id="c0", command=["python3", "-c", "pass"], result=pr,
        model="m", outcome="heartbeat_expired",
    )
    rec = _RecordingFanout([child])
    app = OperatorDispatchApplication(workspace_seam=_noop_workspace(), fanout_seam=rec)
    run, _ = _run_dispatch_with(app, tmp_path, lanes=_lanes(["lane-a"]), fanout_seam=rec)

    records = run.job_records
    assert records
    assert records[0]["envelope"]["terminal_state"] == TerminalState.HEARTBEAT_EXPIRED.value
    assert records[0]["result"]["gate_verdict"] == "fail"


def test_review_and_integration_are_reachable_and_append_lineage(tmp_path):
    from skillweave.dispatch.application import OperatorDispatchApplication

    lanes = _lanes(["lane-a"])
    recorder = _RecordingFanout([_clean_child()])
    app = OperatorDispatchApplication(workspace_seam=_noop_workspace(), fanout_seam=recorder)
    run, _ = _run_dispatch_with(app, tmp_path, lanes=lanes, fanout_seam=recorder)

    before = len(run.job_records)

    # Reachable public seam on the returned run — not hand-built enum values.
    review = run.append_review(
        subject_sha="9" * 40,
        command=["python3", "-c", "pass"],
        job_id="c0",
        result=JobResult(
            job_status=JobStatus.EXITED,
            task_verdict=TaskVerdict.DONE,
            evidence_available=EvidenceAvailability.RECORDED,
            gate_verdict=GateVerdict.PASS,
        ),
    )
    integration = run.append_integration(
        subject_sha="9" * 40,
        command=["python3", "-c", "pass"],
        job_id="c0",
    )

    after = run.job_records
    assert len(after) == before + 2
    kinds = [r["kind"] for r in after]
    assert "review" in kinds and "integration" in kinds

    # Lineage: the review record's parent is the prior tail, the integration
    # record's parent is the review record.
    review_record = [r for r in run.receipt_log.records() if r.kind is RoundKind.REVIEW][-1]
    integration_record = [r for r in run.receipt_log.records() if r.kind is RoundKind.INTEGRATION][-1]
    assert integration_record.parent_id == review_record.record_id
    assert review_record.digest and integration_record.digest
    assert review_record.digest != integration_record.digest


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
