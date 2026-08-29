"""Transfer catalog preview (SW1311-TRANSFER-001).

The transfer catalog carries *advisory learning observations* between
SkillWeave instances: scoped findings from the supplied research, the
2026-08-28 reports and the immutable 1.3.8 final-gate evidence, as
represented through the repository-contained learning ledger. This module is
the read-only, deterministic, provider-neutral surface over those
observations. It is deliberately dependency-light (standard library only) and
imports no optional ``skillweave.runtime`` subpackage (GLE-020).

The module is authoritative in eight ways, matching the eight acceptance
criteria:

1. **Entries are complete observations.** Every entry declares a category,
   claim, resolvable provenance artifacts, observed task/profile/harness
   scope, confidence, contraindications, limitations and a review date or
   validity window (:func:`validate_entry`).

2. **Provider-neutral by construction.** The schema and the catalog accept
   model, harness, process, review and topology observations without requiring
   concrete vendor, model or harness names. Model *tiers* (``flash``/``pro``)
   and harness capability surfaces are the vocabulary; concrete names are
   opaque adapter data only.

3. **Evidence-faithful fixture.** ``2026-08-28-dispatch-learnings.json``
   represents the supplied research, the 2026-08-28 reports (retained by
   explicit source name) and the immutable 1.3.8 final-gate evidence,
   including the single-codebase benchmark limitation, the Pro/Flash
   strengths, the observed failures, the incorrect-digest finding and the
   upheld empty-group finding. Each provenance reference is bound to a
   redacted, content-addressed evidence item whose snapshot digest is
   recomputable from the embedded content.

4. **History is never overwritten.** Superseded and contradicted observations
   remain in the catalog and stay queryable with their dates and disposition
   (:attr:`RetrievalResult.superseded`). A newer entry narrows or replaces an
   older one via ``supersedes``; the older entry is never deleted or mutated.

5. **Retrieval is advisory, never a decision.** :func:`retrieve` matches
   explicit task, risk, profile and harness context and returns
   :class:`AdvisoryObservation` values carrying provenance and limitations —
   never a routing command and never a mutable policy decision.

6. **Validation gates retrieval.** An entry missing resolvable provenance,
   observed scope or a review date/validity window fails validation and is
   excluded from retrieval (:func:`validate_catalog`,
   :func:`retrieve`). Provenance resolves by content address only when the
   declared digest is verifiable against a redacted evidence item; a bare
   asserted digest is not sufficient.

7. **Ingestion and retrieval are read-only.** The catalog cannot mutate
   profiles, model/harness policy, dispatch state, review dispositions,
   topology, integration or gates. :func:`assert_catalog_authority` fails
   closed before any such action, matching the sibling observer/reviewer
   negative-authority layers.

8. **Export is redacted by artifact policy.** :func:`export` applies an
   :class:`ArtifactPolicy` and can never expose private prompts, secrets or
   hidden reasoning; artifact content above the allowed sensitivity level is
   redacted. Restricted-field matching is normalization-aware so case and
   separator variants (``API_KEY``, ``api-key``, ``Private_Prompt``),
   compound variants that embed a restricted token (``secret_token``,
   ``api_key_token``) and nested/list forms are all redacted, while ordinary
   words that merely contain a restricted token (``secretary_name``) are not.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

# ── Vocabulary (criterion 2: provider-neutral by construction) ─────────────

#: The five observation categories. A category is a classification, never a
#: decision: ``model``, ``harness``, ``process``, ``review``, ``topology``.
CATEGORIES: frozenset[str] = frozenset(
    {"model", "harness", "process", "review", "topology"}
)

#: Confidence levels of an observation.
CONFIDENCE_VALUES: frozenset[str] = frozenset({"low", "medium", "high"})

#: Entry statuses. ``superseded`` and ``contradicted`` entries stay queryable;
#: they are never overwritten or removed (criterion 4).
STATUS_VALUES: frozenset[str] = frozenset({"active", "superseded", "contradicted"})

#: Risk levels an observation is scoped to.
RISK_VALUES: frozenset[str] = frozenset({"low", "medium", "high", "critical"})

#: Provider-neutral model capability tiers, never vendor product names.
MODEL_TIER_VALUES: frozenset[str] = frozenset({"flash", "pro"})

#: Provider-neutral harness capability surfaces, aligned with
#: ``harness-capability.schema.json``.
CAPABILITY_SURFACES: frozenset[str] = frozenset(
    {
        "native-tool",
        "external-process",
        "in-place",
        "stdin",
        "status",
        "cancel",
        "state-namespace",
        "installed-skill-digest",
    }
)

#: Artifact sensitivity levels, aligned with ``evidence.schema.json``.
SENSITIVITIES: frozenset[str] = frozenset(
    {"public", "internal", "confidential", "restricted"}
)

#: Full SHA-256 content address pattern (lowercase hex, 64 chars).
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

#: Review kind vocabulary for observed review scope.
_REVIEW_KINDS: frozenset[str] = frozenset(
    {"final_gauntlet", "cold_review", "correction", "adjudication"}
)

#: Topology modes.
_TOPOLOGY_MODES: frozenset[str] = frozenset({"worktree", "in_place", "detached"})

#: Strict ISO date pattern used by both the schema and the stdlib validator.
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

# ── Schema key vocabulary (F-04: unknown-key rejection mirrors the schema) ──

_ENTRY_KEYS: frozenset[str] = frozenset(
    {
        "entry_id",
        "category",
        "claim",
        "provenance_artifacts",
        "observed_scope",
        "confidence",
        "contraindications",
        "limitations",
        "status",
        "review_date",
        "validity_window",
        "supersedes",
        "disposition",
        "related_entry_ids",
        "metadata",
        "evidence",
    }
)

_PROVENANCE_ARTIFACT_KEYS: frozenset[str] = frozenset(
    {"artifact_path", "sha256", "source_name", "sensitivity", "evidence_id"}
)

_OBSERVED_SCOPE_KEYS: frozenset[str] = frozenset(
    {"task", "risk", "profile", "model_tiers", "harness", "process", "review", "topology"}
)

_HARNESS_KEYS: frozenset[str] = frozenset(
    {"capabilities", "names", "control_surfaces"}
)

_REVIEW_KEYS: frozenset[str] = frozenset({"kind", "reviewer_tiers"})

_TOPOLOGY_KEYS: frozenset[str] = frozenset({"mode", "parallelism"})

_VALIDITY_WINDOW_KEYS: frozenset[str] = frozenset({"start", "end"})


# ── Exceptions ──────────────────────────────────────────────────────────────


class CatalogError(Exception):
    """A transfer-catalog contract violation (raised fail-closed)."""


class CatalogValidationError(CatalogError):
    """An entry failed catalog validation (missing/invalid required facts)."""


class CatalogAuthorityError(CatalogError):
    """The catalog attempted a forbidden mutation or policy/routing action."""


class ResolutionError(CatalogError):
    """A provenance artifact could not be resolved.

    Reserved for the stable exception taxonomy: resolution failures are
    surfaced as :class:`ResolutionStatus` values on
    :class:`ProvenanceResolution` rather than raised, so retrieval can
    selectively exclude unresolved references without aborting.
    """


# ── Enums ───────────────────────────────────────────────────────────────────


class EntryCategory(str, Enum):
    """The five observation categories (criterion 1, 2)."""

    MODEL = "model"
    HARNESS = "harness"
    PROCESS = "process"
    REVIEW = "review"
    TOPOLOGY = "topology"


class Confidence(str, Enum):
    """Confidence of an observation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EntryStatus(str, Enum):
    """Entry status; superseded/contradicted stay queryable (criterion 4)."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"


class ResolutionStatus(str, Enum):
    """Provenance resolution of one artifact (criterion 6)."""

    #: The artifact file exists under the repository root and its declared
    #: content address matches (or no address was declared and the file is
    #: present). Path resolution can never escape the repository root.
    RESOLVED = "resolved"
    #: The artifact is not checked out but its content address is matched by a
    #: redacted evidence item whose snapshot digest recomputes to the declared
    #: address — resolution by verifiable content, not by bare assertion.
    RESOLVED_BY_CONTENT = "resolved_by_content"
    #: The artifact carries neither a resolvable path nor a verifiable content
    #: address (a bare digest with no matching evidence is not sufficient).
    UNRESOLVED = "unresolved"
    #: The artifact file/evidence content exists but its content address does
    #: not match the declared immutable digest — immutability is broken.
    MISMATCH = "mismatch"


# ── Immutability helpers (F-05: value immutability, no shallow aliasing) ─────

_EMPTY_MAP: Mapping[str, Any] = MappingProxyType({})


def _freeze(value: Any) -> Any:
    """Recursively deep-copy ``value`` into an immutable structure.

    Mappings become :class:`~types.MappingProxyType` wrapping a freshly built
    dict; sequences become tuples. This breaks any alias to the source object
    and makes the nested surface read-only (criterion 7 / F-05).
    """
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    """Recursively convert a frozen structure back into mutable JSON-safe data.

    Used by ``to_dict``/``export`` so a caller mutating the returned dict can
    never mutate the immutable entry it was derived from.
    """
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


# ── Strict parsing helpers (F-02/F-04: no silent coercion) ──────────────────


def _require_str(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise CatalogValidationError(
            f"{where} must be a string, got {type(value).__name__}"
        )
    return value


def _require_optional_str(value: Any, where: str) -> Optional[str]:
    if value is None:
        return None
    return _require_str(value, where)


def _require_bool(value: Any, where: str) -> bool:
    # ``bool`` is a subclass of ``int``: check it first so a numeric ``1`` is
    # rejected as a non-boolean instead of being accepted as a bool-as-number.
    if not isinstance(value, bool):
        raise CatalogValidationError(
            f"{where} must be a boolean, got {type(value).__name__}"
        )
    return value


def _require_str_list(value: Any, where: str, *, allow_none: bool = True) -> tuple[str, ...]:
    if value is None and allow_none:
        return ()
    if not isinstance(value, (list, tuple)):
        raise CatalogValidationError(
            f"{where} must be an array of strings, got {type(value).__name__}"
        )
    return tuple(_require_str(v, f"{where}[{i}]") for i, v in enumerate(value))


def _require_mapping(value: Any, where: str, *, required: bool = False) -> Optional[Mapping[str, Any]]:
    if value is None:
        if required:
            raise CatalogValidationError(f"{where} is required")
        return None
    if not isinstance(value, Mapping):
        raise CatalogValidationError(
            f"{where} must be an object, got {type(value).__name__}"
        )
    return value


def _unknown_keys(
    data: Mapping[str, Any], known: frozenset[str], where: str, into: list[str]
) -> None:
    for key in data:
        if key not in known:
            into.append(f"{where}.{key}" if where else str(key))


# ── Canonical content addressing (F-06: verifiable, deterministic digests) ──


def _canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 byte encoding of ``value`` (content addressing).

    Strings are encoded verbatim; any other value is canonicalised as compact
    sorted-key JSON, matching the sibling ``trace.contracts`` convention.
    """
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


