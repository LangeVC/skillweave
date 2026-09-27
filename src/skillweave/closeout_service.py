"""Closeout service — the read-only exit door (SW-157-CLOSE-001).

A closeout decides one thing: may this run be declared *closed*? It is the
consumer of every upstream artifact the SW-157 family produces — assessment
receipts, launch receipts, workspace inventory, and intervention telemetry —
and it is the **only** place where those artifacts are allowed to block.

Three disciplines, in deliberate order
--------------------------------------

1. **Deterministic preview precedes authority.** :meth:`CloseoutService.preview`
   is total, pure, and read-only: it touches no filesystem, no git, and no
   clock, and identical inputs always yield a byte-identical preview whose
   ``digest`` identifies it. It can be produced, published and reviewed
   *before* anyone with authority is asked anything. Only
   :meth:`CloseoutService.decide` reads a frozen judgement — the
   :class:`CloseoutDecision` — and maps it additively onto the preview.

2. **Blocked closes are explicit.** Every reason a closeout cannot be declared
   closed is a member of :class:`Hold`, carries a finite ``code``, and names a
   :class:`Boundary`. There is no "warning" tier and no silent downgrade: a
   hold is a hold.

3. **The exit door owns no cleanup.** The service carries a
   :class:`ReadOnlyAuthority` (the same capability shape the assessment service
   uses) and refuses to be constructed with any other. Every action goes through
   ``assert_readable``; the mutating action is that authority's standing refusal.
   Closeout *decides*; the workspace cleanup lane *acts* — and only ever under
   its own explicit authorization. Nothing here removes, archives, moves or
   releases a workspace.

Evidence: missing is not mismatched
-----------------------------------

The two ways evidence can fail are kept strictly apart, because they demand
different human responses:

* ``missing`` — the artifact was never supplied (``None``), or an assessment
  receipt carries no usable evidence. The remedy is to produce it.
* ``mismatched`` — the artifact *is* supplied and self-inconsistent: a
  launch receipt whose digest does not match its own content, or whose
  ``result``/``outcome`` pairing is self-contradictory (verified through the
  launch contract's own ``canonicalize``, never re-implemented here). The
  remedy is to re-run the producer, because something is wrong upstream.

A tampered launch receipt is therefore *not* "missing evidence" — it is
mismatched evidence, and it blocks CLOSED on its own.

Workspace holds
---------------

Given a :class:`~skillweave.repo_health.worktrees.WorkspaceInventory`, the
service blocks the closeout when the run's workspaces are not in a state that
can be walked away from:

============  ===========================================================
State         Hold raised
============  ===========================================================
dirty         the worktree has uncommitted changes
leased        the workspace lease is still active (owned)
active        live process or fresh session evidence remains
unclassified  classification is ``unknown`` or ``healthy`` for a
              **managed** row, so its safety facts were never established
unknown       any safety dimension is explicitly ``unknown``
============  ===========================================================

Two asymmetries are deliberate:

* ``healthy`` is *not* considered a classified disposal state. The only
  classifications already judged adverse are ``stale`` and ``orphaned`` — the
  same pair the cleanup lane is allowed to act on. A healthy workspace that no
  one removed is a loose end, not a completed closeout, so it is held as
  ``UNCLASSIFIED`` rather than waved through.
* An **unmanaged** row (no manifest at all) is not held merely for lacking a
  lease. Absent ownership records are the normal shape of a workspace this run
  never claimed; classifying it is still required, but its absent lease is not
  itself a hold.

Authority boundaries (machine-checked)
--------------------------------------

:data:`AUTHORITY_BOUNDARIES` declares which lanes may act on a closeout and
which are explicitly out of scope; :meth:`CloseoutService.authority_for` is the
machine test of that table. The separations it pins:

* ``releasechain`` is the sole lane that may tag, release or merge — a closeout
  never publishes anything.
* ``closeout`` may declare a run closed, and nothing else.
* ``launch`` supplies the receipt; it is not consulted for closure.
* ``repo_health``/cleanup may remove workspaces, but only under its own
  authorization — a closeout never routes an instruction to it. The closeout's
  workspace verdict is that the state is *intact*; removal is a separate act.

Determinism
-----------

No method reads the clock, the filesystem or git. Timestamps are supplied
(``produced_at``), digests are computed over canonical JSON, and previews are
compared by digest, so a preview produced on one machine verifies on another.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, List, Mapping, Optional, Sequence

from skillweave import assessment_service as _assess_mod
from skillweave import launch as _launch_mod
from skillweave.assessment_service import ReadOnlyViolation
from skillweave.launch import (
    OUTCOME_SUCCESS,
    LaunchReceiptError,
    canonicalize as _canonicalize_launch,
)

__all__ = [
    "SCHEMA_VERSION",
    "PREVIEW_VERSION",
    "STATUS_CLOSED",
    "STATUS_HELD",
    "RESULT_AVAILABLE",
    "RESULT_UNAVAILABLE",
    "EvidenceKind",
    "EvidenceStatus",
    "Boundary",
    "Hold",
    "WorkspaceSignal",
    "Blocker",
    "CloseoutDecision",
    "CloseoutPreview",
    "BlockerPreview",
    "CloseoutReceipt",
    "CloseoutService",
    "AUTHORITY_BOUNDARIES",
    "ReadOnlyViolation",
    "is_closed",
    "tampered_launch_receipt",
    "missing_evidence",
]


# --------------------------------------------------------------------------- #
# Schema constants
# --------------------------------------------------------------------------- #

SCHEMA_VERSION = 1
PREVIEW_VERSION = 1

STATUS_CLOSED = "closed"
STATUS_HELD = "held"

RESULT_AVAILABLE = "available"
RESULT_UNAVAILABLE = "unavailable"

#: Canonical lowercase full 40-hex SHA. Mirrors the assessment contract's own
#: subject pattern; `\Z` anchors the true end of string so a trailing newline
#: cannot ride along inside an identity claim.
_FULL_SHA = re.compile(r"^[0-9a-f]{40}\Z")

#: Canonical lowercase sha256, the receipt/content address.
_SHA256 = re.compile(r"^[a-f0-9]{64}\Z")

#: The control-characters stripped from every human-readable note before a
#: preview is digested. Notes are echoed into receipts and logs; newlines and
#: ESC sequences would let a crafted upstream artifact forge receipt structure.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

# The classifications a workspace must reach before a closeout may walk away.
# Deliberately the same pair the cleanup lane treats as already-adverse.
ADVERSE_CLASSIFICATIONS = frozenset({"stale", "orphaned"})


# --------------------------------------------------------------------------- #
# Authority boundaries — declared here, machine-tested by authority_for()
# --------------------------------------------------------------------------- #

#: Which lane may do what around a closeout. ``may`` is what the lane is
#: authorized to perform; ``must_not`` is what it is structurally denied. The
#: table is the single source of truth for the boundary tests in
#: ``tests/integration/test_closeout_service.py``.
AUTHORITY_BOUNDARIES: Mapping[str, Mapping[str, Any]] = {
    "releasechain": {
        "may": ("tag", "release", "publish", "merge", "sign"),
        "must_not": ("close_run",),
    },
    "closeout": {
        "may": ("close_run", "hold_run"),
        # A closeout states that cleanup *would* be allowed; it never performs
        # it, and it never authorizes an identity on the cleanup lane's behalf.
        "must_not": ("cleanup", "remove_workspace", "tag", "release", "merge"),
    },
    "launch": {
        "may": ("deploy", "health_check", "rollback"),
        "must_not": ("close_run", "cleanup"),
    },
    "repo_health": {
        "may": ("inventory", "classify", "cleanup"),
        "must_not": ("close_run", "tag", "release"),
    },
}


# --------------------------------------------------------------------------- #
# Finite vocabularies
# --------------------------------------------------------------------------- #


class EvidenceKind(str, Enum):
    """The kinds of upstream evidence a closeout consumes."""

    ASSESSMENT = "assessment"
    LAUNCH = "launch"
    WORKSPACES = "workspaces"
    TELEMETRY = "telemetry"


class EvidenceStatus(str, Enum):
    """Whether a named evidence input actually arrived."""

    PRESENT = "present"
    MISSING = "missing"
    MISMATCHED = "mismatched"


class Boundary(str, Enum):
    """The lane a hold belongs to, and therefore who can clear it."""

    RELEASECHAIN = "releasechain"
    LAUNCH = "launch"
    REPO_HEALTH = "repo_health"
    CLOSEOUT = "closeout"


class Hold(str, Enum):
    """Every reason a closeout is refused. Members are the finite reason set.

    Each member's value is its stable ``code``; the set is closed, so a reason
    outside it is a programming error rather than a new state.
    """

    EVIDENCE_MISSING = "evidence_missing"
    EVIDENCE_MISMATCHED = "evidence_mismatched"
    ASSESSMENT_UNAVAILABLE = "assessment_unavailable"
    ASSESSMENT_NO_EVIDENCE = "assessment_no_evidence"
    LAUNCH_UNVERIFIED = "launch_unverified"
    LAUNCH_UNSUCCESSFUL = "launch_unsuccessful"
    WORKSPACE_DIRTY = "workspace_dirty"
    WORKSPACE_LEASED = "workspace_leased"
    WORKSPACE_ACTIVE = "workspace_active"
    WORKSPACE_UNCLASSIFIED = "workspace_unclassified"
    WORKSPACE_EVIDENCE_UNKNOWN = "workspace_evidence_unknown"
    TELEMETRY_UNAVAILABLE = "telemetry_unavailable"
    UNFINISHED_ITEMS = "unfinished_items"
    AUTHORITY_MISMATCH = "authority_mismatch"


#: Every hold's boundary, exhaustively. A :class:`Hold` absent from this table
#: cannot be constructed into a blocker at runtime (``_blocker`` raises), which
#: is what keeps "every hold names a lane" a property rather than a convention.
HOLD_BOUNDARIES: Mapping[Hold, Boundary] = {
    Hold.EVIDENCE_MISSING: Boundary.CLOSEOUT,
    Hold.EVIDENCE_MISMATCHED: Boundary.CLOSEOUT,
    Hold.ASSESSMENT_UNAVAILABLE: Boundary.RELEASECHAIN,
    Hold.ASSESSMENT_NO_EVIDENCE: Boundary.RELEASECHAIN,
    Hold.LAUNCH_UNVERIFIED: Boundary.LAUNCH,
    Hold.LAUNCH_UNSUCCESSFUL: Boundary.LAUNCH,
    Hold.WORKSPACE_DIRTY: Boundary.REPO_HEALTH,
    Hold.WORKSPACE_LEASED: Boundary.REPO_HEALTH,
    Hold.WORKSPACE_ACTIVE: Boundary.REPO_HEALTH,
    Hold.WORKSPACE_UNCLASSIFIED: Boundary.REPO_HEALTH,
    Hold.WORKSPACE_EVIDENCE_UNKNOWN: Boundary.REPO_HEALTH,
    Hold.TELEMETRY_UNAVAILABLE: Boundary.CLOSEOUT,
    Hold.UNFINISHED_ITEMS: Boundary.CLOSEOUT,
    Hold.AUTHORITY_MISMATCH: Boundary.CLOSEOUT,
}

#: Holds that can only be cleared by a lane other than closeout itself.
EXTERNAL_BOUNDARIES = frozenset(
    (Boundary.RELEASECHAIN, Boundary.LAUNCH, Boundary.REPO_HEALTH)
)


def _held(cls: Any) -> bool:
    """True when ``cls`` is a workspace classification the closeout cannot walk away from."""
    value = getattr(cls, "value", cls)
    return value not in ADVERSE_CLASSIFICATIONS


def _state_value(value: Any) -> str:
    """The plain string of an enum member/state, whatever carried it."""
    return getattr(value, "value", value)


def _enum_of(enum_cls: Any, value: Any) -> Any:
    """Coerce ``value`` to ``enum_cls``; ``None`` when it does not belong."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Public shapes
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkspaceSignal:
    """One workspace's closeout-relevant facts, as already-read inventory rows.

    This is deliberately *not* a fresh scan. It is the subset of a
    :class:`~skillweave.repo_health.worktrees.WorkspaceRow` a closeout needs, in
    plain strings, so a closeout never touches a filesystem or git — the
    inventory lane owns reading, the closeout lane owns judging.
    """

    path: str
    repo: str = ""
    registration: str = "registered"
    dirtiness: str = "clean"
    lease: str = "active"
    process: str = "absent"
    session: str = "present"
    reachability: str = "reachable"
    classification: str = "healthy"
    reason: str = ""
    managed: bool = True

    @classmethod
    def from_row(cls, row: Any) -> "WorkspaceSignal":
        """Project an inventory row (or any duck-typed equivalent) read-only."""
        lease = _state_value(getattr(row, "lease", "unknown"))
        return cls(
            path=str(getattr(row, "path", "")),
            repo=str(getattr(row, "repo", "")),
            registration=_state_value(getattr(row, "registration", "unknown")),
            dirtiness=_state_value(getattr(row, "dirtiness", "unknown")),
            lease=lease,
            process=_state_value(getattr(row, "process", "unknown")),
            session=_state_value(getattr(row, "session", "unknown")),
            reachability=_state_value(getattr(row, "reachability", "unknown")),
            classification=_state_value(getattr(row, "classification", "unknown")),
            reason=str(getattr(row, "reason", "")),
            # No manifest at all is the unmanaged shape; any recorded lease state
            # other than "absent" means the run did own this workspace.
            managed=lease != "absent",
        )

    @classmethod
    def from_inventory(cls, inventory: Any) -> tuple["WorkspaceSignal", ...]:
        """Project every row of a workspace inventory."""
        return tuple(_iter_signals(inventory))


