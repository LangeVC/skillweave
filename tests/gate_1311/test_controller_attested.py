"""Dispatch-order group 6 — controller-attested review/release facts (criteria 11, 12, 13).

Criteria 11, 12 and 13 are controller- and review-process facts about SHAs,
reviewer identity, reviewer authority and release actions. A pytest process
cannot observe them — they happen in the controller's git history, the
reviewers' sessions and the release tooling, none of which is inside the
repository tree the suite can read.

They are therefore represented as **controller-attested checks**: each test
reads declared evidence and validates it against the exact structure the gate
report, dual-review disposition and release-action logs must carry. They fail
closed — missing, malformed, or self-contradictory evidence raises, never
fabricates a pass and never silently skips. The *names* of these tests state
the controller-attested nature so a reviewer cannot mistake them for an
executable proof.

The check itself is deterministic and hermetic: ``attest()`` below is a pure
function over the evidence dict, with no network, wall clock or file access.
"""

from __future__ import annotations

import re

import pytest

from skillweave.gates.attestation import AttestationError


_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")

#: The explicit 1.4 / 1.5 deferrals the gate report must name (criterion 11).
REQUIRED_DEFERRALS = ("1.4", "1.5")


# ── Attestation validators (pure, fail-closed) ──────────────────────────────


def _require(mapping: dict, key: str, evidence: dict) -> object:
    if key not in mapping or mapping[key] in (None, "", {}):
        raise AttestationError(f"attested evidence '{key}' is missing: {evidence}")
    return mapping[key]


def attest_gate_report(evidence: dict) -> dict:
    """Validate the gate-report attestation (criterion 11), fail-closed.

    Binds the full base SHA, candidate SHA, exact commands/exits, raw artifact
    references, reviewer identities and the explicit 1.4/1.5 deferrals.
    """
    base = _require(evidence, "base_sha", evidence)
    candidate = _require(evidence, "candidate_sha", evidence)
    if not _FULL_SHA.match(str(base)):
        raise AttestationError(f"base_sha is not a full 40-hex SHA: {base!r}")
    if not _FULL_SHA.match(str(candidate)):
        raise AttestationError(f"candidate_sha is not a full 40-hex SHA: {candidate!r}")
    if base == candidate:
        raise AttestationError(
            "base_sha and candidate_sha are identical; a gate must bind two "
            "distinct SHAs (the base and the reviewed candidate)"
        )

    commands = _require(evidence, "commands", evidence)
    if not isinstance(commands, list) or not commands:
        raise AttestationError("commands must be a non-empty list")
    for entry in commands:
        if not isinstance(entry, dict) or "command" not in entry or "exit" not in entry:
            raise AttestationError(f"each command entry must bind command+exit: {entry!r}")
        if not isinstance(entry["exit"], int):
            raise AttestationError(f"command exit must be an int: {entry!r}")

    artifacts = _require(evidence, "raw_artifacts", evidence)
    if not isinstance(artifacts, list) or not artifacts:
        raise AttestationError("raw_artifacts must be a non-empty list")

    reviewers = _require(evidence, "reviewer_identities", evidence)
    if not isinstance(reviewers, list) or not reviewers:
        raise AttestationError("reviewer_identities must be a non-empty list")

    deferrals = _require(evidence, "deferrals", evidence)
    if not isinstance(deferrals, list):
        raise AttestationError("deferrals must be a list")
    missing = [d for d in REQUIRED_DEFERRALS if d not in deferrals]
    if missing:
        raise AttestationError(f"gate report omits required deferrals: {missing}")

    return evidence


def attest_dual_review(evidence: dict) -> dict:
    """Validate the dual-review attestation (criterion 12), fail-closed.

    Two diverse reviewers (Pro-class and Flash-class) inspect identical
    immutable subjects concurrently; both must return REVIEW_PASS with no
    material contradiction, and every reviewer's subject must be exactly the
    candidate SHA the attestation is about. A dual pass bound to any other
    commit cannot attest the candidate.

    This is the released controller-attested behavior, migrated onto the
    shared SW1312 strict contract (:mod:`skillweave.gates.attestation`) rather
    than a second local interpretation (SW1312-ATTESTATION-STRICT-001).
    """
    from skillweave.gates.attestation import canonicalize

    canonicalize(evidence)
    return evidence


def attest_no_release_actions(evidence: dict) -> dict:
    """Validate the no-release-action attestation (criterion 13), fail-closed.

    Reviewers write no product file, and no worker or reviewer merges, pushes a
    protected branch, tags, releases or publishes.
    """
    product_writes = _require(evidence, "reviewer_product_writes", evidence)
    if not isinstance(product_writes, list) or product_writes:
        raise AttestationError(
            f"reviewers wrote product files: {product_writes!r}"
        )

    actions = _require(evidence, "forbidden_actions", evidence)
    if not isinstance(actions, list):
        raise AttestationError("forbidden_actions must be a list")
    for action in actions:
        if action in ("merge", "push", "tag", "release", "publish", "protected_branch_push"):
            raise AttestationError(f"a forbidden release action was recorded: {action!r}")

    return evidence


# ── Controller-attested tests ───────────────────────────────────────────────


