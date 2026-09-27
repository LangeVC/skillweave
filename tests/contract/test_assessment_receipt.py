"""SW-157-ASSESS-001 assessment receipt contract tests.

This suite proves that the assessment receipt contract
(``skillweave.assessment_contracts``) and its shipped JSON schema implement the
assessment contract:

1. A receipt represents an ``available``/``unavailable`` result, the subject's
   full 40-hex SHA, sources, commands and exit codes, findings, limits,
   provenance and a sha256 content digest.
2. Unknown keys and malformed values are rejected fail-closed at every level.
3. An ``unavailable`` receipt must state its limits; an ``available`` one must
   name at least one source and one command.
4. Any post-hoc mutation of a digested field — flipped result, changed subject
   SHA, altered exit code, dropped/added finding, mutated provenance, reordered
   source, or a swapped digest — fails closed with ``AssessmentTamperError``.
5. The contract module imports without the full skillweave runtime: its own
   import closure is standard-library only and loading it pulls no third-party
   or ``skillweave`` runtime module.

Every negative case is a named fixture; the suite is hermetic (no network, no
wall clock, no file mutation).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import jsonschema

from skillweave.assessment_contracts import (
    RESULT_AVAILABLE,
    RESULT_UNAVAILABLE,
    SCHEMA_VERSION,
    AssessmentError,
    AssessmentReceipt,
    AssessmentTamperError,
    canonicalize,
    compute_digest,
    load_schema,
    seal,
    validate,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
_MODULE_PATH = _SRC / "skillweave" / "assessment_contracts.py"
_SCHEMA_PATH = _REPO_ROOT / "schemas" / "assessment-receipt.schema.json"

_SHA = "0ef44d4ae2d41fb608c01b3d729995ffee5c22ae"
_OTHER_SHA = "1ab44d4ae2d41fb608c01b3d729995ffee5c22ae"
_SHA256 = "a" * 64
_OTHER_SHA256 = "b" * 64


def _core_available() -> dict:
    """An unsealed core available receipt (no digest)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "result": {"status": RESULT_AVAILABLE, "summary": "contract verified"},
        "subject": {"full_sha": _SHA, "repo": "skillweave/skillweave", "ref": "main"},
        "sources": [{"path": "src/skillweave/assessment_contracts.py", "sha256": _SHA256}],
        "commands": [{"command": "pytest tests/contract/test_assessment_receipt.py", "exit": 0}],
        "findings": [{"id": "F-1", "severity": "info", "summary": "no issues"}],
        "limits": ["read-only; no runtime execution beyond the focused test"],
        "provenance": {
            "assessor": "sw-157-assess-001",
            "run_id": "op-SW-157-ASSESS-001",
            "produced_at": "2026-09-27T00:00:00Z",
            "model": "byteplus-deepseek-flash-41",
        },
    }


def _sealed_available() -> dict:
    return seal(_core_available())


def _sealed_unavailable() -> dict:
    core = _core_available()
    core["result"] = {"status": RESULT_UNAVAILABLE, "summary": "toolchain absent"}
    core["sources"] = []
    core["commands"] = []
    core["findings"] = []
    core["limits"] = ["assessment could not run; no commands executed"]
    return seal(core)


