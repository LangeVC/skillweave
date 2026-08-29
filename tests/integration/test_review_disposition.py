"""Integration tests for review dispositions (SW1311-REVIEW-001, criteria 1-3).

Behavioural tests over the review policy in :mod:`skillweave.trace.review`:

1. Every finding carries a stable id, criterion or code location, severity,
   evidence reference, reviewer identity and exact full subject SHA.
2. Before correction generation every finding receives exactly one
   accepted/rejected disposition with rationale and actor identity; a duplicate
   or conflicting disposition fails closed.
3. Controller adjudication separately verifies location, reachable state, causal
   chain and impact, and may uphold / narrow / reject individual findings while
   the immutable reviewer record is preserved — never synthesizing ``REVIEW_PASS``.

No harness, no provider/model name, no text/source-presence assertions.
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.trace.review import (  # noqa: E402
    AdjudicationDecision,
    Disposition,
    DispositionDecision,
    DispositionError,
    DispositionRegister,
    Finding,
    ReviewPolicyError,
    ReviewVerdict,
    Severity,
    adjudicate,
    new_finding,
    review_fail,
    review_pass,
)

_SHA = "a" * 40


# ── Criterion 1: findings are complete and stable ───────────────────────────


def test_finding_carries_all_required_fields():
    finding = new_finding(
        reviewer_id="r1",
        subject_sha=_SHA,
        severity=Severity.MAJOR,
        evidence_ref="ref:stdout:abc",
        code_location="src/foo.py:12",
    )
    assert finding.id
    assert finding.reviewer_id == "r1"
    assert finding.subject_sha == _SHA
    assert finding.severity is Severity.MAJOR
    assert finding.evidence_ref == "ref:stdout:abc"
    assert finding.code_location == "src/foo.py:12"


def test_finding_may_name_criterion_instead_of_location():
    finding = new_finding(
        reviewer_id="r1",
        subject_sha=_SHA,
        severity=Severity.BLOCKER,
        evidence_ref="ref:x",
        criterion="criterion-2",
    )
    assert finding.criterion == "criterion-2"
    assert finding.code_location is None


def test_finding_id_is_stable_for_same_observation():
    f1 = new_finding(
        reviewer_id="r1", subject_sha=_SHA, severity=Severity.MAJOR,
        evidence_ref="ref:x", criterion="c2",
    )
    f2 = new_finding(
        reviewer_id="r1", subject_sha=_SHA, severity=Severity.MAJOR,
        evidence_ref="ref:x", criterion="c2",
    )
    assert f1.id == f2.id


def test_finding_requires_criterion_or_location():
    with pytest.raises(ReviewPolicyError):
        Finding(
            id="f1", severity=Severity.MAJOR, evidence_ref="ref:x",
            reviewer_id="r1", subject_sha=_SHA,
        ).validate()


def test_finding_requires_full_subject_sha():
    with pytest.raises(ReviewPolicyError):
        Finding(
            id="f1", severity=Severity.MAJOR, evidence_ref="ref:x",
            reviewer_id="r1", subject_sha="short",
            criterion="c1",
        ).validate()


def test_finding_requires_reviewer_and_evidence():
    with pytest.raises(ReviewPolicyError):
        Finding(
            id="f1", severity=Severity.MAJOR, evidence_ref="",
            reviewer_id="r1", subject_sha=_SHA, criterion="c1",
        ).validate()
    with pytest.raises(ReviewPolicyError):
        Finding(
            id="f1", severity=Severity.MAJOR, evidence_ref="ref:x",
            reviewer_id="", subject_sha=_SHA, criterion="c1",
        ).validate()


# ── Criterion 2: exactly one disposition per finding, fail-closed ────────────


def test_disposition_records_single_decision():
    register = DispositionRegister()
    d = Disposition(
        finding_id="f1",
        decision=DispositionDecision.ACCEPTED,
        rationale="evidence matches the failure",
        actor_id="controller",
    )
    register.record(d)
    assert register.decision("f1") is DispositionDecision.ACCEPTED
    assert register.accepted_finding_ids() == ["f1"]
    assert register.rejected_finding_ids() == []


def test_duplicate_disposition_fails_closed():
    register = DispositionRegister()
    register.record(Disposition(
        finding_id="f1", decision=DispositionDecision.ACCEPTED,
        rationale="accepted", actor_id="controller",
    ))
    with pytest.raises(DispositionError):
        register.record(Disposition(
            finding_id="f1", decision=DispositionDecision.REJECTED,
            rationale="now rejected", actor_id="controller",
        ))


def test_conflicting_disposition_fails_closed():
    register = DispositionRegister()
    register.record(Disposition(
        finding_id="f1", decision=DispositionDecision.REJECTED,
        rationale="rejected", actor_id="controller",
    ))
    with pytest.raises(DispositionError):
        register.record(Disposition(
            finding_id="f1", decision=DispositionDecision.ACCEPTED,
            rationale="now accepted", actor_id="controller",
        ))
    assert len(register) == 1


def test_disposition_requires_rationale_and_actor():
    with pytest.raises(DispositionError):
        Disposition(
            finding_id="f1", decision=DispositionDecision.ACCEPTED,
            rationale="", actor_id="controller",
        ).validate()
    with pytest.raises(DispositionError):
        Disposition(
            finding_id="f1", decision=DispositionDecision.ACCEPTED,
            rationale="r", actor_id="",
        ).validate()


def test_require_all_fails_on_missing_disposition():
    f1 = new_finding(reviewer_id="r1", subject_sha=_SHA,
                     severity=Severity.MAJOR, evidence_ref="ref", criterion="c1")
    f2 = new_finding(reviewer_id="r1", subject_sha=_SHA,
                     severity=Severity.MINOR, evidence_ref="ref2", criterion="c2")
    register = DispositionRegister()
    register.record(Disposition(
        finding_id=f1.id, decision=DispositionDecision.ACCEPTED,
        rationale="r", actor_id="controller",
    ))
    with pytest.raises(DispositionError):
        register.require_all([f1, f2])


def test_require_all_fails_on_orphan_disposition():
    f1 = new_finding(reviewer_id="r1", subject_sha=_SHA,
                     severity=Severity.MAJOR, evidence_ref="ref", criterion="c1")
    register = DispositionRegister()
    register.record(Disposition(
        finding_id="ghost", decision=DispositionDecision.ACCEPTED,
        rationale="r", actor_id="controller",
    ))
    with pytest.raises(DispositionError):
        register.require_all([f1])


# ── Criterion 3: controller adjudication, never REVIEW_PASS ─────────────────


def test_adjudication_upholds_when_all_four_verified():
    finding = new_finding(reviewer_id="r1", subject_sha=_SHA,
                          severity=Severity.BLOCKER, evidence_ref="ref", criterion="c1")
    result = adjudicate(
        finding, actor_id="controller",
        location_verified=True, reachable_verified=True,
        causal_verified=True, impact_verified=True,
    )
    assert result.decision is AdjudicationDecision.UPHOLD
    assert result.finding_id == finding.id


def test_adjudication_rejects_when_location_not_verified():
    finding = new_finding(reviewer_id="r1", subject_sha=_SHA,
                          severity=Severity.BLOCKER, evidence_ref="ref", criterion="c1")
    result = adjudicate(
        finding, actor_id="controller",
        location_verified=False, reachable_verified=True,
        causal_verified=True, impact_verified=True,
    )
    assert result.decision is AdjudicationDecision.REJECT


def test_adjudication_rejects_when_unreachable_or_not_causal():
    finding = new_finding(reviewer_id="r1", subject_sha=_SHA,
                          severity=Severity.BLOCKER, evidence_ref="ref", criterion="c1")
    unreachable = adjudicate(
        finding, actor_id="controller", location_verified=True,
        reachable_verified=False, causal_verified=True, impact_verified=True,
    )
    assert unreachable.decision is AdjudicationDecision.REJECT
    not_causal = adjudicate(
        finding, actor_id="controller", location_verified=True,
        reachable_verified=True, causal_verified=False, impact_verified=True,
    )
    assert not_causal.decision is AdjudicationDecision.REJECT


def test_adjudication_narrows_when_impact_not_verified():
    finding = new_finding(reviewer_id="r1", subject_sha=_SHA,
                          severity=Severity.BLOCKER, evidence_ref="ref", criterion="c1")
    result = adjudicate(
        finding, actor_id="controller", location_verified=True,
        reachable_verified=True, causal_verified=True, impact_verified=False,
    )
    assert result.decision is AdjudicationDecision.NARROW
    assert result.narrowed_severity is Severity.MAJOR


def test_adjudication_preserves_immutable_finding():
    finding = new_finding(reviewer_id="r1", subject_sha=_SHA,
                          severity=Severity.MAJOR, evidence_ref="ref", criterion="c1")
    original = finding.to_dict()
    adjudicate(
        finding, actor_id="controller", location_verified=True,
        reachable_verified=True, causal_verified=True, impact_verified=False,
    )
    assert finding.to_dict() == original  # immutable reviewer record preserved


def test_adjudication_never_yields_review_verdict():
    finding = new_finding(reviewer_id="r1", subject_sha=_SHA,
                          severity=Severity.MAJOR, evidence_ref="ref", criterion="c1")
    result = adjudicate(
        finding, actor_id="controller", location_verified=True,
        reachable_verified=True, causal_verified=True, impact_verified=True,
    )
    assert isinstance(result, __import__("skillweave.trace.review", fromlist=["Adjudication"]).Adjudication)
    assert not isinstance(result, type(ReviewVerdict.REVIEW_PASS))


def test_reviewer_vernaciates_pass_and_fail_only():
    fail = review_fail("r1", _SHA, [new_finding(
        reviewer_id="r1", subject_sha=_SHA, severity=Severity.BLOCKER,
        evidence_ref="ref", criterion="c1",
    )])
    assert fail.verdict is ReviewVerdict.REVIEW_FAIL
    assert len(fail.findings) == 1

    passed = review_pass("r2", _SHA)
    assert passed.verdict is ReviewVerdict.REVIEW_PASS
    assert passed.findings == ()


def test_review_record_forbids_mismatched_finding_sha():
    finding = new_finding(reviewer_id="r1", subject_sha="b" * 40,
                          severity=Severity.MAJOR, evidence_ref="ref", criterion="c1")
    with pytest.raises(ReviewPolicyError):
        review_fail("r1", _SHA, [finding])


def _run_all() -> int:
    tests = [
        test_finding_carries_all_required_fields,
        test_finding_may_name_criterion_instead_of_location,
        test_finding_id_is_stable_for_same_observation,
        test_finding_requires_criterion_or_location,
        test_finding_requires_full_subject_sha,
        test_finding_requires_reviewer_and_evidence,
        test_disposition_records_single_decision,
        test_duplicate_disposition_fails_closed,
        test_conflicting_disposition_fails_closed,
        test_disposition_requires_rationale_and_actor,
        test_require_all_fails_on_missing_disposition,
        test_require_all_fails_on_orphan_disposition,
        test_adjudication_upholds_when_all_four_verified,
        test_adjudication_rejects_when_location_not_verified,
        test_adjudication_rejects_when_unreachable_or_not_causal,
        test_adjudication_narrows_when_impact_not_verified,
        test_adjudication_preserves_immutable_finding,
        test_adjudication_never_yields_review_verdict,
        test_reviewer_vernaciates_pass_and_fail_only,
        test_review_record_forbids_mismatched_finding_sha,
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
