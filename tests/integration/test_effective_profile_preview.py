"""Immutable effective-profile snapshot (SW1312-PROFILE-RESOLVE-001).

Integration proof of the consumer-side resolution seam: explicit profile
sources travel the canonical precedence chain into a content-addressed,
fully explained, immutable snapshot. Eight acceptance criteria, each as a
red/green proof:

1. Precedence: run override > project > organization > domain pack >
   category pack > core defaults, with the stronger source winning fold-by-fold.
2. Provenance: every inherited default, override, source id, source version and
   conflict is visible; no hidden default changes behaviour.
3. SDK binding: the snapshot records the SDK schema version and digest and
   refuses an incompatible or same-version-different-bytes source.
4. Determinism: identical ordered inputs produce byte-identical snapshots and
   the same content digest.
5. Run immutability: changing a source profile after dispatch does not alter the
   pinned snapshot.
6. Conflict: non-mergeable conflicting values fail with exact source paths,
   never silently preferring a lower-precedence source.
7. Preview boundary: preview-unsupported runtime dimensions are preserved as
   declarations but fail explicitly if a caller requests execution.
8. Domain neutrality: the resolver has no CMS provider branch and resolves the
   two OSS profiles and the private pack through the same public contract.

The fixtures are self-contained (the SDK package is not imported): the resolver
pins the canonical SDK version/digest and accepts an injected schema fileset
digest, so the proof stays hermetic to this repository.
"""

import copy
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.profiles.effective import (  # noqa: E402
    ConflictError,
    EffectiveProfileSnapshot,
    PreviewExecutionError,
    ProfileSource,
    SchemaBindingError,
    SDK_EXPECTED_SCHEMA_DIGEST,
    SDK_PREVIEW_SCHEMA_VERSION,
    SOURCE_KINDS,
    content_digest,
    canonical_json_bytes,
    preview_dimensions_of,
    resolve_effective_profile,
)

# A hermetic schema fileset whose canonical digest the resolver computes when
# injected. The bound digest is derived below so every source must declare it
# to pass binding; it diverges from the pinned ``SDK_EXPECTED_SCHEMA_DIGEST``
# deliberately, so the digest-identity check is exercised against real bytes.
_SCHEMA_SET = (
    ("work-profile.preview.schema.json", '{"$id":"x","preview":"0.1.0"}'),
    ("lifecycle-profile.preview.schema.json", '{"$id":"y","preview":"0.1.0"}'),
)

import hashlib as _hashlib  # noqa: E402


