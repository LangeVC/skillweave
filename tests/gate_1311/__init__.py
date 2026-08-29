"""SW-GATE-1311 — the independent DISPATCH_OPERATIONS_PASS gate suite.

This package is a deterministic, offline, dependency-light pytest suite that
lets an independent reviewer execute the whole SW-GATE-1311 acceptance matrix as
one command instead of reassembling it by hand::

    python3 -m pytest tests/gate_1311 -q

It does not re-derive the contract. The thirteen acceptance criteria and the six
``dispatch_order`` groups below are read verbatim from the binding PRD task
``SW-GATE-1311`` (``.skillweave/prds/skillweave-1.3.11-1.3.12-dispatch-lifecycle-acceleration/1.3.11/prd.json``)
and its validated sequence. Every criterion maps to exactly one named test, and
the mapping is declared here so a reviewer can machine-verify exact-once
coverage without reading every test body.

The suite is hermetic and read-only: it starts no network, reads no wall clock,
depends on nothing outside the repository tree, and mutates no product file,
profile, topology, review disposition or gate outcome. Criteria 1–10 are proven
by direct assertions against the real product surfaces already present at the
base commit; criteria 11–13 are controller-/review-process facts a pytest suite
cannot observe, so they are represented as fail-closed controller-attested
checks (see ``controller_attested.py``).
"""

from __future__ import annotations

from typing import Dict, FrozenSet

# ── The six dispatch_order groups ────────────────────────────────────────────

#: The six declared ``dispatch_order`` groups in dispatch order, with the exact
#: criterion indices each owns. This is a verbatim copy of the binding PRD task
#: ``SW-GATE-1311`` ``dispatch_order`` block.
DISPATCH_ORDER: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("round and structured child-job truth", (1, 2)),
    ("parallel and integration safety", (3, 4)),
    ("strict review loop and harness adherence", (5, 6)),
    ("model policy and live/replay observer", (7, 8)),
    ("transfer safety and release regressions", (9, 10)),
    ("complete evidence, dual independent verdict and authority", (11, 12, 13)),
)

#: The module (test file stem) each dispatch_order group is implemented in.
GROUP_MODULE: Dict[int, str] = {
    1: "rounds_child_truth",
    2: "parallel_integration",
    3: "review_harness",
    4: "model_observer",
    5: "transfer_release",
    6: "controller_attested",
}

# ── The thirteen acceptance criteria, abridged ───────────────────────────────

#: Criterion index -> the exact ``test_*`` function name that proves it.
#: criterion 1 is the first acceptance criterion of SW-GATE-1311, and so on.
CRITERION_TO_TEST: Dict[int, str] = {
    1: "test_criterion_01_append_only_rounds_preserve_bytes_and_separate_dimensions",
    2: "test_criterion_02_noninteractive_terminal_fixtures_yield_typed_results",
    3: "test_criterion_03_disjoint_jobs_overlap_conflicting_scopes_serialize",
    4: "test_criterion_04_integration_eligibility_fails_closed",
    5: "test_criterion_05_review_fail_dispositions_bounded_correction_fresh_pass",
    6: "test_criterion_06_four_harness_adapters_pass_strict_authority",
    7: "test_criterion_07_model_policy_and_council_namespace_attribution",
    8: "test_criterion_08_live_replay_projection_and_observer_authority",
    9: "test_criterion_09_transfer_entries_represent_and_retrieval_is_readonly",
    10: "test_criterion_10_release_regression_suites_pass",
    11: "test_criterion_11_gate_report_binds_shas_commands_exits_reviewer_identity",
    12: "test_criterion_12_dual_diverse_reviewers_both_return_pass",
    13: "test_criterion_13_no_reviewer_or_worker_merge_push_tag_release_publish",
}

#: The controller-attested (non-observable) criteria and the modules that hold
#: their declared-evidence readers.
CONTROLLER_ATTESTED_CRITERIA: FrozenSet[int] = frozenset({11, 12, 13})

#: Module (test file stem) that implements each criterion's test.
CRITERION_MODULE: Dict[int, str] = {
    c: GROUP_MODULE[idx + 1]
    for idx, (_focus, criteria) in enumerate(DISPATCH_ORDER)
    for c in criteria
}

__all__ = [
    "DISPATCH_ORDER",
    "GROUP_MODULE",
    "CRITERION_TO_TEST",
    "CONTROLLER_ATTESTED_CRITERIA",
    "CRITERION_MODULE",
]