def _iter_signals(rows: Any) -> Iterable[WorkspaceSignal]:
    """Project any workspace evidence into plain :class:`WorkspaceSignal`s.

    Accepts a :class:`~skillweave.repo_health.worktrees.WorkspaceInventory`, a
    plain sequence of inventory rows, or a sequence already holding signals —
    so the caller can pass whatever the inventory lane produced without the
    closeout lane having to know its concrete type.
    """
    if rows is None:
        return
    if not isinstance(rows, (list, tuple)):
        inventory_rows = getattr(rows, "rows", None)
        if inventory_rows is None:
            raise CloseoutError(
                "workspace evidence must be a WorkspaceInventory or a sequence "
                f"of workspace rows/signals, got {rows!r}"
            )
        rows = inventory_rows
    for row in rows:
        yield row if isinstance(row, WorkspaceSignal) else WorkspaceSignal.from_row(row)


class CloseoutError(ValueError):
    """A closeout request is malformed and cannot be represented."""


@dataclass(frozen=True)
class Blocker:
    """One reason the run cannot be closed, bound to the lane that can clear it."""

    hold: Hold
    boundary: Boundary
    subject: str
    note: str

    @property
    def code(self) -> str:
        """The stable, finite reason code for this hold."""
        return self.hold.value

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "boundary": self.boundary.value,
            "subject": self.subject,
            "note": _CONTROL_CHARS.sub(" ", self.note),
        }


