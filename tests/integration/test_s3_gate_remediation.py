"""Integration tests for automated S3-Gate remediation slicing (SW-158-RETRO-004).

Behavioural tests over :mod:`skillweave.dispatch.s3_gate_remediation`, proving
both acceptance criteria:

1. The controller automatically spawns lanes based on S3-Gate errors — a single
   ``remediate_from_s3_gate`` call parses ``REVIEW_BLOCKER`` output, slices the
   disjoint micro-lanes and starts every one of them through the spawn seam.
2. Human intervention is not strictly required for standard blockers — a
   standard ``blocker``/``major`` blocker with budget remaining starts with no
   operator and no escalation, while a non-standard severity or an exhausted
   budget starts nothing and is reported as needing a human.

No harness, no provider/model name, no text/source-presence assertions.
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.dispatch.s3_gate_remediation import (  # noqa: E402
    DEFAULT_MAX_ROUNDS,
    REVIEW_BLOCKER,
    REVIEW_FREIGABE,
    S3GateBlocker,
    S3GateRemediationError,
    build_remediation_spawns,
    parse_review_blocker_line,
    parse_review_blocker_output,
    plan_remediation_from_s3_gate,
    remediate_from_s3_gate,
    spawn_remediation_lanes,
)
from skillweave.trace.handoff import CONTROLLER_ROLE  # noqa: E402
from skillweave.trace.review import Severity  # noqa: E402

_SHA_A = "a" * 40
_SHA_B = "b" * 40
_SHA_C = "c" * 40
_SHA_D = "d" * 40

_BLOCKER_LINE = (
    f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-a repo=org/app "
    f"base={_SHA_A} subject={_SHA_B} criteria=c1,c2"
)


class _RecordingSeam:
    """A provider-neutral spawn seam that records the intents it receives."""

    def __init__(self):
        self.spawns = []

    def __call__(self, spawn):
        self.spawns.append(spawn)
        return f"handle:{spawn.lane_id}"


# ── Parsing REVIEW_BLOCKER output ────────────────────────────────────────────


def test_parses_key_value_blocker_line():
    blocker = parse_review_blocker_line(_BLOCKER_LINE)
    assert blocker is not None
    assert blocker.gate == "S3-Gate"
    assert blocker.lane_id == "lane-a"
    assert blocker.repo == "org/app"
    assert blocker.base_sha == _SHA_A
    assert blocker.subject_sha == _SHA_B
    assert blocker.failed_criteria == ("c1", "c2")
    assert blocker.severity is Severity.BLOCKER


def test_parses_positional_blocker_line():
    blocker = parse_review_blocker_line(
        f"{REVIEW_BLOCKER} S3-Gate lane-b org/lib {_SHA_C} {_SHA_D}"
    )
    assert blocker is not None
    assert blocker.lane_id == "lane-b"
    assert blocker.base_sha == _SHA_C
    assert blocker.subject_sha == _SHA_D


def test_non_blocker_lines_are_ignored():
    assert parse_review_blocker_line("") is None
    assert parse_review_blocker_line("unrelated log output") is None
    assert parse_review_blocker_line(f"{REVIEW_FREIGABE} gate=S3-Gate lane=a") is None
    assert parse_review_blocker_line("-*• plain bullet") is None


def test_malformed_blocker_line_fails_closed():
    with pytest.raises(S3GateRemediationError):
        parse_review_blocker_line(f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-a")
    with pytest.raises(S3GateRemediationError):
        parse_review_blocker_line(REVIEW_BLOCKER)  # no fields at all
    with pytest.raises(S3GateRemediationError):
        parse_review_blocker_line(f"{REVIEW_BLOCKER} gate=a lane=b")  # too few fields
    with pytest.raises(S3GateRemediationError):
        parse_review_blocker_line(
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-a repo=r base={_SHA_A} "
            f"subject={_SHA_B} bogus=yes"
        )
    with pytest.raises(S3GateRemediationError):
        parse_review_blocker_line(
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-a repo=r base=short "
            f"subject={_SHA_B}"
        )
    with pytest.raises(S3GateRemediationError):
        parse_review_blocker_line(
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-a repo=r base={_SHA_A} "
            f"subject={_SHA_B} severity=catastrophic"
        )


def test_parse_output_collects_only_blockers():
    log = "\n".join(
        [
            "S3-Gate starting",
            f"{REVIEW_FREIGABE} gate=S3-Gate lane=lane-ok",
            _BLOCKER_LINE,
            "some noise",
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-b repo=org/lib "
            f"base={_SHA_C} subject={_SHA_D}",
        ]
    )
    blockers = parse_review_blocker_output(log)
    assert [b.lane_id for b in blockers] == ["lane-a", "lane-b"]


def test_parse_output_without_blockers_is_empty():
    assert parse_review_blocker_output("all good\n") == []


def test_blocker_domain_is_repo_at_base():
    blocker = parse_review_blocker_line(_BLOCKER_LINE)
    assert blocker.domain.key == f"org/app@{_SHA_A}"


def test_severity_defaults_to_blocker_and_can_be_overridden():
    defaulted = parse_review_blocker_line(_BLOCKER_LINE)
    assert defaulted.severity is Severity.BLOCKER
    major = parse_review_blocker_line(_BLOCKER_LINE + " severity=major")
    assert major.severity is Severity.MAJOR
    assert major.is_standard is True


def test_direct_blocker_validation_rejects_bad_shas():
    with pytest.raises(S3GateRemediationError):
        S3GateBlocker(
            gate="S3-Gate", lane_id="lane-a", repo="org/app",
            base_sha="short", subject_sha=_SHA_B,
        ).validate()
    with pytest.raises(S3GateRemediationError):
        S3GateBlocker(
            gate="S3-Gate", lane_id="lane-a", repo="",
            base_sha=_SHA_A, subject_sha=_SHA_B,
        ).validate()


# ── Slicing into micro-lanes ─────────────────────────────────────────────────


def test_single_domain_stays_bounded():
    log = "\n".join(
        [
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-a repo=org/app "
            f"base={_SHA_A} subject={_SHA_B}",
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-b repo=org/app "
            f"base={_SHA_A} subject={_SHA_B}",
        ]
    )
    plan = plan_remediation_from_s3_gate(log)
    assert plan.single_domain is True
    assert plan.multi_domain is False
    assert plan.total_lanes == 2
    assert len(plan.remediation.groups) == 1


def test_multi_domain_is_split_into_disjoint_lanes():
    log = "\n".join(
        [
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-a repo=org/app "
            f"base={_SHA_A} subject={_SHA_B}",
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=b repo=org/lib "
            f"base={_SHA_C} subject={_SHA_D}",
        ]
    )
    plan = plan_remediation_from_s3_gate(log)
    assert plan.multi_domain is True
    assert len(plan.remediation.groups) == 2
    for group in plan.remediation.groups:
        assert len(group) == 1


def test_empty_gate_output_plans_nothing():
    plan = plan_remediation_from_s3_gate("no blockers here\n")
    assert plan.total_lanes == 0
    assert plan.budget_exhausted is False


def test_plan_rejects_bad_rounds():
    with pytest.raises(S3GateRemediationError):
        plan_remediation_from_s3_gate(_BLOCKER_LINE, failure_round=-1)
    with pytest.raises(S3GateRemediationError):
        plan_remediation_from_s3_gate(_BLOCKER_LINE, max_rounds=0)


# ── Criterion 1: the controller auto-spawns lanes ────────────────────────────


def test_controller_spawns_a_lane_per_blocker():
    seam = _RecordingSeam()
    outcome = remediate_from_s3_gate(_BLOCKER_LINE, seam=seam)
    assert len(outcome.spawns) == 1
    assert len(seam.spawns) == 1
    assert seam.spawns[0].lane_id == "lane-a"
    assert seam.spawns[0].spawned_by == CONTROLLER_ROLE


def test_controller_spawns_every_domain_lane():
    log = "\n".join(
        [
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-a repo=org/app "
            f"base={_SHA_A} subject={_SHA_B}",
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=b repo=org/lib "
            f"base={_SHA_C} subject={_SHA_D}",
        ]
    )
    seam = _RecordingSeam()
    outcome = remediate_from_s3_gate(log, seam=seam)
    assert {s.lane_id for s in seam.spawns} == {"lane-a", "b"}
    assert outcome.requires_human_intervention is False


def test_spawn_records_frozen_facts():
    seam = _RecordingSeam()
    remediate_from_s3_gate(_BLOCKER_LINE, seam=seam)
    spawn = seam.spawns[0]
    assert spawn.base_sha == _SHA_A
    assert spawn.subject_sha == _SHA_B
    assert spawn.failed_criteria == ("c1", "c2")
    assert spawn.domain.key == f"org/app@{_SHA_A}"


def test_spawn_id_is_stable_across_identical_calls():
    first = build_remediation_spawns(plan_remediation_from_s3_gate(_BLOCKER_LINE))
    second = build_remediation_spawns(plan_remediation_from_s3_gate(_BLOCKER_LINE))
    assert first[0].spawn_id == second[0].spawn_id


def test_inert_seam_records_intents_without_launching():
    plan = plan_remediation_from_s3_gate(_BLOCKER_LINE)
    spawns = spawn_remediation_lanes(plan, seam=None)
    assert len(spawns) == 1
    assert spawns[0].requires_human_intervention is False


def test_spawn_requires_an_authorizing_role():
    plan = plan_remediation_from_s3_gate(_BLOCKER_LINE)
    with pytest.raises(S3GateRemediationError):
        build_remediation_spawns(plan, role="")


def test_ambiguous_lane_in_one_domain_fails_closed():
    """Two blockers for the same lane+domain cannot be attributed; refuse them.

    Last-wins would silently auto-spawn a lane carrying the wrong frozen
    subject and criteria, so the plan must fail closed instead.
    """
    log = "\n".join(
        [
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-x repo=org/app "
            f"base={_SHA_A} subject={_SHA_B} criteria=alpha",
            f"{REVIEW_BLOCKER} gate=S3-Gate lane=lane-x repo=org/app "
            f"base={_SHA_A} subject={_SHA_C} criteria=beta",
        ]
    )
    plan = plan_remediation_from_s3_gate(log)
    with pytest.raises(S3GateRemediationError):
        build_remediation_spawns(plan)
    seam = _RecordingSeam()
    with pytest.raises(S3GateRemediationError):
        remediate_from_s3_gate(log, seam=seam)
    assert seam.spawns == []


# ── Criterion 2: no human needed for standard blockers ───────────────────────


def test_standard_blocker_needs_no_human():
    plan = plan_remediation_from_s3_gate(_BLOCKER_LINE)
    assert plan.requires_human_intervention is False
    assert plan.human_intervention_reasons() == ()


def test_major_blocker_needs_no_human():
    plan = plan_remediation_from_s3_gate(_BLOCKER_LINE + " severity=major")
    assert plan.requires_human_intervention is False


def test_non_standard_severity_escalates_and_spawns_nothing():
    seam = _RecordingSeam()
    log = _BLOCKER_LINE + " severity=minor"
    outcome = remediate_from_s3_gate(log, seam=seam)
    assert outcome.requires_human_intervention is True
    assert seam.spawns == []
    assert outcome.spawns[0].requires_human_intervention is True
    reasons = outcome.plan.human_intervention_reasons()
    assert any("non-standard" in r for r in reasons)


def test_exhausted_budget_escalates_and_spawns_nothing():
    seam = _RecordingSeam()
    outcome = remediate_from_s3_gate(
        _BLOCKER_LINE, seam=seam, failure_round=DEFAULT_MAX_ROUNDS
    )
    assert outcome.plan.budget_exhausted is True
    assert outcome.requires_human_intervention is True
    assert seam.spawns == []


def test_budget_with_remaining_round_auto_spawns():
    seam = _RecordingSeam()
    outcome = remediate_from_s3_gate(
        _BLOCKER_LINE, seam=seam, failure_round=DEFAULT_MAX_ROUNDS - 1
    )
    assert outcome.plan.budget_exhausted is False
    assert outcome.requires_human_intervention is False
    assert len(seam.spawns) == 1


def test_custom_max_rounds_bounds_the_budget():
    seam = _RecordingSeam()
    outcome = remediate_from_s3_gate(
        _BLOCKER_LINE, seam=seam, failure_round=1, max_rounds=1
    )
    assert outcome.plan.budget_exhausted is True
    assert seam.spawns == []


def test_outcome_serializes_both_plan_and_spawns():
    outcome = remediate_from_s3_gate(_BLOCKER_LINE)
    payload = outcome.to_dict()
    assert payload["requires_human_intervention"] is False
    assert payload["plan"]["remediation"]["total_lanes"] == 1
    assert payload["spawns"][0]["spawned_by"] == CONTROLLER_ROLE


def _run_all() -> int:
    tests = [
        test_parses_key_value_blocker_line,
        test_parses_positional_blocker_line,
        test_non_blocker_lines_are_ignored,
        test_malformed_blocker_line_fails_closed,
        test_parse_output_collects_only_blockers,
        test_parse_output_without_blockers_is_empty,
        test_blocker_domain_is_repo_at_base,
        test_severity_defaults_to_blocker_and_can_be_overridden,
        test_direct_blocker_validation_rejects_bad_shas,
        test_single_domain_stays_bounded,
        test_multi_domain_is_split_into_disjoint_lanes,
        test_empty_gate_output_plans_nothing,
        test_plan_rejects_bad_rounds,
        test_controller_spawns_a_lane_per_blocker,
        test_controller_spawns_every_domain_lane,
        test_spawn_records_frozen_facts,
        test_spawn_id_is_stable_across_identical_calls,
        test_inert_seam_records_intents_without_launching,
        test_spawn_requires_an_authorizing_role,
        test_ambiguous_lane_in_one_domain_fails_closed,
        test_standard_blocker_needs_no_human,
        test_major_blocker_needs_no_human,
        test_non_standard_severity_escalates_and_spawns_nothing,
        test_exhausted_budget_escalates_and_spawns_nothing,
        test_budget_with_remaining_round_auto_spawns,
        test_custom_max_rounds_bounds_the_budget,
        test_outcome_serializes_both_plan_and_spawns,
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