# ── Value objects ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProvenanceArtifact:
    """One resolvable provenance artifact (criterion 1, 6).

    ``artifact_path`` is repository-relative; ``sha256`` is the immutable
    content address that keeps the artifact resolvable. ``evidence_id`` binds
    the artifact to a redacted evidence item so the digest is verifiable
    rather than a bare assertion (F-06). ``source_name`` retains the explicit
    source name (e.g. a 2026-08-28 report filename); ``sensitivity`` feeds the
    redaction policy on export (criterion 8). ``source_name``/``artifact_path``
    remain non-authoritative labels.
    """

    artifact_path: str
    sha256: str = ""
    source_name: str = ""
    sensitivity: str = "internal"
    evidence_id: str = ""
    extra_keys: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceArtifact":
        extra: list[str] = []
        _unknown_keys(data, _PROVENANCE_ARTIFACT_KEYS, "provenance_artifact", extra)
        sensitivity = _require_str(data.get("sensitivity", "internal"), "provenance_artifact.sensitivity")
        return cls(
            artifact_path=_require_str(data.get("artifact_path", ""), "provenance_artifact.artifact_path"),
            sha256=_require_str(data.get("sha256", ""), "provenance_artifact.sha256"),
            source_name=_require_str(data.get("source_name", ""), "provenance_artifact.source_name"),
            sensitivity=sensitivity,
            evidence_id=_require_str(data.get("evidence_id", ""), "provenance_artifact.evidence_id"),
            extra_keys=tuple(extra),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "artifact_path": self.artifact_path,
            "sha256": self.sha256,
        }
        if self.source_name:
            out["source_name"] = self.source_name
        if self.sensitivity:
            out["sensitivity"] = self.sensitivity
        if self.evidence_id:
            out["evidence_id"] = self.evidence_id
        return out


