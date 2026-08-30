"""Integration tests for the review rework gate (SW1311-REVIEW-001, criteria 4-8).

Behavioural tests over the review policy in :mod:`skillweave.trace.review`:

4. Controller verification failure or ``REVIEW_FAIL`` freezes the exact
   candidate and prevents dependent-lane readiness.
5. Correction handoff includes all-and-only accepted finding ids, consumes a
   bounded correction round and requires subsequent controller verification plus
   a fresh cold review.
6. A changed subject SHA invalidates the prior verdict and dispositions unless
   an explicit finding-by-finding carry-forward rule applies.
7. Producer and reviewer require separate sessions, roles and worktrees; a
   reviewer's mutation/repair authority fails before execution.
8. A critical final gate dispatches two diverse reviewers concurrently against
   one immutable subject, requires both ``REVIEW_PASS``, and routes material
   disagreement to targeted evidence adjudication rather than majority voting.
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.trace.review import (  # noqa: E402
    ActorBinding,
    CarryForwardRule,
    CandidateReviewState,
    CriticalGateError,
    CriticalReviewer,
    Disposition,
    DispositionDecision,
    DispositionRegister,
    EvidenceAdjudication,
    ReviewAuthorityError,
    ReviewPolicyError,
    ReviewVerdict,
    Severity,
    assert_reviewer_authority,
    build_correction_handoff,
    correction_complete,
    dispatch_critical_gate,
    evaluate_critical_gate,
    invalidate_on_subject_change,
    new_finding,
    review_fail,
    review_pass,
    validate_critical_reviewers,
    validate_producer_reviewer_separation,
)

_SHA = "a" * 40
_OTHER_SHA = "b" * 40


def _finding(reviewer_id, subject_sha=_SHA, criterion="c1", severity=Severity.MAJOR):
    return new_finding(
        reviewer_id=reviewer_id, subject_sha=subject_sha,
        severity=severity, evidence_ref="ref", criterion=criterion,
    )


# ── Criterion 4: freeze and dependent readiness ─────────────────────────────


def test_review_fail_freezes_exact_candidate():
    state = CandidateReviewState(subject_sha=_SHA)
    state.record_review(review_fail("r1", _SHA, [_finding("r1")]))
    assert state.frozen is True
    assert state.frozen_subject_sha() == _SHA
    assert state.dependent_ready() is False


def test_controller_verification_failure_freezes_exact_candidate():
    state = CandidateReviewState(subject_sha=_SHA)
    state.record_review(review_pass("r1", _SHA))
    state.record_controller_verification(False)
    assert state.frozen is True
    assert state.frozen_subject_sha() == _SHA
    assert state.dependent_ready() is False


def test_dependent_ready_requires_pass_and_verification_and_not_frozen():
    state = CandidateReviewState(subject_sha=_SHA)
    state.record_review(review_pass("r1", _SHA))
    state.record_controller_verification(True)
    assert state.dependent_ready() is True


def test_frozen_blocked_readiness_even_if_later_passed():
    state = CandidateReviewState(subject_sha=_SHA)
    state.record_review(review_fail("r1", _SHA, [_finding("r1")]))
    # Even a later verification success cannot thaw a frozen candidate.
    state.record_controller_verification(True)
    assert state.frozen is True
    assert state.dependent_ready() is False


def test_candidate_rejects_non_full_sha():
    with pytest.raises(ReviewPolicyError):
        CandidateReviewState(subject_sha="short")


# ── Criterion 5: correction handoff ─────────────────────────────────────────


def test_correction_handoff_carries_only_accepted_ids():
    f1 = _finding("r1", criterion="c1")
    f2 = _finding("r1", criterion="c2")
    f3 = _finding("r1", criterion="c3")
    register = DispositionRegister()
    register.record(Disposition(f1.id, DispositionDecision.ACCEPTED, "a", "controller"))
    register.record(Disposition(f2.id, DispositionDecision.REJECTED, "b", "controller"))
    register.record(Disposition(f3.id, DispositionDecision.ACCEPTED, "c", "controller"))

    handoff = build_correction_handoff(
        [f1, f2, f3], register, subject_sha=_SHA,
        correction_round=1, max_rounds=2,
    )
    assert handoff.finding_ids == tuple(sorted([f1.id, f3.id]))
    assert f2.id not in handoff.finding_ids


def test_correction_handoff_requires_dispositions():
    f1 = _finding("r1", criterion="c1")
    f2 = _finding("r1", criterion="c2")
    register = DispositionRegister()
    register.record(Disposition(f1.id, DispositionDecision.ACCEPTED, "a", "controller"))
    with pytest.raises(__import__("skillweave.trace.review", fromlist=["DispositionError"]).DispositionError):
        build_correction_handoff(
            [f1, f2], register, subject_sha=_SHA, correction_round=1, max_rounds=2,
        )


def test_correction_handoff_is_bounded():
    f1 = _finding("r1", criterion="c1")
    register = DispositionRegister()
    register.record(Disposition(f1.id, DispositionDecision.ACCEPTED, "a", "controller"))
    from skillweave.trace.review import CorrectionHandoffError

    with pytest.raises(CorrectionHandoffError):
        build_correction_handoff(
            [f1], register, subject_sha=_SHA, correction_round=3, max_rounds=2,
        )
    with pytest.raises(CorrectionHandoffError):
        build_correction_handoff(
            [f1], register, subject_sha=_SHA, correction_round=0, max_rounds=2,
        )


def test_correction_complete_requires_fresh_review_and_verification():
    f1 = _finding("r1", criterion="c1")
    register = DispositionRegister()
    register.record(Disposition(f1.id, DispositionDecision.ACCEPTED, "a", "controller"))
    handoff = build_correction_handoff(
        [f1], register, subject_sha=_SHA, correction_round=1, max_rounds=2,
    )

    # No fresh review -> incomplete.
    assert correction_complete(handoff, controller_verified=True, fresh_review=None) is False
    # Fresh review on the wrong subject -> refuses.
    with pytest.raises(ReviewPolicyError):
        correction_complete(
            handoff, controller_verified=True, fresh_review=review_pass("r2", _OTHER_SHA),
        )
    # Fresh REVIEW_FAIL -> incomplete.
    assert correction_complete(
        handoff, controller_verified=True,
        fresh_review=review_fail("r2", _SHA, [_finding("r2")]),
    ) is False
    # Fresh REVIEW_PASS + verification -> complete.
    assert correction_complete(
        handoff, controller_verified=True, fresh_review=review_pass("r2", _SHA),
    ) is True
    # Verification failure keeps it incomplete even with a fresh pass.
    assert correction_complete(
        handoff, controller_verified=False, fresh_review=review_pass("r2", _SHA),
    ) is False


# ── Criterion 6: subject-change invalidation ────────────────────────────────


def test_changed_sha_invalidates_verdict_and_dispositions():
    f1 = _finding("r1", criterion="c1")
    f2 = _finding("r1", criterion="c2")
    review = review_fail("r1", _SHA, [f1, f2])
    register = DispositionRegister()
    register.record(Disposition(f1.id, DispositionDecision.ACCEPTED, "a", "controller"))
    register.record(Disposition(f2.id, DispositionDecision.REJECTED, "b", "controller"))

    result = invalidate_on_subject_change(review, register, new_subject_sha=_OTHER_SHA)
    assert result.verdict_invalidated is True
    assert set(result.invalidated_finding_ids) == {f1.id, f2.id}
    assert result.carried_forward_finding_ids == ()


def test_explicit_carry_forward_rule_preserves_finding():
    f1 = _finding("r1", criterion="c1")
    f2 = _finding("r1", criterion="c2")
    review = review_fail("r1", _SHA, [f1, f2])
    register = DispositionRegister()
    register.record(Disposition(f1.id, DispositionDecision.ACCEPTED, "a", "controller"))
    register.record(Disposition(f2.id, DispositionDecision.REJECTED, "b", "controller"))

    result = invalidate_on_subject_change(
        review, register, new_subject_sha=_OTHER_SHA,
        carry_forward=[CarryForwardRule(f1.id, _OTHER_SHA)],
    )
    assert result.carried_forward_finding_ids == (f1.id,)
    assert result.invalidated_finding_ids == (f2.id,)


def test_carry_forward_rules_for_unknown_finding_refused():
    f1 = _finding("r1", criterion="c1")
    review = review_fail("r1", _SHA, [f1])
    register = DispositionRegister()
    register.record(Disposition(f1.id, DispositionDecision.ACCEPTED, "a", "controller"))
    with pytest.raises(ReviewPolicyError):
        invalidate_on_subject_change(
            review, register, new_subject_sha=_OTHER_SHA,
            carry_forward=[CarryForwardRule("ghost", _OTHER_SHA)],
        )


def test_unchanged_sha_is_not_an_invalidation():
    f1 = _finding("r1", criterion="c1")
    review = review_fail("r1", _SHA, [f1])
    register = DispositionRegister()
    register.record(Disposition(f1.id, DispositionDecision.ACCEPTED, "a", "controller"))
    with pytest.raises(ReviewPolicyError):
        invalidate_on_subject_change(review, register, new_subject_sha=_SHA)


# ── Criterion 7: separation and reviewer authority ──────────────────────────


def test_producer_reviewer_separation_passes_when_distinct():
    producer = ActorBinding("p1", "producer", "sess-1", "/wt/prod")
    reviewer = ActorBinding("r1", "reviewer", "sess-2", "/wt/review")
    validate_producer_reviewer_separation(producer, reviewer)  # no raise


def test_producer_reviewer_same_session_refused():
    producer = ActorBinding("p1", "producer", "sess-1", "/wt/prod")
    reviewer = ActorBinding("r1", "reviewer", "sess-1", "/wt/review")
    with pytest.raises(ReviewAuthorityError):
        validate_producer_reviewer_separation(producer, reviewer)


def test_producer_reviewer_same_worktree_refused():
    producer = ActorBinding("p1", "producer", "sess-1", "/wt/shared")
    reviewer = ActorBinding("r1", "reviewer", "sess-2", "/wt/shared")
    with pytest.raises(ReviewAuthorityError):
        validate_producer_reviewer_separation(producer, reviewer)


def test_wrong_roles_refused():
    producer = ActorBinding("p1", "reviewer", "sess-1", "/wt/prod")
    reviewer = ActorBinding("r1", "reviewer", "sess-2", "/wt/review")
    with pytest.raises(ReviewAuthorityError):
        validate_producer_reviewer_separation(producer, reviewer)


def test_reviewer_mutation_authority_fails_before_execution():
    reviewer = ActorBinding("r1", "reviewer", "sess-2", "/wt/review")
    for action in ("mutate", "repair", "write", "commit", "push", "merge", "release", "tag"):
        with pytest.raises(ReviewAuthorityError):
            assert_reviewer_authority(reviewer, action)


def test_reviewer_read_authority_is_not_forbidden():
    reviewer = ActorBinding("r1", "reviewer", "sess-2", "/wt/review")
    assert_reviewer_authority(reviewer, "read")  # no raise
    assert_reviewer_authority(reviewer, "observe")  # no raise


# ── Criterion 8: critical final gate ────────────────────────────────────────


def test_critical_gate_requires_two_diverse_reviewers():
    with pytest.raises(CriticalGateError):
        validate_critical_reviewers([])
    with pytest.raises(CriticalGateError):
        validate_critical_reviewers([CriticalReviewer("r1", "pro")])
    # Same reviewer id twice -> not distinct.
    with pytest.raises(CriticalGateError):
        validate_critical_reviewers([
            CriticalReviewer("r1", "pro"), CriticalReviewer("r1", "flash"),
        ])
    # Distinct ids but same kind -> not diverse.
    with pytest.raises(CriticalGateError):
        validate_critical_reviewers([
            CriticalReviewer("r1", "pro"), CriticalReviewer("r2", "pro"),
        ])
    # Two distinct, diverse -> OK.
    validate_critical_reviewers([
        CriticalReviewer("r1", "pro"), CriticalReviewer("r2", "flash"),
    ])


def test_dispatch_critical_gate_passes_both_reviewers_concurrently():
    called = []

    def dispatcher(reviewers):
        called.append(list(reviewers))

    dispatch_critical_gate(
        _SHA,
        [CriticalReviewer("r1", "pro"), CriticalReviewer("r2", "flash")],
        dispatcher,
    )
    assert called == [[CriticalReviewer("r1", "pro"), CriticalReviewer("r2", "flash")]]


def test_dispatch_critical_gate_refuses_non_full_or_nondiverse_subject():
    def dispatcher(reviewers):
        raise AssertionError("must not dispatch")

    with pytest.raises(CriticalGateError):
        dispatch_critical_gate(
            "short",
            [CriticalReviewer("r1", "pro"), CriticalReviewer("r2", "flash")],
            dispatcher,
        )
    with pytest.raises(CriticalGateError):
        dispatch_critical_gate(
            _SHA,
            [CriticalReviewer("r1", "pro")],
            dispatcher,
        )


def test_critical_gate_passes_when_both_pass_without_disagreement():
    result = evaluate_critical_gate(
        _SHA, [review_pass("r1", _SHA), review_pass("r2", _SHA)]
    )
    assert result.passed is True
    assert result.evidence_adjudication is None


def test_critical_gate_fails_when_one_reviewer_fails():
    result = evaluate_critical_gate(
        _SHA,
        [review_pass("r1", _SHA), review_fail("r2", _SHA, [_finding("r2")])],
    )
    assert result.passed is False
    # A verdict disagreement routes the failing reviewer's findings to
    # targeted evidence adjudication, not majority voting.
    assert result.evidence_adjudication is not None
    assert result.evidence_adjudication.disputed_finding_ids


def test_critical_gate_routes_material_disagreement_to_adjudication():
    # Both pass, but disagree on the severity of the same criterion -> material
    # disagreement routed to targeted evidence adjudication.
    r1_finding = _finding("r1", criterion="c1", severity=Severity.BLOCKER)
    r2_finding = _finding("r2", criterion="c1", severity=Severity.MINOR)
    result = evaluate_critical_gate(
        _SHA,
        [
            review_pass("r1", _SHA, [r1_finding]),
            review_pass("r2", _SHA, [r2_finding]),
        ],
    )
    assert result.passed is False
    assert isinstance(result.evidence_adjudication, EvidenceAdjudication)
    assert set(result.evidence_adjudication.disputed_finding_ids) == {
        r1_finding.id, r2_finding.id
    }


def test_critical_gate_requires_reviews_for_same_subject():
    with pytest.raises(CriticalGateError):
        evaluate_critical_gate(_SHA, [review_pass("r1", _SHA), review_pass("r2", _OTHER_SHA)])


def _run_all() -> int:
    tests = [
        test_review_fail_freezes_exact_candidate,
        test_controller_verification_failure_freezes_exact_candidate,
        test_dependent_ready_requires_pass_and_verification_and_not_frozen,
        test_frozen_blocked_readiness_even_if_later_passed,
        test_candidate_rejects_non_full_sha,
        test_correction_handoff_carries_only_accepted_ids,
        test_correction_handoff_requires_dispositions,
        test_correction_handoff_is_bounded,
        test_correction_complete_requires_fresh_review_and_verification,
        test_changed_sha_invalidates_verdict_and_dispositions,
        test_explicit_carry_forward_rule_preserves_finding,
        test_carry_forward_rules_for_unknown_finding_refused,
        test_unchanged_sha_is_not_an_invalidation,
        test_producer_reviewer_separation_passes_when_distinct,
        test_producer_reviewer_same_session_refused,
        test_producer_reviewer_same_worktree_refused,
        test_wrong_roles_refused,
        test_reviewer_mutation_authority_fails_before_execution,
        test_reviewer_read_authority_is_not_forbidden,
        test_critical_gate_requires_two_diverse_reviewers,
        test_dispatch_critical_gate_passes_both_reviewers_concurrently,
        test_dispatch_critical_gate_refuses_non_full_or_nondiverse_subject,
        test_critical_gate_passes_when_both_pass_without_disagreement,
        test_critical_gate_fails_when_one_reviewer_fails,
        test_critical_gate_routes_material_disagreement_to_adjudication,
        test_critical_gate_requires_reviews_for_same_subject,
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
