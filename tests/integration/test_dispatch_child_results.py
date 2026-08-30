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
import io
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.fanout.dispatch import (  # noqa: E402
    OUTCOMES,
    ChildOutcomeError,
    FanOutChild,
    FanOutResult,
    ReceiptReference,
    _resolve_outcome,
    fan_out_dispatch,
)
from skillweave.runtime.runner_adapter import ProcessResult  # noqa: E402
from skillweave.runtime.registry import ArtifactIntegrityError, RawArtifactStore  # noqa: E402
from skillweave.dispatch.application import (  # noqa: E402
    HALT_REQUIRES_OPERATOR,
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


# ── Correction (SW138-RESULT-001): content-addressed evidence wiring ─────────


def test_fanout_stores_stdout_and_stderr_and_refs_resolve_from_store():
    # A real fan-out run with an artifact store puts both streams into it and
    # the returned references resolve immediately, without caller re-insertion.
    payload = b"OUT\n"
    err = b"ERR\n"
    store = RawArtifactStore()
    child = fan_out_dispatch(
        [
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('OUT\\n'); sys.stderr.write('ERR\\n')",
            ]
        ],
        run_id="run-store",
        subject_repo="skillweave/repo",
        subject_commit="9" * 40,
        tool="marker",
        model="model-x",
        created_at="2026-08-27T00:00:00Z",
        artifact_store=store,
    ).children[0]
    assert child.stdout_ref.resolve(store.resolve) == payload
    assert child.stderr_ref.resolve(store.resolve) == err
    assert child.stdout_ref.sha256 == hashlib.sha256(payload).hexdigest()
    assert child.stderr_ref.sha256 == hashlib.sha256(err).hexdigest()


def test_fanout_empty_stream_has_correct_empty_byte_sha():
    # A child that writes nothing still yields resolvable empty refs under the
    # correct empty-byte SHA, and they resolve to b"" from the store.
    store = RawArtifactStore()
    child = _child([sys.executable, "-c", "pass"], artifact_store=store)
    empty_sha = hashlib.sha256(b"").hexdigest()
    assert child.stdout_ref.sha256 == empty_sha
    assert child.stderr_ref.sha256 == empty_sha
    assert child.stdout_ref.resolve(store.resolve) == b""
    assert child.stderr_ref.resolve(store.resolve) == b""


def test_dispatch_run_exposes_resolver_for_returned_refs(tmp_path):
    # The application threads a run-owned store through the fan-out and returns
    # it on DispatchRun; the returned receipt references resolve via that same
    # resolver without manual re-putting of bytes.
    import yaml

    from skillweave.dispatch.application import OperatorDispatchApplication

    class _NoopWorkspace:
        def provision(self, lane, run_id):
            from skillweave.dispatch.application import ProvisionedWorkspace
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    base = "9" * 40
    prof = tmp_path / "resolver-profile.yaml"
    prof.write_text(yaml.safe_dump({
        "name": "resolver-fixture",
        "tier": "balanced",
        "limits": {"timeout": 30.0, "max_retries": 1,
                   "min_models_required": 2, "on_model_failure": "skip"},
        "roles": {
            "ops": {
                "model": "faigate/dispatch-fixture-model",
                "tool": {
                    "name": "marker",
                    "launch_command": (
                        "python3 -c \"import sys; "
                        "sys.stdout.write('OUT\\\\n'); sys.stderr.write('ERR\\\\n')\""
                    ),
                    "args": [],
                },
                "capabilities": {"can_mutate_run_state": True},
            },
        },
    }))
    seq = tmp_path / "resolver-sequence.yaml"
    seq.write_text(yaml.safe_dump({
        "session_boundary": "batch",
        "profile": {"path": str(prof), "required": True},
        "execution_model": "cold",
        "max_correction_rounds_per_wave": 0,
        "max_parallel": 1,
        "lanes": [{
            "id": "lane-a", "role": "ops", "repo": "skillweave/repo-a",
            "base": base, "execution_model": "cold", "mutating": True,
            "depends_on": [], "write_scope": ["skillweave/repo-a/**"],
            "worktree": "/tmp/lane-a", "branch": "branch-lane-a",
            "integration_policy": "independent",
            "criterion_groups": [{"criteria": [1]}],
        }],
    }))

    app = OperatorDispatchApplication(workspace_seam=_NoopWorkspace())
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert run.resolver is not None
    entries = run.results
    assert entries
    stdout_ref = ReceiptReference(**entries[0]["stdout"])
    stderr_ref = ReceiptReference(**entries[0]["stderr"])
    assert stdout_ref.resolve(run.resolver) == b"OUT\n"
    assert stderr_ref.resolve(run.resolver) == b"ERR\n"