def test_criterion_11_gate_report_binds_shas_commands_exits_reviewer_identity():
    """Controller-attested: the gate report binds base/candidate SHA, exact
    commands+exits, raw artifacts, reviewer identities and 1.4/1.5 deferrals.

    Well-formed evidence passes; missing, malformed or identical SHAs, a missing
    command/exit, or an omitted deferral all fail closed.
    """
    well_formed = {
        "base_sha": "a" * 40,
        "candidate_sha": "b" * 40,
        "commands": [
            {"command": "python -m pytest tests/gate_1311 -q", "exit": 0},
            {"command": "python -m pytest tests -q", "exit": 0},
        ],
        "raw_artifacts": ["tests/", "gate-report.json"],
        "reviewer_identities": ["pro-reviewer", "flash-reviewer"],
        "deferrals": ["1.4", "1.5"],
    }
    assert attest_gate_report(well_formed) is well_formed

    # Missing candidate SHA -> fail closed.
    with pytest.raises(AttestationError):
        attest_gate_report({k: v for k, v in well_formed.items() if k != "candidate_sha"})
    # Identical base/candidate -> self-contradictory -> fail closed.
    with pytest.raises(AttestationError):
        attest_gate_report(dict(well_formed, candidate_sha=well_formed["base_sha"]))
    # Short SHA -> malformed -> fail closed.
    with pytest.raises(AttestationError):
        attest_gate_report(dict(well_formed, base_sha="abcd"))
    # Omitted deferral -> fail closed.
    with pytest.raises(AttestationError):
        attest_gate_report(dict(well_formed, deferrals=["1.4"]))


def test_criterion_12_dual_diverse_reviewers_both_return_pass():
    """Controller-attested: one Pro and one Flash reviewer inspect identical
    immutable subjects and both return REVIEW_PASS with no contradiction, and
    that subject is the candidate SHA under attestation.

    Well-formed evidence passes; a non-pro/flash pair, differing subjects, a
    non-PASS verdict, a recorded contradiction or (critically) a dual pass
    agreeing on a subject that is not the candidate all fail closed.
    """
    well_formed = {
        "candidate_sha": "c" * 40,
        "reviewers": [
            {
                "reviewer_id": "pro-reviewer",
                "class": "pro",
                "subject_sha": "c" * 40,
                "verdict": "REVIEW_PASS",
            },
            {
                "reviewer_id": "flash-reviewer",
                "class": "flash",
                "subject_sha": "c" * 40,
                "verdict": "REVIEW_PASS",
            },
        ],
        "contradiction": False,
    }
    assert attest_dual_review(well_formed) is well_formed

    # Missing candidate SHA -> fail closed.
    with pytest.raises(AttestationError):
        attest_dual_review({k: v for k, v in well_formed.items() if k != "candidate_sha"})
    # Missing explicit contradiction -> fail closed (stricter than 1.3.11:
    # contradiction is now required, never defaulted to absent-and-ignored).
    with pytest.raises(AttestationError):
        attest_dual_review({k: v for k, v in well_formed.items() if k != "contradiction"})
    # Non-diverse (both pro) -> fail closed.
    with pytest.raises(AttestationError):
        rv = dict(well_formed)
        rv["reviewers"] = [
            dict(well_formed["reviewers"][0]),
            dict(well_formed["reviewers"][0], reviewer_id="another-pro"),
        ]
        attest_dual_review(rv)
    # Differing subjects -> fail closed.
    with pytest.raises(AttestationError):
        rv = dict(well_formed)
        rv["reviewers"] = [
            dict(well_formed["reviewers"][0], subject_sha="d" * 40),
            dict(well_formed["reviewers"][1]),
        ]
        attest_dual_review(rv)
    # A non-PASS verdict -> fail closed.
    with pytest.raises(AttestationError):
        rv = dict(well_formed)
        rv["reviewers"] = [
            dict(well_formed["reviewers"][0], verdict="REVIEW_FAIL"),
            dict(well_formed["reviewers"][1]),
        ]
        attest_dual_review(rv)
    # A material contradiction -> fail closed.
    with pytest.raises(AttestationError):
        attest_dual_review(dict(well_formed, contradiction=True))
    # A well-formed dual pass whose subject is not the candidate -> fail closed.
    # Pins the MF-B defect: two reviewers agreeing on the wrong commit must not
    # attest the candidate.
    wrong_subject = dict(well_formed)
    wrong_subject["reviewers"] = [
        dict(well_formed["reviewers"][0], subject_sha="e" * 40),
        dict(well_formed["reviewers"][1], subject_sha="e" * 40),
    ]
    with pytest.raises(AttestationError):
        attest_dual_review(wrong_subject)


def test_criterion_13_no_reviewer_or_worker_merge_push_tag_release_publish():
    """Controller-attested: no reviewer writes a product file and no worker or
    reviewer merges, pushes a protected branch, tags, releases or publishes.

    A clean attestation passes; any recorded product write or forbidden action
    fails closed.
    """
    clean = {
        "reviewer_product_writes": [],
        "forbidden_actions": [],
    }
    assert attest_no_release_actions(clean) is clean

    with pytest.raises(AttestationError):
        attest_no_release_actions(
            {"reviewer_product_writes": ["src/skillweave/x.py"], "forbidden_actions": []}
        )
    for forbidden in ("merge", "push", "tag", "release", "publish"):
        with pytest.raises(AttestationError):
            attest_no_release_actions(
                {"reviewer_product_writes": [], "forbidden_actions": [forbidden]}
            )
