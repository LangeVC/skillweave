"""SW-GATE-1312 — the LIFECYCLE_PROFILE_PREVIEW_PASS gate suite.

This package is a deterministic, offline, dependency-light pytest suite that lets
an independent reviewer execute the whole SW-GATE-1312 acceptance matrix as one
command instead of reassembling it by hand::

    python3 -m pytest tests/gate_1312 -q

It does not re-derive the contract. The ten acceptance criteria and the five
``dispatch_order`` groups below are read verbatim from the binding task
``SW1312-GATE-SUITE-001`` (``LIFECYCLE_PROFILE_PREVIEW_PASS`` in the
``wt-sw1312-gate-suite-ops`` worktree). Every criterion maps to exactly one named
test module, and the mapping is declared here so a reviewer can machine-verify
exact-once coverage without reading every test body.

The suite is read-only over four repositories:

* ``skillweave`` (this repo) — the execution runtime, ``src/skillweave``;
* ``skillweave-sdk`` — the *contract* (preview schemas + canonical digest);
* ``skillweave-profiles`` — the *opinion* (two OSS base profiles);
* ``skillweave-packs-pro`` — *commercial opinion* (the private CMS pack).

Nothing here merges, pushes, tags, releases, publishes, mutates a production CMS,
or writes a reviewer product file. It performs no network access and reads no wall
clock. Sibling repositories are resolved through ``SKILLWEAVE_SDK_DIR`` /
``SKILLWEAVE_SCHEMA_DIR`` / ``SKILLWEAVE_PROFILES_DIR`` /
``SKILLWEAVE_PACKS_PRO_DIR`` or the known sibling checkout paths, and fail closed
with an actionable message when absent.
"""

from __future__ import annotations

from typing import Dict, Tuple

# ── The five dispatch_order groups ──────────────────────────────────────────

#: The five declared ``dispatch_order`` groups in dispatch order, with the exact
#: criterion indices each owns. This is a verbatim copy of the binding task
#: ``SW1312-GATE-SUITE-001`` ``dispatch_order`` block.
DISPATCH_ORDER: Tuple[Tuple[str, Tuple[int, ...]], ...] = (
    ("owned criterion map and standalone contract identity", (1, 2)),
    ("profile, chain and CMS execution matrix", (3, 4)),
    ("1.3.11 hardening and release provenance", (5, 6)),
    ("architecture negatives and explicit 1.3.13 deferral", (7, 8)),
    ("immutable evidence manifest and non-mutating suite", (9, 10)),
)

#: The module (test file stem) each dispatch_order group is implemented in.
#: Each group owns two criteria that live in one or two test modules; this maps
#: the group to the module named after its first concern for discoverability.
GROUP_MODULE: Dict[int, str] = {
    1: "test_criterion_map",
    2: "test_profiles",
    3: "test_topology_regressions",
    4: "test_architecture_negatives",
    5: "test_manifest",
}

# ── The ten acceptance criteria, abridged ───────────────────────────────────

#: Criterion index -> the exact ``test_*`` function name that proves it.
#: criterion 1 is the first acceptance criterion of SW-GATE-1312, and so on.
CRITERION_TO_TEST: Dict[int, str] = {
    1: "test_criterion_01_criterion_map_and_immutable_evidence_paths",
    2: "test_criterion_02_standalone_sdk_identical_version_and_digest",
    3: "test_criterion_03_profile_precedence_snapshot_parity_and_semantics",
    4: "test_criterion_04_chains_and_cms_through_1_3_11_contracts",
    5: "test_criterion_05_version_topology_foreign_cwd_dual_review",
    6: "test_criterion_06_release_provenance_forgejo_first_no_live_release",
    7: "test_criterion_07_static_rejects_and_architecture_negatives",
    8: "test_criterion_08_generic_router_openrouter_alias_deferred_to_1_3_13",
    9: "test_criterion_09_machine_readable_gate_manifest",
    10: "test_criterion_10_no_merge_push_tag_release_publish_or_mutation",
}

#: Module (test file stem) that implements each criterion's test.
CRITERION_MODULE: Dict[int, str] = {
    1: "test_criterion_map",
    2: "test_standalone_identity",
    3: "test_profiles",
    4: "test_chains_cms",
    5: "test_topology_regressions",
    6: "test_release_provenance",
    7: "test_architecture_negatives",
    8: "test_defect_deferral",
    9: "test_manifest",
    10: "test_manifest",
}

#: The canonical SDK preview-schema digest every consumer pins (schemaVersion
#: 0.1.0). A divergence in any of the five preview schemas changes this value and
#: must refuse to load rather than silently reinterpret.
CANONICAL_SCHEMA_DIGEST = (
    "2a52a4b820f0a1263149433e2f7e47e113133f54e6b38fd59c4cc93f7272e83e"
)

__all__ = [
    "DISPATCH_ORDER",
    "GROUP_MODULE",
    "CRITERION_TO_TEST",
    "CRITERION_MODULE",
    "CANONICAL_SCHEMA_DIGEST",
]