@dataclass(frozen=True)
class CloseoutDecision:
    """The frozen, attributable judgement *about* a preview.

    A preview has no authority. Someone with a name decides whether a *specific*
    preview — identified by its digest — is accepted for closure, and this
    object is that decision, made durable. Binding the digest (rather than the
    inputs) means a decision cannot silently survive a change to the evidence it
    was made against: re-run the preview, and the old decision no longer binds.
    """

    decided_by: str
    preview_digest: str
    accepted: bool
    reason: str = ""
    unfinished: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decided_by, str) or not self.decided_by.strip():
            raise CloseoutError(
                "a closeout decision must name an authority (decided_by)"
            )
        if not isinstance(self.preview_digest, str) or not _SHA256.match(
            self.preview_digest
        ):
            raise CloseoutError(
                "a closeout decision must bind a canonical lowercase sha256 "
                f"preview digest, got {self.preview_digest!r}"
            )
        if not isinstance(self.accepted, bool):
            raise CloseoutError(
                f"accepted must be a bool, got {self.accepted!r}"
            )
        if not self.accepted and not _CONTROL_CHARS.sub("", self.reason).strip():
            raise CloseoutError(
                "a refusal must give a reason; an unexplained refusal is not a "
                "decision"
            )


@dataclass(frozen=True)
class CloseoutPreview:
    """Total, deterministic, read-only output of one closeout evaluation.

    ``digest`` is computed over the canonical JSON of everything below it, so
    two previews are equivalent exactly when their digest matches. The preview
    carries no timestamp and no authority: publishing it commits nothing.
    """

    schema_version: int
    preview_version: int
    run_id: str
    subject: str
    status: str
    evidence: tuple[dict, ...]
    blockers: tuple[Blocker, ...]
    authority: tuple[dict, ...]
    digest: str = ""

    # ── derived views ────────────────────────────────────────────────────

    @property
    def held(self) -> bool:
        """True when at least one hold stands between here and CLOSED."""
        return self.status == STATUS_HELD

    @property
    def codes(self) -> tuple[str, ...]:
        """Every hold code present, sorted and deduplicated."""
        return tuple(sorted({blocker.code for blocker in self.blockers}))

    def by_boundary(self) -> dict[str, tuple[dict, ...]]:
        """Blocker payloads grouped by the lane that must clear them."""
        grouped: dict[str, list[dict]] = {}
        for blocker in self.blockers:
            grouped.setdefault(blocker.boundary.value, []).append(blocker.as_dict())
        return {name: tuple(items) for name, items in grouped.items()}

    def has(self, hold: "Hold | str") -> bool:
        """True when ``hold`` is among this preview's blockers."""
        code = getattr(hold, "value", hold)
        return code in self.codes

    def payload(self) -> dict:
        """The digested payload, without ``digest`` itself."""
        return {
            "schema_version": self.schema_version,
            "preview_version": self.preview_version,
            "run_id": self.run_id,
            "subject": self.subject,
            "status": self.status,
            "evidence": [dict(entry) for entry in self.evidence],
            "blockers": [blocker.as_dict() for blocker in self.blockers],
            "authority": [dict(entry) for entry in self.authority],
        }

    def to_dict(self) -> dict:
        payload = self.payload()
        payload["digest"] = self.digest
        return payload


