"""Workspace manifest contract (SW-155 / SW-WORKSPACE-001).

The default location for a worker's exclusive worktree is::

    <collection>/.worktrees/<repo>/<run>/<lane>

``collection`` is the directory that holds the primary checkout
(``<collection>/<repo>``). It is configurable; when it is not given it defaults
to the parent of the repository root, so the primary checkout stays clean —
worktrees live beside it, never inside it. This supersedes the previous
in-repo ``<repo>/.sw-worktrees`` location, which dirtied the primary checkout.

A workspace is described by a :class:`WorkspaceManifest`: the repo, the full
base and head SHAs, the branch, the run/lane/session identifiers, the declared
write scope, the lease, the last heartbeat, the lifecycle state and the
retention class. The manifest is the contract a worker and a host exchange to
prove which workspace is in play, without re-running git.

Legacy locations are *discoverable, never moved or deleted here*: the previous
in-repo ``.sw-worktrees`` directory and any ``wt-*`` worktrees are surfaced by
:func:`discover_legacy_worktree_locations` for a later migration/cleanup phase.
This phase only reads them.

Compatibility: this module is additive. The existing
``skillweave.workspace.GitWorktreeProvider`` is untouched; its ``acquire``
accepts a ``path`` argument, so the new default path can be handed to it
directly. Nothing here tears down a real worktree or branch.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, FrozenSet, List, Mapping, Optional

#: The new default worktree directory, under the collection root.
WORKTREES_DIRNAME = ".worktrees"

#: The previous in-repo worktree directory (discoverable, never moved/deleted).
LEGACY_SW_WORKTREES_DIRNAME = ".sw-worktrees"

#: The legacy ``wt-*`` worktree-name prefix (discoverable, never moved/deleted).
LEGACY_WT_PREFIX = "wt-"

#: A full SHA is 40 hexadecimal characters.
FULL_SHA_LENGTH = 40

#: The exact full-SHA shape the JSON schema enforces (``^[0-9a-f]{40}$``).
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

#: The retention classes a manifest may declare (mirrors the evidence schema).
RETENTION_VALUES = ("permanent", "temporary", "project_lifetime")

#: The exact set of top-level keys the schema permits (``additionalProperties``
#: is ``false`` there, so the parser must reject any other key).
MANIFEST_KEYS: FrozenSet[str] = frozenset(
    (
        "repo",
        "base_sha",
        "head_sha",
        "branch",
        "run",
        "lane",
        "session",
        "write_scope",
        "lease",
        "heartbeat",
        "state",
        "retention",
    )
)

#: The exact set of lease keys the schema permits.
LEASE_KEYS: FrozenSet[str] = frozenset(("lease_until", "owner"))


class WorkspaceState(str, Enum):
    """The lifecycle states a workspace manifest may declare."""

    PROVISIONED = "provisioned"
    ACTIVE = "active"
    LEASED = "leased"
    RELEASED = "released"
    EXPIRED = "expired"


class WorkspaceManifestError(ValueError):
    """A workspace manifest failed the contract.

    Raised fail-closed, before any consumer acts on the manifest, with the
    offending field named.
    """

    def __init__(self, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


def resolve_collection(repo_root: str, *, collection: Optional[str] = None) -> Path:
    """Resolve the collection root.

    The collection is configurable. When ``collection`` is omitted it defaults
    to the parent of ``repo_root`` — the directory that holds the primary
    checkout, so worktrees land beside it rather than inside it.

    Derivation is lexical: the caller's path is composed, never symlink
    canonicalised, so the returned location stays rooted at the collection the
    caller named.
    """
    if collection is not None:
        return Path(collection)
    return Path(repo_root).parent


def default_worktree_path(
    collection: str, *, repo: str, run: str, lane: str
) -> Path:
    """Return the configurable default worktree path.

    ``<collection>/.worktrees/<repo>/<run>/<lane>``. ``repo``, ``run`` and
    ``lane`` are expected to be single path components (no separators).
    """
    return Path(collection) / WORKTREES_DIRNAME / repo / run / lane


def worktree_path(
    repo_root: str,
    *,
    repo: Optional[str] = None,
    run: str,
    lane: str,
    collection: Optional[str] = None,
) -> Path:
    """Return the default worktree path derived from a repository checkout.

    The collection defaults to ``repo_root``'s parent and the repo name to the
    checkout's directory name; both may be overridden. This is the value to
    pass as ``path=`` to ``skillweave.workspace.GitWorktreeProvider.acquire``.
    """
    root = Path(repo_root)
    coll = resolve_collection(root, collection=collection)
    return default_worktree_path(coll, repo=repo or root.name, run=run, lane=lane)


def is_outside_primary_checkout(repo_root: str, path: str) -> bool:
    """True when ``path`` is not inside (nor equal to) the primary checkout.

    This is the invariant that keeps the primary checkout clean: a worktree at
    the new default path is a sibling of the checkout, never inside it.
    """
    root = Path(repo_root).resolve()
    target = Path(path).resolve()
    return not (target == root or root in target.parents)


def legacy_sw_worktrees_path(repo_root: str) -> Path:
    """Return the previous in-repo worktree location (discoverable only)."""
    return Path(repo_root) / LEGACY_SW_WORKTREES_DIRNAME


def discover_legacy_worktree_locations(collection: str, *, repo: str) -> List[Path]:
    """Read-only discovery of pre-contract worktree locations.

    Returns, in order:

    * the previous in-repo ``<repo>/.sw-worktrees`` directory; and
    * any ``wt-*`` directory directly under the collection or under its
      ``.worktrees`` directory.

    This phase never moves or deletes any of these: it only lists them so a
    later migration/cleanup phase can act deliberately.

    Locations are reported rooted at the caller-named collection (no symlink
    canonicalisation), so a caller can match them against paths it already has.
    """
    collection = Path(collection)
    locations: List[Path] = [legacy_sw_worktrees_path(collection / repo)]
    wt_entries: List[Path] = []
    for parent in (collection, collection / WORKTREES_DIRNAME):
        if parent.is_dir():
            wt_entries.extend(
                entry
                for entry in sorted(parent.glob(f"{LEGACY_WT_PREFIX}*"))
                if entry.is_dir()
            )
    return locations + wt_entries


def _require_nonempty_string(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceManifestError(
            f"'{key}' must be a non-empty string, got {value!r}", field=key
        )
    return value


def _require_known_keys(
    value: Mapping[str, Any], allowed: FrozenSet[str], *, prefix: str = ""
) -> None:
    """Fail-closed parity with the schema's ``additionalProperties: false``."""
    for key in value:
        if key not in allowed:
            field = f"{prefix}{key}"
            raise WorkspaceManifestError(
                f"disallowed property '{field}'", field=field
            )