@dataclass(frozen=True)
class HarnessScope:
    """Observed harness scope using provider-neutral capability surfaces.

    ``names`` and ``control_surfaces`` are opaque data and never required;
    capability surfaces are the vocabulary that makes the schema accept
    harness observations without concrete harness names (criterion 2).
    """

    capabilities: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    control_surfaces: tuple[str, ...] = ()
    extra_keys: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "HarnessScope":
        if not data:
            return cls()
        extra: list[str] = []
        _unknown_keys(data, _HARNESS_KEYS, "observed_scope.harness", extra)
        return cls(
            capabilities=_require_str_list(data.get("capabilities"), "observed_scope.harness.capabilities"),
            names=_require_str_list(data.get("names"), "observed_scope.harness.names"),
            control_surfaces=_require_str_list(
                data.get("control_surfaces"), "observed_scope.harness.control_surfaces"
            ),
            extra_keys=tuple(extra),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.capabilities:
            out["capabilities"] = list(self.capabilities)
        if self.names:
            out["names"] = list(self.names)
        if self.control_surfaces:
            out["control_surfaces"] = list(self.control_surfaces)
        return out


@dataclass(frozen=True)
class ObservedScope:
    """Observed task/profile/harness scope of an entry (criterion 1).

    ``task`` and ``risk`` are required. ``profile``, ``model_tiers``,
    ``harness``, ``process``, ``review`` and ``topology`` are all optional so
    concrete vendor/model/harness names are never required (criterion 2).
    ``review`` and ``topology`` are deeply frozen to preserve value
    immutability (F-05).
    """

    task: str
    risk: str
    profile: str = ""
    model_tiers: tuple[str, ...] = ()
    harness: Optional[HarnessScope] = None
    process: str = ""
    review: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_MAP)
    topology: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_MAP)
    extra_keys: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservedScope":
        extra: list[str] = []
        _unknown_keys(data, _OBSERVED_SCOPE_KEYS, "observed_scope", extra)

        harness_data = _require_mapping(data.get("harness"), "observed_scope.harness")
        review_data = _require_mapping(data.get("review"), "observed_scope.review")
        topology_data = _require_mapping(data.get("topology"), "observed_scope.topology")

        if review_data is not None:
            _unknown_keys(review_data, _REVIEW_KEYS, "observed_scope.review", extra)
            _require_str_list(
                review_data.get("reviewer_tiers"), "observed_scope.review.reviewer_tiers"
            )
            _require_optional_str(review_data.get("kind"), "observed_scope.review.kind")
            review_frozen = _freeze(
                {k: v for k, v in review_data.items() if k in _REVIEW_KEYS}
            )
        else:
            review_frozen = _EMPTY_MAP

        if topology_data is not None:
            _unknown_keys(topology_data, _TOPOLOGY_KEYS, "observed_scope.topology", extra)
            _require_optional_str(topology_data.get("mode"), "observed_scope.topology.mode")
            parallelism = topology_data.get("parallelism")
            if parallelism is not None:
                _require_bool(parallelism, "observed_scope.topology.parallelism")
            topology_frozen = _freeze(
                {k: v for k, v in topology_data.items() if k in _TOPOLOGY_KEYS}
            )
        else:
            topology_frozen = _EMPTY_MAP

        return cls(
            task=_require_str(data.get("task", ""), "observed_scope.task"),
            risk=_require_str(data.get("risk", ""), "observed_scope.risk"),
            profile=_require_str(data.get("profile", ""), "observed_scope.profile"),
            model_tiers=_require_str_list(data.get("model_tiers"), "observed_scope.model_tiers"),
            harness=HarnessScope.from_dict(harness_data) if harness_data is not None else None,
            process=_require_str(data.get("process", ""), "observed_scope.process"),
            review=review_frozen,
            topology=topology_frozen,
            extra_keys=tuple(extra),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"task": self.task, "risk": self.risk}
        if self.profile:
            out["profile"] = self.profile
        if self.model_tiers:
            out["model_tiers"] = list(self.model_tiers)
        if self.harness is not None and self.harness.to_dict():
            out["harness"] = self.harness.to_dict()
        if self.process:
            out["process"] = self.process
        if self.review:
            out["review"] = _thaw(self.review)
        if self.topology:
            out["topology"] = _thaw(self.topology)
        return out


@dataclass(frozen=True)
class Entry:
    """One transfer-catalog observation entry (criterion 1).

    An entry declares its category, claim, resolvable provenance artifacts,
    observed scope, confidence, contraindications, limitations, status and a
    review date or validity window. ``metadata`` is free-form and is never
    exported verbatim — restricted fields (private prompts, secrets, hidden
    reasoning) are redacted by :func:`export` (criterion 8). ``metadata`` is
    deeply frozen (F-05).
    """

    entry_id: str
    category: str
    claim: str
    provenance_artifacts: tuple[ProvenanceArtifact, ...]
    observed_scope: ObservedScope
    confidence: str
    limitations: tuple[str, ...]
    contraindications: tuple[str, ...]
    status: str
    review_date: Optional[str] = None
    validity_window: Optional[Mapping[str, Any]] = None
    supersedes: Optional[str] = None
    disposition: str = ""
    related_entry_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_MAP)
    extra_keys: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Any) -> "Entry":
        if not isinstance(data, Mapping):
            raise CatalogValidationError(
                "a transfer entry must be a mapping, got " f"{type(data).__name__}"
            )
        extra: list[str] = []
        _unknown_keys(data, _ENTRY_KEYS, "entry", extra)

        scope_data = _require_mapping(data.get("observed_scope"), "observed_scope", required=True)
        scope = ObservedScope.from_dict(scope_data)  # type: ignore[arg-type]
        extra.extend(scope.extra_keys)

        artifacts_raw = data.get("provenance_artifacts")
        if not isinstance(artifacts_raw, (list, tuple)):
            raise CatalogValidationError(
                "provenance_artifacts must be an array, got "
                f"{type(artifacts_raw).__name__}"
            )
        artifacts: list[ProvenanceArtifact] = []
        for i, a in enumerate(artifacts_raw):
            amap = _require_mapping(a, f"provenance_artifacts[{i}]", required=True)
            artifact = ProvenanceArtifact.from_dict(amap)  # type: ignore[arg-type]
            if artifact.extra_keys:
                extra.extend(f"provenance_artifacts[{i}].{k[len('provenance_artifact.'):]}" for k in artifact.extra_keys)
            artifacts.append(artifact)

        review_date_raw = data.get("review_date")
        if review_date_raw is not None:
            review_date = _require_str(review_date_raw, "review_date")
        else:
            review_date = None

        validity_raw = data.get("validity_window")
        validity_window = None
        if validity_raw is not None:
            vmap = _require_mapping(validity_raw, "validity_window")
            _unknown_keys(vmap, _VALIDITY_WINDOW_KEYS, "validity_window", extra)
            start = _require_str(vmap.get("start"), "validity_window.start")
            end_raw = vmap.get("end")
            end = _require_optional_str(end_raw, "validity_window.end")
            validity_window = _freeze({"start": start, "end": end})

        supersedes_raw = data.get("supersedes")
        if supersedes_raw is not None:
            supersedes = _require_str(supersedes_raw, "supersedes")
        else:
            supersedes = None

        metadata_raw = data.get("metadata")
        if metadata_raw is not None and not isinstance(metadata_raw, Mapping):
            raise CatalogValidationError(
                f"metadata must be an object, got {type(metadata_raw).__name__}"
            )
        metadata = _freeze(dict(metadata_raw)) if metadata_raw else _EMPTY_MAP

        return cls(
            entry_id=_require_str(data.get("entry_id", ""), "entry_id"),
            category=_require_str(data.get("category", ""), "category"),
            claim=_require_str(data.get("claim", ""), "claim"),
            provenance_artifacts=tuple(artifacts),
            observed_scope=scope,
            confidence=_require_str(data.get("confidence", ""), "confidence"),
            limitations=_require_str_list(data.get("limitations"), "limitations"),
            contraindications=_require_str_list(
                data.get("contraindications"), "contraindications"
            ),
            status=_require_str(data.get("status", ""), "status"),
            review_date=review_date,
            validity_window=validity_window,
            supersedes=supersedes,
            disposition=_require_str(data.get("disposition", ""), "disposition"),
            related_entry_ids=_require_str_list(
                data.get("related_entry_ids"), "related_entry_ids"
            ),
            metadata=metadata,
            extra_keys=tuple(extra),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "entry_id": self.entry_id,
            "category": self.category,
            "claim": self.claim,
            "provenance_artifacts": [a.to_dict() for a in self.provenance_artifacts],
            "observed_scope": self.observed_scope.to_dict(),
            "confidence": self.confidence,
            "contraindications": list(self.contraindications),
            "limitations": list(self.limitations),
            "status": self.status,
        }
        if self.review_date is not None:
            out["review_date"] = self.review_date
        if self.validity_window is not None:
            out["validity_window"] = _thaw(self.validity_window)
        if self.supersedes is not None:
            out["supersedes"] = self.supersedes
        if self.disposition:
            out["disposition"] = self.disposition
        if self.related_entry_ids:
            out["related_entry_ids"] = list(self.related_entry_ids)
        if self.metadata:
            out["metadata"] = _thaw(self.metadata)
        return out