@dataclass(frozen=True)
class BlockerPreview:
    """A preview that found something to answer for, with its running totals."""

    preview: CloseoutPreview
    counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        return self.preview.digest

    @property
    def run_id(self) -> str:
        return self.preview.run_id

    def __getattr__(self, item: str) -> Any:  # pragma: no cover - passthrough
        return getattr(self.preview, item)


@dataclass(frozen=True)
class CloseoutReceipt:
    """The durable outcome: an authorized decision applied to a frozen preview.

    A receipt is emitted for *every* decision, closed or held — the held receipt
    is the artifact that documents a negative hold, and it is the reason S3 can
    persist "all negative holds". ``digest`` covers the receipt's whole content,
    so a held receipt is as tamper-evident as a closed one.
    """

    schema_version: int
    status: str
    run_id: str
    subject: str
    preview_digest: str
    decided_by: str
    decision_reason: str
    blockers: tuple[dict, ...]
    authority: tuple[dict, ...]
    digest: str = ""

    def payload(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "run_id": self.run_id,
            "subject": self.subject,
            "preview_digest": self.preview_digest,
            "decided_by": self.decided_by,
            "decision_reason": _CONTROL_CHARS.sub(" ", self.decision_reason),
            "blockers": [dict(entry) for entry in self.blockers],
            "authority": [dict(entry) for entry in self.authority],
        }

    def to_dict(self) -> dict:
        payload = self.payload()
        payload["digest"] = self.digest
        return payload

    def is_closed(self) -> bool:
        return self.status == STATUS_CLOSED


# --------------------------------------------------------------------------- #
# Canonical JSON / digesting
# --------------------------------------------------------------------------- #


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


