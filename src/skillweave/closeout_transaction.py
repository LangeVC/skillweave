"""Transactional closeout — resumable removal with a complete receipt (SW-157-CLOSE-002).

The read-only exit door (:mod:`skillweave.closeout_service`) *decides* that a run
may close. This module is the narrow, **transactional** step that then performs
the one mutation such a decision can imply — removal of authorized workspaces —
without ever losing track of what it did.

It is not a second closeout service and it does not decide anything: it consumes
a set of :class:`~skillweave.repo_health.worktrees.CleanupAuthorization`
identities and drives them through the *existing, injected* workspace release
policy. There is no new removal machinery here.

Six persisted states, in order
------------------------------

Every attempt persists exactly one state at a time, to a journal that is made
durable *before* the next state is begun:

==============================================  ===========================================
State                                           Meaning
==============================================  ===========================================
:attr:`TransactionState.PLANNED`                authority seen; plan and authority recorded
:attr:`TransactionState.MUTATING`               about to call the remover (crash window)
:attr:`TransactionState.MUTATED`                remover returned True — remove happened
:attr:`TransactionState.PRESERVED`              remover held — nothing removed, outcome known
:attr:`TransactionState.INTERRUPTED`            remover raised — outcome unknown
:attr:`TransactionState.COMPENSATED`            a post-mutation failure was compensated
==============================================  ===========================================

The one dangerous window in any delete-then-record transaction is between
"the mutation happened on disk" and "the record of it was written". This module
closes that window by writing :attr:`TransactionState.MUTATING` *before* it
calls the remover, so an interrupted attempt is always discoverable.

An attempt whose remover *raises* is persisted as
:attr:`TransactionState.INTERRUPTED`, never as ``PRESERVED``: a genuine hold
means the policy returned a known reason, whereas a raised remover means the
outcome is unknown (the removal may or may not have landed). On resume, an
identity left in ``MUTATING`` or ``INTERRUPTED`` has no proof its removal
completed, so it is **preserved and reported** — never removed again. An
identity already in ``MUTATED`` is never re-removed either.

A missing or lost journal record is also covered (SW-157-REMEDY-B)
------------------------------------------------------------------

All of the above relies on the journal being readable on resume. A journal
record that was never written, or was lost with a torn tail, leaves no state
to consult — and a bare ``PLANNED`` record is *not* a licence to re-run the
mutation, because the mutation itself may have landed before its outcome was.
The journal alone therefore cannot make the mutation idempotent, so the
transaction does not rely on it: the removal is gated on **physical evidence**,
the one fact a lost append cannot fabricate.

Before any removal is attempted — for a fresh identity, a ``PLANNED``-only
record, a lost tail, or an empty journal — the transaction checks whether the
workspace is still physically present:

* **present** — it is provably un-removed, so it is removed exactly once;
* **absent** — no path can prove it un-removed, so it is **preserved and
  reported** with a durable record, never removed again.

The durable record makes the check a *checkpoint*: the first resume to see the
absence writes it, and every later resume reads it and is a no-op. That is the
whole idempotency contract — a resume cannot produce a duplicate removal,
whichever side of the window the interruption fell on, and whether or not the
journal survived it.

Every deletion and every deliberate preservation appears in the receipt
-----------------------------------------------------------------------

The receipt is built from the journal, not from the current attempt. An
identity that was removed in an earlier, interrupted run still appears as a
:attr:`ReceiptEntryKind.REMOVED` entry in the later run's receipt; an identity
whose removal was deliberately withheld appears as :attr:`ReceiptEntryKind.HELD`
with the exact reason. Nothing that was acted on, and nothing that was
deliberately not acted on, is absent from the receipt.

Branch deletion stays separately disabled
-----------------------------------------

Branch deletion is *not* part of this transaction. The release policy exposes it
as its own action (``delete_branch``), disabled by default and requiring an
exact-branch authorization. This module never calls it, never supplies an
authorization, and records ``branch_deleted = False`` /
``branch_preserved`` for every workspace. It never routes removal through
:meth:`skillweave.workspace.provider.GitWorktreeProvider.release`, which deletes
the branch implicitly; it uses only the injected, shell-free policy seam.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from skillweave.repo_health.worktrees import (
    CleanupAuthorization,
    WorkspaceIdentity,
)
from skillweave.routing.workspace import (
    WorkspaceManifest,
    WorkspaceManifestError,
    WorkspaceReleasePolicy,
)

__all__ = [
    "SCHEMA_VERSION",
    "JOURNAL_VERSION",
    "RECEIPT_VERSION",
    "STATUS_COMMITTED",
    "STATUS_INCOMPLETE",
    "TransactionState",
    "ReceiptEntryKind",
    "TransactionError",
    "JournalRecord",
    "ReceiptEntry",
    "TransactionReceipt",
    "CloseoutTransaction",
]


SCHEMA_VERSION = 1
JOURNAL_VERSION = 1
RECEIPT_VERSION = 1

#: The run reached a clean, fully-accounted terminal state.
STATUS_COMMITTED = "committed"

#: An attempt was interrupted and deliberately preserved on resume. The run is
#: accounted for, but it did not complete: it is incomplete, not failed.
STATUS_INCOMPLETE = "incomplete"


class TransactionError(ValueError):
    """A transactional closeout was refused fail-closed before it could act.

    Raised only for structurally unusable input (a non-authorization, an
    unknown state or kind). A *decision* about a valid authorization is always
    reported as a receipt entry, never an exception, so held and preserved
    outcomes stay observable and deterministic.
    """


class TransactionState(str, Enum):
    """The persisted states one authorized workspace moves through.

    ``PLANNED`` and ``MUTATING`` are *pre-mutation* states; ``MUTATED``,
    ``PRESERVED`` and ``COMPENSATED`` are terminal for one attempt. The journal
    is append-only, so the latest record for an identity key is its current
    state.
    """

    #: Authority seen; the plan named this workspace but nothing was attempted.
    PLANNED = "planned"
    #: The attempt is entering the removal call. Recorded *before* the call, so
    #: an interruption is discoverable as "may have removed".
    MUTATING = "mutating"
    #: The remover reported success: the workspace was removed.
    MUTATED = "mutated"
    #: The workspace was deliberately kept: the policy returned a known hold
    #: reason and nothing was removed. The outcome is *known*.
    PRESERVED = "preserved"
    #: The remover raised, so the outcome is *unknown*: the removal may or may
    #: not have landed. Distinct from ``PRESERVED`` on purpose — a resume must
    #: treat an interrupt as unproven and preserve rather than risk a repeat.
    INTERRUPTED = "interrupted"
    #: A post-mutation failure was compensated; the identity is accounted for
    #: without claiming a clean removal.
    COMPENSATED = "compensated"


class ReceiptEntryKind(str, Enum):
    """How one workspace appears in the transaction receipt.

    A workspace is in exactly one kind, so the receipt is exhaustive: every
    deletion is ``REMOVED`` and every deliberate non-deletion is ``HELD``.
    """

    #: The workspace was removed by this run (or by an earlier, resumed run of
    #: the same transaction).
    REMOVED = "removed"
    #: The workspace was deliberately preserved, with the policy's reason.
    HELD = "held"
    #: The attempt was interrupted before its outcome was known; on resume it
    #: was preserved rather than risk a duplicate removal.
    INTERRUPTED = "interrupted"
    #: A post-mutation failure was compensated.
    COMPENSATED = "compensated"


#: The states whose removal is proven, and which a resume must never repeat.
_REMOVAL_STATES = frozenset({TransactionState.MUTATED})

#: The states an interrupted attempt may be left in, which resume must treat as
#: unproven and therefore preserve. ``MUTATING`` is the hard-kill window (the
#: process died mid-call); ``INTERRUPTED`` is the caught-failure window (the
#: remover raised). Both leave the outcome unknown.
_UNPROVEN_STATES = frozenset(
    {TransactionState.MUTATING, TransactionState.INTERRUPTED}
)

#: The reasons a removal may be deliberately withheld, each mapping onto a
#: policy hold reason or an already-absent no-op.
_HELD_REASONS = frozenset(
    {
        "dirty",
        "unreachable",
        "active_lease",
        "active_process",
        "unknown",
        "removal_unavailable",
        "already_absent",
        "interrupted_unproven",
        "absent_unverified",
    }
)


# --------------------------------------------------------------------------- #
# Canonical JSON / digesting (the same idiom closeout_service uses)
# --------------------------------------------------------------------------- #


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


# --------------------------------------------------------------------------- #
# Journal — the persisted transaction state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class JournalRecord:
    """One durable transition in a transaction's journal.

    The journal is append-only and each record is fsynced before the next state
    begins, so a torn final line is the only possible damage and is skipped on
    read. ``digest`` binds the record to its content.
    """

    version: int
    identity: str
    state: str
    reason: str
    path: str
    branch: str
    digest: str = ""

    def payload(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "identity": self.identity,
            "state": self.state,
            "reason": self.reason,
            "path": self.path,
            "branch": self.branch,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = self.payload()
        data["digest"] = self.digest
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def _journal_record(
    *,
    identity: WorkspaceIdentity,
    state: TransactionState,
    reason: str,
    path: str,
    branch: str,
) -> JournalRecord:
    if not isinstance(state, TransactionState):
        raise TransactionError(f"unknown transaction state {state!r}")
    payload = {
        "version": JOURNAL_VERSION,
        "identity": identity.key,
        "state": state.value,
        "reason": reason,
        "path": path,
        "branch": branch,
    }
    return JournalRecord(
        version=JOURNAL_VERSION,
        identity=identity.key,
        state=state.value,
        reason=reason,
        path=path,
        branch=branch,
        digest=_digest(payload),
    )


def _identity_from_key(key: Any) -> Optional[WorkspaceIdentity]:
    """Rebuild an identity from its durable ``repo/run/lane`` key, or ``None``.

    Mirrors the cleanup ledger's rule: components cannot contain ``/``, so the
    split is unambiguous and a malformed key is dropped rather than guessed at.
    """
    if not isinstance(key, str):
        return None
    parts = key.split("/")
    if len(parts) != 3:
        return None
    try:
        return WorkspaceIdentity(repo=parts[0], run=parts[1], lane=parts[2])
    except WorkspaceManifestError:
        return None


def _journal_record_from_dict(data: Mapping[str, Any]) -> Optional[JournalRecord]:
    identity = _identity_from_key(data.get("identity"))
    if identity is None:
        return None
    state = data.get("state")
    if state not in {member.value for member in TransactionState}:
        return None
    return JournalRecord(
        version=int(data.get("version", JOURNAL_VERSION)),
        identity=identity.key,
        state=state,
        reason=str(data.get("reason", "")),
        path=str(data.get("path", "")),
        branch=str(data.get("branch", "")),
        digest=str(data.get("digest", "")),
    )


def read_journal(journal_path: str) -> List[JournalRecord]:
    """Read the durable journal; a missing file is an empty journal.

    A torn final line from an interrupted append is skipped, not fatal — the
    same rule the cleanup ledger uses.
    """
    path = Path(journal_path)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: List[JournalRecord] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, Mapping):
            continue
        record = _journal_record_from_dict(data)
        if record is not None:
            records.append(record)
    return records


def _append_journal(record: JournalRecord, journal_path: str) -> None:
    """Append one record durably (write + flush + fsync) before returning."""
    path = Path(journal_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(record.to_json() + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _latest_states(
    records: Sequence[JournalRecord],
) -> Dict[str, JournalRecord]:
    """The current state of every identity, in first-seen order.

    The journal is append-only, so the last record for a key wins. Order is
    preserved so a receipt reads in the order the transaction first saw each
    workspace.
    """
    latest: Dict[str, JournalRecord] = {}
    for record in records:
        latest[record.identity] = record
    return latest


# --------------------------------------------------------------------------- #
# Receipt — every deletion and every deliberate preservation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReceiptEntry:
    """One workspace's disposition in a transaction receipt.

    ``kind`` says what happened; ``reason`` says why. A ``HELD`` or
    ``INTERRUPTED`` entry is a *deliberate preservation* and is recorded with
    the same force as a removal — there is no silent tier.
    """

    kind: ReceiptEntryKind
    identity: str
    path: str
    branch: str
    reason: str
    branch_deleted: bool = False
    branch_status: str = "preserved"

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ReceiptEntryKind):
            raise TransactionError(f"unknown receipt entry kind {self.kind!r}")
        # Branch deletion is not part of this transaction. Guard it structurally
        # so no future edit can quietly claim a deleted branch on a receipt.
        if self.branch_deleted or self.branch_status != "preserved":
            raise TransactionError(
                "transactional closeout never deletes a branch"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "identity": self.identity,
            "path": self.path,
            "branch": self.branch,
            "reason": self.reason,
            "branch_deleted": self.branch_deleted,
            "branch_status": self.branch_status,
        }


@dataclass(frozen=True)
class TransactionReceipt:
    """The complete, deterministic account of one transactional closeout.

    Built from the journal, so it covers every workspace the transaction ever
    acted on — including removals completed by an earlier, interrupted run and
    preservations made deliberately on resume. ``digest`` identifies the whole
    receipt; identical inputs yield an identical digest.
    """

    schema_version: int
    run_id: str
    status: str
    resume: bool
    entries: List[ReceiptEntry]
    journal_digest: str
    digest: str = ""

    def payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_version": RECEIPT_VERSION,
            "run_id": self.run_id,
            "status": self.status,
            "resume": self.resume,
            "entries": [entry.to_dict() for entry in self.entries],
            "journal_digest": self.journal_digest,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = self.payload()
        data["digest"] = self.digest
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def removed(self) -> List[ReceiptEntry]:
        return [e for e in self.entries if e.kind is ReceiptEntryKind.REMOVED]

    def preserved(self) -> List[ReceiptEntry]:
        return [e for e in self.entries if e.kind is not ReceiptEntryKind.REMOVED]


def _receipt(
    *,
    run_id: str,
    status: str,
    resume: bool,
    entries: Sequence[ReceiptEntry],
    journal_digest: str,
) -> TransactionReceipt:
    if status not in (STATUS_COMMITTED, STATUS_INCOMPLETE):
        raise TransactionError(f"unknown transaction status {status!r}")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "receipt_version": RECEIPT_VERSION,
        "run_id": run_id,
        "status": status,
        "resume": resume,
        "entries": [entry.to_dict() for entry in entries],
        "journal_digest": journal_digest,
    }
    return TransactionReceipt(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        status=status,
        resume=resume,
        entries=list(entries),
        journal_digest=journal_digest,
        digest=_digest(payload),
    )


# --------------------------------------------------------------------------- #
# The transaction
# --------------------------------------------------------------------------- #


#: The receipt reasons that mark an outcome as *unproven* rather than an
#: ordinary, evidence-backed hold. ``interrupted_unproven`` is the caught
#: remover failure; ``absent_unverified`` is an absent workspace that no
#: record could prove un-removed (a lost tail, a bare ``PLANNED`` record, or a
#: missing journal), so a removal may already have landed. Both keep the
#: receipt ``INCOMPLETE`` and are never re-run.
_UNPROVEN_REASONS = frozenset({"interrupted_unproven", "absent_unverified"})


def _kind_for(state: str, reason: str) -> ReceiptEntryKind:
    if state == TransactionState.MUTATED.value:
        return ReceiptEntryKind.REMOVED
    if state == TransactionState.COMPENSATED.value:
        return ReceiptEntryKind.COMPENSATED
    # An attempt interrupted mid-removal — or one whose un-removal cannot be
    # proven — stays flagged as interrupted even after resume preserved it, so
    # the receipt never reads as an ordinary hold.
    if state in {s.value for s in _UNPROVEN_STATES} or reason in _UNPROVEN_REASONS:
        return ReceiptEntryKind.INTERRUPTED
    return ReceiptEntryKind.HELD


class CloseoutTransaction:
    """A resumable, receipt-complete closeout over an injected release policy.

    ``policy`` is the *existing* :class:`WorkspaceReleasePolicy`, whose removals
    run only through its injected ``worktree_remover``; this class never shells
    out and never touches a real worktree itself. ``manifests`` maps the path or
    identity of a workspace to its :class:`WorkspaceManifest`, which both the
    policy (for its evidence probe) and the receipt (for the branch name) need.

    ``journal_path`` is the durable transaction journal: it is read first for
    resume state, and each state is appended durably before the next is begun.
    ``remove`` is an optional ``identity -> bool`` override for the mutation
    seam; when omitted, the policy's own ``remove_worktree`` is used. ``False``
    from either means the workspace was already gone — a preservation, not an
    error.
    """

    def __init__(
        self,
        policy: WorkspaceReleasePolicy,
        *,
        journal_path: str,
        manifests: Optional[Mapping[str, Any]] = None,
        remove: Optional[Callable[[WorkspaceIdentity], bool]] = None,
    ):
        if not isinstance(policy, WorkspaceReleasePolicy):
            raise TransactionError(
                "transactional closeout requires a WorkspaceReleasePolicy, got "
                f"{type(policy).__name__}"
            )
        self.policy = policy
        self.journal_path = journal_path
        self._manifests = dict(manifests or {})
        self._remove = remove

    # -- manifest lookup ---------------------------------------------------- #

    def _manifest_for(self, identity: WorkspaceIdentity, path: str) -> Optional[WorkspaceManifest]:
        """The manifest naming ``identity``, keyed by its path or its key."""
        for candidate in (path, identity.key):
            manifest = self._manifests.get(candidate)
            if manifest is not None:
                return manifest
        return None

    def _branch_for(self, identity: WorkspaceIdentity, path: str) -> str:
        manifest = self._manifest_for(identity, path)
        branch = getattr(manifest, "branch", None)
        return branch if isinstance(branch, str) else ""

    # -- the mutation seam -------------------------------------------------- #

    def _perform_removal(
        self, identity: WorkspaceIdentity, path: str
    ) -> "tuple[bool, str]":
        """Attempt one removal, returning ``(removed, reason)``.

        The policy path is authoritative: it re-checks the injected evidence and
        holds fail-closed, and this method reports the policy's own hold reason
        verbatim. The explicit ``remove`` override, when supplied, is the test's
        fault-injection seam: its ``False`` is reported as ``already_absent``.
        """
        if self._remove is not None:
            return (bool(self._remove(identity)), "removed")
        manifest = self._manifest_for(identity, path)
        if manifest is None:
            # Without a manifest the policy would see "unknown" and hold. A
            # caller that cannot be named to the policy cannot be removed.
            return (False, "unknown")
        receipt = self.policy.remove_worktree(manifest)
        if receipt.outcome == "ok":
            return (True, "removed")
        if receipt.outcome == "noop":
            return (False, "already_absent")
        return (False, receipt.reason)

    # -- persistence -------------------------------------------------------- #

    def _persist(
        self,
        identity: WorkspaceIdentity,
        state: TransactionState,
        reason: str,
        path: str,
        branch: str,
    ) -> None:
        _append_journal(
            _journal_record(
                identity=identity,
                state=state,
                reason=reason,
                path=path,
                branch=branch,
            ),
            self.journal_path,
        )

    def _journal_lines_digest(self) -> str:
        """A digest over the durable journal's exact bytes, for the receipt."""
        try:
            data = Path(self.journal_path).read_bytes()
        except OSError:
            data = b""
        return hashlib.sha256(data).hexdigest()

    def _present(self, path: str) -> bool:
        """Whether the workspace for ``path`` is physically present on disk.

        This is the evidence the journal cannot substitute for: a lost append
        can drop any record, but it cannot conjure a workspace back. A blank
        path (no path could be composed) counts as absent, so nothing is ever
        mutated on a guess.
        """
        if not path:
            return False
        try:
            return Path(path).exists()
        except OSError:
            return False

    # -- the entry point ---------------------------------------------------- #

    def run(
        self,
        *,
        run_id: str,
        authorizations: Sequence[CleanupAuthorization],
    ) -> TransactionReceipt:
        """Drive every authorization through the transaction, resumably.

        Returns the complete receipt: every removal (this run's or a resumed
        run's) and every deliberate preservation. Calling ``run`` twice with the
        same journal performs no second removal.
        """
        collection = str(self.policy.collection)

        prior_records = read_journal(self.journal_path)
        prior = _latest_states(prior_records)
        resume = bool(prior_records)
        completed_in_pass = set()

        for authorization in authorizations:
            if not isinstance(authorization, CleanupAuthorization):
                raise TransactionError(
                    "transactional closeout requires a CleanupAuthorization, got "
                    f"{type(authorization).__name__}"
                )
            identity = authorization.identity
            if identity.key in completed_in_pass:
                continue
            completed_in_pass.add(identity.key)

            path = identity.path_under(collection)
            existing = prior.get(identity.key)

            # 1. Resume over proof: a recorded removal is never repeated,
            #    whatever is on disk now.
            if existing is not None and existing.state in {
                s.value for s in _REMOVAL_STATES
            }:
                continue

            # 2. Resume over doubt: an attempt interrupted mid-removal has no
            #    proof it completed, so it is deliberately preserved — once.
            #    The PRESERVED record then makes every later resume a no-op.
            if existing is not None and existing.state in {
                s.value for s in _UNPROVEN_STATES
            }:
                self._persist(
                    identity,
                    TransactionState.PRESERVED,
                    "interrupted_unproven",
                    path,
                    self._branch_for(identity, path),
                )
                continue

            # 3. Any other recorded state — PRESERVED (held or already absent,
            #    including an earlier resume) or COMPENSATED — is a deliberate
            #    outcome and is never re-attempted. Only PLANNED, or no record
            #    at all, proceeds: PLANNED means nothing was ever attempted.
            if existing is not None and existing.state != TransactionState.PLANNED.value:
                continue

            # 4. The lost-record gate. A ``PLANNED`` tail, a lost journal tail
            #    or an empty journal can reach here with no record proving the
            #    mutation never ran — and the mutation may have landed before
            #    its outcome was written. The journal cannot answer that, but
            #    the filesystem can: only a workspace that is still physically
            #    present can be provably un-removed. An absent one is preserved
            #    durably (the checkpoint), so no resume ever re-runs it.
            if not self._present(path):
                self._persist(
                    identity,
                    TransactionState.PRESERVED,
                    "absent_unverified",
                    path,
                    self._branch_for(identity, path),
                )
                continue

            branch = self._branch_for(identity, path)

            # 5. Plan: record that this identity is being attempted, before it
            #    is. A repeat of the same identity in one pass resumes above.
            self._persist(
                identity, TransactionState.PLANNED, "authorized", path, branch
            )

            # 6. Enter the mutation window. MUTATING is durable *before* the
            #    call, so an interruption is always discoverable as unproven.
            self._persist(
                identity, TransactionState.MUTATING, "entering_removal", path, branch
            )
            try:
                removed, reason = self._perform_removal(identity, path)
            except Exception:  # noqa: BLE001 - any remover failure leaves the
                # outcome unknown: the removal may or may not have landed. This
                # is an INTERRUPTED attempt, recorded distinctly from a genuine
                # hold so a resume preserves it instead of risking a repeat.
                self._persist(
                    identity,
                    TransactionState.INTERRUPTED,
                    "interrupted_unproven",
                    path,
                    branch,
                )
                continue

            if removed:
                self._persist(
                    identity, TransactionState.MUTATED, "removed", path, branch
                )
            else:
                self._persist(
                    identity,
                    TransactionState.PRESERVED,
                    reason if reason in _HELD_REASONS else "removal_unavailable",
                    path,
                    branch,
                )

        # Re-read the journal: the receipt is built from what is durably
        # recorded, so it covers prior runs' removals as well as this run's.
        latest = _latest_states(read_journal(self.journal_path))

        entries: List[ReceiptEntry] = []
        for key, record in latest.items():
            entries.append(
                ReceiptEntry(
                    kind=_kind_for(record.state, record.reason),
                    identity=key,
                    path=record.path,
                    branch=record.branch,
                    reason=record.reason,
                )
            )

        # A run is COMMITTED only when nothing in its account is flagged as an
        # interrupted, unproven attempt; anything less is INCOMPLETE, not failed.
        status = (
            STATUS_INCOMPLETE
            if any(entry.kind is ReceiptEntryKind.INTERRUPTED for entry in entries)
            else STATUS_COMMITTED
        )

        return _receipt(
            run_id=run_id,
            status=status,
            resume=resume,
            entries=entries,
            journal_digest=self._journal_lines_digest(),
        )
