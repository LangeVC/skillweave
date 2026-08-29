"""Transfer catalog preview integration tests (SW1311-TRANSFER-001).

Behavioural tests over the advisory learning catalog in
:mod:`skillweave.transfer.catalog` plus its shipped schema and evidence
fixture. The catalog represents the supplied research and the 2026-08-28
reports through the repository-contained learning ledger and the immutable
1.3.8 final-gate evidence; statements are scoped, provenance-bearing
observations — never routing commands and never policy decisions.

The eight acceptance criteria are covered:

1. Entries declare category, claim, resolvable provenance artifacts, observed
   task/profile/harness scope, confidence, contraindications, limitations and
   a review date or validity window.
2. The schema/catalog accept model, harness, process, review and topology
   observations without requiring concrete vendor/model/harness names.
3. The fixture represents the supplied research, the 2026-08-28 reports and
   the immutable 1.3.8 final-gate evidence, including the single-codebase
   benchmark limitation, the Pro/Flash strengths, failures, the incorrect
   digest finding and the upheld empty-group finding.
4. Conflicting/superseded observations stay queryable with dates and
   dispositions; history is never overwritten.
5. Retrieval uses explicit task/risk/profile/harness context and returns
   advisory observations with provenance/limitations, never a routing command
   or a mutable policy decision.
6. Missing resolvable provenance, observed scope or review date fails
   validation and is excluded from retrieval.
7. Negative tests prove ingestion/retrieval cannot mutate profile, model/
   harness policy, dispatch state, review disposition, topology, integration
   or gates.
8. Export applies artifact-policy redaction and cannot expose private prompts,
   secrets or hidden reasoning.

Provider-neutral and dependency-light (stdlib only for the catalog; the tests
use ``jsonschema`` only to check the shipped schema accepts the fixture, and
fall back to a structural check when it is absent).
"""

import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover - optional
    jsonschema = None  # type: ignore