# --------------------------------------------------------------------------- #
# Evidence inputs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EvidenceInput:
    """One named upstream artifact, or its absence.

    ``kind``/``producer`` are what the run *declared* it would supply;
    ``value`` is what actually arrived (``None`` when nothing did).
    :meth:`status` is the only place "missing" and "mismatched" are decided, and
    it decides them from the artifact's own resolution — never from a guess.

    ``cross_check`` is an optional reference the artifact must agree with (for
    an assessment receipt, the closeout's own subject SHA); disagreement is
    ``mismatched``, not missing.
    """

    kind: EvidenceKind
    producer: str
    value: Any = None
    supplied: bool = False
    note: str = ""
    cross_check: Optional[str] = None

    def status(self) -> EvidenceStatus:
        return self.resolve().status

    def resolve(self) -> "_Resolved":
        """Resolve this input to a status plus a human-readable note."""
        if not self.supplied or self.value is None:
            return _Resolved(
                EvidenceStatus.MISSING,
                self.note or f"{self.kind.value} evidence was not supplied",
            )
        if self.kind is EvidenceKind.LAUNCH:
            return self._resolve_launch()
        if self.kind is EvidenceKind.ASSESSMENT:
            return self._resolve_assessment()
        if self.note:
            return _Resolved(EvidenceStatus.PRESENT, self.note)
        return _Resolved(
            EvidenceStatus.PRESENT, f"{self.kind.value} evidence supplied"
        )

    def _resolve_launch(self) -> "_Resolved":
        """Verify a launch receipt through the launch contract's own canonicalize.

        Re-implementing the digest here would create a second, drifting
        definition of launch evidence; delegating means a receipt the launch lane
        would reject is a receipt the closeout rejects, with the same reason.
        """
        try:
            checked = _canonicalize_launch(self.value)
        except LaunchReceiptError as exc:
            return _Resolved(
                EvidenceStatus.MISMATCHED,
                f"launch receipt failed its own contract check: {exc}",
            )
        payload = checked.payload
        outcome = payload.get("outcome", {}).get("status")
        if payload.get("result", {}).get("status") == RESULT_UNAVAILABLE:
            return _Resolved(
                EvidenceStatus.MISMATCHED,
                "launch receipt declares an unavailable result; a deployment "
                "that did not happen cannot attest a closeout",
            )
        if outcome != OUTCOME_SUCCESS:
            return _Resolved(
                EvidenceStatus.PRESENT,
                f"launch receipt is intact but its outcome is {outcome!r}",
            )
        return _Resolved(
            EvidenceStatus.PRESENT, "launch receipt verified and successful"
        )

    def _resolve_assessment(self) -> "_Resolved":
        payload = _payload_of(self.value)
        if payload is None:
            return _Resolved(
                EvidenceStatus.MISMATCHED,
                "assessment receipt is not a resolvable receipt object",
            )
        result = payload.get("result")
        if not isinstance(result, Mapping) or "status" not in result:
            return _Resolved(
                EvidenceStatus.MISMATCHED, "assessment receipt has no result status"
            )
        if self.cross_check is not None:
            subject = payload.get("subject")
            full_sha = subject.get("full_sha") if isinstance(subject, Mapping) else None
            if full_sha != self.cross_check:
                return _Resolved(
                    EvidenceStatus.MISMATCHED,
                    "assessment receipt is bound to subject "
                    f"{full_sha!r}, not the closeout subject {self.cross_check!r}",
                )
        if result.get("status") == RESULT_UNAVAILABLE:
            return _Resolved(
                EvidenceStatus.PRESENT,
                "assessment receipt declares an unavailable result",
            )
        return _Resolved(EvidenceStatus.PRESENT, "assessment receipt verified")


@dataclass(frozen=True)
class _Resolved:
    """The internal status+note pair an :class:`EvidenceInput` resolves to."""

    status: EvidenceStatus
    note: str


def _nested_status(payload: Any, section: str) -> Optional[str]:
    """``payload[section]["status"]`` as a plain string, or ``None``."""
    if not isinstance(payload, Mapping):
        return None
    block = payload.get(section)
    if not isinstance(block, Mapping):
        return None
    value = block.get("status")
    return value if isinstance(value, str) else None


def _payload_of(value: Any) -> Optional[Mapping[str, Any]]:
    """The mapping carried by a receipt object or a raw dict, or ``None``."""
    payload = getattr(value, "payload", None)
    if isinstance(payload, Mapping):
        return payload
    if isinstance(value, Mapping):
        return value
    return None


def _launch_evidence(supplied: bool, value: Any) -> EvidenceInput:
    return EvidenceInput(
        kind=EvidenceKind.LAUNCH, producer="releasechain/launch", value=value,
        supplied=supplied,
    )


def _assessment_evidence(
    supplied: bool, value: Any, subject: str, note: str = ""
) -> EvidenceInput:
    return EvidenceInput(
        kind=EvidenceKind.ASSESSMENT,
        producer="releasechain/assessment",
        value=value,
        supplied=supplied,
        note=note,
        cross_check=subject,
    )