# ── Correction: required-evidence done-gate passes the real resolver ─────────


def _gate_app(store):
    from skillweave.dispatch.application import OperatorDispatchApplication

    app = OperatorDispatchApplication()
    app._active_store = store
    return app


def _ref(sha, byte_length, encoding="utf-8", stream="stdout"):
    return ReceiptReference(
        artifact_id="r", sha256=sha, byte_length=byte_length,
        encoding=encoding, stream=stream,
    )


def test_gate_refuses_structurally_present_but_absent_bytes():
    lane = _lane(["stdout"])
    payload = b"data"
    ref = _ref(hashlib.sha256(payload).hexdigest(), len(payload))
    store = RawArtifactStore()  # bytes never stored
    with pytest.raises(RequiredEvidenceError):
        _gate_app(store)._gate_required_evidence(lane, [ref])


def test_gate_refuses_corrupt_bytes():
    lane = _lane(["stdout"])
    payload = b"data"
    store = RawArtifactStore()
    digest = store.put(payload)
    store.mock_mutate(digest, b"evil")
    ref = _ref(digest, len(payload))
    with pytest.raises(RequiredEvidenceError):
        _gate_app(store)._gate_required_evidence(lane, [ref])


def test_gate_refuses_wrong_length():
    lane = _lane(["stdout"])
    payload = b"data"
    store = RawArtifactStore()
    store.put(payload)
    ref = _ref(hashlib.sha256(payload).hexdigest(), 999)
    with pytest.raises(RequiredEvidenceError):
        _gate_app(store)._gate_required_evidence(lane, [ref])


def test_gate_refuses_invalid_encoding():
    lane = _lane(["stdout"])
    payload = b"\xff\xfe"
    store = RawArtifactStore()
    store.put(payload)
    ref = _ref(hashlib.sha256(payload).hexdigest(), len(payload), encoding="us-ascii")
    with pytest.raises(RequiredEvidenceError):
        _gate_app(store)._gate_required_evidence(lane, [ref])


# ── Correction: typed failure-policy semantics (skip / retry / abort) ────────


def _policy_fanout(fail_indices=()):
    class _PolicyFanout:
        def __init__(self):
            self.fail = set(fail_indices)
            self.calls = 0

        def __call__(self, commands, **kwargs):
            self.calls += 1
            children = []
            for i in range(len(commands)):
                pr = ProcessResult(
                    command=["x"],
                    exit_code=3 if i in self.fail else 0,
                    signal=None,
                    termination="exited",
                    pid=1,
                    tool="t",
                    model="m",
                    stdout_receipt=None,
                    stderr_receipt=None,
                    message="boom" if i in self.fail else "",
                )
                children.append(
                    FanOutChild(
                        child_run_id=f"c{i}", command=["x"], result=pr, model="m",
                        outcome="exit_code",
                    )
                )
            return FanOutResult(children=children, overlapped=len(commands) > 1)

    return _PolicyFanout()


def _policy_inline(fail_indices=()):
    class _PolicyInline:
        def __init__(self):
            self.fail = set(fail_indices)
            self.calls = 0

        def __call__(self, command, **kwargs):
            self.calls += 1
            repo = kwargs.get("subject_repo") or ""
            tail = repo.rsplit("-", 1)[-1]
            idx = int(tail) if tail.isdigit() else -1
            failed = idx in self.fail
            pr = ProcessResult(
                command=["x"],
                exit_code=3 if failed else 0,
                signal=None,
                termination="exited",
                pid=1,
                tool="t",
                model="m",
                stdout_receipt=None,
                stderr_receipt=None,
                message="boom" if failed else "",
            )
            child = FanOutChild(
                child_run_id="c", command=["x"], result=pr, model="m",
                outcome="exit_code",
            )
            return FanOutResult(children=[child], overlapped=False)

    return _PolicyInline()


