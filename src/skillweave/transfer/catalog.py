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
   upheld empty-group finding.

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
   :func:`retrieve`).

7. **Ingestion and retrieval are read-only.** The catalog cannot mutate
   profiles, model/harness policy, dispatch state, review dispositions,
   topology, integration or gates. :func:`assert_catalog_authority` fails
   closed before any such action, matching the sibling observer/reviewer
   negative-authority layers.

8. **Export is redacted by artifact policy.** :func:`export` applies an
   :class:`ArtifactPolicy` and can never expose private prompts, secrets or
   hidden reasoning; artifact content above the allowed sensitivity level is
   redacted.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
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


# ── Exceptions ──────────────────────────────────────────────────────────────


class CatalogError(Exception):
    """A transfer-catalog contract violation (raised fail-closed)."""


class CatalogValidationError(CatalogError):
    """An entry failed catalog validation (missing/invalid required facts)."""


class CatalogAuthorityError(CatalogError):
    """The catalog attempted a forbidden mutation or policy/routing action."""


class ResolutionError(CatalogError):
    """A provenance artifact could not be resolved."""


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
    #: present).
    RESOLVED = "resolved"
    #: The artifact is not checked out but its sha256 content address is a
    #: valid, immutable resolver — resolution by content address.
    RESOLVED_BY_CONTENT = "resolved_by_content"
    #: The artifact carries neither a resolvable path nor a content address.
    UNRESOLVED = "unresolved"
    #: The artifact file exists but its content address does not match the
    #: declared immutable digest — immutability is broken.
    MISMATCH = "mismatch"