# --------------------------------------------------------------------------- #
# The service
# --------------------------------------------------------------------------- #


class CloseoutService:
    """Judge whether a run may be closed, and never act on that judgement.

    ``root`` names the tree the closeout concerns; it is used for identity in
    the preview only and is never read. ``authority`` must be a
    :class:`~skillweave.assessment_service.ReadOnlyAuthority` (or a capability
    with the same shape) — construction refuses anything else, so a mutating
    closeout cannot be built without changing this class.
    """

    def __init__(self, root: Any = ".", *, authority: Optional[Any] = None) -> None:
        auth = _assess_mod.ReadOnlyAuthority() if authority is None else authority
        if not getattr(auth, "read_only", False):
            raise ReadOnlyViolation(
                "CloseoutService requires a read-only authority; the exit door "
                f"decides and never cleans up; got {auth!r}"
            )
        self._root = str(root)
        self._authority = auth

    @property
    def root(self) -> str:
        return self._root

    @property
    def authority(self) -> Any:
        return self._authority

    # ── authority boundaries ─────────────────────────────────────────────

    @staticmethod
    def authority_for(lane: str, action: str) -> bool:
        """Machine test of :data:`AUTHORITY_BOUNDARIES`.

        Returns ``True`` only when ``lane`` is explicitly permitted ``action``.
        Every unlisted lane, and every action an unlisted lane happens to be
        capable of, is refused — the table grants authority, it never assumes it.
        """
        entry = AUTHORITY_BOUNDARIES.get(lane)
        if entry is None:
            return False
        return action in entry["may"]

    # ── step A: deterministic preview ────────────────────────────────────

    def preview(
        self,
        *,
        run_id: str,
        subject: str,
        evidence: Sequence[EvidenceInput] = (),
        workspaces: Any = (),
        telemetry: Any = None,
        unfinished: Sequence[str] = (),
    ) -> CloseoutPreview:
        """Evaluate every input into a total, deterministic, read-only preview.

        Never raises for an adverse finding and never for a shortfall: "the run
        may not be closed, and here is why" is an ordinary, expected output.
        A malformed *identity* — a run id or subject that cannot be represented
        at all — is refused (:class:`CloseoutError`), because no receipt may
        carry a non-canonical SHA.

        This method touches no filesystem, no git and no clock. It is therefore
        safe to produce, publish and review before any authority is consulted —
        which is the ordering Step A requires.
        """
        # The read guard is exercised and released; the mutating guard exists on
        # the same authority and is never reachable from here.
        self._authority.assert_readable("preview closeout")

        if not isinstance(run_id, str) or not run_id.strip():
            raise CloseoutError(f"run_id must be a non-empty string, got {run_id!r}")
        if not isinstance(subject, str) or not _FULL_SHA.match(subject):
            raise CloseoutError(
                "subject is not a canonical lowercase full 40-hex SHA: "
                f"{subject!r}; a closeout receipt cannot represent it"
            )

        blockers: List[Blocker] = []
        blockers.extend(self._evidence_blockers(evidence))
        blockers.extend(self._workspace_blockers(workspaces))
        blockers.extend(_telemetry_blockers(telemetry))
        blockers.extend(_unfinished_blockers(unfinished))

        payload = {
            "schema_version": SCHEMA_VERSION,
            "preview_version": PREVIEW_VERSION,
            "run_id": run_id,
            "subject": subject,
            "status": STATUS_HELD if blockers else STATUS_CLOSED,
            "evidence": [self._evidence_row(item) for item in evidence],
            "blockers": [blocker.as_dict() for blocker in blockers],
            "authority": _authority_rows(),
        }
        return CloseoutPreview(
            schema_version=SCHEMA_VERSION,
            preview_version=PREVIEW_VERSION,
            run_id=run_id,
            subject=subject,
            status=payload["status"],
            evidence=tuple(payload["evidence"]),
            blockers=tuple(blockers),
            authority=tuple(payload["authority"]),
            digest=_digest(payload),
        )

    def preview_blockers(self, **kwargs: Any) -> BlockerPreview:
        """``preview`` plus a per-code tally, for reporting all holds at once."""
        built = self.preview(**kwargs)
        counts: dict[str, int] = {}
        for blocker in built.blockers:
            counts[blocker.code] = counts.get(blocker.code, 0) + 1
        return BlockerPreview(
            preview=built, counts={code: counts[code] for code in sorted(counts)}
        )

    # ── step A: authority, after the preview ─────────────────────────────

    def decide(
        self, preview: CloseoutPreview, decision: CloseoutDecision
    ) -> CloseoutReceipt:
        """Apply ``decision`` to ``preview``, additively, and emit a receipt.

        The authority never overwrites the preview. It can only *withhold*
        closure — ``accepted=False``, or a decision bound to a different preview
        digest, adds holds to whatever the preview already found. It can never
        remove one, which is what makes "a preview that found a hold always
        produces a held receipt" a structural property rather than a rule to
        remember.

        Returns a receipt in every case; a held receipt is a first-class result,
        not an error.
        """
        self._authority.assert_readable("decide closeout")

        blockers: List[Blocker] = list(preview.blockers)
        if not decision.accepted:
            blockers.append(
                _blocker(
                    Hold.AUTHORITY_MISMATCH,
                    preview.run_id,
                    f"{decision.decided_by} refused to close: {decision.reason}",
                )
            )
        if decision.preview_digest != preview.digest:
            blockers.append(
                _blocker(
                    Hold.EVIDENCE_MISMATCHED,
                    preview.subject,
                    "the decision is bound to preview digest "
                    f"{decision.preview_digest}, but the preview under decision "
                    f"digests to {preview.digest}; re-run the preview and decide "
                    "against the current evidence",
                )
            )

        status = STATUS_HELD if blockers else STATUS_CLOSED
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "run_id": preview.run_id,
            "subject": preview.subject,
            "preview_digest": preview.digest,
            "decided_by": decision.decided_by,
            "decision_reason": _CONTROL_CHARS.sub(" ", decision.reason),
            "blockers": [blocker.as_dict() for blocker in blockers],
            "authority": _authority_rows(),
        }
        return CloseoutReceipt(
            schema_version=SCHEMA_VERSION,
            status=status,
            run_id=preview.run_id,
            subject=preview.subject,
            preview_digest=preview.digest,
            decided_by=decision.decided_by,
            decision_reason=_CONTROL_CHARS.sub(" ", decision.reason),
            blockers=tuple(payload["blockers"]),
            authority=tuple(payload["authority"]),
            digest=_digest(payload),
        )

    # ── input → blockers ─────────────────────────────────────────────────

    def _evidence_blockers(
        self, evidence: Sequence[EvidenceInput]
    ) -> List[Blocker]:
        blockers: List[Blocker] = []
        for item in evidence:
            resolved = item.resolve()
            if resolved.status is EvidenceStatus.MISSING:
                blockers.append(
                    _blocker(Hold.EVIDENCE_MISSING, item.producer, resolved.note)
                )
                continue
            if resolved.status is EvidenceStatus.MISMATCHED:
                blockers.append(
                    _blocker(Hold.EVIDENCE_MISMATCHED, item.producer, resolved.note)
                )
                if item.kind is EvidenceKind.LAUNCH:
                    blockers.append(
                        _blocker(
                            Hold.LAUNCH_UNVERIFIED,
                            item.producer,
                            "the launch receipt could not be verified against the "
                            "launch contract, so the deployment is unestablished",
                        )
                    )
                continue

            # Present, but not necessarily an attestation.
            payload = _payload_of(item.value)
            if item.kind is EvidenceKind.ASSESSMENT:
                # An unavailable assessment receipt says the assessment could not
                # be completed: the evidence exists, it establishes nothing.
                if _nested_status(payload, "result") == RESULT_UNAVAILABLE:
                    blockers.append(
                        _blocker(
                            Hold.ASSESSMENT_UNAVAILABLE,
                            item.producer,
                            "the assessment receipt declares an unavailable "
                            "result, so no assessment evidence was established",
                        )
                    )
                continue
            if item.kind is EvidenceKind.LAUNCH:
                outcome = _nested_status(payload, "outcome")
                if outcome is not None and outcome != OUTCOME_SUCCESS:
                    blockers.append(
                        _blocker(
                            Hold.LAUNCH_UNSUCCESSFUL,
                            item.producer,
                            f"the launch receipt's outcome is {outcome!r}, not a "
                            "successful deployment",
                        )
                    )
                continue

        return blockers

    @staticmethod
    def _workspace_blockers(workspaces: Any) -> List[Blocker]:
        if workspaces is None:
            return []
        blockers: List[Blocker] = []
        for signal in _iter_signals(workspaces):
            blocker = _workspace_blocker(signal)
            if blocker is not None:
                blockers.append(blocker)
        return blockers

    @staticmethod
    def _evidence_row(item: EvidenceInput) -> dict:
        resolved = item.resolve()
        return {
            "kind": item.kind.value,
            "producer": item.producer,
            "status": resolved.status.value,
            "note": _CONTROL_CHARS.sub(" ", resolved.note),
        }