# ── Evidence store (F-06: verifiable, redacted, content-addressed) ──────────


@dataclass(frozen=True)
class EvidenceItem:
    """One redacted, content-addressed evidence snapshot (F-06).

    ``content`` is a deterministic, redacted representation of the referenced
    learning/gate evidence — it never embeds private prompts, secrets or hidden
    reasoning. ``sha256`` is the content address and must recompute to
    ``sha256(canonical(content))``; ``source_name``/``source_path`` are
    non-authoritative labels only.
    """

    evidence_id: str
    sha256: str
    content: str
    source_name: str = ""
    source_path: str = ""
    sensitivity: str = "internal"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceItem":
        evidence_id = _require_str(data.get("evidence_id", ""), "evidence.evidence_id")
        sha256 = _require_str(data.get("sha256", ""), "evidence.sha256")
        content = data.get("content", "")
        if not isinstance(content, str):
            raise CatalogValidationError(
                f"evidence.content must be a string, got {type(content).__name__}"
            )
        return cls(
            evidence_id=evidence_id,
            sha256=sha256,
            content=content,
            source_name=_require_str(data.get("source_name", ""), "evidence.source_name"),
            source_path=_require_str(data.get("source_path", ""), "evidence.source_path"),
            sensitivity=_require_str(data.get("sensitivity", "internal"), "evidence.sensitivity"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "sha256": self.sha256,
            "content": self.content,
        }
        if self.source_name:
            out["source_name"] = self.source_name
        if self.source_path:
            out["source_path"] = self.source_path
        if self.sensitivity:
            out["sensitivity"] = self.sensitivity
        return out

    def verify(self) -> bool:
        """True when the declared digest recomputes from the embedded content."""
        return self.sha256 == _sha256_hex(self.content)


@dataclass(frozen=True)
class EvidenceStore:
    """An immutable, indexed set of redacted evidence snapshots (F-06)."""

    items: tuple[EvidenceItem, ...] = ()

    @classmethod
    def empty(cls) -> "EvidenceStore":
        return cls()

    def get(self, evidence_id: str) -> Optional[EvidenceItem]:
        for item in self.items:
            if item.evidence_id == evidence_id:
                return item
        return None

    def to_dict(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.items]


# ── The immutable catalog container (criterion 7) ───────────────────────────


@dataclass(frozen=True)
class Catalog:
    """An immutable set of transfer entries with a redacted evidence store.

    ``entries`` is a tuple, so ingestion (:meth:`ingest`) returns a *new*
    catalog and never mutates this one. ``invalid`` records the raw items
    (index or entry_id) that failed to parse or validate; they stay visible
    for diagnostics but are excluded from retrieval (criterion 6).
    ``evidence`` holds the redacted, content-addressed evidence snapshots that
    make provenance references verifiable (F-06).
    """

    entries: tuple[Entry, ...] = ()
    invalid: tuple[tuple[str, tuple[str, ...]], ...] = ()
    evidence: EvidenceStore = field(default_factory=EvidenceStore.empty)

    @classmethod
    def load(cls, path: Any) -> "Catalog":
        """Load a catalog from a JSON file.

        The file is either a JSON list of entries (legacy) or an object with
        ``entries`` (list) and an optional ``evidence`` (list of evidence
        items). Parsing is lenient: items that are not mappings or that fail
        to parse structurally are recorded in ``invalid`` instead of raising.
        Semantic validation happens later via :func:`validate_catalog` and
        gates retrieval via :func:`retrieve`.
        """
        with open(os.fspath(path), encoding="utf-8") as handle:
            data = json.load(handle)

        if isinstance(data, list):
            raw_entries = data
            raw_evidence: list[dict[str, Any]] = []
        elif isinstance(data, Mapping):
            raw_entries = data.get("entries")
            raw_evidence = data.get("evidence") or []
            if not isinstance(raw_entries, list):
                raise CatalogError(
                    "a transfer catalog object must carry an 'entries' list"
                )
        else:
            raise CatalogError(
                "a transfer catalog file must contain a JSON list or an object"
            )

        entries: list[Entry] = []
        invalid: list[tuple[str, tuple[str, ...]]] = []
        for index, item in enumerate(raw_entries):
            try:
                entries.append(Entry.from_dict(item))
            except (CatalogError, ValueError, TypeError, AttributeError) as exc:
                invalid.append((f"item[{index}]", (str(exc),)))

        evidence_items: list[EvidenceItem] = []
        for index, item in enumerate(raw_evidence):
            if not isinstance(item, Mapping):
                invalid.append((f"evidence[{index}]", ("evidence item must be a mapping",)))
                continue
            try:
                ev = EvidenceItem.from_dict(item)
            except (CatalogError, ValueError, TypeError, AttributeError) as exc:
                invalid.append((f"evidence[{index}]", (str(exc),)))
                continue
            if not ev.verify():
                invalid.append(
                    (
                        ev.evidence_id or f"evidence[{index}]",
                        ("evidence digest does not match its embedded content",),
                    )
                )
                continue
            evidence_items.append(ev)

        return cls(
            entries=tuple(entries),
            invalid=tuple(invalid),
            evidence=EvidenceStore(items=tuple(evidence_items)),
        )

    def ingest(self, data: Any) -> "Catalog":
        """Return a new catalog with ``data`` appended (immutable, criterion 7).

        Ingestion is strict: an entry that fails :func:`validate_entry` raises
        :class:`CatalogValidationError` and nothing is appended.
        """
        if isinstance(data, Entry):
            entry = data
        else:
            entry = Entry.from_dict(data)
        problems = validate_entry(entry)
        if problems:
            raise CatalogValidationError(
                f"entry '{entry.entry_id or '<unnamed>'}' failed validation: "
                + "; ".join(problems)
            )
        return Catalog(
            entries=self.entries + (entry,),
            invalid=self.invalid,
            evidence=self.evidence,
        )

    def retrieve(
        self, context: "RetrievalContext", repo_root: Any = None
    ) -> "RetrievalResult":
        """Advisory retrieval against this catalog (see :func:`retrieve`)."""
        return retrieve(self, context, repo_root=repo_root)

    def __len__(self) -> int:
        return len(self.entries)


# ── Validation (criterion 1, 6) ─────────────────────────────────────────────


def _is_valid_sha256(value: str) -> bool:
    return bool(value) and bool(_SHA256_RE.match(value))


def _is_valid_calendar_date(value: Optional[str]) -> bool:
    """True for a real calendar date in YYYY-MM-DD form (F-04/calendar)."""
    if not value or not isinstance(value, str) or not _DATE_RE.match(value):
        return False
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _parse_calendar_date(value: str) -> Optional[datetime.date]:
    if not _is_valid_calendar_date(value):
        return None
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def validate_entry(entry: Entry) -> tuple[str, ...]:
    """Return the validation problems of one entry (criterion 1, 6).

    Empty result means the entry is structurally complete: category, claim,
    resolvable provenance artifacts (path + verifiable content address),
    observed task and risk scope, confidence, limitations, contraindications,
    status and a review date or validity window are all present and
    well-formed. Any problem excludes the entry from retrieval.
    """
    problems: list[str] = []
    if not entry.entry_id:
        problems.append("entry_id is required")
    if entry.category not in CATEGORIES:
        problems.append(f"category must be one of {sorted(CATEGORIES)}")
    if not entry.claim:
        problems.append("claim is required")
    if not entry.provenance_artifacts:
        problems.append("at least one provenance_artifact is required")
    seen_evidence: set[str] = set()
    for artifact in entry.provenance_artifacts:
        if not artifact.artifact_path:
            problems.append("provenance artifact artifact_path is required")
        if not _is_valid_sha256(artifact.sha256):
            problems.append(
                f"provenance artifact '{artifact.artifact_path}' must carry "
                "a 64-hex sha256 content address"
            )
        if artifact.sensitivity not in SENSITIVITIES:
            problems.append(
                f"provenance artifact '{artifact.artifact_path}' has unknown "
                f"sensitivity {artifact.sensitivity!r}"
            )
        if artifact.evidence_id and artifact.evidence_id in seen_evidence:
            problems.append(
                f"duplicate evidence reference {artifact.evidence_id!r}"
            )
        if artifact.evidence_id:
            seen_evidence.add(artifact.evidence_id)
    scope = entry.observed_scope
    if not scope.task:
        problems.append("observed_scope.task is required")
    if scope.risk not in RISK_VALUES:
        problems.append(f"observed_scope.risk must be one of {sorted(RISK_VALUES)}")
    for tier in scope.model_tiers:
        if tier not in MODEL_TIER_VALUES:
            problems.append(
                f"model_tiers values must be one of {sorted(MODEL_TIER_VALUES)}"
            )
    if scope.harness is not None:
        for capability in scope.harness.capabilities:
            if capability not in CAPABILITY_SURFACES:
                problems.append(f"unknown harness capability surface {capability!r}")
    if scope.review:
        kind = scope.review.get("kind")
        if kind and kind not in _REVIEW_KINDS:
            problems.append(f"unknown review.kind {kind!r}")
        for tier in scope.review.get("reviewer_tiers") or ():
            if tier not in MODEL_TIER_VALUES:
                problems.append(f"unknown reviewer_tier {tier!r}")
    if scope.topology:
        mode = scope.topology.get("mode")
        if mode and mode not in _TOPOLOGY_MODES:
            problems.append(f"unknown topology.mode {mode!r}")
    if entry.confidence not in CONFIDENCE_VALUES:
        problems.append(f"confidence must be one of {sorted(CONFIDENCE_VALUES)}")
    if not entry.limitations:
        problems.append("at least one limitation is required")
    if entry.status not in STATUS_VALUES:
        problems.append(f"status must be one of {sorted(STATUS_VALUES)}")
    if entry.review_date is None and entry.validity_window is None:
        problems.append("review_date or validity_window is required")
    # review_date is only constrained when it is actually provided. An entry
    # may carry a validity_window instead (criterion 1 allows either).
    if entry.review_date is not None and not _is_valid_calendar_date(entry.review_date):
        problems.append("review_date must be a valid YYYY-MM-DD calendar date")
    if entry.validity_window is not None:
        window = entry.validity_window
        start = window.get("start")
        if not _is_valid_calendar_date(start):
            problems.append("validity_window.start must be a valid YYYY-MM-DD calendar date")
        end = window.get("end")
        if end is not None and not _is_valid_calendar_date(str(end)):
            problems.append("validity_window.end must be a valid YYYY-MM-DD calendar date")
        if _is_valid_calendar_date(start) and end is not None and _is_valid_calendar_date(str(end)):
            start_d = _parse_calendar_date(start)
            end_d = _parse_calendar_date(str(end))
            if start_d is not None and end_d is not None and start_d > end_d:
                problems.append("validity_window.start must not be after validity_window.end")
    if entry.supersedes is not None and not entry.supersedes:
        problems.append("supersedes must name an entry_id")
    if entry.extra_keys:
        problems.append(
            "unknown field(s) not allowed by the schema: " + ", ".join(sorted(set(entry.extra_keys)))
        )
    return tuple(problems)


#: A validation report over a whole catalog (criterion 6).
@dataclass(frozen=True)
class ValidationReport:
    """Which entries are valid and which are excluded, with reasons.

    ``valid`` entries are eligible for retrieval. ``invalid`` maps an item
    label (``entry_id``, or ``item[index]`` for unparsable items) to its
    validation problems. Resolution problems against ``repo_root`` and
    catalog-level consistency problems (duplicate ids, supersession) are
    included when applicable.
    """

    valid: tuple[Entry, ...] = ()
    invalid: tuple[tuple[str, tuple[str, ...]], ...] = ()


def _catalog_level_problems(catalog: Catalog) -> dict[str, tuple[str, ...]]:
    """Cross-entry consistency problems keyed by entry_id (F: supersession etc.).

    Detects duplicate ``entry_id`` (all but the first deterministic occurrence
    are flagged), ``supersedes`` referencing a missing target, and supersession
    cycles. Deterministic: driven only by catalog order.
    """
    problems: dict[str, list[str]] = {}
    by_id: dict[str, Entry] = {}
    seen: set[str] = set()
    for entry in catalog.entries:
        if not entry.entry_id:
            continue
        if entry.entry_id in seen:
            problems.setdefault(entry.entry_id, []).append(
                f"duplicate entry_id {entry.entry_id!r}"
            )
            continue
        seen.add(entry.entry_id)
        by_id[entry.entry_id] = entry

    # Missing supersession targets.
    for entry in catalog.entries:
        if entry.supersedes and entry.supersedes not in by_id:
            problems.setdefault(entry.entry_id, []).append(
                f"supersedes target {entry.supersedes!r} does not exist"
            )

    # Supersession cycles (deterministic iterative depth-first traversal).
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {eid: WHITE for eid in by_id}
    on_cycle: set[str] = set()

    def _dfs(node: str) -> None:
        color[node] = GRAY
        for entry in catalog.entries:
            if entry.entry_id != node:
                continue
            target = entry.supersedes
            if target and target in by_id:
                if color[target] == GRAY:
                    on_cycle.add(node)
                    on_cycle.add(target)
                elif color[target] == WHITE:
                    _dfs(target)
        color[node] = BLACK

    for eid in list(by_id):
        if color[eid] == WHITE:
            _dfs(eid)

    for eid in on_cycle:
        problems.setdefault(eid, []).append("supersession cycle detected")

    return {eid: tuple(ps) for eid, ps in problems.items()}


def validate_catalog(catalog: Catalog, repo_root: Any = None) -> ValidationReport:
    """Validate every entry of ``catalog`` (criterion 6).

    Unparsable items recorded on the catalog are included as invalid. With a
    ``repo_root``, each valid entry is additionally required to have all its
    provenance artifacts resolve (RESOLVED or RESOLVED_BY_CONTENT against the
    evidence store). Catalog-level consistency problems (duplicate ids,
    supersession targets/cycles) are also reported.
    """
    invalid: list[tuple[str, tuple[str, ...]]] = list(catalog.invalid)
    valid: list[Entry] = []
    level_problems = _catalog_level_problems(catalog)
    for entry in catalog.entries:
        problems = list(validate_entry(entry))
        if not problems and repo_root is not None:
            status = entry_resolution_status(entry, repo_root, evidence=catalog.evidence)
            if status not in (
                ResolutionStatus.RESOLVED,
                ResolutionStatus.RESOLVED_BY_CONTENT,
            ):
                problems.append(f"provenance unresolved: {status.value}")
        if entry.entry_id in level_problems:
            problems.extend(level_problems[entry.entry_id])
        if problems:
            invalid.append((entry.entry_id or "<unnamed>", tuple(problems)))
        else:
            valid.append(entry)
    return ValidationReport(valid=tuple(valid), invalid=tuple(invalid))


# ── Provenance resolution (criterion 6) ─────────────────────────────────────


@dataclass(frozen=True)
class ProvenanceResolution:
    """The resolution of one provenance artifact against a repository root.

    ``status`` is one of :class:`ResolutionStatus`. ``actual_sha256`` is the
    measured digest when content is available (file or evidence);
    ``expected_sha256`` is the declared content address. ``note`` explains the
    outcome.
    """

    artifact_path: str
    status: ResolutionStatus
    source_name: str = ""
    expected_sha256: str = ""
    actual_sha256: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_path": self.artifact_path,
            "status": self.status.value,
            "source_name": self.source_name,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "note": self.note,
        }