# ── Value objects ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProvenanceArtifact:
    """One resolvable provenance artifact (criterion 1, 6).

    ``artifact_path`` is repository-relative. ``sha256`` is the immutable
    content address that keeps the artifact resolvable even when the file is
    not checked out. ``source_name`` retains the explicit source name
    (e.g. a 2026-08-28 report filename); ``sensitivity`` feeds the redaction
    policy on export (criterion 8).
    """

    artifact_path: str
    sha256: str = ""
    source_name: str = ""
    sensitivity: str = "internal"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceArtifact":
        return cls(
            artifact_path=str(data.get("artifact_path", "")),
            sha256=str(data.get("sha256", "")),
            source_name=str(data.get("source_name", "")),
            sensitivity=str(data.get("sensitivity", "internal")),
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

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "HarnessScope":
        if not data:
            return cls()
        return cls(
            capabilities=tuple(str(v) for v in (data.get("capabilities") or ())),
            names=tuple(str(v) for v in (data.get("names") or ())),
            control_surfaces=tuple(
                str(v) for v in (data.get("control_surfaces") or ())
            ),
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
    """

    task: str
    risk: str
    profile: str = ""
    model_tiers: tuple[str, ...] = ()
    harness: Optional[HarnessScope] = None
    process: str = ""
    review: Mapping[str, Any] = field(default_factory=dict)
    topology: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservedScope":
        return cls(
            task=str(data.get("task", "")),
            risk=str(data.get("risk", "")),
            profile=str(data.get("profile", "")),
            model_tiers=tuple(str(v) for v in (data.get("model_tiers") or ())),
            harness=HarnessScope.from_dict(data.get("harness")),
            process=str(data.get("process", "")),
            review=dict(data.get("review") or {}),
            topology=dict(data.get("topology") or {}),
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
            out["review"] = dict(self.review)
        if self.topology:
            out["topology"] = dict(self.topology)
        return out


@dataclass(frozen=True)
class Entry:
    """One transfer-catalog observation entry (criterion 1).

    An entry declares its category, claim, resolvable provenance artifacts,
    observed scope, confidence, contraindications, limitations, status and a
    review date or validity window. ``metadata`` is free-form and is never
    exported verbatim — restricted fields (private prompts, secrets, hidden
    reasoning) are redacted by :func:`export` (criterion 8).
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
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> "Entry":
        if not isinstance(data, Mapping):
            raise CatalogError(
                "a transfer entry must be a mapping, got " f"{type(data).__name__}"
            )
        scope_data = data.get("observed_scope")
        scope = (
            ObservedScope.from_dict(scope_data)
            if isinstance(scope_data, Mapping)
            else ObservedScope(task="", risk="")
        )
        artifacts = tuple(
            ProvenanceArtifact.from_dict(a)
            for a in data.get("provenance_artifacts") or ()
        )
        validity = data.get("validity_window")
        return cls(
            entry_id=str(data.get("entry_id", "")),
            category=str(data.get("category", "")),
            claim=str(data.get("claim", "")),
            provenance_artifacts=artifacts,
            observed_scope=scope,
            confidence=str(data.get("confidence", "")),
            limitations=tuple(str(v) for v in (data.get("limitations") or ())),
            contraindications=tuple(
                str(v) for v in (data.get("contraindications") or ())
            ),
            status=str(data.get("status", "")),
            review_date=(str(data["review_date"]) if data.get("review_date") else None),
            validity_window=(dict(validity) if isinstance(validity, Mapping) else None),
            supersedes=(str(data["supersedes"]) if data.get("supersedes") else None),
            disposition=str(data.get("disposition", "")),
            related_entry_ids=tuple(
                str(v) for v in (data.get("related_entry_ids") or ())
            ),
            metadata=dict(data.get("metadata") or {}),
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
            out["validity_window"] = dict(self.validity_window)
        if self.supersedes is not None:
            out["supersedes"] = self.supersedes
        if self.disposition:
            out["disposition"] = self.disposition
        if self.related_entry_ids:
            out["related_entry_ids"] = list(self.related_entry_ids)
        if self.metadata:
            out["metadata"] = dict(self.metadata)
        return out


# ── The immutable catalog container (criterion 7) ───────────────────────────


@dataclass(frozen=True)
class Catalog:
    """An immutable set of transfer entries.

    ``entries`` is a tuple, so ingestion (:meth:`ingest`) returns a *new*
    catalog and never mutates this one. ``invalid`` records the raw items
    (index or entry_id) that failed to parse or validate; they stay visible
    for diagnostics but are excluded from retrieval (criterion 6).
    """

    entries: tuple[Entry, ...] = ()
    invalid: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @classmethod
    def load(cls, path: Any) -> "Catalog":
        """Load a catalog from a JSON file containing a list of entries.

        Parsing is lenient: items that are not mappings are recorded in
        ``invalid`` instead of raising. Semantic validation happens later via
        :func:`validate_catalog` and gates retrieval via :func:`retrieve`.
        """
        import os

        with open(os.fspath(path), encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            raise CatalogError("a transfer catalog file must contain a JSON list")
        entries: list[Entry] = []
        invalid: list[tuple[str, tuple[str, ...]]] = []
        for index, item in enumerate(data):
            try:
                entries.append(Entry.from_dict(item))
            except CatalogError as exc:  # non-mapping item
                invalid.append((f"item[{index}]", (str(exc),)))
        return cls(entries=tuple(entries), invalid=tuple(invalid))

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


def _is_valid_date(value: Optional[str]) -> bool:
    return bool(value) and bool(_DATE_RE.match(value))


def validate_entry(entry: Entry) -> tuple[str, ...]:
    """Return the validation problems of one entry (criterion 1, 6).

    Empty result means the entry is structurally complete: category, claim,
    resolvable provenance artifacts (path + content address), observed task
    and risk scope, confidence, limitations, contraindications, status and a
    review date or validity window are all present and well-formed. Any
    problem excludes the entry from retrieval.
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
    if entry.review_date is not None and not _is_valid_date(entry.review_date):
        problems.append("review_date must be YYYY-MM-DD")
    if entry.validity_window is not None:
        window = entry.validity_window
        if not _is_valid_date(window.get("start")):
            problems.append("validity_window.start must be YYYY-MM-DD")
        end = window.get("end")
        if end is not None and not _is_valid_date(str(end)):
            problems.append("validity_window.end must be YYYY-MM-DD")
    if entry.supersedes is not None and not entry.supersedes:
        problems.append("supersedes must name an entry_id")
    return tuple(problems)


#: A validation report over a whole catalog (criterion 6).
@dataclass(frozen=True)
class ValidationReport:
    """Which entries are valid and which are excluded, with reasons.

    ``valid`` entries are eligible for retrieval. ``invalid`` maps an item
    label (``entry_id``, or ``item[index]`` for unparsable items) to its
    validation problems. Resolution problems against ``repo_root`` are
    included when a repo root was supplied.
    """

    valid: tuple[Entry, ...] = ()
    invalid: tuple[tuple[str, tuple[str, ...]], ...] = ()


def validate_catalog(catalog: Catalog, repo_root: Any = None) -> ValidationReport:
    """Validate every entry of ``catalog`` (criterion 6).

    Unparsable items recorded on the catalog are included as invalid. With a
    ``repo_root``, each valid entry is additionally required to have all its
    provenance artifacts resolve (RESOLVED or RESOLVED_BY_CONTENT).
    """
    invalid: list[tuple[str, tuple[str, ...]]] = list(catalog.invalid)
    valid: list[Entry] = []
    for entry in catalog.entries:
        problems = list(validate_entry(entry))
        if not problems and repo_root is not None:
            status = entry_resolution_status(entry, repo_root)
            if status not in (
                ResolutionStatus.RESOLVED,
                ResolutionStatus.RESOLVED_BY_CONTENT,
            ):
                problems.append(f"provenance unresolved: {status.value}")
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
    measured file digest when the file exists; ``expected_sha256`` is the
    declared content address. ``note`` explains the outcome.
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


def resolve_provenance(
    artifact: ProvenanceArtifact, repo_root: Any = None
) -> ProvenanceResolution:
    """Resolve one provenance artifact (criterion 6).

    * The file exists under ``repo_root`` and its digest matches the declared
      content address (or no address was declared) -> ``RESOLVED``.
    * The file exists but its digest differs -> ``MISMATCH`` (immutability
      broken).
    * The file is not checked out but the artifact carries a valid content
      address -> ``RESOLVED_BY_CONTENT``.
    * Otherwise -> ``UNRESOLVED``.
    """
    import os

    base = ProvenanceResolution(
        artifact_path=artifact.artifact_path,
        status=ResolutionStatus.UNRESOLVED,
        source_name=artifact.source_name,
        expected_sha256=artifact.sha256,
    )
    if not artifact.artifact_path:
        return base
    target = None
    if repo_root is not None:
        candidate = os.path.join(os.fspath(repo_root), artifact.artifact_path)
        if os.path.isfile(candidate):
            target = candidate
    if target is not None:
        actual = _file_sha256(target)
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
    if _is_valid_sha256(artifact.sha256):
        return ProvenanceResolution(
            artifact_path=artifact.artifact_path,
            status=ResolutionStatus.RESOLVED_BY_CONTENT,
            source_name=artifact.source_name,
            expected_sha256=artifact.sha256,
            note="artifact not checked out; resolved by content address",
        )
    return base


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def entry_resolution_status(entry: Entry, repo_root: Any = None) -> ResolutionStatus:
    """The worst resolution status across an entry's artifacts (criterion 6).

    Only entries whose every artifact resolves (RESOLVED or
    RESOLVED_BY_CONTENT) are eligible for retrieval.
    """
    if not entry.provenance_artifacts:
        return ResolutionStatus.UNRESOLVED
    statuses = [
        resolve_provenance(artifact, repo_root).status
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
                dict(self.validity_window) if self.validity_window else None
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

    Only entries that pass :func:`validate_entry` and whose provenance all
    resolves (criterion 6) are eligible. Matching is deterministic and returns
    :class:`AdvisoryObservation` values — advisory observations with
    provenance and limitations, never a routing command or a policy decision.
    """
    advisory: list[AdvisoryObservation] = []
    superseded: list[AdvisoryObservation] = []
    for entry in catalog.entries:
        if validate_entry(entry):
            continue
        if entry_resolution_status(entry, repo_root) not in (
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
                resolve_provenance(a, repo_root) for a in entry.provenance_artifacts
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


#: Fields whose content export must never expose, regardless of policy.
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


@dataclass(frozen=True)
class ArtifactPolicy:
    """The redaction policy applied by :func:`export` (criterion 8).

    Artifacts whose ``sensitivity`` is not in ``allowed_sensitivities`` have
    their content redacted. Any field whose name is in ``restricted_fields``
    (top-level or nested inside ``metadata``) is replaced with
    ``redaction_token``. Private prompts, secrets and hidden reasoning can
    therefore never be exported.
    """

    allowed_sensitivities: frozenset[str] = DEFAULT_ALLOWED_SENSITIVITIES
    restricted_fields: frozenset[str] = DEFAULT_RESTRICTED_FIELDS
    redaction_token: str = "***REDACTED***"


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
                if key in policy.restricted_fields
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
    or nested inside ``metadata`` — is replaced with the redaction token.
    Deterministic and provider-neutral.
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
            if name in policy.restricted_fields:
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
