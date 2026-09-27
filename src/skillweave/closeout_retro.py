"""Closeout → retrospective handoff (SW-157-CLOSE-003).

The closeout service (:mod:`skillweave.closeout_service`) decides whether a run
may be declared closed. This module is what happens *afterwards*: the retro
lane that turns a closeout into an evidence-linked retrospective, syncs that
retrospective into the durable ``.skillweave/retrospectives/`` area (which the
planning-sync contract then carries to the org planning repository), and hands
the planning lane a deduplicated set of backlog candidates.

Two disciplines carry over from the exit door, and both are structural.

1. **Evidence links, not adjectives.** A :class:`Metric` is a number *about* a
   named upstream artifact, and it is only constructible with at least one
   :attr:`EvidenceLink` whose digest is a canonical sha256. A metric with no
   link is a malformed metric: :meth:`CloseoutRetro.record_metric` refuses it.
   Numbers that cannot be traced back to a receipt are not metrics.

2. **Narrative alone cannot close a finding.** Every finding opens by default.
   :class:`FindingDisposition` moves a finding to CLOSED **only** when it
   carries at least one evidence link, and every link must be one this run has
   already recorded. A disposition whose ``narrative`` is persuasive but whose
   ``evidence`` is empty — the "it's fine, trust me" shape — is refused, and the
   finding stays :data:`STATUS_OPEN`. This is the machine proof Step B asks for:
   prose is not a resolution.

Durability
----------

A retrospective is a *generated, durable, sealed* area: the persistence layer
already declares ``retrospectives`` as such, and the planning-sync backing store
already carries it. This module produces the payload that contract expects — a
digest-sealed :class:`RetrospectiveReceipt` for machines and a
``vX.Y.Z.md`` document for humans — and writes both, via an explicit
:class:`RetroWriter`. No method here reaches for a global; the caller supplies
the writer, so the retro lane is as load-bearing-free as the exit door.

Nothing in this module merges, tags, releases or removes a workspace. It plans;
other lanes act.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence

from skillweave.assessment_service import ReadOnlyViolation

__all__ = [
    "SCHEMA_VERSION",
    "FILENAME_VERSION",
    "STATUS_OPEN",
    "STATUS_CLOSED",
    "FindingSource",
    "MetricKind",
    "EvidenceLink",
    "Metric",
    "Finding",
    "FindingDisposition",
    "BacklogCandidate",
    "RetrospectiveReceipt",
    "CloseoutRetroError",
    "CloseoutRetro",
    "RetroWriter",
    "DuplicationKind",
]


SCHEMA_VERSION = 1
FILENAME_VERSION = 1

#: A finding that has not been resolved by evidence.
STATUS_OPEN = "open"
#: A finding resolved by evidence (never by narrative alone).
STATUS_CLOSED = "closed"

#: Canonical lowercase full 40-hex SHA — the run subject.
_FULL_SHA = re.compile(r"^[0-9a-f]{40}\Z")
#: Canonical lowercase sha256 — a receipt/artifact address.
_SHA256 = re.compile(r"^[a-f0-9]{64}\Z")
#: Control characters stripped from every human-readable field before digesting,
#: so a crafted retro item cannot forge receipt structure in a log line.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class CloseoutRetroError(ValueError):
    """A retro request is malformed and cannot be represented."""


# --------------------------------------------------------------------------- #
# Finite vocabularies
# --------------------------------------------------------------------------- #


class FindingSource(str, Enum):
    """Where a retrospective finding came from."""

    CLOSEOUT = "closeout"
    TELEMETRY = "telemetry"
    RETRO = "retro"


class MetricKind(str, Enum):
    """The finite set of evidence-linked metric kinds this lane emits."""

    BLOCKER_COUNT = "blocker_count"
    EVIDENCE_PRESENT = "evidence_present"
    EVIDENCE_MISSING = "evidence_missing"
    EVIDENCE_MISMATCHED = "evidence_mismatched"
    FINDING_COUNT = "finding_count"


class DuplicationKind(str, Enum):
    """How a backlog candidate duplicates one already accepted."""

    EXACT = "exact"
    FUZZY = "fuzzy"


# --------------------------------------------------------------------------- #
# Canonical JSON / digesting — the same convention the closeout service uses
# --------------------------------------------------------------------------- #


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _clean(value: str) -> str:
    return _CONTROL_CHARS.sub(" ", str(value))


# --------------------------------------------------------------------------- #
# Evidence links and metrics
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EvidenceLink:
    """A pointer from a retro claim back to a concrete upstream receipt.

    ``digest`` is the receipt/content address the claim is licensed by; ``source``
    names the lane that produced it. A link with a non-canonical digest is not a
    link — it cannot be constructed.
    """

    source: str
    digest: str
    kind: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise CloseoutRetroError("an evidence link must name its source")
        if not isinstance(self.digest, str) or not _SHA256.match(self.digest):
            raise CloseoutRetroError(
                "an evidence link must carry a canonical lowercase sha256 digest, "
                f"got {self.digest!r}"
            )

    def as_dict(self) -> dict:
        return {
            "source": _clean(self.source),
            "kind": _clean(self.kind),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class Metric:
    """A quantity about a named upstream artifact, tied to its evidence.

    The link set is not optional and not decorative: :meth:`__post_init__`
    refuses a metric with no links, so "0 blockers" and "3 blockers" are equally
    traceable to the receipts that say so. A metric that cannot be traced is a
    rumour.
    """

    kind: MetricKind
    subject: str
    value: int
    evidence: tuple[EvidenceLink, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise CloseoutRetroError(
                f"metric {self.kind!r} for {self.subject!r} carries no evidence "
                "link; an untraceable number is not a metric"
            )
        if not all(isinstance(link, EvidenceLink) for link in self.evidence):
            raise CloseoutRetroError(
                "every metric evidence entry must be an EvidenceLink"
            )
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise CloseoutRetroError(f"metric value must be an int, got {self.value!r}")
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise CloseoutRetroError("a metric must name its subject")

    @property
    def digests(self) -> tuple[str, ...]:
        return tuple(sorted({link.digest for link in self.evidence}))

    def as_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "subject": _clean(self.subject),
            "value": self.value,
            "evidence": [link.as_dict() for link in self.evidence],
        }


# --------------------------------------------------------------------------- #
# Findings and their dispositions (Step B: narrative cannot close)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Finding:
    """An observation that opens unresolved until evidence resolves it."""

    finding_id: str
    source: FindingSource
    summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.finding_id, str) or not self.finding_id.strip():
            raise CloseoutRetroError("a finding must carry a non-empty finding_id")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise CloseoutRetroError(
                f"finding {self.finding_id!r} must carry a non-empty summary"
            )

    def as_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "source": self.source.value,
            "summary": _clean(self.summary),
        }


@dataclass(frozen=True)
class FindingDisposition:
    """How a finding was resolved — and the evidence that licensed it.

    A disposition is constructible in two shapes, and only two:

    * **OPEN**, with no evidence and any narrative. Nothing is resolved; the
      narrative is a note.
    * **CLOSED**, which demands at least one :class:`EvidenceLink`.

    There is no third shape. A CLOSED disposition with an empty ``evidence``
    tuple cannot be constructed at all — so "the narrative convinced me" has no
    representation, and :meth:`CloseoutRetro.close_finding` is a second gate
    that the links it is given are already recorded.
    """

    finding_id: str
    status: str
    narrative: str = ""
    evidence: tuple[EvidenceLink, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in (STATUS_OPEN, STATUS_CLOSED):
            raise CloseoutRetroError(
                f"disposition status must be {STATUS_OPEN!r} or {STATUS_CLOSED!r}, "
                f"got {self.status!r}"
            )
        if not isinstance(self.evidence, tuple):
            raise CloseoutRetroError("disposition evidence must be a tuple of links")
        if self.status == STATUS_CLOSED and not self.evidence:
            raise CloseoutRetroError(
                f"cannot close finding {self.finding_id!r} on narrative alone: a "
                "closed disposition must carry at least one evidence link"
            )
        if not all(isinstance(link, EvidenceLink) for link in self.evidence):
            raise CloseoutRetroError(
                "every disposition evidence entry must be an EvidenceLink"
            )

    @property
    def is_closed(self) -> bool:
        return self.status == STATUS_CLOSED

    @property
    def digests(self) -> tuple[str, ...]:
        return tuple(sorted({link.digest for link in self.evidence}))

    def as_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "status": self.status,
            "narrative": _clean(self.narrative),
            "evidence": [link.as_dict() for link in self.evidence],
        }


# --------------------------------------------------------------------------- #
# Backlog candidates (deduplicated)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BacklogCandidate:
    """A deduplicated unit of follow-up work proposed by the retro.

    Identity is content: the ``key`` is derived from the source and the
    normalised description, so two candidates that say the same thing collide on
    purpose. ``duplicate_of`` records the accepted candidate it was folded into,
    which is how a plan can show *what it dropped* rather than silently merge.
    """

    source: str
    description: str
    effort: str = "medium"
    urgency: str = "medium"
    key: str = ""
    duplicate_of: str = ""
    duplication: str = ""

    EFFORT_ORDER = {"small": 1, "medium": 2, "large": 3}
    URGENCY_ORDER = {"high": 3, "medium": 2, "low": 1}

    def __post_init__(self) -> None:
        if self.effort not in self.EFFORT_ORDER:
            raise CloseoutRetroError(f"invalid effort: {self.effort!r}")
        if self.urgency not in self.URGENCY_ORDER:
            raise CloseoutRetroError(f"invalid urgency: {self.urgency!r}")
        if not self.description.strip():
            raise CloseoutRetroError("a backlog candidate needs a description")
        if not self.key:
            object.__setattr__(self, "key", _candidate_key(self.source, self.description))

    @property
    def priority_score(self) -> float:
        """The plan_iteration score: urgency over effort, higher is sooner."""
        return self.URGENCY_ORDER[self.urgency] / self.EFFORT_ORDER[self.effort]

    def as_dict(self) -> dict:
        return {
            "source": _clean(self.source),
            "description": _clean(self.description),
            "effort": self.effort,
            "urgency": self.urgency,
            "key": self.key,
            "duplicate_of": self.duplicate_of,
            "duplication": self.duplication,
        }


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def _candidate_key(source: str, description: str) -> str:
    payload = f"{_normalise(source)}\x00{_normalise(description)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# The durable receipt
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RetrospectiveReceipt:
    """The digest-sealed machine artifact of one retrospective.

    ``digest`` covers everything above it, so a receipt verifies on another
    machine and a tampered field no longer verifies. ``document`` is the same
    content rendered for humans (the ``vX.Y.Z.md`` payload the planning-sync
    contract carries); ``document_digest`` binds the two together, so the prose
    a human reads is the prose the receipt underwrote.
    """

    schema_version: int
    run_id: str
    subject: str
    release: str
    status: str
    metrics: tuple[dict, ...]
    findings: tuple[dict, ...]
    candidates: tuple[dict, ...]
    document: str
    document_digest: str
    digest: str = ""

    def payload(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "subject": self.subject,
            "release": self.release,
            "status": self.status,
            "metrics": [dict(entry) for entry in self.metrics],
            "findings": [dict(entry) for entry in self.findings],
            "candidates": [dict(entry) for entry in self.candidates],
            "document_digest": self.document_digest,
        }

    def to_dict(self) -> dict:
        payload = self.payload()
        payload["digest"] = self.digest
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def verify_receipt(receipt: Any) -> bool:
    """True when ``receipt`` still digests to its own recorded ``digest``."""
    payload = receipt.payload() if hasattr(receipt, "payload") else None
    recorded = getattr(receipt, "digest", None)
    if not isinstance(payload, Mapping) or not isinstance(recorded, str):
        return False
    return _digest(payload) == recorded


# --------------------------------------------------------------------------- #
# The writer seam
# --------------------------------------------------------------------------- #


class RetroWriter:
    """Writes the two durable artifacts of a retrospective, read-only elsewhere.

    A writer is deliberately the *only* mutating seam in this module, and it is
    injected rather than imported so the retro lane never reaches for a global
    filesystem. Its surface is closed: write the receipt, write the document.
    There is no delete, move or release method on it.
    """

    def __init__(self, root: str, *, authority: Optional[Any] = None) -> None:
        if authority is not None and getattr(authority, "read_only", False):
            raise ReadOnlyViolation(
                "a RetroWriter needs a write authority; a read-only authority "
                "cannot persist a retrospective"
            )
        self._root = str(root)

    @property
    def root(self) -> str:
        return self._root

    def write_receipt(self, receipt: RetrospectiveReceipt, *, run_id: str) -> str:
        """Persist the sealed receipt; return its path. Subclasses/vcs decide how."""
        raise NotImplementedError

    def write_document(self, document: str, *, release: str, subject: str) -> str:
        """Persist the human document (``vX.Y.Z.md``); return its path."""
        raise NotImplementedError

    def sync(self, area: str) -> Any:
        """Carry the durable area to its backing store; return the sync report."""
        raise NotImplementedError


class InMemoryRetroWriter(RetroWriter):
    """A deterministic, filesystem-free writer for tests and dry runs."""

    def __init__(self) -> None:
        super().__init__("memory://")
        self.receipts: dict[str, RetrospectiveReceipt] = {}
        self.documents: dict[str, str] = {}
        self.synced: list[str] = []

    def write_receipt(self, receipt: RetrospectiveReceipt, *, run_id: str) -> str:
        self.receipts[run_id] = receipt
        return f"memory://retrospectives/{run_id}.json"

    def write_document(self, document: str, *, release: str, subject: str) -> str:
        name = f"v{release}.md"
        self.documents[name] = document
        return f"memory://retrospectives/{name}"

    def sync(self, area: str) -> Any:
        self.synced.append(area)
        return {"area": area, "carried": sorted(self.documents), "at_risk": False}


# --------------------------------------------------------------------------- #
# The service
# --------------------------------------------------------------------------- #

#: The durable area a retrospective belongs to. Matches the persistence
#: declaration (GENERATED, DURABLE, SEALED) and the planning-sync area name.
RETRO_AREA = "retrospectives"


class CloseoutRetro:
    """Turn a closeout's outcome into an evidence-linked, durable retrospective.

    Accumulate :class:`Metric` objects and :class:`Finding` objects, close the
    findings that evidence licenses, then :meth:`handoff` to plan the iteration
    and sync the durable area. The accumulation is pure and read-only; only
    :meth:`handoff` — through the injected :class:`RetroWriter` — touches
    anything.
    """

    def __init__(
        self,
        *,
        run_id: str,
        subject: str,
        release: str = "",
        writer: Optional[RetroWriter] = None,
    ) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise CloseoutRetroError(f"run_id must be a non-empty string, got {run_id!r}")
        if not isinstance(subject, str) or not _FULL_SHA.match(subject):
            raise CloseoutRetroError(
                "subject is not a canonical lowercase full 40-hex SHA: "
                f"{subject!r}"
            )
        self._run_id = run_id
        self._subject = subject
        self._release = release
        self._writer = writer
        self._metrics: list[Metric] = []
        self._findings: dict[str, Finding] = {}
        self._dispositions: dict[str, FindingDisposition] = {}
        self._recorded: set[str] = set()

    # ── properties ───────────────────────────────────────────────────────

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def subject(self) -> str:
        return self._subject

    @property
    def recorded_digests(self) -> tuple[str, ...]:
        """Every evidence digest this run has seen, sorted."""
        return tuple(sorted(self._recorded))

    # ── Step A: evidence-linked metrics ──────────────────────────────────

    def record_metric(
        self, kind: MetricKind, subject: str, value: int, evidence: Sequence[EvidenceLink]
    ) -> Metric:
        """Record a metric. Refuses any metric without at least one link."""
        links = tuple(evidence)
        if not links:
            raise CloseoutRetroError(
                f"metric {kind!r} for {subject!r} carries no evidence link; "
                "numbers must be traceable to the receipts that license them"
            )
        metric = Metric(kind=kind, subject=subject, value=value, evidence=links)
        self._metrics.append(metric)
        self._recorded.update(metric.digests)
        return metric

    def metrics_from_closeout(self, preview: Any) -> tuple[Metric, ...]:
        """Derive evidence-linked metrics from a closeout preview.

        Reads the public shape of :class:`~skillweave.closeout_service.CloseoutPreview`
        by attribute only, so this lane never imports the exit door and the two
        stay independently loadable. Every evidence row's ``note`` is *not*
        evidence — the link is the preview digest, which addresses the whole
        finding set, plus the per-row status which the preview itself decided.
        """
        preview_digest = getattr(preview, "digest", None)
        if not isinstance(preview_digest, str) or not _SHA256.match(preview_digest):
            raise CloseoutRetroError(
                "cannot derive metrics: closeout preview carries no verifiable "
                "digest"
            )
        blockers = tuple(getattr(preview, "blockers", ()) or ())
        evidence = tuple(getattr(preview, "evidence", ()) or ())

        link = EvidenceLink(source="closeout", digest=preview_digest, kind="preview")
        produced: list[Metric] = [
            self.record_metric(
                MetricKind.BLOCKER_COUNT, self._run_id, len(blockers), [link]
            )
        ]
        for status in ("present", "missing", "mismatched"):
            count = sum(
                1 for row in evidence if _row_status(row) == status
            )
            kind = {
                "present": MetricKind.EVIDENCE_PRESENT,
                "missing": MetricKind.EVIDENCE_MISSING,
                "mismatched": MetricKind.EVIDENCE_MISMATCHED,
            }[status]
            produced.append(
                self.record_metric(kind, self._run_id, count, [link])
            )
        return tuple(produced)

    # ── Step B: findings cannot close on narrative ───────────────────────

    def open_finding(self, finding: Finding) -> Finding:
        """Register a finding in the OPEN state. Opening needs no evidence."""
        if finding.finding_id in self._findings:
            raise CloseoutRetroError(
                f"finding {finding.finding_id!r} is already open"
            )
        self._findings[finding.finding_id] = finding
        self._dispositions[finding.finding_id] = FindingDisposition(
            finding_id=finding.finding_id, status=STATUS_OPEN
        )
        return finding

    def close_finding(
        self, finding_id: str, evidence: Sequence[EvidenceLink], narrative: str = ""
    ) -> FindingDisposition:
        """Resolve a finding — only with evidence already recorded this run.

        Two gates stand between narrative and closure:

        1. :class:`FindingDisposition` refuses a CLOSED disposition with no
           links (so the shape is unrepresentable).
        2. Every link supplied here must address evidence this run has already
           recorded. A plausible-looking digest that no metric ever produced is
           not a resolution; it is a fabricated citation, and it is refused.
        """
        if finding_id not in self._findings:
            raise CloseoutRetroError(f"no such finding: {finding_id!r}")
        links = tuple(evidence)
        if not links:
            raise CloseoutRetroError(
                f"cannot close finding {finding_id!r} on narrative alone: "
                "closing requires evidence"
            )
        unrecorded = sorted(
            link.digest for link in links if link.digest not in self._recorded
        )
        if unrecorded:
            raise CloseoutRetroError(
                f"cannot close finding {finding_id!r} on unrecorded evidence: "
                f"{unrecorded}; a resolution must cite evidence this run produced"
            )
        disposition = FindingDisposition(
            finding_id=finding_id,
            status=STATUS_CLOSED,
            narrative=narrative,
            evidence=links,
        )
        self._dispositions[finding_id] = disposition
        return disposition

    @property
    def open_findings(self) -> tuple[Finding, ...]:
        return tuple(
            finding
            for fid, finding in self._findings.items()
            if not self._dispositions[fid].is_closed
        )

    def disposition(self, finding_id: str) -> FindingDisposition:
        try:
            return self._dispositions[finding_id]
        except KeyError:
            raise CloseoutRetroError(f"no such finding: {finding_id!r}") from None

    # ── Step A: deduplicated backlog candidates ──────────────────────────

    def backlog_candidates(
        self,
        candidates: Iterable[BacklogCandidate],
        *,
        existing: Iterable[BacklogCandidate] = (),
        fuzzy_threshold: float = 0.85,
    ) -> tuple[BacklogCandidate, ...]:
        """Deduplicate candidates against each other and against ``existing``.

        Exact duplicates (identical key) are folded first. Near-duplicates —
        the same work described in different words — are folded by a
        :class:`difflib.SequenceMatcher` ratio over the normalised description,
        the same 0.85 default the repo-health file dedup uses. The survivor
        keeps its place; each dropped candidate records which accepted key it
        was folded into, so a plan shows what it merged rather than losing it.
        """
        accepted: list[BacklogCandidate] = list(existing)
        result: list[BacklogCandidate] = []
        for candidate in candidates:
            dup_of, kind = _find_duplicate(
                candidate, accepted, fuzzy_threshold=fuzzy_threshold
            )
            if dup_of is not None:
                result.append(
                    BacklogCandidate(
                        source=candidate.source,
                        description=candidate.description,
                        effort=candidate.effort,
                        urgency=candidate.urgency,
                        key=candidate.key,
                        duplicate_of=dup_of,
                        duplication=kind,
                    )
                )
                continue
            accepted.append(candidate)
            result.append(candidate)

        # Stable order: the plan_iteration score, then key, so a plan is
        # reproducible regardless of input order.
        return tuple(
            sorted(result, key=lambda c: (-c.priority_score, c.key))
        )

    def candidates_from_findings(
        self, *, source: str = "retro"
    ) -> tuple[BacklogCandidate, ...]:
        """Propose one backlog candidate per still-open finding.

        Only OPEN findings become work. A finding resolved by evidence is not
        re-raised, which is what makes closing a finding *mean* something to the
        next iteration.
        """
        return tuple(
            BacklogCandidate(
                source=source,
                description=f"resolve {finding.finding_id}: {finding.summary}",
                urgency="high" if finding.source is FindingSource.CLOSEOUT else "medium",
            )
            for finding in self.open_findings
        )

    # ── Step A: durable handoff ──────────────────────────────────────────

    def render_document(
        self,
        *,
        dispositions: Optional[Mapping[str, FindingDisposition]] = None,
        candidates: Sequence[BacklogCandidate] = (),
    ) -> str:
        """Render the human retrospective document deterministically."""
        lines: list[str] = []
        title = f"# Retrospective {self._release}".rstrip()
        lines.append(title)
        lines.append("")
        lines.append(f"- run: `{self._run_id}`")
        lines.append(f"- subject: `{self._subject}`")
        lines.append("")

        lines.append("## Metrics")
        lines.append("")
        lines.append("| Kind | Subject | Value | Evidence |")
        lines.append("|------|---------|-------|----------|")
        for metric in self._metrics:
            links = ", ".join(f"`{d[:12]}`" for d in metric.digests)
            lines.append(
                f"| {metric.kind.value} | {_clean(metric.subject)} | "
                f"{metric.value} | {links} |"
            )
        lines.append("")

        lines.append("## Findings")
        lines.append("")
        known = dispositions or self._dispositions
        for fid in sorted(self._findings):
            finding = self._findings[fid]
            disp = known.get(fid, FindingDisposition(finding_id=fid, status=STATUS_OPEN))
            mark = "x" if disp.is_closed else " "
            suffix = (
                " — resolved by " + ", ".join(f"`{d[:12]}`" for d in disp.digests)
                if disp.is_closed
                else " — open"
            )
            lines.append(f"- [{mark}] {finding.finding_id}: {_clean(finding.summary)}{suffix}")
        lines.append("")

        if candidates:
            lines.append("## Backlog Candidates")
            lines.append("")
            lines.append("| Score | Source | Description | Effort | Urgency | Duplicate Of |")
            lines.append("|-------|--------|-------------|--------|---------|--------------|")
            for candidate in candidates:
                dup = candidate.duplicate_of[:12] if candidate.duplicate_of else "-"
                tag = f" ({candidate.duplication})" if candidate.duplication else ""
                lines.append(
                    f"| {candidate.priority_score:.2f} | {candidate.source} | "
                    f"{_clean(candidate.description)} | {candidate.effort} | "
                    f"{candidate.urgency} | {dup}{tag} |"
                )
            lines.append("")

        return "\n".join(lines)

    def handoff(
        self,
        *,
        dispositions: Optional[Mapping[str, FindingDisposition]] = None,
        candidates: Sequence[BacklogCandidate] = (),
        writer: Optional[RetroWriter] = None,
    ) -> RetrospectiveReceipt:
        """Seal the retrospective, persist it, and sync its durable area.

        The receipt is built first and digested; only then is anything written.
        The writer is required — there is no default that reaches for a global —
        and the durable area is synced through that writer's own ``sync``, so a
        failed sync is reported by the backing store, not swallowed here.
        """
        active_writer = writer or self._writer
        if active_writer is None:
            raise CloseoutRetroError(
                "a handoff needs a RetroWriter; the retro lane does not persist "
                "through an implicit global"
            )

        known = dict(self._dispositions)
        if dispositions:
            known.update(dispositions)

        document = self.render_document(dispositions=known, candidates=candidates)
        document_digest = hashlib.sha256(document.encode("utf-8")).hexdigest()

        findings_payload = tuple(
            {
                **self._findings[fid].as_dict(),
                "status": known.get(
                    fid, FindingDisposition(finding_id=fid, status=STATUS_OPEN)
                ).status,
            }
            for fid in sorted(self._findings)
        )

        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self._run_id,
            "subject": self._subject,
            "release": self._release,
            "status": _rolled_up_status(known),
            "metrics": [metric.as_dict() for metric in self._metrics],
            "findings": list(findings_payload),
            "candidates": [candidate.as_dict() for candidate in candidates],
            "document_digest": document_digest,
        }
        receipt = RetrospectiveReceipt(
            schema_version=SCHEMA_VERSION,
            run_id=self._run_id,
            subject=self._subject,
            release=self._release,
            status=payload["status"],
            metrics=tuple(payload["metrics"]),
            findings=tuple(payload["findings"]),
            candidates=tuple(payload["candidates"]),
            document=document,
            document_digest=document_digest,
            digest=_digest(payload),
        )

        active_writer.write_receipt(receipt, run_id=self._run_id)
        active_writer.write_document(document, release=self._release, subject=self._subject)
        active_writer.sync(RETRO_AREA)
        return receipt


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _row_status(row: Any) -> str:
    """The ``status`` of one closeout evidence row, as a plain string."""
    if isinstance(row, Mapping):
        value = row.get("status")
    else:
        value = getattr(row, "status", None)
    return getattr(value, "value", value) or ""


def _rolled_up_status(dispositions: Mapping[str, FindingDisposition]) -> str:
    """CLOSED only when every finding is resolved; otherwise OPEN."""
    if dispositions and all(d.is_closed for d in dispositions.values()):
        return STATUS_CLOSED
    return STATUS_OPEN


def _find_duplicate(
    candidate: BacklogCandidate,
    accepted: Sequence[BacklogCandidate],
    *,
    fuzzy_threshold: float,
) -> tuple[Optional[str], str]:
    """The accepted key ``candidate`` duplicates, plus how. ``(None, "")`` if new."""
    from difflib import SequenceMatcher

    target = _normalise(candidate.description)
    fuzzy_match: Optional[str] = None
    for existing in accepted:
        if existing.key == candidate.key:
            return existing.key, DuplicationKind.EXACT.value
        if fuzzy_match is None and target:
            ratio = SequenceMatcher(
                None, target, _normalise(existing.description)
            ).ratio()
            if ratio >= fuzzy_threshold:
                fuzzy_match = existing.key
    if fuzzy_match is not None:
        return fuzzy_match, DuplicationKind.FUZZY.value
    return None, ""
