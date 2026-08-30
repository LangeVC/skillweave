"""Semantic observer preview tests (SW1311-OBSERVER-001, criteria 1-3, 9).

Behavioural tests over the semantic layer in :mod:`skillweave.trace.observer`
plus the read-only/negative authority in :mod:`skillweave.trace.view`:

1. The observer distinguishes nine semantic finding kinds covering evidence
   location, claim, causality, actionability, criterion coverage, child terminal
   coverage, heartbeat expiry, blocked input and resource collision.
2. It reports seen-vs-expected criteria and terminal children, coverage envelope,
   run-to-run variance, verified/rejected claims, FP/FN indicators, correction
   budget and gate state.
3. Cost/token/latency appear only from typed measured facts and otherwise are
   unavailable with a reason.

No harness, no provider/model name, no raw log/pid assertions.
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
    JobResult,
    JobStatus,
    JobRecord,
    RoundKind,
    TaskVerdict,
    TerminalEnvelope,
    TerminalState,
)
from skillweave.trace.observer import (  # noqa: E402
    MeasuredFactKind,
    SemanticFindingKind,
    SeverityLevel,
    classify_record,
    classify_review,
    measured_fact,
    observe_run,
)
from skillweave.trace.review import (  # noqa: E402
    Severity,
    new_finding,
    review_fail,
)
from skillweave.trace.view import (  # noqa: E402
    FORBIDDEN_MUTATIONS,
    FORBIDDEN_RUNTIME_ACTIONS,
    ObserverAuthorityError,
    assert_observer_authority,
)

_SHA = "a" * 40


def _record(record_id, *, round_=1, kind=RoundKind.DISPATCH, job_id=None,
            result=None, envelope=None, payload=None):
    return JobRecord(
        record_id=record_id, round=round_, kind=kind, parent_id=None, digest="",
        job_id=job_id, result=result, envelope=envelope, payload=payload,
    )


def _result(job_status=JobStatus.EXITED,
            evidence=EvidenceAvailability.RECORDED, gate=GateVerdict.PASS):
    return JobResult(
        job_status=job_status, task_verdict=TaskVerdict.DONE,
        evidence_available=evidence, gate_verdict=gate,
    )


# ── Criterion 1: semantic finding taxonomy ───────────────────────────────────


def test_missing_evidence_finding():
    record = _record("r1", result=_result(
        evidence=EvidenceAvailability.MISSING, gate=GateVerdict.FAIL,
    ))
    kinds = {f.kind for f in classify_record(record)}
    assert SemanticFindingKind.MISSING_EVIDENCE in kinds


def test_unresolvable_evidence_is_critical():
    record = _record("r1", result=_result(
        evidence=EvidenceAvailability.UNRESOLVABLE, gate=GateVerdict.FAIL,
    ))
    findings = classify_record(record)
    matched = [f for f in findings if f.kind is SemanticFindingKind.MISSING_EVIDENCE]
    assert matched and matched[0].severity is SeverityLevel.CRITICAL


def test_heartbeat_expired_finding():
    record = _record("r1", result=JobResult(
        job_status=JobStatus.HEARTBEAT_EXPIRED, task_verdict=TaskVerdict.FAILED,
        evidence_available=EvidenceAvailability.MISSING, gate_verdict=GateVerdict.FAIL,
    ))
    kinds = {f.kind for f in classify_record(record)}
    assert SemanticFindingKind.HEARTBEAT_EXPIRED in kinds


def test_blocked_input_finding():
    record = _record("r1", result=JobResult(
        job_status=JobStatus.BLOCKED_INPUT, task_verdict=TaskVerdict.BLOCKED,
        evidence_available=EvidenceAvailability.MISSING, gate_verdict=GateVerdict.FAIL,
    ))
    kinds = {f.kind for f in classify_record(record)}
    assert SemanticFindingKind.BLOCKED_INPUT in kinds


def test_resource_collision_finding_from_preflight():
    envelope = TerminalEnvelope(
        subject_sha=_SHA, command=["cmd"],
        terminal_state=TerminalState.PREFLIGHT_FAILED,
    )
    record = _record("r1", envelope=envelope, result=JobResult(
        job_status=JobStatus.LAUNCH_FAILED, task_verdict=TaskVerdict.FAILED,
        evidence_available=EvidenceAvailability.MISSING, gate_verdict=GateVerdict.FAIL,
    ))
    kinds = {f.kind for f in classify_record(record)}
    assert SemanticFindingKind.RESOURCE_COLLISION in kinds


def test_review_findings_become_claim_and_location_findings():
    finding = new_finding(
        reviewer_id="r1", subject_sha=_SHA, severity=Severity.MAJOR,
        evidence_ref="ref", criterion="c1", code_location="src/x.py:1",
    )
    review = review_fail("r1", _SHA, [finding])
    findings = classify_review(review)
    assert findings
    assert any(f.location == "src/x.py:1" for f in findings)


# ── Criterion 2: coverage, variance, claims, budget, gate ────────────────────


def test_seen_vs_expected_criteria_coverage():
    record = _record("r1", payload={"criteria": ["c1", "c2"]})
    obs = observe_run("run-1", [record], expected_criteria=["c1", "c2", "c3"])
    assert obs.coverage.seen_criteria == ("c1", "c2")
    assert obs.coverage.missing_criteria() == ("c3",)
    kinds = {f.kind for f in obs.findings}
    assert SemanticFindingKind.CRITERION_COVERAGE_GAP in kinds


def test_terminal_child_coverage_gap():
    record = _record("r-x", job_id="child-1")
    obs = observe_run("run-1", [record], expected_terminal_children=["child-1", "child-2"])
    assert obs.coverage.seen_terminal_children == ("child-1",)
    assert obs.coverage.missing_terminal_children() == ("child-2",)
    kinds = {f.kind for f in obs.findings}
    assert SemanticFindingKind.CHILD_TERMINAL_COVERAGE_GAP in kinds


def test_coverage_envelope_and_variance_and_budget_and_gate():
    record = _record("r1", payload={"criteria": ["c1"]},
                     result=_result(gate=GateVerdict.PASS))
    obs = observe_run(
        "run-1", [record], expected_criteria=["c1"],
        budget_total=3, budget_consumed=1,
        prior_seen_criteria=[("c1",), ("c2",)],
    )
    assert obs.coverage.coverage_envelope_min == 1
    assert obs.coverage.coverage_envelope_max == 1
    assert obs.coverage.run_to_run_variance == 0.5
    assert obs.coverage.budget_remaining == 2
    assert obs.coverage.budget_consumed == 1
    assert obs.coverage.gate_state == "pass"


def test_verified_and_rejected_claims_with_fn_indicator():
    finding = new_finding(
        reviewer_id="r1", subject_sha=_SHA, severity=Severity.MAJOR,
        evidence_ref="ref", criterion="c1",
    )
    fail_review = review_fail("r1", _SHA, [finding])
    obs = observe_run("run-1", [], reviews=[fail_review])
    status = obs.coverage.claim_statuses[finding.id]
    assert status.rejected is True
    assert status.false_negative is True


# ── Criterion 3: honest measured facts ───────────────────────────────────────


def test_cost_available_only_from_typed_measured_fact():
    available = measured_fact(MeasuredFactKind.COST, value=42, unit="usd", source="recv-1")
    assert available.available is True
    assert available.value == 42


def test_cost_unavailable_with_reason_when_no_typed_fact():
    for kind in (MeasuredFactKind.COST, MeasuredFactKind.TOKENS, MeasuredFactKind.LATENCY):
        unavailable = measured_fact(kind)
        assert unavailable.available is False
        assert unavailable.reason


def test_observe_run_only_records_measured_facts_it_was_given():
    obs = observe_run("run-1", [], measured=[
        measured_fact(MeasuredFactKind.COST, value=1.0, unit="usd", source="s"),
    ])
    assert obs.measured_facts[0].available is True


# ── Criterion 9: negative authority ──────────────────────────────────────────


def test_observer_forbidden_runtime_actions():
    for action in ("cancel", "kill", "dispatch", "correct", "correction",
                   "disposition", "integrate", "integration", "gate"):
        with pytest.raises(ObserverAuthorityError):
            assert_observer_authority(action)


def test_observer_forbidden_mutations():
    for action in ("mutate", "write", "commit", "push", "merge", "release", "tag"):
        with pytest.raises(ObserverAuthorityError):
            assert_observer_authority(action)


def test_forbidden_action_sets_cover_the_required_surface():
    assert {"cancel", "kill", "dispatch", "disposition", "integration", "gate"} <= FORBIDDEN_RUNTIME_ACTIONS
    assert FORBIDDEN_MUTATIONS


def _run_all() -> int:
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
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