def _schema_digest_of(schema_set):
    hasher = _hashlib.sha256()
    for filename, canonical in sorted(schema_set):
        hasher.update(filename.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(canonical.encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


_BOUND_DIGEST = _schema_digest_of(_SCHEMA_SET)

# ── shared fixtures ────────────────────────────────────────────────────────

# The two OSS profiles (software-product-delivery, research-and-synthesis) and
# the private pack (cms-ops-management) as domain-neutral source specs. All
# three travel the same public contract; none carries a concrete provider.
_SOFTWARE = {
    "kind": "domain_pack",
    "id": "software-product-delivery",
    "version": "v1-preview",
    "schemaVersion": SDK_PREVIEW_SCHEMA_VERSION,
    "schemaDigest": _BOUND_DIGEST,
    "content": {
        "primaryCategory": "build",
        "topology": "linear",
        "phases": [
            "discovery",
            "blueprint",
            "design",
            "build",
            "release",
            "launch",
            "post_release",
        ],
        "kernel_stage": "K0",
    },
}

_RESEARCH = {
    "kind": "domain_pack",
    "id": "research-and-synthesis",
    "version": "v1-preview",
    "schemaVersion": SDK_PREVIEW_SCHEMA_VERSION,
    "schemaDigest": _BOUND_DIGEST,
    "content": {
        "primaryCategory": "research",
        "topology": "iterative",
        "phases": ["research", "synthesis", "evidence_review", "handoff", "learning"],
        "kernel_stage": "K1",
    },
}

_CMS_PACK = {
    "kind": "category_pack",
    "id": "cms-ops-management",
    "version": "v1-pack",
    "schemaVersion": SDK_PREVIEW_SCHEMA_VERSION,
    "schemaDigest": _BOUND_DIGEST,
    "content": {
        "primaryCategory": "operate",
        "topology": "human_cadenced",
        "capabilities": {"cms_authoring": True, "text_humanization": True},
    },
}


_software = _SOFTWARE
_research = _RESEARCH
_cms_pack = _CMS_PACK


def _core_defaults(**extra):
    return {
        "kind": "core_defaults",
        "id": "core-defaults",
        "version": "1.3.12",
        "schemaVersion": SDK_PREVIEW_SCHEMA_VERSION,
        "schemaDigest": _BOUND_DIGEST,
        "content": {"primaryCategory": "build", "topology": "linear", **extra},
    }


def _source(spec, **overrides):
    merged = copy.deepcopy(spec) if "content" in spec else dict(spec)
    merged.update(overrides)
    return merged


# ── criterion 1: precedence order ──────────────────────────────────────────

def test_precedence_chain_matches_prd_order():
    assert SOURCE_KINDS == (
        "run_override",
        "project_profile",
        "organization_profile",
        "domain_pack",
        "category_pack",
        "core_defaults",
    )


def test_run_override_wins_over_every_weaker_source():
    run = _source(
        _core_defaults(),
        kind="run_override",
        id="run-abc",
        version="1",
        content={"primaryCategory": "research"},
    )
    snap = resolve_effective_profile(
        [run, _software, _CMS_PACK, _core_defaults()], schema_set=_SCHEMA_SET
    )
    assert snap.resolved["primaryCategory"] == "research"


def test_project_profile_outranks_organization_and_everything_weaker():
    project = _source(
        _core_defaults(),
        kind="project_profile",
        id="project-x",
        version="1",
        content={"topology": "dag"},
    )
    org = _source(
        _core_defaults(),
        kind="organization_profile",
        id="org-y",
        version="1",
        content={"topology": "linear"},
    )
    snap = resolve_effective_profile(
        [project, org, _software, _core_defaults()], schema_set=_SCHEMA_SET
    )
    assert snap.resolved["topology"] == "dag"


def test_domain_pack_wins_over_category_pack_and_core_defaults():
    snap = resolve_effective_profile(
        [_software, _CMS_PACK, _core_defaults()], schema_set=_SCHEMA_SET
    )
    assert snap.resolved["primaryCategory"] == "build"


def test_weaker_value_merge_preserves_stronger_win_per_key():
    # The software domain pack sets topology=linear; the research-ish run
    # override sets primaryCategory=research but leaves topology untouched, so
    # the domain pack's topology survives while the run override's category wins.
    run = _source(
        _core_defaults(),
        kind="run_override",
        id="run-abc",
        version="1",
        content={"primaryCategory": "research"},
    )
    snap = resolve_effective_profile([run, _software, _core_defaults()], schema_set=_SCHEMA_SET)
    assert snap.resolved["primaryCategory"] == "research"
    assert snap.resolved["topology"] == "linear"


# ── criterion 2: visible provenance / defaults ─────────────────────────────

def test_every_resolved_key_is_attributable_to_one_source():
    snap = resolve_effective_profile(
        [_software, _CMS_PACK, _core_defaults()], schema_set=_SCHEMA_SET
    )
    for key in snap.resolved:
        assert key in snap.provenance, f"resolved key {key!r} has no provenance"
        src = snap.provenance[key]
        assert src.source_id and src.source_version


def test_snapshot_exposes_all_sources_with_ids_and_versions():
    snap = resolve_effective_profile(
        [_software, _CMS_PACK, _core_defaults()], schema_set=_SCHEMA_SET
    )
    ids = [(s.kind, s.source_id, s.source_version) for s in snap.sources]
    assert ids == [
        ("domain_pack", "software-product-delivery", "v1-preview"),
        ("category_pack", "cms-ops-management", "v1-pack"),
        ("core_defaults", "core-defaults", "1.3.12"),
    ]


def test_inherited_default_is_visible_with_its_winning_source():
    snap = resolve_effective_profile([_software, _core_defaults()], schema_set=_SCHEMA_SET)
    assert snap.resolved["topology"] == "linear"
    assert snap.provenance["topology"].source_id == "software-product-delivery"


# ── criterion 3: SDK version + digest binding ──────────────────────────────

def test_snapshot_records_sdk_version_and_digest():
    snap = resolve_effective_profile([_software, _core_defaults()], schema_set=_SCHEMA_SET)
    assert snap.sdk_version == SDK_PREVIEW_SCHEMA_VERSION
    assert snap.sdk_digest == _BOUND_DIGEST


def test_incompatible_schema_version_is_refused():
    bad = _source(_software, schemaVersion="0.0.9")
    with pytest.raises(SchemaBindingError):
        resolve_effective_profile([bad, _core_defaults()], schema_set=_SCHEMA_SET)


def test_same_version_different_bytes_is_refused():
    bad = _source(_software, schemaDigest="f" * 64)
    with pytest.raises(SchemaBindingError) as exc:
        resolve_effective_profile([bad, _core_defaults()], schema_set=_SCHEMA_SET)
    assert "same version, different bytes" in str(exc.value)


# ── criterion 4: determinism ───────────────────────────────────────────────

def test_identical_ordered_inputs_produce_byte_identical_snapshots():
    a = resolve_effective_profile([_software, _CMS_PACK, _core_defaults()], schema_set=_SCHEMA_SET)
    b = resolve_effective_profile([_software, _CMS_PACK, _core_defaults()], schema_set=_SCHEMA_SET)
    assert a.canonical_bytes == b.canonical_bytes
    assert a.digest == b.digest
    assert a.to_canonical_json() == b.to_canonical_json()


def test_same_content_digest_for_structurally_equal_snapshot():
    a = resolve_effective_profile([_software, _core_defaults()], schema_set=_SCHEMA_SET)
    assert a.digest == content_digest(a.resolved)


# ── criterion 5: run immutability ──────────────────────────────────────────

def test_changing_source_after_dispatch_does_not_alter_pinned_snapshot():
    snap = resolve_effective_profile([_software, _core_defaults()], schema_set=_SCHEMA_SET)
    pinned_resolved = copy.deepcopy(snap.resolved)
    pinned_digest = snap.digest

    # Mutate the input source image after the snapshot was built.
    _software["content"]["topology"] = "dag"

    assert snap.resolved["topology"] == pinned_resolved["topology"]
    assert snap.digest == pinned_digest


def test_first_writer_nested_mapping_is_independently_owned():
    # The first writer contributes a nested mapping. The snapshot must own an
    # independent deep copy, so mutating the source's nested leaf (scalar and
    # list) after resolution leaves resolved, canonical bytes and digest
    # byte-identical.
    strong = _source(
        _core_defaults(),
        kind="organization_profile",
        id="org-a",
        version="1",
        content={"engine": {"pipeline": {"batch_size": 10, "modes": ["sync", "async"]}}},
    )
    snap = resolve_effective_profile([strong, _core_defaults()], schema_set=_SCHEMA_SET)
    pinned_resolved = copy.deepcopy(snap.resolved)
    pinned_digest = snap.digest
    pinned_bytes = snap.canonical_bytes

    strong["content"]["engine"]["pipeline"]["batch_size"] = 999
    strong["content"]["engine"]["pipeline"]["modes"].append("burst")

    assert snap.resolved == pinned_resolved
    assert snap.resolved["engine"]["pipeline"]["batch_size"] == 10
    assert snap.resolved["engine"]["pipeline"]["modes"] == ["sync", "async"]
    assert snap.digest == pinned_digest
    assert snap.canonical_bytes == pinned_bytes


def test_weaker_gap_fill_nested_mapping_is_independently_owned():
    # A weaker source fills a gap inside a stronger source's nested mapping.
    # That gap-fill must be stored as an independent deep copy, so mutating the
    # weaker source's nested leaf after resolution leaves the snapshot
    # byte-identical.
    strong = _source(
        _core_defaults(),
        kind="organization_profile",
        id="org-a",
        version="1",
        content={"control": {"risk": "low"}},
    )
    weak = _source(
        _core_defaults(),
        kind="domain_pack",
        id="software-product-delivery",
        version="v1-preview",
        content={"control": {"nested_child": {"x": 1, "tags": ["a"]}}},
    )
    snap = resolve_effective_profile([strong, weak, _core_defaults()], schema_set=_SCHEMA_SET)
    pinned_resolved = copy.deepcopy(snap.resolved)
    pinned_digest = snap.digest
    pinned_bytes = snap.canonical_bytes

    weak["content"]["control"]["nested_child"]["x"] = 999
    weak["content"]["control"]["nested_child"]["tags"].append("mutated")

    assert snap.resolved == pinned_resolved
    assert snap.resolved["control"]["nested_child"]["x"] == 1
    assert snap.resolved["control"]["nested_child"]["tags"] == ["a"]
    assert snap.digest == pinned_digest
    assert snap.canonical_bytes == pinned_bytes


# ── criterion 6: conflict handling ─────────────────────────────────────────

def test_conflicting_non_mergeable_values_fail_with_exact_source_paths():
    # Two sources of the SAME precedence (two domain packs) set the same
    # non-mergeable key to different values. No precedence order exists between
    # them, so the resolver must fail naming both exact paths rather than
    # silently preferring either one.
    a = _source(
        _software,
        id="software-product-delivery",
        version="v1-preview",
        content={"topology": "linear"},
    )
    b = _source(
        _software,
        id="research-and-synthesis",
        version="v1-preview",
        content={"topology": "dag"},
    )
    with pytest.raises(ConflictError) as exc:
        resolve_effective_profile([a, b, _core_defaults()], schema_set=_SCHEMA_SET)
    msg = str(exc.value)
    assert "topology" in msg
    assert "domain_pack/software-product-delivery@v1-preview" in msg
    assert "domain_pack/research-and-synthesis@v1-preview" in msg


def test_lower_precedence_override_is_visible_not_silent():
    # A weaker source's differing non-mergeable value does NOT silently win:
    # the stronger source wins and the override is recorded on the snapshot.
    org = _source(
        _core_defaults(),
        kind="organization_profile",
        id="org-a",
        version="1",
        content={"topology": "linear"},
    )
    domain = _source(
        _core_defaults(),
        kind="domain_pack",
        id="software-product-delivery",
        version="v1-preview",
        content={"topology": "dag"},
    )
    snap = resolve_effective_profile([org, domain, _core_defaults()], schema_set=_SCHEMA_SET)
    # Stronger (org) wins.
    assert snap.resolved["topology"] == "linear"
    assert snap.provenance["topology"].source_id == "org-a"
    # The override is recorded, so no hidden default changed behaviour unseen.
    assert any(
        o["key"] == "topology" and o["winner"] == "organization_profile/org-a@1"
        for o in snap.overrides
    )


def test_same_precedence_nested_conflict_fails_with_exact_paths():
    # Two sources of the SAME precedence set a nested non-mergeable scalar to
    # different values. The conflict must be detected at the nested leaf and
    # name both exact paths, never silently prefer the first writer.
    a = _source(
        _core_defaults(),
        kind="domain_pack",
        id="software-product-delivery",
        version="v1-preview",
        content={"control": {"risk": "low"}},
    )
    b = _source(
        _core_defaults(),
        kind="domain_pack",
        id="research-and-synthesis",
        version="v1-preview",
        content={"control": {"risk": "high"}},
    )
    with pytest.raises(ConflictError) as exc:
        resolve_effective_profile([a, b, _core_defaults()], schema_set=_SCHEMA_SET)
    msg = str(exc.value)
    assert "control.risk" in msg
    assert "domain_pack/software-product-delivery@v1-preview" in msg
    assert "domain_pack/research-and-synthesis@v1-preview" in msg


def test_weaker_nested_override_is_visible_and_leaf_provenance_preserved():
    # A stronger source owns a nested mapping; a weaker source overrides one
    # nestable scalar. The stronger leaf value must win, the weaker override
    # must be recorded, and both the winning leaf provenance and the parent
    # provenance stay visible in the snapshot.
    strong = _source(
        _core_defaults(),
        kind="organization_profile",
        id="org-a",
        version="1",
        content={"control": {"risk": "low", "nested": {"timeout": 30}}},
    )
    weak = _source(
        _core_defaults(),
        kind="domain_pack",
        id="software-product-delivery",
        version="v1-preview",
        content={"control": {"risk": "high"}},
    )
    snap = resolve_effective_profile([strong, weak, _core_defaults()], schema_set=_SCHEMA_SET)
    assert snap.resolved["control"]["risk"] == "low"
    assert snap.provenance["control.risk"].source_id == "org-a"
    assert snap.provenance["control.nested.timeout"].source_id == "org-a"
    assert any(
        o["key"] == "control.risk"
        and o["winner"] == "organization_profile/org-a@1"
        and o["overridden"] == "domain_pack/software-product-delivery@v1-preview"
        for o in snap.overrides
    )


def test_equal_values_are_not_a_conflict():
    a = _source(
        _core_defaults(),
        kind="organization_profile",
        id="org-a",
        version="1",
        content={"topology": "linear"},
    )
    b = _source(
        _core_defaults(),
        kind="domain_pack",
        id="software-product-delivery",
        version="v1-preview",
        content={"topology": "linear"},
    )
    snap = resolve_effective_profile([a, b, _core_defaults()], schema_set=_SCHEMA_SET)
    assert snap.resolved["topology"] == "linear"
    # The stronger source stays the attributed winner.
    assert snap.provenance["topology"].source_id == "org-a"


def test_mapping_values_merge_without_conflict():
    a = _source(_core_defaults(), kind="organization_profile", id="org-a", version="1",
                content={"control": {"risk": "medium"}})
    b = _source(_core_defaults(), kind="project_profile", id="proj-b", version="1",
                content={"control": {"reversibility": "reversible"}})
    snap = resolve_effective_profile([b, a, _core_defaults()], schema_set=_SCHEMA_SET)
    # The stronger source's control dict merges with the weaker source's fill.
    assert snap.resolved["control"] == {"risk": "medium", "reversibility": "reversible"}
    assert snap.provenance["control"].source_id == "proj-b"
    # The weaker source's gap-fill is individually attributable.
    assert snap.provenance["control.risk"].source_id == "org-a"


# ── criterion 7: preview boundary ──────────────────────────────────────────

def test_preview_dimensions_preserved_as_declarations():
    snap = resolve_effective_profile([_software, _core_defaults()], schema_set=_SCHEMA_SET)
    dims = snap.preview_dimensions
    assert "phases" in dims
    assert "topology" in dims
    assert dims["phases"] == _software["content"]["phases"]


def test_preview_execution_request_fails_explicitly():
    snap = resolve_effective_profile([_software, _core_defaults()], schema_set=_SCHEMA_SET)
    with pytest.raises(PreviewExecutionError):
        snap.require_execution("phases")


def test_non_preview_dimension_execution_is_not_refused():
    snap = resolve_effective_profile([_software, _core_defaults()], schema_set=_SCHEMA_SET)
    # primaryCategory is not a preview-only runtime dimension.
    assert snap.require_execution("primaryCategory") is None


# ── criterion 8: domain neutrality, no CMS provider branch ────────────────

def test_two_oss_profiles_and_private_pack_resolve_through_same_public_contract():
    # Both OSS profiles and the private pack produce valid, distinct snapshots
    # through the identical resolver — there is no per-domain code branch.
    software = resolve_effective_profile([_software, _core_defaults()], schema_set=_SCHEMA_SET)
    research = resolve_effective_profile([_research, _core_defaults()], schema_set=_SCHEMA_SET)
    cms = resolve_effective_profile([_CMS_PACK, _core_defaults()], schema_set=_SCHEMA_SET)

    assert software.resolved["primaryCategory"] == "build"
    assert research.resolved["primaryCategory"] == "research"
    assert cms.resolved["primaryCategory"] == "operate"
    # The private pack's provider capability names are data, resolved without a
    # provider branch.
    assert cms.resolved["capabilities"] == {"cms_authoring": True, "text_humanization": True}


def test_resolver_source_has_no_cms_or_provider_branch():
    module_text = Path(
        _SRC / "skillweave" / "profiles" / "effective.py"
    ).read_text(encoding="utf-8")
    lowered = module_text.lower()
    for forbidden in ("cms", "element", "elementeer", "txthumanizer", "opencode", "deepseek"):
        assert forbidden not in lowered, (
            f"concrete provider/CMS token {forbidden!r} leaked into resolver"
        )


def test_sources_out_of_order_are_refused():
    # A weaker source (category pack) listed before a stronger one (domain pack)
    # is refused rather than silently re-ranked, keeping precedence explicit.
    with pytest.raises(Exception):
        resolve_effective_profile([_CMS_PACK, _software, _core_defaults()], schema_set=_SCHEMA_SET)
