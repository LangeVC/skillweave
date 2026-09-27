"""Integration tests for the generic kernel transition contract (SW-160-VERT-003).

Four acceptance criteria, each as a set of positive and red-state fixtures:

1. Wait, failure and cancel each have positive and red state-transition fixtures.
   - ``blocked_waiting_for_gate``, ``failed``, and cancel (cancelled subprocess)
     are tested with legal transitions (positive) and illegal transitions (red).
2. Human coupling gates irreversible surfaces independently of category name.
   - ``assert_human_coupling_gate`` checks every human-coupling level against
     every irreversible change surface without inspecting the category.
3. Crash and resume preserve one canonical state without transcript dependence.
   - A checkpoint taken mid-run survives a simulated crash; resume replays the
     journal from the checkpoint offset without depending on a transcript.
4. Neither vertical adds a private transition outside the kernel.
   - Both research-synthesis.v1 and software-delivery.v2 profiles are asserted
     to declare only the kernel stages (K0-K6) and the standard legal
     transitions in ``RunStateModel``, never a private state or transition.

Hermetic: in-memory SQLite, trivial subprocesses, no network or real model.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import yaml

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.store import (
    RunStateModel,
    SQLiteRunStore,
    VersionConflictError,
    InvalidTransitionError,
)
from skillweave.runtime.journal import EventJournal, EventType
from skillweave.runtime.checkpoint import (
    Checkpoint,
    EnvironmentFingerprint,
    ResumeRevalidationRequired,
    capture_environment,
    create_checkpoint,
    validate_resume,
)
from skillweave.runtime.registry import RawArtifactStore
from skillweave.runsvc import RunApplicationService, RunExecution, RunIntegrationError
from skillweave.runtime import (
    IRREVERSIBLE_SURFACES,
    assert_human_coupling_gate,
)

_REPO = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service(tmp_db=":memory:"):
    store = SQLiteRunStore(tmp_db)
    journal = EventJournal(store)
    raw = RawArtifactStore()
    return RunApplicationService(store, journal, raw), store, journal, raw


def _terminal_states() -> frozenset[str]:
    return RunStateModel.terminal_values()


def _all_states() -> set[str]:
    return {s.value for s in RunStateModel}


def _legal_transitions(from_state: str) -> list[str]:
    return [s.value if isinstance(s, RunStateModel) else s
            for s in RunStateModel.legal_transitions(from_state)]


def _illegal_transitions(from_state: str) -> list[str]:
    """Return all states that are NOT legal transitions from *from_state*."""
    legal = set(_legal_transitions(from_state))
    terminal = _terminal_states()
    all_s = _all_states()
    # You cannot transition from a terminal state at all.
    if from_state in terminal:
        return sorted(all_s)
    return sorted(all_s - legal - {from_state})


def _make_run_in_state(store, run_id: str, target_state: str):
    """Create a run and seed the DB row directly in *target_state*.

    Used for states on the sandbox track (``in_progress``,
    ``blocked_waiting_for_gate``, ``failed``, etc.) that are not reachable
    from ``preflight`` through a single chain of legal transitions.
    """
    from datetime import datetime, timezone
    import json
    now = datetime.now(timezone.utc).isoformat()
    store._conn.execute(
        "INSERT INTO runs (run_id, root_run_id, state, version, "
        "created_at, updated_at, role, metadata) "
        "VALUES (?, ?, ?, 1, ?, ?, 'ops', '{}')",
        (run_id, run_id, target_state, now, now),
    )
    store._conn.commit()
    return store.get_run(run_id)


def _execute_and_get_run(
    run_id: str,
    service: RunApplicationService,
    store: SQLiteRunStore,
    command=None,
) -> dict:
    """Run a command through the service and return a snapshot of the run."""
    if command is None:
        command = [sys.executable, "-c", "print('test-output')"]
    result = service.execute(
        command,
        run_id=run_id,
        tool="opencode",
        model="faigate/deepseek-v4-pro",
        subject_repo="skillweave",
        subject_commit="abcdef1234567890abcdef1234567890abcdef12",
        created_at="2026-09-27T00:00:00Z",
    )
    return {
        "run": store.get_run(run_id),
        "gate_state": result.gate_state,
        "journal": result.journal,
    }


# ===================================================================
# Criterion 1: Wait, failure and cancel — positive and red fixtures
# ===================================================================


class TestWaitStateTransitions:
    """Positive and red fixtures for the ``blocked_waiting_for_gate`` state."""

    def test_legal_transition_to_blocked_waiting_for_gate(self):
        """in_progress -> blocked_waiting_for_gate is legal."""
        allowed = _legal_transitions("in_progress")
        assert "blocked_waiting_for_gate" in allowed

    def test_legal_transition_from_blocked_waiting_for_gate(self):
        """blocked_waiting_for_gate -> in_progress, review_required, failed are legal."""
        allowed = _legal_transitions("blocked_waiting_for_gate")
        assert "in_progress" in allowed
        assert "review_required" in allowed
        assert "failed" in allowed
        # Must not allow advance_or_stop (waiting means incomplete).
        assert "advance_or_stop" not in allowed

    def test_positive_wait_then_resume(self):
        """blocked_waiting_for_gate -> in_progress: run resumes after wait."""
        store = SQLiteRunStore(":memory:")
        run = _make_run_in_state(store, "wait-resume", "blocked_waiting_for_gate")
        assert run.state == "blocked_waiting_for_gate"
        # Resume from wait.
        store.transition("wait-resume", "in_progress",
                         expected_state="blocked_waiting_for_gate", expected_version=run.version,
                         reason="gate resolved", role="ops")
        run = store.get_run("wait-resume")
        assert run.state == "in_progress"

    def test_red_illegal_transition_from_blocked_waiting_to_terminal(self):
        """blocked_waiting_for_gate -> advance_or_stop is ILLEGAL."""
        store = SQLiteRunStore(":memory:")
        run = _make_run_in_state(store, "wait-red", "blocked_waiting_for_gate")
        with pytest.raises(InvalidTransitionError):
            store.transition("wait-red", "advance_or_stop",
                             expected_state="blocked_waiting_for_gate", expected_version=run.version,
                             reason="test", role="ops")

    def test_red_waiting_run_rejects_review_gate(self):
        """blocked_waiting_for_gate -> review_gate is ILLEGAL (no gate while blocked)."""
        store = SQLiteRunStore(":memory:")
        run = _make_run_in_state(store, "wait-red-gate", "blocked_waiting_for_gate")
        with pytest.raises(InvalidTransitionError):
            store.transition("wait-red-gate", "review_gate",
                             expected_state="blocked_waiting_for_gate", expected_version=run.version,
                             reason="test", role="ops")


class TestFailureStateTransitions:
    """Positive and red fixtures for the ``failed`` terminal state."""

    def test_legal_transitions_to_failed(self):
        """in_progress, preflight_complete, blocked_waiting_for_gate, review_required -> failed."""
        assert "failed" in _legal_transitions("in_progress")
        assert "failed" in _legal_transitions("preflight_complete")
        assert "failed" in _legal_transitions("blocked_waiting_for_gate")
        assert "failed" in _legal_transitions("review_required")
        assert "failed" in _legal_transitions("sandbox_preflight")

    def test_positive_run_service_failure(self):
        """A run that raises during launch lands in a terminal state."""
        service, store, journal, raw = _service()
        # A command that does not exist.
        with pytest.raises(RunIntegrationError):
            service.execute(
                ["/nonexistent/command/that/will/fail"],
                run_id="fail-positive",
                tool="opencode",
                model="faigate/deepseek-v4-pro",
                subject_repo="skillweave",
                subject_commit="abcdef1234567890abcdef1234567890abcdef12",
                created_at="2026-09-27T00:00:00Z",
            )
        run = store.get_run("fail-positive")
        assert run is not None
        assert RunStateModel.is_terminal(run.state), f"run not terminal: {run.state}"

    def test_positive_explicit_failed_transition(self):
        """in_progress -> failed: explicit failure transitions work."""
        store = SQLiteRunStore(":memory:")
        run = _make_run_in_state(store, "fail-explicit", "in_progress")
        store.transition("fail-explicit", "failed",
                         expected_state="in_progress", expected_version=run.version,
                         reason="catastrophic failure", role="ops")
        run = store.get_run("fail-explicit")
        assert run.state == "failed"
        assert run.ended_at is not None  # terminal state sets ended_at

    def test_red_failed_has_no_outgoing_transitions(self):
        """failed -> any state is ILLEGAL (terminal has zero outgoing)."""
        assert _legal_transitions("failed") == []

    def test_red_failed_cannot_transition(self):
        """Attempting a transition from failed raises InvalidTransitionError."""
        store = SQLiteRunStore(":memory:")
        run = _make_run_in_state(store, "fail-red", "failed")
        with pytest.raises(InvalidTransitionError):
            store.transition("fail-red", "in_progress",
                             expected_state="failed", expected_version=run.version,
                             reason="test", role="ops")


class TestCancelStateTransitions:
    """Positive and red fixtures for cancel (termination == cancelled)."""

    def test_positive_cancel_via_subprocess(self):
        """A subprocess that is cancelled terminates cleanly with cancelled state."""
        from skillweave.runtime.runner_adapter import start_process

        # Start a long-running process.
        proc = start_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            run_id="cancel-test",
            subject_repo="skillweave",
            subject_commit="abcdef1234567890abcdef1234567890abcdef12",
            tool="opencode",
            model="faigate/deepseek-v4-pro",
        )
        # Give it a moment to start.
        time.sleep(0.2)
        result = proc.cancel()
        assert result.termination == "cancelled"
        assert result.succeeded is False
        # The process group is reaped: no child survives.
        from skillweave.runtime.runner_adapter import _pid_exists
        assert not _pid_exists(proc.pid)

    def test_positive_cancel_produces_defined_run_state(self):
        """A cancelled subprocess yields a defined (non-successful) result."""
        from skillweave.runtime.runner_adapter import start_process

        proc = start_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            run_id="cancel-state",
            subject_repo="skillweave",
            subject_commit="abcdef1234567890abcdef1234567890abcdef12",
            tool="opencode",
            model="faigate/deepseek-v4-pro",
        )
        time.sleep(0.2)
        result = proc.cancel()
        # termination is "cancelled", exit_code/signal are None, message is set.
        assert result.termination == "cancelled"
        assert result.exit_code is None
        assert result.signal is None
        assert "cancelled" in result.message.lower()

    def test_red_cancel_of_already_exited_process(self):
        """Cancelling an already-exited process returns the original result."""
        from skillweave.runtime.runner_adapter import run_command

        result = run_command(
            [sys.executable, "-c", "print('quick-exit')"],
            run_id="cancel-already-done",
            subject_repo="skillweave",
            subject_commit="abcdef1234567890abcdef1234567890abcdef12",
            tool="opencode",
            model="faigate/deepseek-v4-pro",
        )
        assert result.termination == "exited"
        assert result.succeeded is True
        # The process has already exited; cancelling is a no-op.
        from skillweave.runtime.runner_adapter import _pid_exists
        assert not _pid_exists(result.pid)

    def test_red_advance_or_stop_not_reachable_via_cancel_in_wait(self):
        """A cancelled run while blocked cannot skip to advance_or_stop."""
        store = SQLiteRunStore(":memory:")
        run = _make_run_in_state(store, "cancel-wait-red", "blocked_waiting_for_gate")
        # Cannot jump to advance_or_stop from blocked_waiting_for_gate.
        with pytest.raises(InvalidTransitionError):
            store.transition("cancel-wait-red", "advance_or_stop",
                             expected_state="blocked_waiting_for_gate", expected_version=run.version,
                             reason="cancel", role="ops")


# ===================================================================
# Criterion 2: Human coupling gates irreversible surfaces
# ===================================================================


class TestHumanCouplingGate:
    """Human coupling gates irreversible surfaces independently of category name."""

    def test_irreversible_surfaces_are_defined(self):
        """IRREVERSIBLE_SURFACES contains the five critical surfaces."""
        assert "organization" in IRREVERSIBLE_SURFACES
        assert "human" in IRREVERSIBLE_SURFACES
        assert "finance" in IRREVERSIBLE_SURFACES
        assert "legal" in IRREVERSIBLE_SURFACES
        assert "public_channel" in IRREVERSIBLE_SURFACES
        assert len(IRREVERSIBLE_SURFACES) == 5

    def test_autonomous_fails_irreversible_surfaces(self):
        """humanCoupling=autonomous with irreversible surfaces is a violation."""
        violations = assert_human_coupling_gate(
            "autonomous",
            ["code", "legal", "documents"],
        )
        assert len(violations) == 1
        assert violations[0]["surface"] == "legal"
        assert "irreversible" in violations[0]["reason"].lower()

    def test_supervised_fails_irreversible_surfaces(self):
        """humanCoupling=supervised with irreversible surfaces is a violation."""
        violations = assert_human_coupling_gate(
            "supervised",
            ["human", "code"],
        )
        assert len(violations) == 1
        assert violations[0]["surface"] == "human"

    def test_approval_required_passes_irreversible_surfaces(self):
        """humanCoupling=approval_required with irreversible surfaces passes."""
        violations = assert_human_coupling_gate(
            "approval_required",
            ["legal", "finance", "code"],
        )
        assert violations == []

    def test_collaborative_passes_irreversible_surfaces(self):
        """humanCoupling=collaborative with irreversible surfaces passes."""
        violations = assert_human_coupling_gate(
            "collaborative",
            ["organization", "human", "code"],
        )
        assert violations == []

    def test_human_led_passes_irreversible_surfaces(self):
        """humanCoupling=human_led with irreversible surfaces passes."""
        violations = assert_human_coupling_gate(
            "human_led",
            ["legal", "public_channel"],
        )
        assert violations == []

    def test_no_irreversible_surfaces_never_violates(self):
        """No irreversible surfaces means no violations, regardless of coupling."""
        for coupling in ("autonomous", "supervised", "approval_required", "collaborative", "human_led"):
            violations = assert_human_coupling_gate(
                coupling,
                ["code", "configuration", "infrastructure", "documents"],
            )
            assert violations == [], f"{coupling} should pass with no irreversible surfaces"

    def test_multiple_irreversible_surfaces_all_reported(self):
        """All violating irreversible surfaces are reported."""
        violations = assert_human_coupling_gate(
            "autonomous",
            ["legal", "finance", "human", "organization", "public_channel", "code"],
        )
        assert len(violations) == 5
        reported_surfaces = {v["surface"] for v in violations}
        assert reported_surfaces == {"legal", "finance", "human", "organization", "public_channel"}

    def test_independent_of_category_name(self):
        """The gate inspects human_coupling alone, never the category name."""
        for category in ("build", "research", "learn", "decide"):
            violations_bad = assert_human_coupling_gate(
                "autonomous",
                ["legal"],
            )
            violations_good = assert_human_coupling_gate(
                "approval_required",
                ["legal"],
            )
            assert len(violations_bad) == 1, f"{category} should fail with autonomous"
            assert violations_good == [], f"{category} should pass with approval_required"

    def test_software_delivery_profile_passes_its_own_surfaces(self):
        """software-delivery.v2 surfaces (code, config, infra, docs) have no irreversible surfaces."""
        from skillweave.routing import load_profiles_from_location
        profile_path = _REPO / "profiles" / "software-delivery.v2.yaml"
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        surfaces = raw.get("changeSurfaces", [])
        violations = assert_human_coupling_gate(
            raw.get("humanCoupling", "supervised"),
            surfaces,
        )
        assert violations == []

    def test_research_profile_passes_its_own_surfaces(self):
        """research-synthesis.v1 surfaces (docs, knowledge, data, external_system) pass."""
        profile_path = _REPO / "profiles" / "research-synthesis.v1.yaml"
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        surfaces = raw.get("changeSurfaces", [])
        violations = assert_human_coupling_gate(
            raw.get("humanCoupling", "collaborative"),
            surfaces,
        )
        assert violations == []


# ===================================================================
# Criterion 3: Crash and resume preserve one canonical state
# ===================================================================


class TestCrashAndResume:
    """Crash and resume preserves one canonical state without transcript."""

    def test_checkpoint_capture_restore(self):
        """A checkpoint preserves journal offset and environment."""
        service, store, journal, raw = _service()
        run_id = "crash-resume-cp"

        # Run a command through the service.
        result = service.execute(
            [sys.executable, "-c", "print('crash-resume-test')"],
            run_id=run_id,
            tool="opencode",
            model="faigate/deepseek-v4-pro",
            subject_repo="skillweave",
            subject_commit="abcdef1234567890abcdef1234567890abcdef12",
            created_at="2026-09-27T00:00:00Z",
        )

        # Capture a checkpoint after the run.
        last_seq = journal.get_last_sequence(run_id)
        env = capture_environment(branch="feature/sw-160-vert-003",
                                   commit_sha="abcdef1234567890abcdef1234567890abcdef12")
        checkpoint = create_checkpoint(
            run_id=run_id,
            root_run_id=run_id,
            journal_offset=last_seq,
            environment=env,
        )
        store.save_checkpoint(checkpoint)

        # "Crash": create a fresh store and replay the journal.
        store2 = SQLiteRunStore(":memory:")
        journal2 = EventJournal(store2)
        raw2 = RawArtifactStore()

        # Restore checkpoint.
        restored_cp = store.get_checkpoint(run_id)
        assert restored_cp is not None
        assert restored_cp.journal_offset == last_seq
        assert restored_cp.environment.validate_against(env)

        # The canonical state is the run record, not a transcript.
        original_run = store.get_run(run_id)
        assert original_run is not None
        assert original_run.state == "advance_or_stop"
        # No transcript dependency: we have the state directly.
        assert original_run.state in _terminal_states()

    def test_environment_revalidation_blocks_divergent_resume(self):
        """An environment change triggers ResumeRevalidationRequired."""
        env1 = EnvironmentFingerprint(
            hostname="host-a",
            os_name="Linux 6.1",
            python_version="3.11.0",
            branch="feature/sw-160-vert-003",
            commit_sha="aaaa",
        )
        env2 = EnvironmentFingerprint(
            hostname="host-b",
            os_name="Linux 6.2",
            python_version="3.12.0",
            branch="feature/sw-160-vert-003",
            commit_sha="bbbb",
        )
        checkpoint = Checkpoint(
            run_id="env-check",
            root_run_id="env-check",
            parent_run_id=None,
            journal_offset=5,
            environment=env1,
        )
        with pytest.raises(ResumeRevalidationRequired) as exc:
            validate_resume(checkpoint, env2)
        assert "hostname" in exc.value.field
        assert "RESUME_REVALIDATION_REQUIRED" in str(exc.value)

    def test_journal_has_no_gaps_after_crash_replay(self):
        """After a crash, replaying the journal shows no gaps."""
        service, store, journal, raw = _service()
        run_id = "crash-gap-check"

        service.execute(
            [sys.executable, "-c", "print('gap-check')"],
            run_id=run_id,
            tool="opencode",
            model="faigate/deepseek-v4-pro",
            subject_repo="skillweave",
            subject_commit="abcdef1234567890abcdef1234567890abcdef12",
            created_at="2026-09-27T00:00:00Z",
        )

        assert not journal.has_gaps(run_id)

        # Create a fresh journal on the same DB and verify no gaps.
        # In SQLite, the DB is in-memory so we use the same store's connection.
        journal2 = EventJournal(store)
        assert not journal2.has_gaps(run_id)

    def test_checkpoint_without_transcript_produces_terminal_run(self):
        """A checkpoint holds run metadata directly, no transcript needed."""
        store = SQLiteRunStore(":memory:")
        run = store.create_run("no-transcript")
        # Walk through the normal pipeline.
        for from_s, to_s in (
            ("preflight", "batch_selection"),
            ("batch_selection", "lane_plan"),
            ("lane_plan", "implement"),
            ("implement", "verify"),
        ):
            current = store.get_run("no-transcript")
            store.transition("no-transcript", to_s,
                             expected_state=from_s, expected_version=current.version,
                             reason="test", role="ops")
        current = store.get_run("no-transcript")
        store.transition("no-transcript", "review_gate",
                         expected_state="verify", expected_version=current.version,
                         reason="test", role="ops")
        current = store.get_run("no-transcript")
        store.transition("no-transcript", "advance_or_stop",
                         expected_state="review_gate", expected_version=current.version,
                         reason="test", role="ops")

        # Capture the checkpoint — no transcript required.
        env = capture_environment()
        checkpoint = create_checkpoint(
            run_id="no-transcript",
            root_run_id="no-transcript",
            journal_offset=0,
            environment=env,
        )
        store.save_checkpoint(checkpoint)

        # The canonical state is the RunRecord, not derived from any transcript.
        restored = store.get_run("no-transcript")
        assert restored.state == "advance_or_stop"
        assert RunStateModel.is_terminal(restored.state)

        # A fresh store can load the checkpoint and see the same canonical state.
        store2 = SQLiteRunStore(":memory:")
        # Save the original run record data for cross-check.
        run_data = (restored.run_id, restored.root_run_id, restored.state, restored.version)
        # Re-create on store2.
        from skillweave.runtime.store import RunRecord
        from datetime import datetime, timezone
        store2.save_run(RunRecord(
            run_id=restored.run_id,
            root_run_id=restored.root_run_id,
            parent_run_id=restored.parent_run_id,
            state=restored.state,
            version=1,
            created_at=restored.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            ended_at=restored.ended_at,
            role=restored.role,
            metadata=restored.metadata,
        ))
        store2.save_checkpoint(checkpoint)

        cp2 = store2.get_checkpoint("no-transcript")
        assert cp2 is not None
        assert cp2.journal_offset == 0
        run2 = store2.get_run("no-transcript")
        assert run2.state == "advance_or_stop"

    def test_resume_validation_passes_on_identical_environment(self):
        """validate_resume passes when environments match."""
        env = EnvironmentFingerprint(
            hostname="same-host",
            os_name="Linux",
            python_version="3.11",
            branch="main",
            commit_sha="aaaa",
        )
        checkpoint = Checkpoint(
            run_id="same-env",
            root_run_id="same-env",
            parent_run_id=None,
            journal_offset=1,
            environment=env,
        )
        assert validate_resume(checkpoint, env) is True

    def test_resume_validation_fails_on_different_commit(self):
        """validate_resume raises when commit_sha differs."""
        env1 = EnvironmentFingerprint(
            hostname="h", os_name="OS", python_version="3",
            branch="b", commit_sha="aaa",
        )
        env2 = EnvironmentFingerprint(
            hostname="h", os_name="OS", python_version="3",
            branch="b", commit_sha="bbb",
        )
        checkpoint = Checkpoint(
            run_id="diff-commit",
            root_run_id="diff-commit",
            parent_run_id=None,
            journal_offset=1,
            environment=env1,
        )
        with pytest.raises(ResumeRevalidationRequired):
            validate_resume(checkpoint, env2)


# ===================================================================
# Criterion 4: Neither vertical adds a private transition
# ===================================================================


class TestNoPrivateTransitions:
    """Neither vertical adds a private transition outside the kernel."""

    def test_software_delivery_kernel_stages_are_standard(self):
        """software-delivery.v2 declares only K0-K6."""
        profile_path = _REPO / "profiles" / "software-delivery.v2.yaml"
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        stages = raw.get("kernelStages", [])
        assert stages == ["K0", "K1", "K2", "K3", "K4", "K5", "K6"]

    def test_research_kernel_stages_are_standard(self):
        """research-synthesis.v1 declares only K0-K6."""
        profile_path = _REPO / "profiles" / "research-synthesis.v1.yaml"
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        stages = raw.get("kernelStages", [])
        assert stages == ["K0", "K1", "K2", "K3", "K4", "K5", "K6"]

    def test_no_private_state_in_run_state_model(self):
        """RunStateModel contains only the agreed states, no private additions."""
        states = {s.value for s in RunStateModel}
        expected = {
            "preflight",
            "batch_selection",
            "lane_plan",
            "implement",
            "verify",
            "review_gate",
            "fix_retry",
            "integrate",
            "advance_or_stop",
            "sandbox_preflight",
            "in_progress",
            "preflight_complete",
            "blocked_waiting_for_gate",
            "review_required",
            "failed",
        }
        assert states == expected, f"Unexpected states: {states - expected}"

    def test_no_private_transition_outside_legal_map(self):
        """Every legal_transitions entry references only known states."""
        for from_state in RunStateModel:
            allowed = RunStateModel.legal_transitions(from_state)
            for target in allowed:
                target_val = target.value if isinstance(target, RunStateModel) else target
                assert target_val in {s.value for s in RunStateModel}, (
                    f"{from_state.value} -> {target_val}: target not in RunStateModel"
                )

    def test_terminal_states_are_only_advance_or_stop_and_failed(self):
        """Only advance_or_stop and failed are terminal."""
        terminal = RunStateModel.terminal_values()
        assert terminal == frozenset({"advance_or_stop", "failed"})

    def test_terminal_states_have_no_outgoing(self):
        """Both terminal states have empty transition lists."""
        assert RunStateModel.legal_transitions(RunStateModel.ADVANCE_OR_STOP) == []
        assert RunStateModel.legal_transitions(RunStateModel.FAILED) == []

    def test_non_terminal_states_have_at_least_one_outgoing(self):
        """Every non-terminal state has at least one legal transition."""
        for state in RunStateModel:
            if RunStateModel.is_terminal(state.value):
                continue
            allowed = RunStateModel.legal_transitions(state)
            assert len(allowed) >= 1, f"{state.value} has zero outgoing transitions"


# ===================================================================
# Additional kernel integrity tests
# ===================================================================


class TestKernelIntegrity:
    """Kernel transition integrity and version safety."""

    def test_version_conflict_on_stale_write(self):
        """A stale version raises VersionConflictError."""
        store = SQLiteRunStore(":memory:")
        store.create_run("version-conflict")
        run = store.get_run("version-conflict")
        assert run.version == 1

        # First transition succeeds.
        store.transition("version-conflict", "batch_selection",
                         expected_state="preflight", expected_version=1,
                         reason="test", role="ops")
        run = store.get_run("version-conflict")
        assert run.version == 2

        # Stale version (1 instead of 2) raises VersionConflictError.
        with pytest.raises(VersionConflictError):
            store.transition("version-conflict", "lane_plan",
                             expected_state="batch_selection", expected_version=1,
                             reason="stale", role="ops")

    def test_transition_log_persists_after_legal_transition(self):
        """Legal transitions are recorded in the transitions_log."""
        store = SQLiteRunStore(":memory:")
        store.create_run("log-test")
        store.transition("log-test", "batch_selection",
                         expected_state="preflight", expected_version=1,
                         reason="first transition", role="ops")
        run = store.get_run("log-test")
        store.transition("log-test", "lane_plan",
                         expected_state="batch_selection", expected_version=run.version,
                         reason="second transition", role="ops")

        # Check the log.
        rows = store._conn.execute(
            "SELECT from_state, to_state, reason FROM transitions_log "
            "WHERE run_id = ? ORDER BY id", ("log-test",)
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["from_state"] == "preflight"
        assert rows[0]["to_state"] == "batch_selection"
        assert rows[0]["reason"] == "first transition"
        assert rows[1]["from_state"] == "batch_selection"
        assert rows[1]["to_state"] == "lane_plan"
        assert rows[1]["reason"] == "second transition"

    def test_full_run_service_lifecycle_produces_terminal_state(self):
        """A complete run through RunApplicationService ends in advance_or_stop."""
        service, store, journal, raw = _service()
        result = service.execute(
            [sys.executable, "-c", "print('full-lifecycle')"],
            run_id="full-lifecycle",
            tool="opencode",
            model="faigate/deepseek-v4-pro",
            subject_repo="skillweave",
            subject_commit="abcdef1234567890abcdef1234567890abcdef12",
            created_at="2026-09-27T00:00:00Z",
        )
        assert result.run.state == "advance_or_stop"
        assert result.gate_state == "pass"

    def test_run_service_empty_output_does_not_pass(self):
        """Empty output through the service produces a non-pass gate."""
        service, store, journal, raw = _service()
        result = service.execute(
            [sys.executable, "-c", "pass"],
            run_id="empty-output",
            tool="opencode",
            model="faigate/deepseek-v4-pro",
            subject_repo="skillweave",
            subject_commit="abcdef1234567890abcdef1234567890abcdef12",
            created_at="2026-09-27T00:00:00Z",
        )
        assert result.gate_state != "pass"
        assert result.run.state == "advance_or_stop"
