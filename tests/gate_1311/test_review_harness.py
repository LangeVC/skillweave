"""Dispatch-order group 3 — "strict review loop and harness adherence" (criteria 5, 6).

Criterion 5 exercises the real review state machine in
``skillweave.trace.review``: a ``REVIEW_FAIL`` freezes the candidate, dispositions
must land before correction, the correction handoff carries only accepted
findings within a bounded round, and only a verified + fresh cold ``REVIEW_PASS``
completes it.

Criterion 6 exercises ``skillweave.dispatch.harness_contract`` against the
shipped hermetic adapter fixtures: strict binding, stale/mismatched digests,
bypass refusal, distinct single-role authority, and honest statuses.

Nothing here touches the network or mutates product state.
"""

from __future__ import annotations

from pathlib import Path
import yaml
import pytest

from skillweave.trace import review as R
from skillweave.dispatch import harness_contract as H

SHA_A = "a" * 40
SHA_B = "b" * 40

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "harnesses"


# ── Criterion 5: review loop ─────────────────────────────────────────────────


def test_criterion_05_review_fail_dispositions_bounded_correction_fresh_pass():
    """REVIEW_FAIL -> dispositions -> bounded correction -> fresh cold PASS."""
    # A reviewer records findings against an exact subject.
    f1 = R.new_finding(
        reviewer_id="reviewer-1", subject_sha=SHA_A, severity=R.Severity.MAJOR,
        evidence_ref="ev-1", criterion="append-only",
    )
    f2 = R.new_finding(
        reviewer_id="reviewer-1", subject_sha=SHA_A, severity=R.Severity.MINOR,
        evidence_ref="ev-2", criterion="terminal-envelope",
    )

    # Each finding gets exactly one disposition; record accept/reject.
    register = R.DispositionRegister()
    register.record(R.Disposition(
        finding_id=f1.id, decision=R.DispositionDecision.ACCEPTED,
        rationale="digest mutation observed", actor_id="controller-1",
    ))
    register.record(R.Disposition(
        finding_id=f2.id, decision=R.DispositionDecision.REJECTED,
        rationale="out of scope", actor_id="controller-1",
    ))
    # Exactly one disposition per finding.
    with pytest.raises(R.DispositionError):
        register.record(R.Disposition(
            finding_id=f1.id, decision=R.DispositionDecision.ACCEPTED,
            rationale="duplicate disposition", actor_id="controller-1",
        ))

    # REVIEW_FAIL freezes the candidate and blocks dependent readiness.
    fail = R.review_fail("reviewer-1", SHA_A, findings=(f1, f2))
    state = R.CandidateReviewState(subject_sha=SHA_A)
    state.record_review(fail)
    assert state.frozen
    assert state.frozen_subject_sha() == SHA_A
    assert not state.dependent_ready()

    # Controller adjudication verifies dimensions separately and never
    # synthesizes REVIEW_PASS (returns an Adjudication, not a verdict).
    adj = R.adjudicate(
        f1, actor_id="controller-1", location_verified=True,
        reachable_verified=True, causal_verified=False, impact_verified=True,
    )
    assert adj.decision is R.AdjudicationDecision.REJECT

    # Correction handoff carries all and only the accepted findings, bounded.
    handoff = R.build_correction_handoff(
        (f1, f2), register, subject_sha=SHA_A, correction_round=1, max_rounds=2,
    )
    assert handoff.finding_ids == (f1.id,)
    assert f2.id not in handoff.finding_ids
    assert handoff.correction_round == 1 and handoff.max_rounds == 2
    assert handoff.requires_controller_verification
    assert handoff.requires_fresh_review

    # Correction is NOT complete until controller verified + fresh cold PASS.
    assert not R.correction_complete(
        handoff, controller_verified=False,
        fresh_review=R.review_pass("reviewer-2", SHA_A),
    )
    # A fresh REVIEW_FAIL also keeps it incomplete.
    assert not R.correction_complete(
        handoff, controller_verified=True,
        fresh_review=R.review_fail("reviewer-2", SHA_A),
    )
    # A fresh cold REVIEW_PASS on the same subject completes it.
    assert R.correction_complete(
        handoff, controller_verified=True,
        fresh_review=R.review_pass("reviewer-2", SHA_A),
    )

    # Changing the subject SHA invalidates the prior verdict + dispositions,
    # unless an explicit finding-by-finding carry-forward rule is applied.
    changed = R.invalidate_on_subject_change(fail, register, new_subject_sha=SHA_B)
    assert changed.verdict_invalidated
    assert f1.id in changed.invalidated_finding_ids
    carry = R.invalidate_on_subject_change(
        fail, register, new_subject_sha=SHA_B,
        carry_forward=[R.CarryForwardRule(finding_id=f1.id, new_subject_sha=SHA_B)],
    )
    assert carry.carried_forward_finding_ids == (f1.id,)
    assert f2.id not in carry.carried_forward_finding_ids

    # Producer/reviewer separation: same session or worktree is refused.
    producer = R.ActorBinding(
        actor_id="p", role=R.PRODUCER_ROLE, session_id="s1", worktree="w1"
    )
    reviewer = R.ActorBinding(
        actor_id="r", role=R.REVIEWER_ROLE, session_id="s1", worktree="w1"
    )
    with pytest.raises(R.ReviewAuthorityError):
        R.validate_producer_reviewer_separation(producer, reviewer)


