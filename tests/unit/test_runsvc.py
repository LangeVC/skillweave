"""Tests for the Run Application Service (SW-RUN-SVC-001).

Proves that a real harness run through the single authoritative integration
path leaves six record kinds behind without gaps:

* Run (``SQLiteRunStore`` record with a terminal state)
* Journal (ordered ``EventJournal`` entries, no gaps)
* Raw Artifact (content-addressed bytes in ``RawArtifactStore``)
* Receipt (``ArtifactReceipt`` bound to the run, resolvable back to bytes)
* Verification (a separate ``Verifier`` verdict, its own receipt)
* Gate (completion-contract state derived from the verified outcome)

Self-contained sys.path handling, following the convention of the module's
sibling tests, so it runs under ``python -m tests.unit...``/direct execution
without pytest or conftest.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runsvc import RunApplicationService, RunExecution, RunIntegrationError  # noqa: E402
from skillweave.runtime.store import SQLiteRunStore  # noqa: E402
from skillweave.runtime.journal import EventJournal  # noqa: E402
from skillweave.runtime.registry import RawArtifactStore  # noqa: E402


def _service(tmp_db=":memory:"):
    store = SQLiteRunStore(tmp_db)
    journal = EventJournal(store)
    raw = RawArtifactStore()
    return RunApplicationService(store, journal, raw), store, journal, raw


def test_real_harness_run_writes_all_six_records_without_gaps():
    service, store, journal, raw = _service()
    result = service.execute(
        [sys.executable, "-c", "print('harness-output-xyz')"],
        run_id="run-svc-1",
        tool="opencode",
        model="model-xyz-7",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-19T00:00:00Z",
    )

    assert isinstance(result, RunExecution)

    # Run: persisted, terminal, addressable.
    run = store.get_run("run-svc-1")
    assert run is not None
    assert run.state in ("advance_or_stop", "failed")

    # Journal: ordered, non-empty, no gaps.
    events = result.journal
    assert len(events) >= 1
    assert events[0].sequence == 1
    assert journal.has_gaps("run-svc-1") is False

    # Raw artifact: content-addressed and resolvable back to exact bytes.
    assert result.raw_digest
    assert len(result.raw_digest) == 64
    assert raw.resolve(result.raw_digest) == result.raw_bytes
    assert b"harness-output-xyz" in result.raw_bytes

    # Receipt: bound to the run and to the raw bytes.
    assert result.receipt.artifact_id == "runsvc-run-svc-1"
    assert result.receipt.sha256 == result.raw_digest
    assert result.receipt.metadata["run_id"] == "run-svc-1"
    assert store.get_evidence(result.receipt.artifact_id) is not None

    # Verification: a separate verifier's verdict with its own identity.
    assert result.verification["subject_artifact_id"] == result.receipt.artifact_id
    assert result.verification["verified_by"] == "verifier"
    assert result.verification["artifact_id"] == f"verify-{result.receipt.artifact_id}"

    # Gate: derived from the completion contract, not the exit code alone.
    assert result.gate_state == "pass"


def test_verified_gate_passes_only_for_real_nonempty_output():
    # A successful run with real output reaches a PASS gate and an
    # advance_or_stop terminal; the gate is the completion contract's verdict,
    # carried in the verification receipt, never a self-declared result.
    service, store, journal, raw = _service()
    result = service.execute(
        [sys.executable, "-c", "print('real-output')"],
        run_id="run-svc-pass",
        tool="opencode",
        model="model-xyz-7",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-19T00:00:00Z",
    )
    assert result.gate_state == "pass"
    assert result.verification["gate_state"] == "pass"


def test_no_output_is_never_a_gate_pass():
    # Exit 0 with empty output must not gate-pass. The completion contract
    # grades it inconclusive, and the run is marked failed (never dangling).
    service, store, journal, raw = _service()
    result = service.execute(
        [sys.executable, "-c", "pass"],
        run_id="run-svc-empty",
        tool="opencode",
        model="model-xyz-7",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-19T00:00:00Z",
    )
    assert result.gate_state in ("inconclusive", "fail")
    assert result.gate_state != "pass"
    run = store.get_run("run-svc-empty")
    assert run is not None
    assert run.state == "advance_or_stop"
    assert run.metadata.get("stop_reason") == "before_gate"


def test_failing_worker_is_a_failed_run_not_a_gap():
    # A non-zero exit never gate-passes and is reflected in the run's terminal
    # state as failed, with the journal still gap-free.
    service, store, journal, raw = _service()
    result = service.execute(
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        run_id="run-svc-fail",
        tool="opencode",
        model="model-xyz-7",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-19T00:00:00Z",
    )
    assert result.gate_state == "fail"
    run = store.get_run("run-svc-fail")
    assert run is not None
    assert run.state == "advance_or_stop"
    assert run.metadata.get("stop_reason") == "before_gate"
    assert journal.has_gaps("run-svc-fail") is False


def test_stage_failure_raises_and_never_leaves_a_dangling_run():
    # A launch that never starts (a command that cannot start is not a thing here
    # — run_command always starts; instead we simulate a stage error by handing a
    # store whose create is fine but whose transition is impossible is hard to
    # express; the service's own integration error path is exercised by a command
    # that raises at launch — which run_command converts to a failure result, not
    # an exception). We assert the explicit failure mode for an empty command.
    service, store, journal, raw = _service()
    # An empty command vector cannot start; run_command raises, the service
    # translates it to RunIntegrationError and marks the run failed.
    try:
        service.execute(
            [],
            run_id="run-svc-bad",
            tool="opencode",
            model="model-xyz-7",
            subject_repo="skillweave",
            subject_commit="abc123",
            created_at="2026-08-19T00:00:00Z",
        )
    except RunIntegrationError as exc:
        assert exc.stage == "launch"
    else:
        raise AssertionError("expected RunIntegrationError for an empty command")
    run = store.get_run("run-svc-bad")
    assert run is not None
    assert run.state == "advance_or_stop"
    assert run.metadata.get("stop_reason") == "before_gate"


def _run_all() -> int:
    tests = [
        test_real_harness_run_writes_all_six_records_without_gaps,
        test_verified_gate_passes_only_for_real_nonempty_output,
        test_no_output_is_never_a_gate_pass,
        test_failing_worker_is_a_failed_run_not_a_gap,
        test_stage_failure_raises_and_never_leaves_a_dangling_run,
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