def _is_full_sha(value: Any) -> bool:
    return isinstance(value, str) and FULL_SHA_PATTERN.fullmatch(value) is not None


def _require_full_sha(value: Any, key: str) -> str:
    if not _is_full_sha(value):
        raise WorkspaceManifestError(
            f"'{key}' must be a full 40-hex SHA, got {value!r}", field=key
        )
    return value


def _require_state(value: Any) -> str:
    allowed = {member.value for member in WorkspaceState}
    if value not in allowed:
        raise WorkspaceManifestError(
            f"'state' must be one of {sorted(allowed)}, got {value!r}", field="state"
        )
    return value


def _require_retention(value: Any) -> str:
    if value not in RETENTION_VALUES:
        raise WorkspaceManifestError(
            f"'retention' must be one of {list(RETENTION_VALUES)}, got {value!r}",
            field="retention",
        )
    return value


def _parse_write_scope(value: Any) -> List[str]:
    if not isinstance(value, list) or not value:
        raise WorkspaceManifestError(
            "'write_scope' must be a non-empty list of paths", field="write_scope"
        )
    return [_require_nonempty_string(entry, "write_scope") for entry in value]


def _parse_lease(value: Any) -> "Lease":
    if not isinstance(value, Mapping):
        raise WorkspaceManifestError("'lease' must be an object", field="lease")
    _require_known_keys(value, LEASE_KEYS, prefix="lease.")
    lease_until = _require_nonempty_string(value.get("lease_until"), "lease.lease_until")
    owner = value.get("owner")
    if owner is not None and not isinstance(owner, str):
        raise WorkspaceManifestError(
            "'lease.owner' must be a string", field="lease.owner"
        )
    return Lease(lease_until=lease_until, owner=owner)