def _within_root(candidate: str, root_real: str) -> bool:
    """True when the fully-resolved ``candidate`` stays within ``root_real``."""
    candidate_real = os.path.realpath(candidate)
    try:
        common = os.path.commonpath([candidate_real, root_real])
    except ValueError:
        return False
    return common == root_real


def resolve_provenance(
    artifact: ProvenanceArtifact,
    repo_root: Any = None,
    evidence: Optional[EvidenceStore] = None,
) -> ProvenanceResolution:
    """Resolve one provenance artifact (criterion 6, F-01, F-06).

    * The file exists under ``repo_root`` and its digest matches the declared
      content address (or no address was declared) -> ``RESOLVED``. Path
      resolution is confined to the repository root: a path that escapes via
      ``..``, an absolute path or a symlink is ``UNRESOLVED`` fail-closed.
    * The file is not present but the artifact references an evidence item
      whose snapshot digest matches -> ``RESOLVED_BY_CONTENT`` (verified
      content, not a bare assertion).
    * The artifact's declared digest differs from the available file/evidence
      content, or the evidence reference is missing/unmatched -> ``MISMATCH``.
    * Otherwise -> ``UNRESOLVED``.
    """
    base = ProvenanceResolution(
        artifact_path=artifact.artifact_path,
        status=ResolutionStatus.UNRESOLVED,
        source_name=artifact.source_name,
        expected_sha256=artifact.sha256,
    )
    if not artifact.artifact_path:
        return base

    # 1. Try resolving the file under repo_root, confined to the root.
    if repo_root is not None:
        root_real = os.path.realpath(os.fspath(repo_root))
        candidate = os.path.join(os.fspath(repo_root), artifact.artifact_path)
        if _within_root(candidate, root_real):
            if os.path.isfile(candidate):
                actual = _file_sha256(candidate)
                if artifact.sha256 and actual != artifact.sha256:
                    return ProvenanceResolution(
                        artifact_path=artifact.artifact_path,
                        status=ResolutionStatus.MISMATCH,
                        source_name=artifact.source_name,
                        expected_sha256=artifact.sha256,
                        actual_sha256=actual,
                        note="file digest differs from the declared content address",
                    )
                return ProvenanceResolution(
                    artifact_path=artifact.artifact_path,
                    status=ResolutionStatus.RESOLVED,
                    source_name=artifact.source_name,
                    expected_sha256=artifact.sha256,
                    actual_sha256=actual,
                    note="file resolved and content address verified",
                )
        else:
            return ProvenanceResolution(
                artifact_path=artifact.artifact_path,
                status=ResolutionStatus.UNRESOLVED,
                source_name=artifact.source_name,
                expected_sha256=artifact.sha256,
                note="artifact path escapes the repository root",
            )

    # 2. Verify against the evidence store (content-addressed, F-06).
    if artifact.evidence_id and evidence is not None:
        item = evidence.get(artifact.evidence_id)
        if item is None:
            return ProvenanceResolution(
                artifact_path=artifact.artifact_path,
                status=ResolutionStatus.UNRESOLVED,
                source_name=artifact.source_name,
                expected_sha256=artifact.sha256,
                note="evidence reference does not exist in the evidence store",
            )
        if not item.verify():
            return ProvenanceResolution(
                artifact_path=artifact.artifact_path,
                status=ResolutionStatus.MISMATCH,
                source_name=artifact.source_name,
                expected_sha256=artifact.sha256,
                actual_sha256=_sha256_hex(item.content),
                note="evidence digest does not match its embedded content",
            )
        item_digest = item.sha256
        if artifact.sha256 and artifact.sha256 != item_digest:
            return ProvenanceResolution(
                artifact_path=artifact.artifact_path,
                status=ResolutionStatus.MISMATCH,
                source_name=artifact.source_name,
                expected_sha256=artifact.sha256,
                actual_sha256=item_digest,
                note="declared digest differs from the evidence snapshot digest",
            )
        return ProvenanceResolution(
            artifact_path=artifact.artifact_path,
            status=ResolutionStatus.RESOLVED_BY_CONTENT,
            source_name=artifact.source_name,
            expected_sha256=artifact.sha256,
            actual_sha256=item_digest,
            note="artifact resolved by verifiable evidence content",
        )

    # 3. A bare, asserted digest without a verifiable evidence reference is not
    # sufficient provenance (F-06): it cannot be verified, so it is unresolved.
    if _is_valid_sha256(artifact.sha256):
        return ProvenanceResolution(
            artifact_path=artifact.artifact_path,
            status=ResolutionStatus.UNRESOLVED,
            source_name=artifact.source_name,
            expected_sha256=artifact.sha256,
            note="bare digest without an evidence reference is not verifiable",
        )
    return base


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def entry_resolution_status(
    entry: Entry, repo_root: Any = None, evidence: Optional[EvidenceStore] = None
) -> ResolutionStatus:
    """The worst resolution status across an entry's artifacts (criterion 6).

    Only entries whose every artifact resolves (RESOLVED or
    RESOLVED_BY_CONTENT) are eligible for retrieval.
    """
    if not entry.provenance_artifacts:
        return ResolutionStatus.UNRESOLVED
    statuses = [
        resolve_provenance(artifact, repo_root, evidence).status
        for artifact in entry.provenance_artifacts
    ]
    if ResolutionStatus.MISMATCH in statuses:
        return ResolutionStatus.MISMATCH
    if ResolutionStatus.UNRESOLVED in statuses:
        return ResolutionStatus.UNRESOLVED
    if ResolutionStatus.RESOLVED in statuses:
        return ResolutionStatus.RESOLVED
    return ResolutionStatus.RESOLVED_BY_CONTENT


