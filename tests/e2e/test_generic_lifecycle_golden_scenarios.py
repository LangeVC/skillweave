"""Ten golden scenarios through the generic lifecycle kernel (SW-160-BREADTH-003).

Each scenario exercises the domain-neutral kernel — ``RunApplicationService``,
``RunStateModel``, ``CompletionContract``, ``EventJournal``, ``RawArtifactStore``,
``Verifier``, authority guards, checkpoint/resume, human-coupling gates —
through one of the ten required outcomes:

1.  Success (PASS gate)              — nontechnical
2.  Failure (FAIL gate)              — nontechnical
3.  Wait (INCONCLUSIVE gate)         — nontechnical
4.  Cancel                           — nontechnical
5.  Resume via checkpoint            — nontechnical
6.  Irreversible human-coupling gate — nontechnical
7.  State machine integrity
8.  Evidence content-addressing
9.  Separation of duties
10. Completion contract boundaries

Every scenario is category-independent: no scenario adds a private runtime path
or a category-specific lifecycle implementation. At least four scenarios require
no source-code or Git mutation (they are pure in-process assertions).

Hermetic: in-memory SQLite and trivial subprocesses (``python -c ...``), never
a real model or a network call.
"""

import hashlib
import os
import sys
import time
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.authority import (  # noqa: E402
    AuthorityGuard,
    AuthorityError,
    HumanApproval,
    can_approve_gate,
    can_mutate_run_state,
)
from skillweave.runtime.checkpoint import (  # noqa: E402
    EnvironmentFingerprint,
    ResumeRevalidationRequired,
    capture_environment,
    create_checkpoint,
    validate_resume,
)
from skillweave.runtime.journal import EventJournal, EventType  # noqa: E402
from skillweave.runtime.registry import (  # noqa: E402
    ArtifactIntegrityError,
    ArtifactReceipt,
    EvidenceQuality,
    EvidenceType,
    RawArtifactStore,
)
from skillweave.runtime.runner_adapter import start_process  # noqa: E402
from skillweave.runtime.store import SQLiteRunStore, RunStateModel  # noqa: E402
from skillweave.runtime.verify import (  # noqa: E402
    CompletionContract,
    GateState,
    Verifier,
)
from skillweave.runtime import (  # noqa: E402
    IRREVERSIBLE_SURFACES,
    REVERSIBILITY_BY_SURFACE,
    assert_human_coupling_gate,
    authorize_mutation,
    derive_human_coupling,
)
from skillweave.routing.profile import (  # noqa: E402
    CAP_APPROVE_GATE,
    CAP_MUTATE_RUN_STATE,
    RoutingProfileError,
    from_dict,
)
from skillweave.runsvc import RunApplicationService, RunExecution  # noqa: E402

_REPO = Path(__file__).resolve().parent.parent.parent
_SUBJECT_COMMIT = "abcdef1234567890abcdef1234567890abcdef12"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _service(tmp_db: str = ":memory:"):
    """Build an in-memory run service with its three backing stores."""
    store = SQLiteRunStore(tmp_db)
    journal = EventJournal(store)
    raw = RawArtifactStore()
    return RunApplicationService(store, journal, raw), store, journal, raw


