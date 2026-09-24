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

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, FrozenSet, List, Mapping, Optional

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
]