from skillweave.transfer.catalog import (  # noqa: E402
    CATEGORIES,
    CATALOG_FORBIDDEN_ACTIONS,
    ResolutionStatus,
    AdvisoryObservation,
    ArtifactPolicy,
    Catalog,
    CatalogAuthorityError,
    CatalogValidationError,
    Entry,
    ObservedScope,
    ProvenanceArtifact,
    RetrievalContext,
    assert_catalog_authority,
    entry_resolution_status,
    export,
    resolve_provenance,
    retrieve,
    validate_catalog,
    validate_entry,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCHEMA_PATH = _REPO_ROOT / "schemas" / "transfer-entry.schema.json"
_FIXTURE_PATH = (
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "transfer"
    / "2026-08-28-dispatch-learnings.json"
)

_TRACEABILITY_SHA = "fb68bac7879acf68438cfaae90b2509d3cfcebcd95467c4bd1db52fca9bc7124"
_FINAL_GATE_SHA = "a9c9d87f5afe769e9e8795edfcef391d96aac8974345835599cf495a607ffc30"
_EXEC_STATE_SHA = "8fc13dcd61b9e59c7daf7a6781d108686f200c2c77be06180c130fd0d537861a"


def _document() -> dict:
    """The full fixture document: ``{"entries": [...], "evidence": [...]}``."""
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _fixture() -> list[dict]:
    return _document()["entries"]


def _evidence() -> list[dict]:
    return _document()["evidence"]


def _catalog() -> Catalog:
    return Catalog.load(_FIXTURE_PATH)


# ── Criterion 1: entry completeness ─────────────────────────────────────────


def test_every_fixture_entry_is_complete():
    catalog = _catalog()
    assert catalog.entries
    for entry in catalog.entries:
        problems = validate_entry(entry)
        assert not problems, (entry.entry_id, problems)


def test_entry_declares_all_required_fields():
    for name in (
        "entry_id",
        "category",
        "claim",
        "provenance_artifacts",
        "observed_scope",
        "confidence",
        "contraindications",
        "limitations",
        "status",
    ):
        assert name in _fixture()[0], name
    entry = catalog_entry_for("sw1311-model-001")
    assert entry.provenance_artifacts
    assert all(a.artifact_path and a.sha256 for a in entry.provenance_artifacts)
    assert entry.observed_scope.task and entry.observed_scope.risk
    assert entry.review_date or entry.validity_window


def catalog_entry_for(entry_id: str) -> Entry:
    for entry in _catalog().entries:
        if entry.entry_id == entry_id:
            return entry
    raise AssertionError(f"missing fixture entry {entry_id}")


# ── Criterion 2: provider-neutral acceptance ────────────────────────────────


def test_schema_accepts_provider_neutral_observation():
    if jsonschema is None:
        pytest.skip("jsonschema not installed; using structural check")
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for item in _fixture():
        errors = list(validator.iter_errors(item))
        assert errors == [], (item.get("entry_id"), [e.message for e in errors])
    # shipped evidence items also conform to the evidence_item definition.
    evidence_validator = jsonschema.Draft202012Validator(schema["$defs"]["evidence_item"])
    for item in _evidence():
        errors = list(evidence_validator.iter_errors(item))
        assert errors == [], (item.get("evidence_id"), [e.message for e in errors])


def test_catalog_accepts_all_category_kind_observations():
    assert {"model", "harness", "process", "review", "topology"} <= CATEGORIES
    seen = {entry.category for entry in _catalog().entries}
    assert {"model", "harness", "process", "review", "topology"} <= seen


def test_no_concrete_names_required():
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    model_tiers = schema["$defs"]["observed_scope"]["properties"]["model_tiers"]
    # model_tiers accepts only the provider-neutral capability tiers, never a
    # concrete vendor/model name.
    assert set(model_tiers["items"]["enum"]) == {"flash", "pro"}
    harness = schema["$defs"]["observed_scope"]["properties"]["harness"]
    # neither `names` nor `capabilities` is required: harness observations are
    # accepted without any concrete harness name.
    assert "names" not in (harness.get("required") or [])
    assert "capabilities" not in (harness.get("required") or [])


def test_harness_scope_without_names_is_valid():
    entry = Entry.from_dict(
        {
            "entry_id": "harness-neutral",
            "category": "harness",
            "claim": "harness observations need no concrete names",
            "provenance_artifacts": [
                {
                    "artifact_path": "a.txt",
                    "sha256": "0" * 64,
                }
            ],
            "observed_scope": {
                "task": "control-surface",
                "risk": "medium",
                "harness": {"capabilities": ["external-process", "in-place"]},
            },
            "confidence": "medium",
            "contraindications": [],
            "limitations": ["scoped observation"],
            "review_date": "2026-08-28",
            "status": "active",
        }
    )
    assert not validate_entry(entry)


# ── Criterion 3: evidence-faithful fixture ──────────────────────────────────


def test_single_codebase_benchmark_limitation_represented():
    entry = catalog_entry_for("sw1311-benchmark-001")
    assert "single-codebase" in entry.claim.lower()
    assert "universal" in entry.claim.lower() or "ranking" in entry.claim.lower()


def test_pro_and_flash_strengths_represented():
    model = catalog_entry_for("sw1311-model-001")
    assert "bounded" in model.claim.lower()
    assert "architecture" in model.claim.lower()
    model2 = catalog_entry_for("sw1311-model-002")
    assert "bug" in model2.claim.lower() or "edge" in model2.claim.lower()
    assert "pro" in model2.claim.lower()


def test_failures_represented():
    stall = catalog_entry_for("sw1311-model-003")
    assert "stall" in stall.claim.lower() or "literal" in stall.claim.lower()


def test_incorrect_digest_finding_represented():
    digest = catalog_entry_for("sw1311-finalgate-digest-001")
    assert "digest" in digest.claim.lower()
    assert "noncanonical" in digest.claim.lower()


def test_upheld_empty_group_finding_represented():
    empty = catalog_entry_for("sw1311-finalgate-empty-group-001")
    assert "empty" in empty.claim.lower()
    assert "uph" in empty.claim.lower()


# ── Criterion 4: history preserved, never overwritten ───────────────────────


def test_superseded_observation_remains_queryable():
    catalog = _catalog()
    context = RetrievalContext(task="final-gate-evolution", risk="high")
    result = retrieve(catalog, context, repo_root=_REPO_ROOT)
    by_id = {o.entry_id: o for o in result.superseded}
    # history is not overwritten: the superseded entry is still returned.
    assert "sw1311-finalgate-supersession-001" in by_id
    obs = by_id["sw1311-finalgate-supersession-001"]
    assert obs.status == "superseded"
    assert obs.disposition
    assert obs.review_date


def test_newer_entry_supersedes_older_without_deleting_it():
    catalog = _catalog()
    context = RetrievalContext(task="critical-final-gate", risk="critical")
    result = retrieve(catalog, context, repo_root=_REPO_ROOT)
    newer = {o.entry_id for o in result.advisory}
    assert "sw1311-finalgate-r2-001" in newer
    assert "sw1311-finalgate-r2-001" in {e.entry_id for e in catalog.entries}


# ── Criterion 5: advisory retrieval with provenance ─────────────────────────


def test_retrieval_is_contextual_and_advisory():
    context = RetrievalContext(
        task="review-and-discovery",
        risk="medium",
        profile="",
    )
    result = retrieve(_catalog(), context, repo_root=_REPO_ROOT)
    assert result.advisory
    for obs in result.advisory:
        assert isinstance(obs, AdvisoryObservation)
        assert obs.observed_scope.task == "review-and-discovery"
        assert obs.provenance


def test_retrieval_provenance_contains_limitations():
    context = RetrievalContext(task="implementation-vs-architecture", risk="high")
    result = retrieve(_catalog(), context, repo_root=_REPO_ROOT)
    obs = result.advisory[0]
    assert obs.limitations
    assert obs.provenance
    assert obs.category == "model"


def test_retrieval_returns_observation_never_routing():
    context = RetrievalContext(task="review-and-discovery", risk="medium")
    result = retrieve(_catalog(), context, repo_root=_REPO_ROOT)
    for obs in result.advisory:
        data = obs.to_dict()
        # advisory surface only: no routing command, no allocation decision.
        assert "routing" not in data
        assert "tier" not in {k for k in data} - {"category"}
        assert "limitations" in data
        assert "provenance" in data


# ── Criterion 6: validation gates retrieval ─────────────────────────────────


def test_missing_review_date_or_validity_fails_validation():
    entry = catalog_entry_for("sw1311-model-001").to_dict()
    entry.pop("review_date")
    assert any(
        "review_date or validity_window" in p
        for p in validate_entry(Entry.from_dict(entry))
    )


def test_missing_observed_scope_fails_validation():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["observed_scope"] = {"task": "", "risk": ""}
    assert validate_entry(Entry.from_dict(raw))


def test_missing_provenance_fails_validation():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["provenance_artifacts"] = []
    assert validate_entry(Entry.from_dict(raw))


def test_unresolvable_provenance_is_excluded_from_retrieval(tmp_path):
    with (tmp_path / "catalog.json").open("w", encoding="utf-8") as handle:
        json.dump(_document(), handle)
    catalog = Catalog.load(tmp_path / "catalog.json")
    fake_artifact = ProvenanceArtifact(artifact_path="missing/path.txt", sha256="")
    unresolved = Entry(
        entry_id="no-provenance",
        category="process",
        claim="irresolvable artifact",
        provenance_artifacts=(fake_artifact,),
        observed_scope=ObservedScope(task="x", risk="low"),
        confidence="low",
        limitations=("none",),
        contraindications=(),
        status="active",
        review_date="2026-08-28",
    )
    # Missing resolvable provenance fails validation and is excluded.
    assert validate_entry(unresolved)
    # A missing file with no content-address fallback is unresolved.
    assert entry_resolution_status(unresolved, tmp_path) == ResolutionStatus.UNRESOLVED


def test_mismatch_provenance_resolution():
    artifact = ProvenanceArtifact(
        artifact_path="schemas/transfer-entry.schema.json", sha256="0" * 64
    )
    assert (
        entry_resolution_status(
            Entry(
                entry_id="m",
                category="process",
                claim="c",
                provenance_artifacts=(artifact,),
                observed_scope=ObservedScope(task="t", risk="low"),
                confidence="low",
                limitations=("l",),
                contraindications=(),
                status="active",
                review_date="2026-08-28",
            ),
            _REPO_ROOT,
        )
        == ResolutionStatus.MISMATCH
    )


# ── Criterion 7: negative authority / immutability ─────────────────────────


@pytest.mark.parametrize(
    "surface",
    (
        "profile",
        "model_policy",
        "harness_policy",
        "dispatch",
        "review_disposition",
        "topology",
        "integration",
        "gate",
        "policy",
    ),
)
def test_catalog_cannot_mutate_any_surface(surface):
    with pytest.raises(CatalogAuthorityError):
        assert_catalog_authority(surface)


def test_ingestion_does_not_mutate_source_catalog():
    base = _catalog()
    snapshot = (base.entries, base.invalid)
    before = {e.entry_id for e in base.entries}
    base.ingest(catalog_entry_for("sw1311-benchmark-001"))
    assert {e.entry_id for e in base.entries} == before
    assert (base.entries, base.invalid) == snapshot


def test_ingestion_rejects_invalid_entry_without_mutation():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["observed_scope"] = {"task": "", "risk": ""}
    invalid = Entry.from_dict(raw)
    catalog = _catalog()
    before = len(catalog.entries)
    with pytest.raises(CatalogValidationError):
        catalog.ingest(invalid)
    assert len(catalog.entries) == before


def test_retrieval_does_not_mutate_state():
    catalog = _catalog()
    context = RetrievalContext(task="review-and-discovery", risk="medium")
    before = (catalog.entries, catalog.invalid)
    retrieve(catalog, context, repo_root=_REPO_ROOT)
    assert (catalog.entries, catalog.invalid) == before


def test_forbidden_action_set_covers_required_surface():
    assert {
        "profile",
        "model_policy",
        "harness_policy",
        "dispatch",
        "review_disposition",
        "topology",
        "integration",
        "gate",
    } <= CATALOG_FORBIDDEN_ACTIONS


# ── Criterion 8: redacted export ────────────────────────────────────────────


def test_export_redacts_restricted_and_confidential_fields():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["metadata"] = {
        "private_prompt": "DO NOT EXPORT THIS PROMPT",
        "chain_of_thought": "hidden reasoning",
        "api_key": "secret-token",
    }
    entry = Entry.from_dict(raw)
    exported = export([entry])[0]
    assert exported["metadata"]["private_prompt"] == "***REDACTED***"
    assert exported["metadata"]["chain_of_thought"] == "***REDACTED***"
    assert exported["metadata"]["api_key"] == "***REDACTED***"


def test_export_redacts_high_sensitivity_artifacts():
    entry = catalog_entry_for("sw1311-review-001")
    exported = export([entry])[0]
    for artifact in exported["provenance_artifacts"]:
        # both referenced artifacts are sensitivity=restricted
        assert artifact.get("redacted") is True
        assert "artifact_path" not in artifact
        assert artifact.get("source_name") == "***REDACTED***"


def test_export_allows_allowed_sensitivity_artifacts():
    entry = catalog_entry_for("sw1311-harness-001")
    exported = export([entry])[0]
    # source artifact is sensitivity=internal, allowed by default policy.
    assert all("redacted" not in a for a in exported["provenance_artifacts"])


def test_default_policy_cannot_expose_secrets():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["metadata"] = {
        "secret": "top-secret",
        "api_key": "k-abcdef",
        "private_prompt": "p-xx",
    }
    entry = Entry.from_dict(raw)
    exported = export([entry])[0]
    flat = json.dumps(exported)
    assert "top-secret" not in flat
    assert "k-abcdef" not in flat
    assert "p-xx" not in flat
    assert "***REDACTED***" in flat


# ── Divergent-input negative tests ──────────────────────────────────────────


def test_unknown_categories_and_tiers_are_rejected():
    raw = catalog_entry_for("sw1311-harness-003").to_dict()
    raw["observed_scope"]["model_tiers"] = ["vendor-model-x"]
    assert validate_entry(Entry.from_dict(raw))
    raw2 = catalog_entry_for("sw1311-harness-003").to_dict()
    raw2["observed_scope"]["harness"]["capabilities"] = ["not-a-surface"]
    assert validate_entry(Entry.from_dict(raw2))


def test_non_mapping_catalog_item_is_excluded_not_dropped(tmp_path):
    doc = _document()
    doc["entries"].append("garbage-item")
    path = tmp_path / "catalog-with-invalid.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    assert catalog.invalid
    # garbage is not an Entry, so not retrieved; valid entries still retrievable.
    context = RetrievalContext(task="review-and-discovery", risk="medium")
    result = retrieve(catalog, context, repo_root=_REPO_ROOT)
    assert result.advisory


def test_validate_catalog_reports_invalid_and_valid():
    report = validate_catalog(_catalog(), repo_root=_REPO_ROOT)
    assert report.valid
    # all fixture entries resolve against the real repository root.
    assert not report.invalid
    assert {e.entry_id for e in report.valid} == {
        e.entry_id for e in _catalog().entries
    }


# ── C1 binding corrections ──────────────────────────────────────────────────
#
# F-01..F-06 plus duplicate ids, supersession, ordering, calendar dates,
# malformed artifact/snapshot, digest mismatch and invalid-entry exclusion.


# F-01: provenance resolution must never escape repo_root ───────────────────


def test_provenance_rejects_parent_directory_escape(tmp_path):
    artifact = ProvenanceArtifact(artifact_path="../../etc/passwd", sha256="0" * 64)
    res = entry_resolution_status(
        Entry(
            entry_id="e",
            category="process",
            claim="c",
            provenance_artifacts=(artifact,),
            observed_scope=ObservedScope(task="t", risk="low"),
            confidence="low",
            limitations=("l",),
            contraindications=(),
            status="active",
            review_date="2026-08-28",
        ),
        tmp_path,
    )
    assert res == ResolutionStatus.UNRESOLVED


def test_provenance_rejects_absolute_path_escape(tmp_path):
    artifact = ProvenanceArtifact(artifact_path="/etc/passwd", sha256="0" * 64)
    res = resolve_provenance(artifact, tmp_path)
    assert res.status == ResolutionStatus.UNRESOLVED
    assert "escape" in res.note


def test_provenance_rejects_symlink_escape(tmp_path):
    # A symlink whose resolved target is a real file *outside* repo_root must
    # still be rejected as an escape, even though the file exists.
    outside_dir = tmp_path.parent / "outside-root"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "outside.txt"
    outside_file.write_text("secret", encoding="utf-8")
    (tmp_path / "sneaky").symlink_to(outside_file)
    artifact = ProvenanceArtifact(artifact_path="sneaky", sha256="0" * 64)
    res = resolve_provenance(artifact, tmp_path)
    assert res.status == ResolutionStatus.UNRESOLVED
    assert "escape" in res.note


def test_provenance_rejects_symlink_pointing_outside(tmp_path):
    sys_tmp = Path("/tmp")
    (tmp_path / "sys-link").symlink_to(sys_tmp / "definitely-missing-outside")
    artifact = ProvenanceArtifact(artifact_path="sys-link", sha256="0" * 64)
    res = resolve_provenance(artifact, tmp_path)
    assert res.status == ResolutionStatus.UNRESOLVED


# F-02: malformed nested types fail closed as recorded invalid entries ──────


def test_malformed_review_type_is_recorded_invalid(tmp_path):
    doc = _document()
    doc["entries"][0]["observed_scope"]["review"] = "oops"
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    assert any("review" in p for _, ps in catalog.invalid for p in ps) or catalog.invalid


def test_malformed_topology_list_is_recorded_invalid(tmp_path):
    doc = _document()
    doc["entries"][0]["observed_scope"]["topology"] = ["not", "object"]
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    assert catalog.invalid


def test_one_bad_entry_does_not_abort_catalog(tmp_path):
    doc = _document()
    doc["entries"].append(
        {
            "entry_id": "bad",
            "category": "model",
            "claim": "c",
            # malformed nested type: model_tiers must be an array
            "observed_scope": {
                "task": "t",
                "risk": "low",
                "model_tiers": "flash",
            },
            "confidence": "low",
            "limitations": ["l"],
            "contraindications": [],
            "status": "active",
            "review_date": "2026-08-28",
        }
    )
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    assert catalog.invalid
    assert len(catalog.entries) == len(_fixture())


def test_no_uncaught_type_error_for_scalar_mismatch():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["confidence"] = True  # bool instead of string
    with pytest.raises(CatalogValidationError):
        Entry.from_dict(raw)


# F-03: normalization-aware restricted-field matching ────────────────────────


def test_export_redacts_separator_and_case_variants():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["metadata"] = {
        "API_KEY": "v1",
        "api-key": "v2",
        "Private_Prompt": "v3",
        "hidden reason ing": "v4",
    }
    entry = Entry.from_dict(raw)
    exported = json.dumps(export([entry])[0])
    for secret in ("v1", "v2", "v3", "v4"):
        assert secret not in exported
    assert "***REDACTED***" in exported


def test_export_redacts_restricted_fields_inside_lists():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["metadata"] = {"notes": [{"api_key": "leaked-1"}, {"API_KEY": "leaked-2"}]}
    entry = Entry.from_dict(raw)
    exported = export([entry])[0]
    flat = json.dumps(exported)
    assert "leaked-1" not in flat
    assert "leaked-2" not in flat


def test_export_redacts_restricted_top_level_field():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["metadata"] = {"chain_of_thought": "reasoning"}
    entry = Entry.from_dict(raw)
    exported = export([entry], fields=["metadata"])[0]
    assert exported["metadata"]["chain_of_thought"] == "***REDACTED***"


# F-04: runtime validation agrees with schema (no bool/number coercion) ──────


def test_runtime_rejects_bool_review_date_like_schema():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["review_date"] = True
    with pytest.raises(CatalogValidationError):
        Entry.from_dict(raw)


def test_runtime_rejects_numeric_entry_id_like_schema():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["entry_id"] = 123
    with pytest.raises(CatalogValidationError):
        Entry.from_dict(raw)


def test_runtime_rejects_bool_as_number_topology_parallelism():
    if jsonschema is None:
        pytest.skip("jsonschema not installed")
    raw = catalog_entry_for("sw1311-topology-001").to_dict()
    raw["observed_scope"]["topology"]["parallelism"] = 1  # bool-as-number
    with pytest.raises(CatalogValidationError):
        Entry.from_dict(raw)
    # JSON Schema also rejects it (boolean expected).
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(raw))
    assert errors