@dataclass
class Lease:
    """The workspace lease: when it expires and who holds it."""

    lease_until: str
    owner: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"lease_until": self.lease_until}
        if self.owner is not None:
            data["owner"] = self.owner
        return data


@dataclass
class WorkspaceManifest:
    """The machine-readable facts of one acquired workspace.

    ``base_sha`` and ``head_sha`` are full 40-hex SHAs (base is the pinned
    starting commit; head is where the branch currently is). ``write_scope`` is
    a non-empty list of paths the workspace may write. ``lease`` records the
    lease deadline and holder; ``heartbeat`` is the last heartbeat timestamp;
    ``state`` and ``retention`` are drawn from the module's vocabularies.
    """

    repo: str
    base_sha: str
    head_sha: str
    branch: str
    run: str
    lane: str
    session: str
    write_scope: List[str]
    lease: Lease
    heartbeat: str
    state: str
    retention: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "branch": self.branch,
            "run": self.run,
            "lane": self.lane,
            "session": self.session,
            "write_scope": list(self.write_scope),
            "lease": self.lease.to_dict(),
            "heartbeat": self.heartbeat,
            "state": self.state,
            "retention": self.retention,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorkspaceManifest":
        """Parse and fail-closed validate a manifest mapping.

        Raises :class:`WorkspaceManifestError` on any missing, short-SHA, or
        out-of-vocabulary field — before any consumer acts on the manifest.
        """
        if not isinstance(data, Mapping):
            raise WorkspaceManifestError("manifest must be a mapping", field=None)
        _require_known_keys(data, MANIFEST_KEYS)
        return cls(
            repo=_require_nonempty_string(data.get("repo"), "repo"),
            base_sha=_require_full_sha(data.get("base_sha"), "base_sha"),
            head_sha=_require_full_sha(data.get("head_sha"), "head_sha"),
            branch=_require_nonempty_string(data.get("branch"), "branch"),
            run=_require_nonempty_string(data.get("run"), "run"),
            lane=_require_nonempty_string(data.get("lane"), "lane"),
            session=_require_nonempty_string(data.get("session"), "session"),
            write_scope=_parse_write_scope(data.get("write_scope")),
            lease=_parse_lease(data.get("lease")),
            heartbeat=_require_nonempty_string(data.get("heartbeat"), "heartbeat"),
            state=_require_state(data.get("state")),
            retention=_require_retention(data.get("retention")),
        )


# --- Release lifecycle (SW-155 / SW-155-WORKSPACE-002) ---------------------
#
# The manifest contract above says *what* a workspace is. This block says how
# it is released, fail-closed. Three operations, deliberately not fused:
#
#   1. ``release_lease``   — drop the lease only;
#   2. ``remove_worktree`` — remove the worktree only, and only when the facts
#      prove it safe;
#   3. ``delete_branch``   — a separate action, disabled unless explicitly
#      authorized for the exact branch.
#
# Facts arrive through an injected ``evidence_probe`` and mutations through
# injected callables. This module never shells out and never touches a real
# worktree: an absent or unusable probe is *unknown*, and unknown holds.

#: The outcomes an attempt can yield: acted, refused (fail-closed), or already
#: in the requested terminal state.
RELEASE_OUTCOMES = ("ok", "hold", "noop")