# ── Contextual retrieval (criterion 5) ──────────────────────────────────────


@dataclass(frozen=True)
class RetrievalContext:
    """The explicit retrieval context: task, risk, profile, harness.

    ``task`` and ``risk`` are required; ``profile`` and ``harness`` are
    optional. ``harness`` is an opaque harness label that may name a concrete
    harness or a capability surface.
    """

    task: str
    risk: str
    profile: str = ""
    harness: str = ""

    def __post_init__(self) -> None:
        if not self.task:
            raise CatalogError("retrieval context requires an explicit task")
        if self.risk not in RISK_VALUES:
            raise CatalogError(
                f"retrieval context risk must be one of {sorted(RISK_VALUES)}"
            )


@dataclass(frozen=True)
class AdvisoryObservation:
    """One advisory observation returned by :func:`retrieve` (criterion 5).

    Carries the entry's claim, category, confidence, observed scope,
    limitations, contraindications, review date/validity and the resolved
    provenance. It is *advisory only*: it carries no routing command, no
    allocation tier decision and no mutable policy value. Superseded and
    contradicted observations are returned with their ``status`` and
    ``disposition`` intact (criterion 4).
    """

    entry_id: str
    category: str
    claim: str
    confidence: str
    status: str
    observed_scope: ObservedScope
    limitations: tuple[str, ...]
    contraindications: tuple[str, ...]
    provenance: tuple[ProvenanceResolution, ...]
    review_date: Optional[str] = None
    validity_window: Optional[Mapping[str, Any]] = None
    disposition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "category": self.category,
            "claim": self.claim,
            "confidence": self.confidence,
            "status": self.status,
            "observed_scope": self.observed_scope.to_dict(),
            "limitations": list(self.limitations),
            "contraindications": list(self.contraindications),
            "provenance": [p.to_dict() for p in self.provenance],
            "review_date": self.review_date,
            "validity_window": (
                _thaw(self.validity_window) if self.validity_window else None
            ),
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class RetrievalResult:
    """The advisory retrieval result (criterion 4, 5).

    ``advisory`` holds the matching active observations. ``superseded`` holds
    the matching superseded/contradicted observations with their disposition
    intact, so conflicting history stays queryable. Results preserve catalog
    order and are deterministic.
    """

    advisory: tuple[AdvisoryObservation, ...] = ()
    superseded: tuple[AdvisoryObservation, ...] = ()

    @property
    def total(self) -> int:
        return len(self.advisory) + len(self.superseded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "advisory": [o.to_dict() for o in self.advisory],
            "superseded": [o.to_dict() for o in self.superseded],
        }