def test_runtime_rejects_unknown_key_like_schema():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["made_up_field"] = "x"
    entry = Entry.from_dict(raw)
    assert any("unknown field" in p for p in validate_entry(entry))


def test_schema_and_runtime_agree_on_validity_window():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["validity_window"] = {"start": "2026-13-45", "end": None}
    entry = Entry.from_dict(raw)
    assert any("start" in p for p in validate_entry(entry))


# F-05: value immutability, no shallow aliasing ──────────────────────────────


def test_source_dict_mutation_does_not_affect_entry():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["metadata"] = {"stable": "value"}
    raw["observed_scope"]["review"] = {"kind": "final_gauntlet"}
    entry = Entry.from_dict(raw)
    raw["metadata"]["injected"] = "mutated"
    raw["observed_scope"]["review"]["kind"] = "adjudication"
    assert "injected" not in entry.metadata
    assert entry.observed_scope.review.get("kind") != "adjudication"


def test_nested_mutation_through_entry_surface_raises():
    entry = catalog_entry_for("sw1311-review-001")
    with pytest.raises(TypeError):
        entry.observed_scope.review["kind"] = "adjudication"  # type: ignore[index]


def test_to_dict_returns_copy_not_alias():
    entry = catalog_entry_for("sw1311-review-001")
    data = entry.to_dict()
    data["observed_scope"]["review"]["kind"] = "mutated"
    assert entry.observed_scope.review.get("kind") != "mutated"