#: Every reason code an attempt can carry. ``hold`` is always one of the
#: blocking facts; ``noop`` is always an already-satisfied state.
RELEASE_REASONS = (
    "lease_released",
    "lease_absent",
    "worktree_removed",
    "worktree_absent",
    "branch_deleted",
    "branch_absent",
    "branch_deletion_disabled",
    "branch_authorization_mismatch",
    "removal_blocked",
    "dirty",
    "unreachable",
    "active_lease",
    "active_process",
    "unknown",
)

#: The recognized worktree evidence values. Anything else is coerced to
#: ``unknown``, which holds removal.
WORKTREE_EVIDENCE = ("clean", "dirty", "unreachable", "absent", "unknown")

#: The recognized lease evidence values. Only ``active`` blocks removal.
LEASE_EVIDENCE = ("active", "released", "absent", "unknown")

#: The recognized process/session evidence values. Only ``active`` blocks.
PROCESS_EVIDENCE = ("active", "inactive", "unknown")


class WorkspaceReleaseError(ValueError):
    """A release attempt was refused fail-closed before it could act.

    Raised only for structurally unusable input (for example, a non-manifest).
    Every *decision* about a valid manifest is reported as a receipt, never an
    exception, so HOLD and no-op outcomes stay observable and deterministic.
    """


@dataclass(frozen=True)
class WorkspaceEvidence:
    """The facts a release decision runs on.

    Every dimension is injected, never probed by this module. An unrecognized
    value is treated as ``unknown`` by the policy, and unknown holds: absence
    of proof is never read as proof of absence.
    """

    worktree: str = "unknown"
    lease: str = "unknown"
    process: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "worktree": self.worktree,
            "lease": self.lease,
            "process": self.process,
        }


@dataclass(frozen=True)
class BranchDeletionAuthorization:
    """Explicit authorization to delete one named branch.

    Deletion is a separate action and defaults to disabled. When supplied, the
    ``branch`` must name the exact branch to delete — an authorization for a
    different branch is refused, never retargeted.
    """

    branch: str
    authorized_by: str

    def __post_init__(self) -> None:
        if not isinstance(self.branch, str) or not self.branch.strip():
            raise WorkspaceReleaseError(
                "branch authorization must name a branch", field=None
            )
        if not isinstance(self.authorized_by, str) or not self.authorized_by.strip():
            raise WorkspaceReleaseError(
                "branch authorization must name an authorizer"
            )