def _scope_matches(scope: ObservedScope, context: RetrievalContext) -> bool:
    """Deterministic scope match against the retrieval context (criterion 5).

    A scope dimension that is empty on the entry matches any context value; a
    scoped entry requires an equal context value. A harness-scoped entry
    requires the context harness to be one of its names, capability surfaces
    or control surfaces.
    """
    if scope.task and scope.task != context.task:
        return False
    if scope.risk and scope.risk != context.risk:
        return False
    if scope.profile and scope.profile != context.profile:
        return False
    if scope.harness is not None and (
        scope.harness.names
        or scope.harness.capabilities
        or scope.harness.control_surfaces
    ):
        if not context.harness:
            return False
        if scope.harness.names and context.harness in scope.harness.names:
            return True
        if scope.harness.capabilities and context.harness in scope.harness.capabilities:
            return True
        if (
            scope.harness.control_surfaces
            and context.harness in scope.harness.control_surfaces
        ):
            return True
        return False
    return True


def retrieve(
    catalog: Catalog,
    context: RetrievalContext,
    repo_root: Any = None,
) -> RetrievalResult:
    """Retrieve advisory observations matching ``context`` (criterion 5).

    Only entries that pass :func:`validate_entry`, whose provenance all
    resolves (criterion 6) and which carry no catalog-level consistency
    problem are eligible. Matching is deterministic and returns
    :class:`AdvisoryObservation` values — advisory observations with
    provenance and limitations, never a routing command or a policy decision.
    """
    advisory: list[AdvisoryObservation] = []
    superseded: list[AdvisoryObservation] = []
    level_problems = _catalog_level_problems(catalog)
    for entry in catalog.entries:
        if validate_entry(entry):
            continue
        if entry.entry_id in level_problems:
            continue
        if entry_resolution_status(entry, repo_root, evidence=catalog.evidence) not in (
            ResolutionStatus.RESOLVED,
            ResolutionStatus.RESOLVED_BY_CONTENT,
        ):
            continue
        if not _scope_matches(entry.observed_scope, context):
            continue
        observation = AdvisoryObservation(
            entry_id=entry.entry_id,
            category=entry.category,
            claim=entry.claim,
            confidence=entry.confidence,
            status=entry.status,
            observed_scope=entry.observed_scope,
            limitations=entry.limitations,
            contraindications=entry.contraindications,
            provenance=tuple(
                resolve_provenance(a, repo_root, catalog.evidence)
                for a in entry.provenance_artifacts
            ),
            review_date=entry.review_date,
            validity_window=entry.validity_window,
            disposition=entry.disposition,
        )
        if entry.status == EntryStatus.ACTIVE.value:
            advisory.append(observation)
        else:
            superseded.append(observation)
    return RetrievalResult(advisory=tuple(advisory), superseded=tuple(superseded))


# ── Negative authority (criterion 7) ────────────────────────────────────────


#: Actions the transfer catalog may never perform. The catalog is read-only
#: with respect to every mutable SkillWeave surface: profiles, model/harness
#: policy, dispatch state, review dispositions, topology, integration and
#: gates.
CATALOG_FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {
        "mutate",
        "write",
        "commit",
        "push",
        "merge",
        "release",
        "tag",
        "routing",
        "dispatch",
        "profile",
        "model_policy",
        "harness_policy",
        "review_disposition",
        "integration",
        "topology",
        "gate",
        "policy",
    }
)


def assert_catalog_authority(action: str) -> None:
    """Fail closed before any forbidden catalog action (criterion 7).

    Ingestion and retrieval are pure read operations; they may never mutate
    profiles, model/harness policy, dispatch state, review dispositions,
    topology, integration or gates. Mirrors the observer/reviewer negative
    authority layers.
    """
    if action in CATALOG_FORBIDDEN_ACTIONS:
        raise CatalogAuthorityError(
            f"the transfer catalog is read-only and may not {action}: "
            "ingestion and retrieval never mutate profiles, model/harness "
            "policy, dispatch state, review dispositions, topology, "
            "integration or gates"
        )


