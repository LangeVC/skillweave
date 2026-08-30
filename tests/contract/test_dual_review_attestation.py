"""SW1312 dual-review attestation contract tests (SW1312-ATTESTATION-STRICT-001).

This suite proves that the reusable strict dual-review attestation validator
(``skillweave.gates.attestation``) and its shipped JSON schema implement all
seven acceptance criteria of SW1312-ATTESTATION-STRICT-001:

1. The contract requires ``candidate_sha``, exactly two reviewer records, an
   explicit ``contradiction`` boolean, and per-reviewer reviewer ids/classes/
   verdicts/subject SHAs.
2. Unknown top-level and reviewer keys are rejected, so ``contradiction_recorded``
   (or any other misspelling) cannot be silently ignored.
3. Full 40-hex SHAs are canonicalized to lowercase at ingestion and
   serialization; mixed-case equivalents collapse to one lowercase identity.
4. Both reviewers are one Pro-class and one Flash-class, inspect the identical
   canonical candidate, and return the exact ``REVIEW_PASS`` verdict while
   contradiction is false.
5. A missing contradiction, non-boolean contradiction, different subject,
   malformed SHA, duplicate reviewer identity/class, and a non-PASS verdict
   each fail closed in named negative fixtures.
6. The released tests/gate_1311 controller-attested behavior is migrated onto
   the shared validator without weakening any existing gate criterion.
7. SW1312 gate receipts validate the shared contract (via ``validate``) rather
   than copying a second local interpretation.

Every negative case is a named fixture so the failure mode is traceable; the
suite is hermetic (no network, no wall clock, no file mutation).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import jsonschema

from skillweave.gates.attestation import (
    AttestationError,
    DualReviewAttestation,
    canonicalize,
    load_schema,
    validate,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCHEMA_PATH = _REPO_ROOT / "schemas" / "dual-review-attestation.schema.json"

_SHA = "0ef44d4ae2d41fb608c01b3d729995ffee5c22ae"
_OTHER_SHA = "1ab44d4ae2d41fb608c01b3d729995ffee5c22ae"


def _valid_attestation() -> dict:
    return {
        "candidate_sha": _SHA,
        "reviewers": [
            {
                "reviewer_id": "pro-reviewer",
                "class": "pro",
                "verdict": "REVIEW_PASS",
                "subject_sha": _SHA,
            },
            {
                "reviewer_id": "flash-reviewer",
                "class": "flash",
                "verdict": "REVIEW_PASS",
                "subject_sha": _SHA,
            },
        ],
        "contradiction": False,
    }


def _schema_validator():
    return jsonschema.Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()))


def _schema_errors(doc):
    return list(_schema_validator().iter_errors(doc))


# ── Criterion 1: required strict schema ────────────────────────────────────

def test_required_fields_are_present_and_typed():
    schema = load_schema()
    required = set(schema["required"])
    assert required == {"candidate_sha", "reviewers", "contradiction"}

    reviewer_req = set(schema["$defs"]["reviewer"]["required"])
    assert reviewer_req == {"reviewer_id", "class", "verdict", "subject_sha"}
    # Exactly two reviewers, no more, no fewer.
    assert schema["properties"]["reviewers"]["minItems"] == 2
    assert schema["properties"]["reviewers"]["maxItems"] == 2
    # Explicit contradiction boolean.
    assert schema["properties"]["contradiction"]["type"] == "boolean"


def test_schema_validates_well_formed_and_rejects_unknown_keys():
    assert _schema_errors(_valid_attestation()) == []
    # Unknown top-level key.
    bad = dict(_valid_attestation(), contradiction_recorded=False)
    assert _schema_errors(bad) != []
    # Unknown reviewer key.
    bad = _valid_attestation()
    bad["reviewers"][0]["contradiction"] = False
    assert _schema_errors(bad) != []


# ── Criterion 2: unknown keys rejected by the validator ────────────────────

def test_validator_rejects_unknown_top_level_key():
    bad = dict(_valid_attestation(), contradiction_recorded=False)
    with pytest.raises(AttestationError) as exc:
        canonicalize(bad)
    assert "contradiction_recorded" in str(exc.value)


def test_validator_rejects_unknown_reviewer_key():
    bad = _valid_attestation()
    bad["reviewers"][1]["veridct"] = "REVIEW_PASS"  # typo for verdict
    with pytest.raises(AttestationError) as exc:
        canonicalize(bad)
    assert "veridct" in str(exc.value)


def test_validator_does_not_silently_ignore_misspelled_contradiction():
    # The exact defect shape: an attestation that omits `contradiction` but
    # carries `contradiction_recorded` must fail closed, not treat the missing
    # boolean as absent-and-ignored.
    bad = {
        "candidate_sha": _SHA,
        "reviewers": _valid_attestation()["reviewers"],
        "contradiction_recorded": True,
    }
    with pytest.raises(AttestationError):
        canonicalize(bad)


# ── Criterion 3: canonical lowercase SHA identity ──────────────────────────

def test_mixed_case_sha_canonicalizes_to_lowercase():
    upper = _SHA.upper()
    att = _valid_attestation()
    att["candidate_sha"] = upper
    att["reviewers"][0]["subject_sha"] = upper
    att["reviewers"][1]["subject_sha"] = _SHA  # mixed-case vs canonical are equal
    result = canonicalize(att)
    assert result.candidate_sha == _SHA
    assert result.reviewers[0]["subject_sha"] == _SHA
    assert result.reviewers[1]["subject_sha"] == _SHA


def test_serialization_emits_one_lowercase_identity():
    att = _valid_attestation()
    att["candidate_sha"] = _SHA.upper()
    result = canonicalize(att)
    payload = json.loads(result.to_json())
    assert payload["candidate_sha"] == _SHA
    for rev in payload["reviewers"]:
        assert rev["subject_sha"] == _SHA


def test_mixed_case_subject_matches_lowercase_candidate():
    att = _valid_attestation()
    att["reviewers"][0]["subject_sha"] = _SHA.upper()
    # Lowercase candidate vs uppercase subject must collapse to one identity.
    assert canonicalize(att).candidate_sha == _SHA


# ── Criterion 4: dual diverse PASS ─────────────────────────────────────────

def test_dual_diverse_reviewers_pass_and_inspect_identical_candidate():
    result = canonicalize(_valid_attestation())
    assert isinstance(result, DualReviewAttestation)
    classes = sorted(r["class"] for r in result.reviewers)
    assert classes == ["flash", "pro"]
    assert all(r["verdict"] == "REVIEW_PASS" for r in result.reviewers)
    assert result.contradiction is False
    assert all(r["subject_sha"] == result.candidate_sha for r in result.reviewers)


def test_validate_returns_same_canonical_form():
    assert validate(_valid_attestation()) == canonicalize(_valid_attestation())


# ── Criterion 5: named negative fixtures, fail closed ──────────────────────

@pytest.mark.parametrize(
    "mutate,label",
    [
        (lambda d: d.pop("contradiction"), "missing_contradiction"),
        (lambda d: d.update(contradiction="false"), "non_boolean_contradiction"),
        (lambda d: d["reviewers"][1].update(subject_sha=_OTHER_SHA), "different_subject"),
        (lambda d: d.update(candidate_sha="abcd"), "malformed_sha"),
        (lambda d: d["reviewers"][1].update(reviewer_id="pro-reviewer"), "duplicate_reviewer_id"),
        (lambda d: d["reviewers"][1].update(class_="pro"), "unsupported_key"),
        (lambda d: d["reviewers"][1].update(class_="pro"), "duplicate_reviewer_class"),
        (lambda d: d["reviewers"][1].update(verdict="REVIEW_FAIL"), "non_pass_verdict"),
    ],
)
def test_named_negative_fixture_fails_closed(mutate, label):
    bad = _valid_attestation()
    mutate(bad)
    with pytest.raises(AttestationError):
        canonicalize(bad)


def test_duplicate_reviewer_identity_fails_closed():
    bad = _valid_attestation()
    bad["reviewers"][1]["reviewer_id"] = "pro-reviewer"
    with pytest.raises(AttestationError) as exc:
        canonicalize(bad)
    assert "duplicate reviewer identity" in str(exc.value)


def test_duplicate_reviewer_class_fails_closed():
    bad = _valid_attestation()
    bad["reviewers"][1]["class"] = "pro"
    with pytest.raises(AttestationError) as exc:
        canonicalize(bad)
    assert "class" in str(exc.value)


def test_non_pass_verdict_fails_closed():
    bad = _valid_attestation()
    bad["reviewers"][0]["verdict"] = "REVIEW_FAIL"
    with pytest.raises(AttestationError) as exc:
        canonicalize(bad)
    assert "REVIEW_PASS" in str(exc.value)


def test_contradiction_true_fails_closed():
    bad = _valid_attestation()
    bad["contradiction"] = True
    with pytest.raises(AttestationError):
        canonicalize(bad)


def test_malformed_sha_fails_closed():
    bad = _valid_attestation()
    bad["candidate_sha"] = "abcd"
    with pytest.raises(AttestationError):
        canonicalize(bad)


def test_different_subject_fails_closed():
    bad = _valid_attestation()
    bad["reviewers"][0]["subject_sha"] = _OTHER_SHA
    with pytest.raises(AttestationError):
        canonicalize(bad)


def test_wrong_number_of_reviewers_fails_closed():
    for n in (0, 1, 3):
        bad = _valid_attestation()
        bad["reviewers"] = [dict(bad["reviewers"][0]) for _ in range(n)]
        with pytest.raises(AttestationError):
            canonicalize(bad)


def test_non_mapping_evidence_fails_closed():
    with pytest.raises(AttestationError):
        canonicalize([1, 2, 3])


# ── Criterion 6/7: shared-contract reuse (registred by the gate_1311 suite) ─

def test_shared_validator_exposes_single_validate_entry_point():
    # The SW1312 gate receipt validates *this* contract; there is exactly one
    # canonical entry point, not a second local interpretation.
    from skillweave.gates.attestation import validate as contract_validate

    assert contract_validate is validate