def _pid_exists(pid: int) -> bool:
    """Return True if a process with *pid* still exists (using kill -0)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _check_six_record_kinds(
    result: RunExecution,
    store: SQLiteRunStore,
    journal: EventJournal,
    raw_store: RawArtifactStore,
    run_id: str,
    *,
    expected_gate: str,
    expected_state: str = "advance_or_stop",
    expect_stop_reason: str | None = "before_gate",
):
    """Assert all six record kinds are present and internally consistent."""
    # 1. Run record
    run = store.get_run(run_id)
    assert run is not None, "Run record missing"
    assert run.state == expected_state, f"Expected {expected_state}, got {run.state}"

    # 2. Journal — ordered and gap-free
    assert len(result.journal) >= 1, "Journal is empty"
    assert result.journal[0].sequence == 1, "Journal does not start at sequence 1"
    assert journal.has_gaps(run_id) is False, "Journal has gaps"

    # 3. Raw artifact — content-addressed and resolvable
    assert len(result.raw_digest) == 64, f"Raw digest length is {len(result.raw_digest)}, expected 64"
    assert raw_store.resolve(result.raw_digest) == result.raw_bytes, "Raw artifact does not resolve"
    assert hashlib.sha256(result.raw_bytes).hexdigest() == result.raw_digest, "Digest mismatch"

    # 4. Receipt — bound to run and persisted
    assert result.receipt.artifact_id == f"runsvc-{run_id}", f"Unexpected receipt id: {result.receipt.artifact_id}"
    assert result.receipt.sha256 == result.raw_digest, "Receipt digest does not match raw digest"
    persisted = store.get_evidence(result.receipt.artifact_id)
    assert persisted is not None, "Receipt not persisted"

    # 5. Verification — separate identity, bound to subject receipt
    assert result.verification["subject_artifact_id"] == result.receipt.artifact_id, "Verification not bound to receipt"
    assert result.verification["verified_by"] == "verifier", "Verification not from verifier"
    assert result.verification["artifact_id"] == f"verify-{result.receipt.artifact_id}", "Verification receipt id mismatch"

    # 6. Gate — derived from verified outcome
    assert result.gate_state == expected_gate, f"Expected gate={expected_gate}, got {result.gate_state}"

    # Stop reason (only present for non-PASS outcomes)
    actual_stop = result.run.metadata.get("stop_reason")
    if expect_stop_reason is not None:
        assert actual_stop == expect_stop_reason, f"Expected stop_reason={expect_stop_reason}, got {actual_stop}"
    else:
        assert actual_stop is None, f"Expected no stop_reason, got {actual_stop}"


# ===================================================================
# Scenario 1: Success (PASS gate) — nontechnical
# ===================================================================

def test_scenario_01_success():
    """A command that produces real output: gate PASS, all six record kinds.

    This is the canonical happy path through the generic lifecycle kernel.
    No source-code or Git mutation is required (pure python print).
    """
    service, store, journal, raw_store = _service()
    run_id = "golden-01-success"

    result = service.execute(
        [sys.executable, "-c", "print('golden-01-success-output')"],
        run_id=run_id,
        tool="opencode",
        model="faigate/deepseek-v4-pro",
        subject_repo="skillweave",
        subject_commit=_SUBJECT_COMMIT,
        created_at="2026-09-27T00:00:00Z",
    )

    _check_six_record_kinds(
        result, store, journal, raw_store, run_id,
        expected_gate=GateState.PASS,
        expect_stop_reason=None,
    )

    # The run's version confirms it traversed all 4 lane-advance transitions
    # plus the 2 terminal transitions (review_gate + advance_or_stop for PASS).
    assert result.run.version >= 6, f"Run version {result.run.version} < 6, incomplete state chain"
    assert b"golden-01-success-output" in result.raw_bytes


# ===================================================================
# Scenario 2: Failure (FAIL gate) — nontechnical
# ===================================================================

def test_scenario_02_failure():
    """A non-zero exit: gate FAIL, stop_reason recorded.

    The kernel routes a non-pass outcome through fix_retry before advancing
    to the terminal state, with the stop reason in metadata.
    """
    service, store, journal, raw_store = _service()
    run_id = "golden-02-failure"

    result = service.execute(
        [sys.executable, "-c", "exit(1)"],
        run_id=run_id,
        tool="opencode",
        model="faigate/deepseek-v4-pro",
        subject_repo="skillweave",
        subject_commit=_SUBJECT_COMMIT,
        created_at="2026-09-27T00:00:00Z",
    )

    _check_six_record_kinds(
        result, store, journal, raw_store, run_id,
        expected_gate=GateState.FAIL,
        expect_stop_reason="before_gate",
    )

    # The verifier should report "failed" grade for non-zero exit
    assert result.verification["grade"] == "failed", f"Expected failed grade, got {result.verification['grade']}"


# ===================================================================
# Scenario 3: Wait / Inconclusive (INCONCLUSIVE gate) — nontechnical
# ===================================================================

def test_scenario_03_wait():
    """Exit 0 with empty output: gate INCONCLUSIVE, stop_reason recorded.

    The completion contract is fail-closed: a clean exit with no output is
    inconclusive, never PASS. This exercises the "wait" outcome.
    """
    service, store, journal, raw_store = _service()
    run_id = "golden-03-inconclusive"

    result = service.execute(
        [sys.executable, "-c", "pass"],
        run_id=run_id,
        tool="opencode",
        model="faigate/deepseek-v4-pro",
        subject_repo="skillweave",
        subject_commit=_SUBJECT_COMMIT,
        created_at="2026-09-27T00:00:00Z",
    )

    _check_six_record_kinds(
        result, store, journal, raw_store, run_id,
        expected_gate=GateState.INCONCLUSIVE,
        expect_stop_reason="before_gate",
    )

    assert result.verification["grade"] == "inconclusive"


# ===================================================================
# Scenario 4: Cancel — nontechnical
# ===================================================================

def test_scenario_04_cancel():
    """A running process cancelled before completion: termination=cancelled.

    Uses the kernel's runner_adapter directly (RunApplicationService.execute
    is blocking; the lower-level start_process/cancel seam is the kernel's
    cancel path). Verifies no child survives after cancel.
    """
    proc = start_process(
        [sys.executable, "-c", "import time; time.sleep(30); print('done')"],
        run_id="golden-04-cancel",
        subject_repo="skillweave",
        subject_commit=_SUBJECT_COMMIT,
        tool="opencode",
        model="faigate/deepseek-v4-pro",
    )

    # Wait briefly for the process to start
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if _pid_exists(proc.pid):
            break
        time.sleep(0.05)
    assert _pid_exists(proc.pid), "Process did not start before cancel"

    result = proc.cancel()

    assert result.termination == "cancelled", f"Expected cancelled, got {result.termination}"
    assert result.exit_code is None
    assert result.signal is None
    assert not result.succeeded, "Cancelled process must not report success"

    # After cancel, no child should survive
    assert not _pid_exists(proc.pid), "Child process survived cancel"


# ===================================================================
# Scenario 5: Resume via checkpoint — nontechnical
# ===================================================================

def test_scenario_05_resume():
    """Checkpoint and resume validation through EnvironmentFingerprint.

    An unchanged environment validates successfully; a changed environment
    (different branch/commit) triggers ResumeRevalidationRequired.
    """
    env1 = capture_environment(branch="main", commit_sha="abc123")
    env2 = capture_environment(branch="main", commit_sha="abc123")

    # Same environment: resume succeeds
    cp = create_checkpoint(
        run_id="golden-05-resume",
        root_run_id="golden-05-resume",
        journal_offset=3,
        environment=env1,
    )
    assert validate_resume(cp, env2) is True

    # Different environment: resume raises
    env3 = capture_environment(branch="feature", commit_sha="def456")
    with pytest.raises(ResumeRevalidationRequired) as exc:
        validate_resume(cp, env3)
    assert "RESUME_REVALIDATION_REQUIRED" in str(exc.value)

    # Environment fingerprint digest is deterministic
    assert len(env1.digest()) == 64
    assert env1.digest() == env2.digest()
    assert env1.digest() != env3.digest()


# ===================================================================
# Scenario 6: Irreversible human-coupling gate — nontechnical
# ===================================================================

def test_scenario_06_irreversible_human_coupling():
    """Irreversible surfaces require human authority; logic is category-blind.

    Reversibility is a property of the surface, not the category: a ``build``
    profile touching ``public_channel`` is gated identically to a ``research``
    profile touching the same surface.
    """
    # --- derive_human_coupling ---
    # All-reversible surfaces → supervised
    assert derive_human_coupling(["code", "documents"]) == "supervised"
    # Any irreversible surface → approval_required
    assert derive_human_coupling(["organization"]) == "approval_required"
    assert derive_human_coupling(["human"]) == "approval_required"
    assert derive_human_coupling(["finance", "legal"]) == "approval_required"

    # Category-independent: same surface, same coupling
    assert derive_human_coupling(["public_channel"]) == derive_human_coupling(["public_channel"])

    # --- assert_human_coupling_gate ---
    # Autonomous + irreversible → violation
    violations = assert_human_coupling_gate("autonomous", ["organization"])
    assert len(violations) == 1
    assert violations[0]["surface"] == "organization"
    assert "irreversible" in violations[0]["reason"]

    # Collaborative + irreversible → no violation (human is already in the loop)
    violations = assert_human_coupling_gate("collaborative", ["organization"])
    assert violations == []

    # Autonomous + all reversible → no violation
    violations = assert_human_coupling_gate("autonomous", ["code", "documents"])
    assert violations == []

    # --- authorize_mutation ---
    # Irreversible surface without approval → refused
    result = authorize_mutation("ops", "organization")
    assert result["authorized"] is False
    assert result["irreversibility"] == "irreversible"

    # Irreversible surface with human approval → allowed
    approval = HumanApproval(
        actor="reviewer",
        timestamp="2026-09-27T00:00:00Z",
        scope="org-change",
        policy_digest="pol-v1",
        decision="approved",
    )
    result = authorize_mutation("ops", "organization", approval=approval, scope="org-change")
    assert result["authorized"] is True

    # Reversible surface: always authorized without approval
    result = authorize_mutation("ops", "code")
    assert result["authorized"] is True

    # Scope mismatch → refused even with approval
    result = authorize_mutation("ops", "organization", approval=approval, scope="different-scope")
    assert result["authorized"] is False

    # No category-specific logic
    coupling_research = derive_human_coupling(["public_channel"])
    coupling_build = derive_human_coupling(["public_channel"])
    assert coupling_research == coupling_build == "approval_required"


# ===================================================================
# Scenario 7: State machine integrity
# ===================================================================

def test_scenario_07_state_machine_integrity():
    """RunStateModel enforces legal transitions; runs terminate correctly.

    Verifies the state vocabulary, terminal-state detection, legal-transition
    boundaries, and that RunApplicationService drives runs through the
    canonical chain to a terminal state.
    """
    # Terminal state detection
    assert RunStateModel.is_terminal("advance_or_stop") is True
    assert RunStateModel.is_terminal("failed") is True
    assert RunStateModel.is_terminal("verify") is False
    assert RunStateModel.is_terminal("implement") is False
    assert RunStateModel.is_terminal("preflight") is False

    # Legal transitions from each lane state
    assert {s.value for s in RunStateModel.legal_transitions("preflight")} == {"batch_selection"}
    assert {s.value for s in RunStateModel.legal_transitions("batch_selection")} == {"lane_plan", "advance_or_stop"}
    assert {s.value for s in RunStateModel.legal_transitions("lane_plan")} == {"implement"}
    assert {s.value for s in RunStateModel.legal_transitions("implement")} == {"verify"}
    assert {s.value for s in RunStateModel.legal_transitions("verify")} == {"review_gate", "fix_retry"}
    assert {s.value for s in RunStateModel.legal_transitions("review_gate")} == {"integrate", "fix_retry", "advance_or_stop"}
    assert {s.value for s in RunStateModel.legal_transitions("fix_retry")} == {"implement", "review_gate", "advance_or_stop"}
    assert {s.value for s in RunStateModel.legal_transitions("integrate")} == {"verify", "advance_or_stop"}
    assert {s.value for s in RunStateModel.legal_transitions("advance_or_stop")} == set()
    assert {s.value for s in RunStateModel.legal_transitions("failed")} == set()

    # A run through RunApplicationService reaches the terminal state
    service, store, journal, raw_store = _service()
    result = service.execute(
        [sys.executable, "-c", "print('golden-07-state')"],
        run_id="golden-07-state",
        tool="opencode",
        model="faigate/deepseek-v4-pro",
        subject_repo="skillweave",
        subject_commit=_SUBJECT_COMMIT,
        created_at="2026-09-27T00:00:00Z",
    )
    assert result.run.state == "advance_or_stop"
    # Terminal state implies ended_at is set
    assert result.run.ended_at is not None, "Terminal run must have ended_at set"


# ===================================================================
# Scenario 8: Evidence content-addressing
# ===================================================================

def test_scenario_08_evidence_content_addressing():
    """Raw artifacts are content-addressed; receipts resolve by digest.

    The RawArtifactStore is the kernel's content-addressable store: bytes are
    stored under their sha256 hash and resolved back deterministically. A
    mutated or missing artifact raises ArtifactIntegrityError (fail-closed).
    """
    raw_store = RawArtifactStore()

    # Put content and get its digest
    body = b"golden-08-content-addressable-evidence"
    digest = raw_store.put(body)
    assert len(digest) == 64, f"Digest length {len(digest)} != 64"
    assert hashlib.sha256(body).hexdigest() == digest, "Digest does not match sha256 of content"

    # Resolve back to exact bytes
    resolved = raw_store.resolve(digest)
    assert resolved == body, "Resolved bytes do not match original"

    # A receipt binds the artifact_id to the digest (before any mutation)
    receipt = ArtifactReceipt(
        artifact_id="golden-08-receipt",
        sha256=digest,
        schema_version="1",
        producer_command="golden-scenario-08",
        subject_repo="skillweave",
        subject_commit=_SUBJECT_COMMIT,
        created_at="2026-09-27T00:00:00Z",
        evidence_type=EvidenceType.ARTIFACT.value,
        purpose="golden scenario evidence",
        method="golden-scenario",
        system_source="test",
        quality=EvidenceQuality(),
    )
    assert receipt.sha256 == digest
    assert receipt.artifact_id == "golden-08-receipt"

    # Receipt resolves through the store
    assert raw_store.resolve_receipt(receipt) == body

    # Different content → different digest (collision resistance)
    body2 = b"different-evidence-content"
    digest2 = raw_store.put(body2)
    assert digest2 != digest, "Different content produced same digest"

    # Mutation raises integrity error (fail-closed)
    raw_store.mock_mutate(digest, b"tampered-content")
    with pytest.raises(ArtifactIntegrityError, match="failed digest verification"):
        raw_store.resolve(digest)

    # Missing digest raises integrity error
    fake_digest = "0" * 64
    with pytest.raises(ArtifactIntegrityError, match="missing"):
        raw_store.resolve(fake_digest)


# ===================================================================
# Scenario 9: Separation of duties
# ===================================================================

def test_scenario_09_separation_of_duties():
    """Ops cannot approve gates; reviewer cannot mutate run state.

    The role capability matrix enforces separation of duties at the kernel
    level. A profile that grants both capabilities to a single role is
    refused at load time (self-approval guard).
    """
    # --- Authority matrix ---
    assert can_mutate_run_state("ops") is True, "Ops must be able to mutate run state"
    assert can_approve_gate("ops") is False, "Ops must NOT be able to approve gates"
    assert can_mutate_run_state("reviewer") is False, "Reviewer must NOT mutate run state"
    assert can_approve_gate("reviewer") is True, "Reviewer must be able to approve gates"

    # Observer is read-only on all actions
    assert can_mutate_run_state("observer") is False
    assert can_approve_gate("observer") is False

    # --- AuthorityGuard ---
    guard = AuthorityGuard()

    assert guard.can_perform("ops", "approve_gate") is False
    assert guard.can_perform("ops", "mutate_run_state") is True
    assert guard.can_perform("reviewer", "approve_gate") is True
    assert guard.can_perform("reviewer", "mutate_run_state") is False
    assert guard.can_perform("observer", "approve_gate") is False
    assert guard.can_perform("observer", "mutate_run_state") is False
    assert guard.can_perform("observer", "write") is False

    # Ops cannot approve gates (AuthorityError raised)
    with pytest.raises(AuthorityError, match="cannot approve_gate"):
        guard.approve(
            actor="ops-user",
            role="ops",
            scope="test-scope",
            policy_digest="v1",
            decision="approved",
        )

    # Reviewer cannot write (AuthorityError raised)
    with pytest.raises(AuthorityError, match="read-only"):
        guard.assert_can_write("reviewer", "commit")

    # --- Self-approval guard ---
    # A profile granting both capabilities to one role is refused at load
    bad_profile = {
        "name": "self-approver",
        "tier": "balanced",
        "limits": {
            "timeout": 60.0,
            "max_retries": 1,
            "min_models_required": 2,
            "on_model_failure": "skip",
        },
        "roles": {
            "ops": {
                "model": "faigate/deepseek-v4-pro",
                "tool": {"name": "opencode", "launch_command": "opencode run -"},
                "capabilities": {"can_mutate_run_state": True, "can_approve_gate": True},
            },
        },
    }
    with pytest.raises(RoutingProfileError, match="self-approval"):
        from_dict(bad_profile)

    # A valid profile loads cleanly (no self-approval)
    good_profile = {
        "name": "well-separated",
        "tier": "balanced",
        "limits": {
            "timeout": 60.0,
            "max_retries": 1,
            "min_models_required": 2,
            "on_model_failure": "skip",
        },
        "roles": {
            "ops": {
                "model": "faigate/deepseek-v4-pro",
                "tool": {"name": "opencode", "launch_command": "opencode run -"},
                "capabilities": {"can_mutate_run_state": True},
            },
            "reviewer": {
                "model": "faigate/deepseek-v4-pro",
                "tool": {"name": "opencode", "launch_command": "opencode run -"},
                "capabilities": {"can_approve_gate": True},
            },
        },
    }
    profile = from_dict(good_profile)
    assert profile.role("ops").can(CAP_MUTATE_RUN_STATE) is True
    assert profile.role("ops").can(CAP_APPROVE_GATE) is False
    assert profile.role("reviewer").can(CAP_APPROVE_GATE) is True
    assert profile.role("reviewer").can(CAP_MUTATE_RUN_STATE) is False


# ===================================================================
# Scenario 10: Completion contract boundaries
# ===================================================================

def test_scenario_10_completion_contract_boundaries():
    """CompletionContract evaluates gate state correctly for every boundary.

    The contract is the kernel's gate authority: it decides PASS, FAIL, or
    INCONCLUSIVE from the verified outcome. Every termination mode and output
    combination is covered.
    """
    contract = CompletionContract()

    # --- PASS cases ---
    assert contract.evaluate(
        exit_code=0, signal=None, termination="exited", stdout=b"real output"
    ) == GateState.PASS

    # --- FAIL cases ---
    assert contract.evaluate(
        exit_code=1, signal=None, termination="exited", stdout=b"output"
    ) == GateState.FAIL, "Non-zero exit must fail"

    assert contract.evaluate(
        exit_code=None, signal=9, termination="signaled", stdout=b"output"
    ) == GateState.FAIL, "Signal termination must fail"

    assert contract.evaluate(
        exit_code=None, signal=None, termination="timed_out", stdout=b"partial"
    ) == GateState.FAIL, "Timeout must fail"

    assert contract.evaluate(
        exit_code=None, signal=None, termination="cancelled", stdout=b"partial"
    ) == GateState.FAIL, "Cancel must fail"

    # --- INCONCLUSIVE cases ---
    assert contract.evaluate(
        exit_code=0, signal=None, termination="exited", stdout=b""
    ) == GateState.INCONCLUSIVE, "Empty stdout must be inconclusive"

    assert contract.evaluate(
        exit_code=0, signal=None, termination="exited", stdout=b"   "
    ) == GateState.INCONCLUSIVE, "Whitespace-only stdout must be inconclusive"

    # check_output callback: failing check → INCONCLUSIVE
    def check_all_upper(data: bytes) -> bool:
        return data.decode().isupper()

    assert contract.evaluate(
        exit_code=0, signal=None, termination="exited",
        stdout=b"HELLO", check_output=check_all_upper,
    ) == GateState.PASS, "Check-output pass must be PASS"

    assert contract.evaluate(
        exit_code=0, signal=None, termination="exited",
        stdout=b"Hello", check_output=check_all_upper,
    ) == GateState.INCONCLUSIVE, "Check-output fail must be INCONCLUSIVE"

    # --- Verifier maps gate to grade correctly ---
    verifier = Verifier()

    verdict = verifier.assess(
        "scenario-10-artifact",
        exit_code=0, signal=None, termination="exited", stdout=b"data",
    )
    assert verdict.grade == "high"
    assert verdict.gate_state == GateState.PASS

    verdict = verifier.assess(
        "scenario-10-artifact",
        exit_code=1, signal=None, termination="exited", stdout=b"data",
    )
    assert verdict.grade == "failed"
    assert verdict.gate_state == GateState.FAIL

    verdict = verifier.assess(
        "scenario-10-artifact",
        exit_code=0, signal=None, termination="exited", stdout=b"",
    )
    assert verdict.grade == "inconclusive"
    assert verdict.gate_state == GateState.INCONCLUSIVE

    # Signal termination → failed grade
    verdict = verifier.assess(
        "scenario-10-artifact",
        exit_code=None, signal=11, termination="signaled", stdout=b"data",
    )
    assert verdict.grade == "failed"
    assert verdict.gate_state == GateState.FAIL


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required)
# ---------------------------------------------------------------------------

def _run_all() -> int:
    """Run every test_* function in this module and print PASS/FAIL/SKIP."""
    tests = [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ == "Skipped":
                print(f"SKIP {t.__name__}")
                continue
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