# ── Criterion 6: four-harness adherence ─────────────────────────────────────


def _load_profiles() -> dict:
    return yaml.safe_load((_FIXTURES / "profiles.yaml").read_text())


def test_criterion_06_four_harness_adapters_pass_strict_authority():
    """Four adapters pass strict digest, bypass and role-authority checks.

    The four shipped adapters (claude-code, codex, antigravity, opencode) are
    loaded from the real fixtures; each must hold a distinct single authority
    and a strict controller must refuse a missing binding, a stale digest, and a
    bypass, while honest statuses are respected.
    """
    profiles = _load_profiles()
    adapters = {
        name: H.HarnessAdapterProfile.from_dict(data, adapter_name=name)
        for name, data in profiles.items()
    }

    # The four distinct adapters are present and each holds exactly one role.
    assert set(adapters) == {"claude-code", "codex", "antigravity", "opencode"}
    roles = {adapters[n].authority_role() for n in adapters}
    assert None not in roles
    assert len(roles) == len(adapters), "authority roles are not distinct"

    # Strict controller: a dispatch must bind all four facts.
    strict = H.StrictController(require_skillweave_dispatch=True)
    with pytest.raises(H.StrictControllerError):
        strict.bind(
            sequence=None, profile=object(), task_brief=b"", skill_digests={},
        )
    bound = strict.bind(
        sequence=object(), profile=object(), task_brief=b"brief",
        skill_digests={"skillweave-promptchain": "a" * 32},
    )
    assert bound is not None

    # Stale / mismatched digest fails closed naming the asset.
    adapter = adapters["opencode"]
    adapter.skill_digests = {"skillweave-promptchain": "a" * 32}
    with pytest.raises(H.DigestMismatchError):
        strict.observe_actual_digests(adapter, {"skillweave-promptchain": "b" * 32})

    # Bypass (native delegation / direct shell) is recorded and refused.
    with pytest.raises(H.BypassNotRecordedError):
        strict.record_attempt(kind="direct-shell", detail="curl | sh", adapter=adapter)
    assert any(a["kind"] == "direct-shell" for a in strict.attempts)

    # A SkillWeave dispatch attempt is allowed.
    strict.record_attempt(kind="skillweave", detail="normal dispatch", adapter=adapter)

    # authority reconciliation: a role that also claims a foreign role is refused.
    neg = yaml.safe_load((_FIXTURES / "negative-authority.yaml").read_text())
    neg_profile = neg["negative-authority-profiles"]["claude-code"]
    double_role = H.HarnessAdapterProfile.from_dict(
        neg_profile, adapter_name="claude-code"
    )
    with pytest.raises(H.HarnessContractError):
        strict.reconcile_authority(double_role)

    # Honest statuses: production without dispatch-proven is refused.
    dishonest = H.HarnessAdapterProfile(
        name="fake", statuses={H.STATUS_PRODUCTION: True, H.STATUS_DISPATCH_PROVEN: False},
    )
    with pytest.raises(H.HarnessContractError):
        H.assert_statuses_honest(dishonest)