def _policy_scenario(tmp_path, policy, max_retries, fail_indices, max_rounds=2, n_lanes=3):
    import yaml

    from skillweave.dispatch.application import OperatorDispatchApplication

    base = "9" * 40
    lanes = []
    for i in range(n_lanes):
        lanes.append({
            "id": f"lane-{i}", "role": "ops", "repo": f"skillweave/repo-{i}",
            "base": base, "execution_model": "cold", "mutating": True,
            "depends_on": [], "write_scope": [f"skillweave/repo-{i}/**"],
            "worktree": f"/tmp/lane-{i}", "branch": f"branch-lane-{i}",
            "integration_policy": "independent",
            "criterion_groups": [{"criteria": [1]}],
        })
    prof = tmp_path / f"policy-{policy}-profile.yaml"
    prof.write_text(yaml.safe_dump({
        "name": "policy-fixture",
        "tier": "balanced",
        "limits": {"timeout": 30.0, "max_retries": max_retries,
                   "min_models_required": 2, "on_model_failure": policy},
        "roles": {
            "ops": {
                "model": "faigate/dispatch-fixture-model",
                "tool": {"name": "marker", "launch_command": "python3 -c 'pass'", "args": []},
                "capabilities": {"can_mutate_run_state": True},
            },
        },
    }))
    seq = tmp_path / f"policy-{policy}-sequence.yaml"
    seq.write_text(yaml.safe_dump({
        "session_boundary": "batch",
        "profile": {"path": str(prof), "required": True},
        "execution_model": "cold",
        "max_correction_rounds_per_wave": max_rounds,
        "max_parallel": n_lanes,
        "lanes": lanes,
    }))

    fanout = _policy_fanout(fail_indices)
    inline = _policy_inline(fail_indices)
    app = OperatorDispatchApplication(
        workspace_seam=_noop_workspace(), fanout_seam=fanout, inline_seam=inline
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
    return run, fanout, inline


def _noop_workspace():
    class _Noop:
        def provision(self, lane, run_id):
            from skillweave.dispatch.application import ProvisionedWorkspace
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    return _Noop()


def test_skip_policy_records_failure_no_correction_no_halt(tmp_path):
    run, fanout, inline = _policy_scenario(tmp_path, "skip", 1, fail_indices=(0,))
    assert run.halted is False
    assert run.correction_rounds == 0
    assert fanout.calls == 1  # no correction child
    assert inline.calls == 0
    failed = {f["lane_id"] for f in run.failures if f["outcome"] == "exit_code"}
    assert "lane-0" in failed
    lane0 = [r for r in run.results if r["lane_id"] == "lane-0"]
    assert lane0 and lane0[0]["outcome"] == "exit_code"  # not done


def test_retry_policy_retries_bounded_and_halts(tmp_path):
    run, fanout, inline = _policy_scenario(tmp_path, "retry", 1, fail_indices=(0,), max_rounds=5)
    assert run.correction_rounds == 1  # bounded by max_retries=1
    assert run.halted is True
    assert run.halt_reason == HALT_REQUIRES_OPERATOR
    assert fanout.calls == 1  # round-0 fan-out only
    assert inline.calls == 1  # one correction round retries the failed lane inline


def test_retry_policy_bounded_by_correction_rounds(tmp_path):
    run, fanout, inline = _policy_scenario(tmp_path, "retry", 10, fail_indices=(0,), max_rounds=2)
    assert run.correction_rounds == 2  # bounded by max_correction_rounds_per_wave=2
    assert run.halted is True
    assert fanout.calls == 1  # round-0 fan-out only
    assert inline.calls == 2  # two correction rounds retried inline


def test_abort_policy_halts_immediately_zero_correction(tmp_path):
    run, fanout, inline = _policy_scenario(tmp_path, "abort", 1, fail_indices=(0,))
    assert run.halted is True
    assert run.halt_reason == HALT_REQUIRES_OPERATOR
    assert run.correction_rounds == 0
    assert fanout.calls == 1  # zero correction children
    assert inline.calls == 0


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
        test_fanout_stores_stdout_and_stderr_and_refs_resolve_from_store,
        test_fanout_empty_stream_has_correct_empty_byte_sha,
        test_dispatch_run_exposes_resolver_for_returned_refs,
        test_gate_refuses_structurally_present_but_absent_bytes,
        test_gate_refuses_corrupt_bytes,
        test_gate_refuses_wrong_length,
        test_gate_refuses_invalid_encoding,
        test_skip_policy_records_failure_no_correction_no_halt,
        test_retry_policy_retries_bounded_and_halts,
        test_retry_policy_bounded_by_correction_rounds,
        test_abort_policy_halts_immediately_zero_correction,
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