# --------------------------------------------------------------------------- #
# Blocker construction
# --------------------------------------------------------------------------- #


def _blocker(hold: Hold, subject: str, note: str) -> Blocker:
    """Build a blocker, refusing any hold without a declared boundary."""
    boundary = HOLD_BOUNDARIES.get(hold)
    if boundary is None:
        raise CloseoutError(
            f"hold {hold!r} has no declared authority boundary; every hold must "
            "name the lane that can clear it"
        )
    return Blocker(
        hold=hold,
        boundary=boundary,
        subject=str(subject),
        note=_CONTROL_CHARS.sub(" ", str(note)),
    )


def _workspace_blocker(signal: WorkspaceSignal) -> Optional[Blocker]:
    """The single most actionable hold for one workspace, or ``None``.

    Precedence mirrors the inventory's own: a definite adverse finding first
    (dirty, then active owner, then ownership), then unavailable evidence, then
    the classification itself. Clearing the top hold re-evaluates the workspace
    from the top, so the sequence of holds a workspace produces walks exactly the
    sequence of things a human must fix.
    """
    subject = signal.path or signal.repo or "(unnamed workspace)"

    if signal.dirtiness == "dirty":
        return _blocker(
            Hold.WORKSPACE_DIRTY, subject,
            "working tree has uncommitted changes; closeout would strand them",
        )
    if signal.process == "present":
        return _blocker(
            Hold.WORKSPACE_ACTIVE, subject,
            "a live process still occupies this workspace",
        )
    if signal.session == "present":
        return _blocker(
            Hold.WORKSPACE_ACTIVE, subject,
            "a fresh session heartbeat still claims this workspace",
        )
    if signal.managed and signal.lease == "active":
        return _blocker(
            Hold.WORKSPACE_LEASED, subject,
            "the workspace lease is still active; it is still owned",
        )
    if signal.registration == "unregistered":
        return _blocker(
            Hold.WORKSPACE_UNCLASSIFIED, subject,
            "workspace-like path is not registered with git; it was never "
            "classified as a disposal",
        )
    if signal.classification == "unknown" or _unknown_dimension(signal):
        return _blocker(
            Hold.WORKSPACE_EVIDENCE_UNKNOWN, subject,
            "workspace safety evidence is unavailable: "
            + (signal.reason or "no definite classification"),
        )
    if _held(signal.classification):
        if signal.classification == "healthy":
            note = (
                "workspace is healthy and still present; a closeout does not "
                "walk away from a live workspace it never disposed of"
            )
        else:
            note = signal.reason or (
                f"workspace classification {signal.classification!r} is not a "
                "completed disposal"
            )
        return _blocker(Hold.WORKSPACE_UNCLASSIFIED, subject, note)
    return None


