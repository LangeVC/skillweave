# SkillWeave Runtime Foundation — Gate B06 Preparation
#
# This file is a READ-ONLY summary for a human reviewer to validate before
# granting GATE-B06 approval. It has NOT been self-approved by an ops agent.
#
# The ops agent MUST NOT call `evaluate_with_approval` with approver_role="ops".
# Self-approval is forbidden by AuthorityGuard (separation of duties, I00.3.3).
#
# A REVIEWER or RELEASE_AUTHORITY must independently:
#  1. Verify all 160 tests pass.
#  2. Confirm every forbidden transition (self-approval, merge, release, tag) is blocked.
#  3. Review the GNF suite: 12 negative cases covering all control-plane layers.
#  4. Verify evidence registry integrity (Merkle root, redaction, findings).
#  5. Approve with `policy.prevent_self_approval("reviewer", "I00")` — NOT "ops".

CONTROL_PLANE_SUMMARY = {
    "sequence_id": "SW-RTF-I00",
    "target_release": "v1.3.0",
    "base_sha": "3330883",
    "branch": "feature/SW-RTF-runtime-foundation",
    "execution_mode": "ralph_attended",
    "risk_mode": "conservative",
    "batches": {
        "B00_FOUNDATION": {"tasks": ["RTF-001"], "tests": 81, "gate": "PASS"},
        "B01_VOCABULARY_AND_JOURNAL": {"tasks": ["RTF-002", "RTF-003"], "tests": 101, "gate": "PASS"},
        "B02_AUTHORITY_AND_EVIDENCE": {"tasks": ["RTF-004", "RTF-006"], "tests": 120, "gate": "PASS"},
        "B03_PARALLEL": {"tasks": ["RTF-005", "RTF-007", "RTF-009", "RTF-011", "RTF-014"], "tests": 138, "gate": "PASS"},
        "B04_CHECKPOINT_AND_RECONCILIATION": {"tasks": ["RTF-008", "RTF-010"], "tests": 138, "gate": "PASS"},
        "B05_GOLDEN_NEGATIVE_FIXTURES": {"tasks": ["RTF-012"], "tests": 160, "gate": "PASS"},
    },
    "final_test_count": 160,
    "gnf_cases": 12,
    "forbidden_transitions": ["self_approval", "merge", "release", "tag"],
    "pending_approval": {
        "gate": "B06_FINAL_INTEGRATION",
        "task": "RTF-013",
        "required_approver": "REVIEWER or RELEASE_AUTHORITY",
        "NOT_ops": True,
    },
    "stopped_at": "2026-08-11T00:00:00Z",
    "ready_for_review": True,
}