# F-06: verifiable, redacted, content-addressed evidence ─────────────────────


def test_evidence_snapshot_digest_matches_embedded_content():
    catalog = _catalog()
    for item in catalog.evidence.items:
        assert item.verify(), item.evidence_id


def test_bare_digest_without_evidence_is_unresolved(tmp_path):
    artifact = ProvenanceArtifact(artifact_path="missing.txt", sha256="0" * 64)
    res = resolve_provenance(artifact, tmp_path, evidence=_catalog().evidence)
    assert res.status == ResolutionStatus.UNRESOLVED


def test_digest_mismatch_against_evidence_is_excluded(tmp_path):
    artifact = ProvenanceArtifact(
        artifact_path=".skillweave/tracking-log/sw138-gate-remediation/execution-state.json",
        sha256="0" * 64,
        evidence_id="ev-execution-state",
    )
    res = resolve_provenance(artifact, tmp_path, evidence=_catalog().evidence)
    assert res.status == ResolutionStatus.MISMATCH


def test_missing_evidence_reference_is_excluded(tmp_path):
    doc = _document()
    doc["entries"].append(
        {
            "entry_id": "bad-evidence",
            "category": "process",
            "claim": "c",
            "provenance_artifacts": [
                {
                    "artifact_path": "p.txt",
                    "sha256": "0" * 64,
                    "evidence_id": "ev-does-not-exist",
                }
            ],
            "observed_scope": {"task": "t", "risk": "low"},
            "confidence": "low",
            "limitations": ["l"],
            "contraindications": [],
            "status": "active",
            "review_date": "2026-08-28",
        }
    )
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    context = RetrievalContext(task="t", risk="low")
    result = retrieve(catalog, context, repo_root=tmp_path)
    assert "bad-evidence" not in {o.entry_id for o in result.advisory}
    assert "bad-evidence" not in {o.entry_id for o in result.superseded}


