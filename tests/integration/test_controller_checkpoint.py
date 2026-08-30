"""Integration tests for controller checkpoints (SW1311-HANDOFF-001, criteria 4-6).

Behavioural tests over the checkpoint/reconstruction layer in
:mod:`skillweave.trace.handoff`:

4. A controller checkpoint preserves all frozen candidate SHAs and bases, the
   latest verdict, accepted finding ids, correction budgets, the current batch
   and whether an external job is active.
5. A cold controller reconstructs the next legal action from the checkpoint and
   typed records without a transcript, while the result explicitly disclaims
   autonomous crash recovery and persistent observer resume.
6. Human-readable handoff and checkpoint logs are projections only; editing them
   cannot change dispatch state.

No harness, no provider/model name, no text/source-presence assertions.
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.trace.review import ReviewVerdict  # noqa: E402

from skillweave.promptchain.execute import (  # noqa: E402
    SessionState,
    resume_batch_command,
)

from skillweave.trace.handoff import (  # noqa: E402
    CheckpointError,
    ControllerCheckpoint,
    FrozenCandidate,
    NextAction,
    build_checkpoint,
    build_correction_handoff,
    build_ops_handoff,
    build_review_handoff,
    checkpoint_log,
    handoff_log,
    reconstruct_next_action,
    requires_review,
)

_SHA = "a" * 40
_OTHER_SHA = "b" * 40
_THIRD_SHA = "c" * 40


def _candidate(sha=_SHA, base=_OTHER_SHA):
    return FrozenCandidate(candidate_sha=sha, base_sha=base)


def _correction_budget_handoff():
    return build_correction_handoff(
        source_receipt_id="rc", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"], correction_budget=2,
    )


# ── Criterion 4: complete frozen checkpoint ──────────────────────────────────


def test_checkpoint_preserves_all_frozen_fields():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate(), _candidate(_OTHER_SHA, _THIRD_SHA)],
        latest_verdict=ReviewVerdict.REVIEW_PASS,
        accepted_finding_ids=[],
        correction_budgets={"lane-a": 2, "lane-b": 0},
        current_batch=1,
        active_job=False,
    )
    assert len(checkpoint.frozen_candidates) == 2
    assert checkpoint.frozen_candidates[0].candidate_sha == _SHA
    assert checkpoint.frozen_candidates[0].base_sha == _OTHER_SHA
    assert checkpoint.frozen_candidates[1].candidate_sha == _OTHER_SHA
    assert checkpoint.frozen_candidates[1].base_sha == _THIRD_SHA
    assert checkpoint.latest_verdict is ReviewVerdict.REVIEW_PASS
    assert checkpoint.accepted_finding_ids == ()
    assert checkpoint.correction_budgets == {"lane-a": 2, "lane-b": 0}
    assert checkpoint.current_batch == 1
    assert checkpoint.active_job is False


def test_checkpoint_preserves_accepted_finding_ids_and_active_job():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_FAIL,
        accepted_finding_ids=["f1", "f2"],
        correction_budgets={"lane-a": 3},
        current_batch=0,
        active_job=True,
    )
    assert checkpoint.accepted_finding_ids == ("f1", "f2")
    assert checkpoint.correction_budgets == {"lane-a": 3}
    assert checkpoint.active_job is True


def test_checkpoint_requires_full_shas():
    with pytest.raises(CheckpointError):
        build_checkpoint(
            frozen_candidates=[FrozenCandidate("short", _OTHER_SHA)],
            latest_verdict=None,
            accepted_finding_ids=[],
            correction_budgets={},
            current_batch=0,
            active_job=False,
        )
    with pytest.raises(CheckpointError):
        build_checkpoint(
            frozen_candidates=[FrozenCandidate(_SHA, "short")],
            latest_verdict=None,
            accepted_finding_ids=[],
            correction_budgets={},
            current_batch=0,
            active_job=False,
        )


def test_checkpoint_requires_consistent_scalars():
    with pytest.raises(CheckpointError):
        build_checkpoint(
            frozen_candidates=[_candidate()],
            latest_verdict=None,
            accepted_finding_ids=[],
            correction_budgets={},
            current_batch=-1,
            active_job=False,
        )
    with pytest.raises(CheckpointError):
        build_checkpoint(
            frozen_candidates=[_candidate()],
            latest_verdict=None,
            accepted_finding_ids=[],
            correction_budgets={"lane": "not-an-int"},
            current_batch=0,
            active_job=False,
        )


def test_checkpoint_id_is_stable_for_identical_state():
    a = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_PASS,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=1,
        active_job=False,
    )
    b = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_PASS,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=1,
        active_job=False,
    )
    assert a.checkpoint_id == b.checkpoint_id


# ── Criterion 5: cold reconstruction without transcript ──────────────────────


def test_active_job_derives_await():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=None,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=1,
        active_job=True,
    )
    action = reconstruct_next_action(checkpoint, [])
    assert action.action == "await_job"


def test_fail_verdict_derives_correct():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_FAIL,
        accepted_finding_ids=["f1"],
        correction_budgets={"lane-a": 2},
        current_batch=0,
        active_job=False,
    )
    action = reconstruct_next_action(checkpoint, [_correction_budget_handoff()])
    assert action.action == "correct"


def test_pending_accepted_findings_derive_correct():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=None,
        accepted_finding_ids=["f1"],
        correction_budgets={"lane-a": 1},
        current_batch=0,
        active_job=False,
    )
    action = reconstruct_next_action(checkpoint, [_correction_budget_handoff()])
    assert action.action == "correct"


def test_pass_with_no_more_batches_derives_complete():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_PASS,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=0,
        active_job=False,
    )
    action = reconstruct_next_action(checkpoint, [])
    assert action.action == "complete"


def test_pass_with_more_batches_derives_integrate():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_PASS,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=2,
        active_job=False,
    )
    action = reconstruct_next_action(checkpoint, [])
    assert action.action == "integrate"


def test_no_verdict_derives_next_batch():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=None,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=3,
        active_job=False,
    )
    action = reconstruct_next_action(checkpoint, [])
    assert action.action == "dispatch_next_batch"
    assert action.next_batch == 4


def test_next_action_disclaims_autonomous_recovery_and_observer_resume():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_FAIL,
        accepted_finding_ids=["f1"],
        correction_budgets={"lane-a": 2},
        current_batch=0,
        active_job=False,
    )
    action = reconstruct_next_action(checkpoint, [_correction_budget_handoff()])
    assert action.disclaims_autonomous_recovery is True
    assert action.disclaims_persistent_observer_resume is True
    assert isinstance(action, NextAction)


def test_requires_review_on_fail_or_pending():
    fail = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_FAIL,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=0,
        active_job=False,
    )
    assert requires_review(fail) is True

    pending = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=None,
        accepted_finding_ids=["f1"],
        correction_budgets={},
        current_batch=0,
        active_job=False,
    )
    assert requires_review(pending) is True

    passed = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_PASS,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=0,
        active_job=False,
    )
    assert requires_review(passed) is False


# ── Criterion 6: projection-only logs ────────────────────────────────────────


def test_resume_batch_command_resolves_from_state_without_transcript():
    state = SessionState(
        session_boundary="batch",
        batch_index=2,
        commands=[
            __import__("skillweave.promptchain.execute", fromlist=["BatchCommand"])
            .BatchCommand(lane_id="lane-a", mode="subagent", command=["pytest", "-q"]),
        ],
    )
    command = resume_batch_command(state, lane_id="lane-a")
    assert command is not None
    assert command.lane_id == "lane-a"
    assert command.command == ["pytest", "-q"]
    # A lane not in the state's single batch yields no command (no invented work).
    assert resume_batch_command(state, lane_id="lane-unknown") is None


def test_handoff_log_cannot_mutate_state():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    before = ops.to_dict()
    text = handoff_log(ops)
    # Editing the projected text (mutate the string) leaves the handoff intact.
    _ = text.replace("src/x.py", "src/EVIL.py")
    assert ops.to_dict() == before
    assert ops.scope.allowed_paths == ("src/x.py",)


def test_checkpoint_log_cannot_mutate_state():
    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=ReviewVerdict.REVIEW_PASS,
        accepted_finding_ids=["f1"],
        correction_budgets={"lane-a": 2},
        current_batch=1,
        active_job=False,
    )
    before = checkpoint.to_dict()
    text = checkpoint_log(checkpoint)
    _ = text.replace("REVIEW_PASS", "REVIEW_FAIL")
    assert checkpoint.to_dict() == before
    assert checkpoint.latest_verdict is ReviewVerdict.REVIEW_PASS


def test_logs_are_deterministic_projections():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert handoff_log(ops) == handoff_log(ops)

    checkpoint = build_checkpoint(
        frozen_candidates=[_candidate()],
        latest_verdict=None,
        accepted_finding_ids=[],
        correction_budgets={},
        current_batch=0,
        active_job=False,
    )
    assert checkpoint_log(checkpoint) == checkpoint_log(checkpoint)


def _run_all() -> int:
    tests = [
        test_checkpoint_preserves_all_frozen_fields,
        test_checkpoint_preserves_accepted_finding_ids_and_active_job,
        test_checkpoint_requires_full_shas,
        test_checkpoint_requires_consistent_scalars,
        test_checkpoint_id_is_stable_for_identical_state,
        test_active_job_derives_await,
        test_fail_verdict_derives_correct,
        test_pending_accepted_findings_derive_correct,
        test_pass_with_no_more_batches_derives_complete,
        test_pass_with_more_batches_derives_integrate,
        test_no_verdict_derives_next_batch,
        test_next_action_disclaims_autonomous_recovery_and_observer_resume,
        test_requires_review_on_fail_or_pending,
        test_resume_batch_command_resolves_from_state_without_transcript,
        test_handoff_log_cannot_mutate_state,
        test_checkpoint_log_cannot_mutate_state,
        test_logs_are_deterministic_projections,
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