#: The workspace dimensions that make a row's evidence incomplete. Kept as the
#: same finite set the inventory treats as "unknown/unavailable evidence".
_SAFETY_DIMENSIONS = (
    "registration",
    "dirtiness",
    "lease",
    "reachability",
    "classification",
)


def _unknown_dimension(signal: WorkspaceSignal) -> bool:
    return any(
        getattr(signal, name) == "unknown" for name in _SAFETY_DIMENSIONS
    )


def _telemetry_blockers(telemetry: Any) -> List[Blocker]:
    """Holds derived from the intervention-telemetry closeout consumer.

    The service never imports the telemetry lane: it reads the same
    ``snapshot()`` shape that lane's ``InterventionCloseout`` publishes, so the
    two lanes stay independently loadable. A run whose telemetry could not be
    read is held; an intact, all-zero telemetry is *not* a hold — clean runs are
    the normal case, and inventing a hold for them would make CLOSED
    unreachable.
    """
    if telemetry is None:
        return [
            _blocker(
                Hold.TELEMETRY_UNAVAILABLE, "telemetry",
                "intervention telemetry was not consumed, so restarts, malformed "
                "payloads and desyncs are unaccounted for",
            )
        ]
    snapshot = getattr(telemetry, "snapshot", None)
    data = snapshot() if callable(snapshot) else telemetry
    if not isinstance(data, Mapping):
        return [
            _blocker(
                Hold.TELEMETRY_UNAVAILABLE, "telemetry",
                f"intervention telemetry is not a readable snapshot: {data!r}",
            )
        ]
    digest = data.get("receipt_digest")
    if not isinstance(digest, str) or not _SHA256.match(digest):
        return [
            _blocker(
                Hold.TELEMETRY_UNAVAILABLE, "telemetry",
                "intervention telemetry carries no verifiable receipt digest",
            )
        ]
    return []


def _unfinished_blockers(unfinished: Sequence[str]) -> List[Blocker]:
    blockers: List[Blocker] = []
    for item in unfinished:
        blockers.append(
            _blocker(
                Hold.UNFINISHED_ITEMS, str(item),
                "declared work item was not finished before closeout",
            )
        )
    return blockers


def _authority_rows() -> List[dict]:
    """The declared boundary table, rendered deterministically for the digest."""
    return [
        {
            "lane": lane,
            "may": list(AUTHORITY_BOUNDARIES[lane]["may"]),
            "must_not": list(AUTHORITY_BOUNDARIES[lane]["must_not"]),
        }
        for lane in sorted(AUTHORITY_BOUNDARIES)
    ]


# --------------------------------------------------------------------------- #
# Convenience constructors, used by callers and tests
# --------------------------------------------------------------------------- #


def missing_evidence(kind: EvidenceKind, producer: str) -> EvidenceInput:
    """An input the run declared it would supply and did not."""
    return EvidenceInput(kind=kind, producer=producer, supplied=False)


def tampered_launch_receipt(value: Any) -> EvidenceInput:
    """A supplied launch receipt; its own contract decides whether it is intact."""
    return _launch_evidence(True, value)


def is_closed(receipt: Any) -> bool:
    """True when ``receipt`` records a closed run — and nothing else."""
    return getattr(receipt, "status", None) == STATUS_CLOSED