def _receipt_digest(
    action: str, outcome: str, reason: str, path: str, branch: str
) -> str:
    payload = json.dumps(
        {
            "action": action,
            "outcome": outcome,
            "reason": reason,
            "path": path,
            "branch": branch,
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ReleaseReceipt:
    """A deterministic record of one release attempt.

    Deterministic means: identical inputs yield an identical receipt, including
    its ``digest``. It carries no timestamp and no host-local detail. Every
    attempt — ``ok``, ``hold`` or ``noop`` — produces one.
    """

    action: str
    outcome: str
    reason: str
    path: str
    branch: str
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "outcome": self.outcome,
            "reason": self.reason,
            "path": self.path,
            "branch": self.branch,
            "digest": self.digest,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def _receipt(
    action: str, outcome: str, reason: str, path: str, branch: str
) -> ReleaseReceipt:
    if outcome not in RELEASE_OUTCOMES:
        raise WorkspaceReleaseError(f"unknown outcome {outcome!r}")
    if reason not in RELEASE_REASONS:
        raise WorkspaceReleaseError(f"unknown reason {reason!r}")
    return ReleaseReceipt(
        action=action,
        outcome=outcome,
        reason=reason,
        path=path,
        branch=branch,
        digest=_receipt_digest(action, outcome, reason, path, branch),
    )


def _hold(action: str, reason: str, path: str, branch: str) -> ReleaseReceipt:
    return _receipt(action, "hold", reason, path, branch)


def _known(value: Any, allowed: tuple) -> str:
    return value if value in allowed else "unknown"


def _removal_blocker(worktree: str, lease: str, process: str) -> Optional[str]:
    """Return the reason removal must be held, or ``None`` when it may proceed.

    Fail-closed order: unavailable facts first, then the unsafe states.
    """
    if worktree == "unknown" or lease == "unknown" or process == "unknown":
        return "unknown"
    if worktree == "unreachable":
        return "unreachable"
    if worktree == "dirty":
        return "dirty"
    if lease == "active":
        return "active_lease"
    if process == "active":
        return "active_process"
    return None


class WorkspaceReleasePolicy:
    """Fail-closed release lifecycle over an injected evidence/mutation seam.

    ``evidence_probe(manifest) -> WorkspaceEvidence`` reports the facts;
    ``lease_releaser(manifest) -> bool``, ``worktree_remover(path) -> bool`` and
    ``branch_deleter(branch) -> bool`` perform the three mutations. A ``bool``
    of ``False`` means the target was already gone (a no-op, not an error).

    With no probe injected, every fact is unknown and every mutating operation
    holds — the default is inert. This class never shells out and never removes
    or deletes anything itself: only the injected callables act.
    """

    def __init__(
        self,
        repo_root: str,
        *,
        collection: Optional[str] = None,
        evidence_probe: Optional[Callable[[WorkspaceManifest], WorkspaceEvidence]] = None,
        worktree_remover: Optional[Callable[[Path], bool]] = None,
        branch_deleter: Optional[Callable[[str], bool]] = None,
        lease_releaser: Optional[Callable[[WorkspaceManifest], bool]] = None,
    ):
        self.repo_root = Path(repo_root)
        self.collection = resolve_collection(self.repo_root, collection=collection)
        self._evidence_probe = evidence_probe
        self._worktree_remover = worktree_remover
        self._branch_deleter = branch_deleter
        self._lease_releaser = lease_releaser

    @staticmethod
    def _require_manifest(manifest: Any) -> WorkspaceManifest:
        if not isinstance(manifest, WorkspaceManifest):
            raise WorkspaceReleaseError(
                "release policy requires a WorkspaceManifest, got "
                f"{type(manifest).__name__}"
            )
        return manifest

    def _path(self, manifest: WorkspaceManifest) -> str:
        return str(
            worktree_path(
                str(self.repo_root),
                repo=manifest.repo,
                run=manifest.run,
                lane=manifest.lane,
                collection=str(self.collection),
            )
        )

    def _evidence(self, manifest: WorkspaceManifest) -> WorkspaceEvidence:
        probe = self._evidence_probe
        if probe is None:
            return WorkspaceEvidence()
        try:
            evidence = probe(manifest)
        except Exception:  # noqa: BLE001 - any probe failure is unknown
            return WorkspaceEvidence()
        if not isinstance(evidence, WorkspaceEvidence):
            return WorkspaceEvidence()
        return evidence

    def release_lease(self, manifest: WorkspaceManifest) -> ReleaseReceipt:
        """Release the lease only: no worktree removal, no branch deletion."""
        manifest = self._require_manifest(manifest)
        path = self._path(manifest)
        lease = _known(self._evidence(manifest).lease, LEASE_EVIDENCE)
        if lease == "unknown":
            return _hold("release_lease", "unknown", path, manifest.branch)
        if lease in ("released", "absent"):
            return _receipt(
                "release_lease", "noop", "lease_absent", path, manifest.branch
            )
        if self._lease_releaser is None:
            return _hold("release_lease", "unknown", path, manifest.branch)
        if not self._lease_releaser(manifest):
            return _hold("release_lease", "unknown", path, manifest.branch)
        return _receipt(
            "release_lease", "ok", "lease_released", path, manifest.branch
        )

    def remove_worktree(self, manifest: WorkspaceManifest) -> ReleaseReceipt:
        """Remove the worktree only, gated by the injected facts.

        Dirty, unreachable, active lease, active process and unknown all hold.
        Branch deletion is never implied by removal.
        """
        manifest = self._require_manifest(manifest)
        path = self._path(manifest)
        evidence = self._evidence(manifest)
        worktree = _known(evidence.worktree, WORKTREE_EVIDENCE)
        lease = _known(evidence.lease, LEASE_EVIDENCE)
        process = _known(evidence.process, PROCESS_EVIDENCE)

        blocker = _removal_blocker(worktree, lease, process)
        if blocker is not None:
            return _hold("remove_worktree", blocker, path, manifest.branch)
        if worktree == "absent":
            return _receipt(
                "remove_worktree", "noop", "worktree_absent", path, manifest.branch
            )
        if self._worktree_remover is None:
            return _hold("remove_worktree", "unknown", path, manifest.branch)
        if not self._worktree_remover(Path(path)):
            return _receipt(
                "remove_worktree", "noop", "worktree_absent", path, manifest.branch
            )
        return _receipt(
            "remove_worktree", "ok", "worktree_removed", path, manifest.branch
        )

    def delete_branch(
        self,
        manifest: WorkspaceManifest,
        *,
        authorization: Optional[BranchDeletionAuthorization] = None,
    ) -> ReleaseReceipt:
        """Delete the branch only when explicitly authorized for it.

        Disabled by default. An authorization naming a different branch is
        refused (held), never retargeted. Removal is never a precondition this
        method checks: the caller decides the order.
        """
        manifest = self._require_manifest(manifest)
        path = self._path(manifest)
        if authorization is None:
            return _receipt(
                "delete_branch",
                "noop",
                "branch_deletion_disabled",
                path,
                manifest.branch,
            )
        if not isinstance(authorization, BranchDeletionAuthorization):
            return _hold("delete_branch", "unknown", path, manifest.branch)
        if authorization.branch != manifest.branch:
            return _hold(
                "delete_branch",
                "branch_authorization_mismatch",
                path,
                manifest.branch,
            )
        if self._branch_deleter is None:
            return _hold("delete_branch", "unknown", path, manifest.branch)
        if not self._branch_deleter(manifest.branch):
            return _receipt(
                "delete_branch", "noop", "branch_absent", path, manifest.branch
            )
        return _receipt("delete_branch", "ok", "branch_deleted", path, manifest.branch)

    def release_workspace(
        self,
        manifest: WorkspaceManifest,
        *,
        branch_authorization: Optional[BranchDeletionAuthorization] = None,
    ) -> tuple:
        """Run the three steps in order, without ever chaining them implicitly.

        Returns the three receipts. Branch deletion is attempted only when
        removal did not hold; when removal held, the branch receipt is itself a
        HOLD (reason ``removal_blocked``) and no deletion is attempted even if
        authorized.
        """
        manifest = self._require_manifest(manifest)
        lease = self.release_lease(manifest)
        removal = self.remove_worktree(manifest)
        if removal.outcome == "hold":
            branch = _hold(
                "delete_branch", "removal_blocked", self._path(manifest), manifest.branch
            )
        else:
            branch = self.delete_branch(manifest, authorization=branch_authorization)
        return (lease, removal, branch)


__all__ = [
    "WORKTREES_DIRNAME",
    "LEGACY_SW_WORKTREES_DIRNAME",
    "LEGACY_WT_PREFIX",
    "FULL_SHA_LENGTH",
    "RETENTION_VALUES",
    "WorkspaceState",
    "WorkspaceManifestError",
    "Lease",
    "WorkspaceManifest",
    "resolve_collection",
    "default_worktree_path",
    "worktree_path",
    "is_outside_primary_checkout",
    "legacy_sw_worktrees_path",
    "discover_legacy_worktree_locations",
    "RELEASE_OUTCOMES",
    "RELEASE_REASONS",
    "WORKTREE_EVIDENCE",
    "LEASE_EVIDENCE",
    "PROCESS_EVIDENCE",
    "WorkspaceReleaseError",
    "WorkspaceEvidence",
    "BranchDeletionAuthorization",
    "ReleaseReceipt",
    "WorkspaceReleasePolicy",
]