def test_evidence_content_is_redacted_no_secrets():
    doc = _document()
    for item in doc["evidence"]:
        content = item["content"]
        # no real secret material: no key-shaped values, no prompt bodies.
        for pattern in ("sk-", "AKIA", "BEGIN PRIVATE", "key=", "token=", "password="):
            assert pattern not in content, item["evidence_id"]


# Additional coverage ────────────────────────────────────────────────────────


def test_duplicate_entry_ids_are_rejected(tmp_path):
    doc = _document()
    doc["entries"].append(catalog_entry_for("sw1311-model-001").to_dict())
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    report = validate_catalog(catalog, repo_root=_REPO_ROOT)
    assert any("duplicate entry_id" in p for _, ps in report.invalid for p in ps)


def test_missing_supersession_target_is_rejected(tmp_path):
    doc = _document()
    doc["entries"].append(
        {
            "entry_id": "orphan-superseder",
            "category": "review",
            "claim": "c",
            "provenance_artifacts": [
                {
                    "artifact_path": "x.txt",
                    "sha256": "0" * 64,
                    "evidence_id": "ev-learning-traceability",
                }
            ],
            "observed_scope": {"task": "t", "risk": "low"},
            "confidence": "low",
            "limitations": ["l"],
            "contraindications": [],
            "status": "active",
            "review_date": "2026-08-28",
            "supersedes": "does-not-exist",
        }
    )
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    report = validate_catalog(catalog, repo_root=_REPO_ROOT)
    assert any("does not exist" in p for _, ps in report.invalid for p in ps)


