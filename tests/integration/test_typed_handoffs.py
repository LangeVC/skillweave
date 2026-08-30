"""Integration tests for typed operational handoffs (SW1311-HANDOFF-001, criteria 1-3).

Behavioural tests over the transfer layer in :mod:`skillweave.trace.handoff`:

1. ``ops``, ``review``, ``correction``, ``integration`` and ``controller_resume``
   are distinct, immutable schema variants with stable ids and source receipt ids.
2. Every handoff binds the destination role, exact base/subject SHAs,
   dependencies, allowed/forbidden scope, required inputs, criteria, commands,
   a correction budget and the expected receipt type.
3. A destination cannot start when a source receipt/artifact is missing, a base
   or subject differs, a digest is stale, or the role lacks authority.

No harness, no provider/model name, no text/source-presence assertions.
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.trace.handoff import (  # noqa: E402
    CONTROLLER_ROLE,
    INTEGRATOR_ROLE,
    OPS_ROLE,
    PRODUCER_ROLE,
    REVIEWER_ROLE,
    Handoff,
    HandoffBuildError,
    HandoffKind,
    HandoffStartError,
    RECEIPT_CONTROLLER_RESUME,
    RECEIPT_CORRECTION,
    RECEIPT_INTEGRATION,
    RECEIPT_OPS,
    RECEIPT_REVIEW,
    assert_can_start,
    build_correction_handoff,
    build_controller_resume_handoff,
    build_integration_handoff,
    build_ops_handoff,
    build_review_handoff,
    can_start,
    start_blocking_reason,
)

_SHA = "a" * 40
_OTHER_SHA = "b" * 40
_THIRD_SHA = "c" * 40


def _receipts(handoff=None):
    if handoff is None:
        return {}
    return {handoff.source_receipt_id: object()}


# ── Criterion 1: distinct immutable variants with stable ids ─────────────────


def test_builders_produce_distinct_variants():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    review = build_review_handoff(
        source_receipt_id="r2", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/y.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    correction = build_correction_handoff(
        source_receipt_id="r3", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/z.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"], correction_budget=2,
    )
    integration = build_integration_handoff(
        source_receipt_id="r4", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/w.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    resume = build_controller_resume_handoff(
        source_receipt_id="r5", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/v.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )

    assert ops.kind is HandoffKind.OPS
    assert review.kind is HandoffKind.REVIEW
    assert correction.kind is HandoffKind.CORRECTION
    assert integration.kind is HandoffKind.INTEGRATION
    assert resume.kind is HandoffKind.CONTROLLER_RESUME

    kinds = {ops.kind, review.kind, correction.kind, integration.kind, resume.kind}
    assert len(kinds) == 5


def test_variants_bind_distinct_destination_roles():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    review = build_review_handoff(
        source_receipt_id="r2", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/y.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    correction = build_correction_handoff(
        source_receipt_id="r3", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/z.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"], correction_budget=1,
    )
    integration = build_integration_handoff(
        source_receipt_id="r4", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/w.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    resume = build_controller_resume_handoff(
        source_receipt_id="r5", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/v.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert ops.destination_role == OPS_ROLE
    assert review.destination_role == REVIEWER_ROLE
    assert correction.destination_role == PRODUCER_ROLE
    assert integration.destination_role == INTEGRATOR_ROLE
    assert resume.destination_role == CONTROLLER_ROLE


def test_variants_bind_distinct_expected_receipt_types():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    review = build_review_handoff(
        source_receipt_id="r2", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/y.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    correction = build_correction_handoff(
        source_receipt_id="r3", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/z.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"], correction_budget=1,
    )
    integration = build_integration_handoff(
        source_receipt_id="r4", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/w.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    resume = build_controller_resume_handoff(
        source_receipt_id="r5", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/v.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert ops.expected_receipt_type == RECEIPT_OPS
    assert review.expected_receipt_type == RECEIPT_REVIEW
    assert correction.expected_receipt_type == RECEIPT_CORRECTION
    assert integration.expected_receipt_type == RECEIPT_INTEGRATION
    assert resume.expected_receipt_type == RECEIPT_CONTROLLER_RESUME


def test_handoff_id_is_stable_for_identical_transfer():
    a = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    b = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert a.id == b.id
    assert a.digest == b.digest


def test_handoff_id_differs_when_subject_differs():
    a = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    b = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_OTHER_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert a.id != b.id


def test_handoff_is_immutable():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    with pytest.raises(Exception):
        ops.subject_sha = _OTHER_SHA  # frozen dataclass


def test_handoff_requires_source_receipt_id():
    with pytest.raises(HandoffBuildError):
        build_ops_handoff(
            source_receipt_id="", base_sha=_SHA, subject_sha=_SHA,
            allowed_paths=["src/x.py"], required_inputs=["i1"],
            criteria=["c1"], commands=["cmd"],
        )


# ── Criterion 2: complete destination contract ───────────────────────────────


def test_handoff_binds_full_destination_contract():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_OTHER_SHA,
        allowed_paths=["src/x.py"], forbidden_paths=["src/y.py"],
        dependencies=["SW1311-OTHER"],
        required_inputs=["in/one", "in/two"],
        criteria=["c1", "c2"],
        commands=["pytest -q"],
    )
    assert ops.base_sha == _SHA
    assert ops.subject_sha == _OTHER_SHA
    assert ops.dependencies == ("SW1311-OTHER",)
    assert ops.scope.allowed_paths == ("src/x.py",)
    assert ops.scope.forbidden_paths == ("src/y.py",)
    assert ops.required_inputs == ("in/one", "in/two")
    assert ops.criteria == ("c1", "c2")
    assert ops.commands == ("pytest -q",)
    assert ops.correction_budget == 0


def test_handoff_requires_full_base_sha():
    with pytest.raises(HandoffBuildError):
        build_ops_handoff(
            source_receipt_id="r1", base_sha="short", subject_sha=_SHA,
            allowed_paths=["src/x.py"], required_inputs=["i1"],
            criteria=["c1"], commands=["cmd"],
        )


def test_handoff_requires_full_subject_sha():
    with pytest.raises(HandoffBuildError):
        build_ops_handoff(
            source_receipt_id="r1", base_sha=_SHA, subject_sha="short",
            allowed_paths=["src/x.py"], required_inputs=["i1"],
            criteria=["c1"], commands=["cmd"],
        )


def test_handoff_requires_allowed_scope_criteria_inputs_commands():
    with pytest.raises(HandoffBuildError):
        build_ops_handoff(
            source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
            allowed_paths=[], required_inputs=["i1"],
            criteria=["c1"], commands=["cmd"],
        )
    with pytest.raises(HandoffBuildError):
        build_ops_handoff(
            source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
            allowed_paths=["src/x.py"], required_inputs=[],
            criteria=["c1"], commands=["cmd"],
        )
    with pytest.raises(HandoffBuildError):
        build_ops_handoff(
            source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
            allowed_paths=["src/x.py"], required_inputs=["i1"],
            criteria=[], commands=["cmd"],
        )
    with pytest.raises(HandoffBuildError):
        build_ops_handoff(
            source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
            allowed_paths=["src/x.py"], required_inputs=["i1"],
            criteria=["c1"], commands=[],
        )


def test_correction_budget_is_bounded_and_negative_refused():
    correction = build_correction_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"], correction_budget=3,
    )
    assert correction.correction_budget == 3

    with pytest.raises(HandoffBuildError):
        build_correction_handoff(
            source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
            allowed_paths=["src/x.py"], required_inputs=["i1"],
            criteria=["c1"], commands=["cmd"], correction_budget=-1,
        )


def test_expected_receipt_type_must_match_role():
    # A reviewer may only produce a review receipt, never an ops receipt.
    with pytest.raises(HandoffBuildError):
        from skillweave.trace.handoff import build_handoff
        build_handoff(
            kind=HandoffKind.REVIEW,
            source_receipt_id="r1",
            destination_role=REVIEWER_ROLE,
            base_sha=_SHA,
            subject_sha=_SHA,
            allowed_paths=["src/x.py"],
            required_inputs=["i1"],
            criteria=["c1"],
            commands=["cmd"],
            expected_receipt_type=RECEIPT_OPS,
        )


# ── Criterion 3: fail-closed launch ──────────────────────────────────────────


def test_missing_source_receipt_blocks_start():
    ops = build_ops_handoff(
        source_receipt_id="missing", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert not can_start(ops, receipts={})
    assert start_blocking_reason(ops, receipts={}) == (
        "source receipt 'missing' is missing"
    )
    with pytest.raises(HandoffStartError):
        assert_can_start(ops, receipts={})


def test_base_mismatch_blocks_start():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert not can_start(
        ops, receipts=_receipts(ops), current_base_sha=_OTHER_SHA,
    )
    assert "base differs" in start_blocking_reason(
        ops, receipts=_receipts(ops), current_base_sha=_OTHER_SHA,
    )


def test_subject_mismatch_blocks_start():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert not can_start(
        ops, receipts=_receipts(ops), current_subject_sha=_OTHER_SHA,
    )
    assert "subject differs" in start_blocking_reason(
        ops, receipts=_receipts(ops), current_subject_sha=_OTHER_SHA,
    )


def test_stale_digest_blocks_start():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    tampered = Handoff(
        id=ops.id, kind=ops.kind, source_receipt_id=ops.source_receipt_id,
        destination_role=ops.destination_role, base_sha=_OTHER_SHA,
        subject_sha=ops.subject_sha, dependencies=ops.dependencies,
        scope=ops.scope, required_inputs=ops.required_inputs,
        criteria=ops.criteria, commands=ops.commands,
        correction_budget=ops.correction_budget,
        expected_receipt_type=ops.expected_receipt_type,
        digest=ops.digest,
    )
    # tampered base_sha no longer matches the recorded digest
    assert not can_start(tampered, receipts=_receipts(ops))
    assert start_blocking_reason(tampered, receipts=_receipts(ops)) == (
        "handoff digest is stale"
    )


def test_insufficient_role_authority_blocks_start():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert not can_start(
        ops, receipts=_receipts(ops), role=REVIEWER_ROLE,
    )
    assert "lacks authority" in start_blocking_reason(
        ops, receipts=_receipts(ops), role=REVIEWER_ROLE,
    )


def test_can_start_succeeds_when_contract_holds():
    ops = build_ops_handoff(
        source_receipt_id="r1", base_sha=_SHA, subject_sha=_SHA,
        allowed_paths=["src/x.py"], required_inputs=["i1"],
        criteria=["c1"], commands=["cmd"],
    )
    assert can_start(
        ops, receipts=_receipts(ops),
        current_base_sha=_SHA, current_subject_sha=_SHA, role=OPS_ROLE,
    )
    assert start_blocking_reason(
        ops, receipts=_receipts(ops),
        current_base_sha=_SHA, current_subject_sha=_SHA, role=OPS_ROLE,
    ) is None
    assert_can_start(  # does not raise
        ops, receipts=_receipts(ops),
        current_base_sha=_SHA, current_subject_sha=_SHA, role=OPS_ROLE,
    )


def _run_all() -> int:
    tests = [
        test_builders_produce_distinct_variants,
        test_variants_bind_distinct_destination_roles,
        test_variants_bind_distinct_expected_receipt_types,
        test_handoff_id_is_stable_for_identical_transfer,
        test_handoff_id_differs_when_subject_differs,
        test_handoff_is_immutable,
        test_handoff_requires_source_receipt_id,
        test_handoff_binds_full_destination_contract,
        test_handoff_requires_full_base_sha,
        test_handoff_requires_full_subject_sha,
        test_handoff_requires_allowed_scope_criteria_inputs_commands,
        test_correction_budget_is_bounded_and_negative_refused,
        test_expected_receipt_type_must_match_role,
        test_missing_source_receipt_blocks_start,
        test_base_mismatch_blocks_start,
        test_subject_mismatch_blocks_start,
        test_stale_digest_blocks_start,
        test_insufficient_role_authority_blocks_start,
        test_can_start_succeeds_when_contract_holds,
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