# ── Redacted export (criterion 8) ───────────────────────────────────────────


#: Fields whose normalized content export must never expose, regardless of
#: policy. Field names are normalized (lowercase, separators removed) before
#: comparison so ``API_KEY``, ``api-key`` and ``api_key`` all match (F-03).
DEFAULT_RESTRICTED_FIELDS: frozenset[str] = frozenset(
    {
        "private_prompt",
        "hidden_reasoning",
        "secret",
        "api_key",
        "token",
        "chain_of_thought",
    }
)

#: Sensitivities allowed by the default artifact policy.
DEFAULT_ALLOWED_SENSITIVITIES: frozenset[str] = frozenset({"public", "internal"})


def _normalize_field_name(name: str) -> str:
    """Normalize a field name for restricted-field matching (F-03).

    Lowercases and strips every non-alphanumeric character so case and
    separator variants (``API_KEY``, ``api-key``, ``api.key``, ``api key``)
    compare equal.
    """
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _field_name_tokens(name: str) -> tuple[str, ...]:
    """Split a field name into lowercase semantic words.

    Separators and camelCase boundaries are treated as word boundaries so
    ``private_prompt``, ``Private_Prompt``, ``PRIVATE-PROMPT`` and
    ``privatePrompt`` all yield ``("private", "prompt")``. A word that merely
    *contains* a restricted token (``secretary``) stays one token and never
    matches the standalone ``secret`` token.
    """
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))
    words = re.split(r"[^a-zA-Z0-9]+", s)
    return tuple(w.lower() for w in words if w)


def _contains_word_sequence(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    """True when ``needle`` appears as a contiguous subsequence of ``haystack``."""
    if not needle:
        return True
    if len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(
        haystack[i : i + width] == needle
        for i in range(len(haystack) - width + 1)
    )


@dataclass(frozen=True)
class ArtifactPolicy:
    """The redaction policy applied by :func:`export` (criterion 8).

    Artifacts whose ``sensitivity`` is not in ``allowed_sensitivities`` have
    their content redacted. Any field whose *normalized* name matches a
    restricted field (top-level, nested inside ``metadata``, or inside any
    list) is replaced with ``redaction_token``. Private prompts, secrets and
    hidden reasoning can therefore never be exported.
    """

    allowed_sensitivities: frozenset[str] = DEFAULT_ALLOWED_SENSITIVITIES
    restricted_fields: frozenset[str] = DEFAULT_RESTRICTED_FIELDS
    redaction_token: str = "***REDACTED***"

    def is_restricted(self, name: Any) -> bool:
        normalized = _normalize_field_name(name)
        tokens = _field_name_tokens(name)
        for restricted in self.restricted_fields:
            # Exact normalized equality preserves the single-token forms such as
            # ``api_key``/``apikey`` and ``hidden reason ing``/``hiddenreasoning``.
            if normalized == _normalize_field_name(restricted):
                return True
            # Compound/case/separator variants are redacted when they contain a
            # restricted token or a restricted token *sequence* as distinct
            # words. This catches ``secret_token``, ``api_key_token`` and
            # ``apiKeyNested`` while never matching ``secretary_name``.
            if _contains_word_sequence(tokens, _field_name_tokens(restricted)):
                return True
        return False


#: The top-level entry fields an export may carry (schema order).
_EXPORT_FIELDS: tuple[str, ...] = (
    "entry_id",
    "category",
    "claim",
    "provenance_artifacts",
    "observed_scope",
    "confidence",
    "contraindications",
    "limitations",
    "status",
    "review_date",
    "validity_window",
    "supersedes",
    "disposition",
    "related_entry_ids",
    "metadata",
)


def _redact_artifact(
    artifact: Mapping[str, Any], policy: ArtifactPolicy
) -> dict[str, Any]:
    sensitivity = str(artifact.get("sensitivity", "internal"))
    if sensitivity not in policy.allowed_sensitivities:
        return {
            "redacted": True,
            "sensitivity": sensitivity,
            "source_name": policy.redaction_token,
        }
    return dict(artifact)


def _redact_nested(value: Any, policy: ArtifactPolicy) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (
                policy.redaction_token
                if policy.is_restricted(key)
                else _redact_nested(item, policy)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_nested(item, policy) for item in value]
    return value


def export(
    entries: Sequence[Entry],
    policy: Optional[ArtifactPolicy] = None,
    *,
    fields: Optional[Sequence[str]] = None,
) -> tuple[dict[str, Any], ...]:
    """Export entries as JSON-safe dicts under an artifact policy (criterion 8).

    Applies ``policy`` (default :class:`ArtifactPolicy`): artifact content
    whose sensitivity exceeds ``allowed_sensitivities`` is redacted, and any
    restricted field (private prompts, secrets, hidden reasoning) — top-level
    or nested inside ``metadata`` or lists — is replaced with the redaction
    token. Matching is normalization-aware (F-03). Deterministic and
    provider-neutral.
    """
    policy = policy or ArtifactPolicy()
    allowed_fields = tuple(fields) if fields is not None else _EXPORT_FIELDS
    exported: list[dict[str, Any]] = []
    for entry in entries:
        data = entry.to_dict()
        out: dict[str, Any] = {}
        for name in allowed_fields:
            if name not in data:
                continue
            if policy.is_restricted(name):
                out[name] = policy.redaction_token
            elif name == "provenance_artifacts":
                out[name] = [_redact_artifact(a, policy) for a in data[name]]
            elif name == "metadata" and isinstance(data[name], Mapping):
                out[name] = _redact_nested(data[name], policy)
            else:
                out[name] = data[name]
        exported.append(out)
    return tuple(exported)


__all__ = [
    "CATEGORIES",
    "CONFIDENCE_VALUES",
    "STATUS_VALUES",
    "RISK_VALUES",
    "MODEL_TIER_VALUES",
    "CAPABILITY_SURFACES",
    "SENSITIVITIES",
    "CatalogError",
    "CatalogValidationError",
    "CatalogAuthorityError",
    "ResolutionError",
    "EntryCategory",
    "Confidence",
    "EntryStatus",
    "ResolutionStatus",
    "ProvenanceArtifact",
    "HarnessScope",
    "ObservedScope",
    "Entry",
    "EvidenceItem",
    "EvidenceStore",
    "Catalog",
    "validate_entry",
    "ValidationReport",
    "validate_catalog",
    "ProvenanceResolution",
    "resolve_provenance",
    "entry_resolution_status",
    "RetrievalContext",
    "AdvisoryObservation",
    "RetrievalResult",
    "retrieve",
    "CATALOG_FORBIDDEN_ACTIONS",
    "assert_catalog_authority",
    "DEFAULT_RESTRICTED_FIELDS",
    "DEFAULT_ALLOWED_SENSITIVITIES",
    "ArtifactPolicy",
    "export",
]