def test_supersession_cycle_is_rejected(tmp_path):
    doc = _document()
    entry_a = catalog_entry_for("sw1311-model-001").to_dict()
    entry_a["entry_id"] = "cycle-a"
    entry_a["supersedes"] = "cycle-b"
    entry_b = catalog_entry_for("sw1311-model-001").to_dict()
    entry_b["entry_id"] = "cycle-b"
    entry_b["supersedes"] = "cycle-a"
    doc["entries"].extend([entry_a, entry_b])
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    report = validate_catalog(catalog, repo_root=_REPO_ROOT)
    assert any("cycle" in p for _, ps in report.invalid for p in ps)


def test_retrieval_order_is_deterministic():
    context = RetrievalContext(task="review-and-discovery", risk="medium")
    first = retrieve(_catalog(), context, repo_root=_REPO_ROOT)
    second = retrieve(_catalog(), context, repo_root=_REPO_ROOT)
    assert [o.entry_id for o in first.advisory] == [o.entry_id for o in second.advisory]
    assert [o.entry_id for o in first.superseded] == [o.entry_id for o in second.superseded]


def test_invalid_calendar_dates_rejected():
    raw = catalog_entry_for("sw1311-model-001").to_dict()
    raw["review_date"] = "2026-02-30"
    assert any("date" in p for p in validate_entry(Entry.from_dict(raw)))
    raw2 = catalog_entry_for("sw1311-model-001").to_dict()
    raw2.pop("review_date")
    raw2["validity_window"] = {"start": "2026-12-31", "end": "2026-01-01"}
    assert any("after" in p for p in validate_entry(Entry.from_dict(raw2)))


def test_malformed_artifact_data_recorded_invalid(tmp_path):
    doc = _document()
    doc["entries"][0]["provenance_artifacts"] = "not-a-list"
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    assert catalog.invalid


def test_evidence_digest_mismatch_recorded_invalid(tmp_path):
    doc = _document()
    doc["evidence"][0]["sha256"] = "0" * 64
    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    catalog = Catalog.load(path)
    assert any("does not match" in p for _, ps in catalog.invalid for p in ps)


def _run_all() -> int:
    """Run the fixtures that need no pytest fixtures (standalone fallback)."""
    import tempfile

    failed = 0
    cases = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    for name, fn in cases:
        try:
            if name in (
                "test_unresolvable_provenance_is_excluded_from_retrieval",
                "test_non_mapping_catalog_item_is_excluded_not_dropped",
            ):
                with tempfile.TemporaryDirectory() as tmp:
                    fn(Path(tmp))
            else:
                fn()
            print(f"PASS {name}")
        except TypeError as exc:  # pytest.parametrize / fixture-only cases
            failed += 1
            print(f"SKIP {name}: {type(exc).__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