def _schema_validator():
    return jsonschema.Draft202012Validator(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _schema_errors(doc):
    return list(_schema_validator().iter_errors(doc))


# ── Criterion 1: representation ────────────────────────────────────────────


def test_available_receipt_represents_full_shape():
    receipt = canonicalize(_sealed_available())
    assert isinstance(receipt, AssessmentReceipt)
    payload = receipt.payload
    assert payload["result"]["status"] == RESULT_AVAILABLE
    assert payload["subject"]["full_sha"] == _SHA
    assert payload["sources"] and payload["commands"]
    assert payload["findings"] and payload["limits"]
    assert payload["provenance"]["assessor"]
    assert receipt.digest == compute_digest(payload)


def test_unavailable_receipt_is_representable():
    receipt = canonicalize(_sealed_unavailable())
    assert receipt.payload["result"]["status"] == RESULT_UNAVAILABLE
    assert receipt.payload["limits"]


def test_seal_is_idempotent_and_round_trips():
    first = seal(_core_available())
    second = seal(first)
    assert first == second
    assert canonicalize(first).to_dict() == first


def test_validate_is_canonicalize():
    assert validate(_sealed_available()) == canonicalize(_sealed_available())


def test_schema_required_fields_and_shape():
    schema = load_schema()
    assert schema["$id"].endswith("assessment-receipt/v1")
    assert set(schema["required"]) == {
        "schema_version",
        "result",
        "subject",
        "sources",
        "commands",
        "findings",
        "limits",
        "provenance",
        "digest",
    }
    assert schema["additionalProperties"] is False
    assert schema["properties"]["result"]["properties"]["status"]["enum"] == [
        "available",
        "unavailable",
    ]
    assert schema["properties"]["subject"]["properties"]["full_sha"]["pattern"] == "^[0-9a-f]{40}$"
    assert schema["properties"]["digest"]["pattern"] == "^[a-f0-9]{64}$"


def test_schema_validates_sealed_documents_and_rejects_unknown_key():
    assert _schema_errors(_sealed_available()) == []
    assert _schema_errors(_sealed_unavailable()) == []
    bad = _sealed_available()
    bad["smuggled"] = True
    assert _schema_errors(bad) != []


def test_schema_rejects_available_without_sources_or_commands():
    bad = _sealed_available()
    bad["sources"] = []
    assert _schema_errors(bad) != []
    bad = _sealed_available()
    bad["commands"] = []
    assert _schema_errors(bad) != []


def test_schema_rejects_unavailable_without_limits():
    bad = _sealed_unavailable()
    bad["limits"] = []
    assert _schema_errors(bad) != []


# ── Criterion 2: fail-closed validation ────────────────────────────────────


@pytest.mark.parametrize(
    "mutate,label",
    [
        (lambda d: d.pop("subject"), "missing_subject"),
        (lambda d: d.update(schema_version=2), "wrong_schema_version"),
        (lambda d: d.update(schema_version=True), "boolean_schema_version"),
        (lambda d: d["result"].update(status="maybe"), "bad_status"),
        (lambda d: d["result"].update(status=[]), "non_string_status"),
        (lambda d: d["subject"].update(full_sha="abcd"), "malformed_sha"),
        (lambda d: d["subject"].update(full_sha=_SHA.upper()), "mixed_case_sha"),
        (lambda d: d["sources"][0].update(sha256="nothex"), "malformed_source_sha256"),
        (lambda d: d["sources"][0].update(sha256=_SHA256.upper()), "mixed_case_source_sha256"),
        (lambda d: d["commands"][0].update(exit="0"), "non_integer_exit"),
        (lambda d: d["findings"][0].update(severity="blocker"), "bad_severity"),
        (lambda d: d["findings"][0].update(severity=[]), "unhashable_severity"),
        (lambda d: d["provenance"].pop("assessor"), "missing_assessor"),
        (lambda d: d.update(extra="x"), "unknown_top_level_key"),
    ],
)
def test_named_negative_fixture_fails_closed(mutate, label):
    bad = _core_available()
    mutate(bad)
    with pytest.raises(AssessmentError):
        seal(bad)


def test_duplicate_finding_id_fails_closed():
    bad = _core_available()
    bad["findings"].append(dict(bad["findings"][0]))
    with pytest.raises(AssessmentError) as exc:
        seal(bad)
    assert "duplicate finding id" in str(exc.value)


def test_unavailable_without_limits_fails_closed():
    core = _core_available()
    core["result"] = {"status": RESULT_UNAVAILABLE}
    core["limits"] = []
    with pytest.raises(AssessmentError):
        seal(core)


def test_available_without_sources_fails_closed():
    core = _core_available()
    core["sources"] = []
    with pytest.raises(AssessmentError):
        seal(core)


def test_non_mapping_receipt_fails_closed():
    with pytest.raises(AssessmentError):
        seal([1, 2, 3])


def test_mixed_case_sha_is_refused_like_the_schema():
    # The module must agree with the shipped schema's lowercase-anchored
    # patterns: a mixed-case SHA is a different string, not an equivalent
    # identity that gets silently lowered.
    core = _core_available()
    core["subject"]["full_sha"] = _SHA.upper()
    with pytest.raises(AssessmentError):
        seal(core)


def test_mixed_case_source_sha256_is_refused():
    core = _core_available()
    core["sources"][0]["sha256"] = _SHA256.upper()
    with pytest.raises(AssessmentError):
        seal(core)


def test_boolean_and_float_schema_version_are_refused():
    for bad_version in (True, 1.0, "1"):
        core = _core_available()
        core["schema_version"] = bad_version
        with pytest.raises(AssessmentError):
            seal(core)


def test_unhashable_membership_inputs_raise_assessment_error_not_typeerror():
    # Fail closed with the contract's own error, never a raw TypeError leaked
    # from a set membership test on an unhashable value.
    for mutate in (
        lambda d: d["result"].update(status=[]),
        lambda d: d["findings"][0].update(severity={}),
    ):
        core = _core_available()
        mutate(core)
        with pytest.raises(AssessmentError):
            seal(core)


def test_module_and_schema_agree_on_rejected_shapes():
    # Every shape the module refuses must also fail the shipped schema, so the
    # two artifacts cannot drift into different notions of "valid".
    cases = []
    sealed = _sealed_available()
    sealed["subject"]["full_sha"] = _SHA.upper()
    cases.append(sealed)
    sealed = _sealed_available()
    sealed["sources"][0]["sha256"] = _SHA256.upper()
    cases.append(sealed)
    sealed = _sealed_available()
    sealed["findings"][0]["severity"] = "blocker"
    cases.append(sealed)
    for bad in cases:
        with pytest.raises(AssessmentError):
            seal(bad)
        assert _schema_errors(bad) != [], bad


# ── Criterion 4: tamper rejection ──────────────────────────────────────────


@pytest.mark.parametrize(
    "mutate,label",
    [
        (lambda d: d["result"].update(status=RESULT_UNAVAILABLE), "flip_status"),
        (lambda d: d["result"].update(summary="tampered"), "alter_summary"),
        (lambda d: d["subject"].update(full_sha=_OTHER_SHA), "swap_subject_sha"),
        (lambda d: d["sources"][0].update(sha256=_OTHER_SHA256), "swap_source_hash"),
        (lambda d: d["commands"][0].update(exit=1), "alter_exit_code"),
        (lambda d: d["findings"][0].update(summary="tampered"), "alter_finding"),
        (lambda d: d["provenance"].update(assessor="someone-else"), "mutate_provenance"),
        (lambda d: d.update(digest=_OTHER_SHA256), "swap_digest"),
    ],
)
def test_tampered_receipt_fails_closed(mutate, label):
    bad = _sealed_available()
    mutate(bad)
    with pytest.raises(AssessmentTamperError):
        canonicalize(bad)


def test_dropping_a_finding_is_detected():
    bad = _sealed_available()
    bad["findings"] = []
    with pytest.raises(AssessmentTamperError):
        canonicalize(bad)


def test_adding_a_finding_is_detected():
    bad = _sealed_available()
    bad["findings"].append({"id": "F-2", "severity": "high", "summary": "injected"})
    with pytest.raises(AssessmentTamperError):
        canonicalize(bad)


def test_reordering_sources_is_detected():
    core = _core_available()
    core["sources"] = [
        {"path": "b.py", "sha256": _OTHER_SHA256},
        {"path": "a.py", "sha256": _SHA256},
    ]
    sealed = seal(core)
    sealed["sources"] = list(reversed(sealed["sources"]))
    with pytest.raises(AssessmentTamperError):
        canonicalize(sealed)


def test_adding_a_command_is_detected():
    bad = _sealed_available()
    bad["commands"].append({"command": "rm -rf /", "exit": 0})
    with pytest.raises(AssessmentTamperError):
        canonicalize(bad)


def test_missing_digest_is_not_a_tamper_but_an_error():
    bad = _sealed_available()
    bad.pop("digest")
    with pytest.raises(AssessmentError):
        canonicalize(bad)


def test_digest_is_recomputed_from_payload_excluding_itself():
    sealed = _sealed_available()
    assert sealed["digest"] == compute_digest(sealed)
    # compute_digest ignores any digest key present on its input.
    assert compute_digest(sealed) == compute_digest({k: v for k, v in sealed.items() if k != "digest"})


# ── Criterion 5: imports without the full runtime ──────────────────────────


def test_module_import_closure_is_standard_library_only():
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    non_stdlib = sorted(imported - set(sys.stdlib_module_names) - {"__future__"})
    assert non_stdlib == [], f"contract module imports non-stdlib modules: {non_stdlib}"


def test_module_loads_in_isolation_without_skillweave_runtime():
    # Load the module by file path so `skillweave/__init__.py` (which eagerly
    # pulls PyYAML and 13 submodules) never executes; then diff sys.modules
    # across the load and assert it pulled no third-party or skillweave module.
    # The diff (not the final set) is measured so interpreter site machinery
    # (sitecustomize, editable-install finders) that pre-exists is not miscounted.
    probe = f'''
import importlib.util as u, json, sys
before = set(sys.modules)
spec = u.spec_from_file_location("skillweave_assessment_contracts", {str(_MODULE_PATH)!r})
module = u.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
sealed = module.seal(json.loads({json.dumps(_core_available())!r}))
checked = module.canonicalize(sealed)
newly_loaded = sorted(set(sys.modules) - before)
third_party = [n for n in newly_loaded if n.split(".")[0] not in sys.stdlib_module_names
               and not n.startswith("skillweave_assessment_contracts")]
print(json.dumps({{"third_party": third_party,
                  "skillweave_loaded": any(n == "skillweave" or n.startswith("skillweave.") for n in newly_loaded),
                  "status": checked.payload["result"]["status"],
                  "digest_len": len(sealed["digest"])}}))
'''
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert report["third_party"] == [], report["third_party"]
    assert report["skillweave_loaded"] is False
    assert report["status"] == RESULT_AVAILABLE
    assert report["digest_len"] == 64
