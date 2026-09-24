"""Read-only multi-repository workspace inventory (SW-155-HEALTH-001).

This module sits on top of the SW-155 / SW-WORKSPACE-001 contract in
:mod:`skillweave.routing.workspace`, consumed **read-only**. It answers, for a
collection of repositories, *what workspaces exist and what state is each in*,
without ever creating a directory, moving a path or mutating git/filesystem
state.

Each :class:`WorkspaceRow` reports a finite :class:`Classification` plus a
human-readable ``reason`` and covers the ten required dimensions as finite enum
values:

* :class:`RegistrationState` - git worktree registration;
* :class:`ExistenceState` - filesystem existence of the registered path;
* :class:`DirtyState` - clean / dirty working tree;
* :class:`HeadState` - branch or detached HEAD;
* :class:`UpstreamState` - ahead / behind / diverged relative to upstream;
* :class:`ReachabilityState` - the pinned base commit reachable from the head;
* :class:`LeaseState` - manifest lease active / expired / absent;
* :class:`EvidenceState` (process) - live active-process evidence;
* :class:`EvidenceState` (session) - live session/heartbeat evidence;
* :class:`DiskState` - measured disk use.

**Unknown is a first-class, finite value.** Every dimension has an explicit
``UNKNOWN`` member (``ABSENT`` where "no record" is itself the fact). When
evidence is unavailable, the row's ``classification`` is never ``HEALTHY``:
either a *definite* adverse finding wins (unregistered, missing, unreachable,
expired lease) or, absent one, the row is classified ``UNKNOWN``. Unavailable
evidence is never silently collapsed into a safe state.

Read-only discipline:

* only ``git`` verbs that read are run, all under ``--no-optional-locks`` so
  ``status`` never rewrites the index;
* no ``git worktree prune/add/remove``, no ``git gc``, no branch operations;
* ``os.walk``/``lstat``/``exists`` are used for size and existence, never
  ``mkdir``/``resolve`` that would materialise a path;
* legacy ``.sw-worktrees`` / ``wt-*`` locations are surfaced, never moved.

The module is deliberately additive: it lives inside the existing
``skillweave.repo_health`` package and does not touch the manifest contract.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from skillweave.routing.workspace import (
    LEGACY_SW_WORKTREES_DIRNAME,
    WORKTREES_DIRNAME,
    WorkspaceManifest,
    WorkspaceManifestError,
    discover_legacy_worktree_locations,
)

#: The single sentinel value every "we could not tell" enum member shares.
UNKNOWN = "unknown"

#: The default session/heartbeat freshness window, in seconds.
DEFAULT_SESSION_TTL_SECONDS = 3600.0

#: How deep to look for workspace-like (``.git``-bearing) directories under
#: ``<collection>/.worktrees/<repo>`` (``<run>/<lane>`` is depth 2).
_MAX_WORKSPACE_DEPTH = 4


class RegistrationState(str, Enum):
    """Whether a path is registered with git as a worktree."""

    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    UNKNOWN = UNKNOWN


class ExistenceState(str, Enum):
    """Whether the path exists on the filesystem."""

    PRESENT = "present"
    MISSING = "missing"
    UNKNOWN = UNKNOWN


class DirtyState(str, Enum):
    """Whether the working tree has uncommitted changes."""

    CLEAN = "clean"
    DIRTY = "dirty"
    UNKNOWN = UNKNOWN


class HeadState(str, Enum):
    """Whether HEAD is on a branch or detached."""

    BRANCH = "branch"
    DETACHED = "detached"
    UNKNOWN = UNKNOWN


class UpstreamState(str, Enum):
    """Position of HEAD relative to its configured upstream."""

    UP_TO_DATE = "up_to_date"
    AHEAD = "ahead"
    BEHIND = "behind"
    DIVERGED = "diverged"
    NO_UPSTREAM = "no_upstream"
    UNKNOWN = UNKNOWN


class ReachabilityState(str, Enum):
    """Whether the manifest's pinned base is reachable from the head."""

    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    UNKNOWN = UNKNOWN


class LeaseState(str, Enum):
    """State of the workspace manifest's lease."""

    ACTIVE = "active"
    EXPIRED = "expired"
    ABSENT = "absent"
    UNKNOWN = UNKNOWN


class EvidenceState(str, Enum):
    """Active-process / live-session evidence, as a finite state."""

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = UNKNOWN


class DiskState(str, Enum):
    """Whether disk use could be measured."""

    MEASURED = "measured"
    UNKNOWN = UNKNOWN


class LocationKind(str, Enum):
    """What kind of location a row describes."""

    WORKTREE = "worktree"
    LEGACY_SW_WORKTREES = "legacy_sw_worktrees"
    LEGACY_WT = "legacy_wt"
    UNREGISTERED = "unregistered"


class Classification(str, Enum):
    """The finite health classification of one inventory row."""

    HEALTHY = "healthy"
    DIRTY = "dirty"
    DETACHED = "detached"
    STALE = "stale"
    ORPHANED = "orphaned"
    UNMANAGED = "unmanaged"
    UNKNOWN = UNKNOWN


@dataclass
class WorkspaceRow:
    """One workspace-like location and its read-only health facts."""

    path: str
    repo: str
    kind: LocationKind
    registration: RegistrationState
    existence: ExistenceState
    dirtiness: DirtyState
    head: HeadState
    upstream: UpstreamState
    reachability: ReachabilityState
    lease: LeaseState
    process: EvidenceState
    session: EvidenceState
    disk: DiskState
    disk_bytes: Optional[int]
    classification: Classification
    reason: str

    @property
    def evidence_available(self) -> bool:
        """True only when no dimension is explicitly UNKNOWN."""
        states = (
            self.registration,
            self.existence,
            self.dirtiness,
            self.head,
            self.upstream,
            self.reachability,
            self.lease,
            self.process,
            self.session,
            self.disk,
        )
        return all(state is not None and state.value != UNKNOWN for state in states)


@dataclass
class WorkspaceInventory:
    """The result of one read-only inventory pass."""

    collection: str
    rows: List[WorkspaceRow] = field(default_factory=list)

    def row_for(self, path: str) -> WorkspaceRow:
        """Return the row for ``path``, or raise ``KeyError``.

        Matching is symlink-tolerant: git may report a worktree path with the
        canonicalised prefix (``/private/var`` on macOS) while the caller names
        the lexical one (``/var``).
        """
        for row in self.rows:
            if _same_location(row.path, path):
                return row
        raise KeyError(path)

    @property
    def unregistered_paths(self) -> List[str]:
        """Every surfaced path git does not know as a worktree."""
        return [
            row.path
            for row in self.rows
            if row.registration is RegistrationState.UNREGISTERED
        ]

    def by_classification(self) -> Dict[str, List[WorkspaceRow]]:
        """Group rows by their classification value."""
        grouped: Dict[str, List[WorkspaceRow]] = {}
        for row in self.rows:
            grouped.setdefault(row.classification.value, []).append(row)
        return grouped


# --------------------------------------------------------------------------- #
# lexical path helpers (never resolve symlinks; the caller's path is preserved)
# --------------------------------------------------------------------------- #
def _norm(path: Any) -> str:
    return os.path.normpath(os.path.abspath(str(path)))


def _same_location(a: str, b: str) -> bool:
    if _norm(a) == _norm(b):
        return True
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# timestamp parsing
# --------------------------------------------------------------------------- #
def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _reference_now(now: Optional[str]) -> datetime:
    parsed = _parse_ts(now)
    return parsed if parsed is not None else datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# git: read-only invocations only
# --------------------------------------------------------------------------- #
def _git_read(cwd: str, *args: str) -> Optional[subprocess.CompletedProcess]:
    """Run a read-only git command; ``None`` when git itself is unavailable."""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError:
        return None


def _parse_worktree_list(text: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for line in text.splitlines():
        if line.startswith("worktree "):
            if current is not None:
                entries.append(current)
            current = {
                "path": line[len("worktree "):].strip(),
                "detached": False,
                "prunable": False,
            }
        elif current is None:
            continue
        elif line.strip() == "detached":
            current["detached"] = True
        elif line.startswith("prunable"):
            current["prunable"] = True
    if current is not None:
        entries.append(current)
    return entries


def _registered_entries(primary: str) -> Tuple[Optional[List[Dict[str, Any]]], bool]:
    """Return (entries, git_available) for a primary checkout."""
    result = _git_read(primary, "worktree", "list", "--porcelain")
    if result is None:
        return None, False
    if result.returncode != 0:
        return [], True
    return _parse_worktree_list(result.stdout), True


def _dirty_state(path: str) -> DirtyState:
    result = _git_read(path, "status", "--porcelain=v1", "--untracked-files=normal")
    if result is None or result.returncode != 0:
        return DirtyState.UNKNOWN
    return DirtyState.CLEAN if not result.stdout.strip() else DirtyState.DIRTY


def _head_state(path: str) -> HeadState:
    result = _git_read(path, "symbolic-ref", "-q", "HEAD")
    if result is None:
        return HeadState.UNKNOWN
    if result.returncode == 0 and result.stdout.strip():
        return HeadState.BRANCH
    if result.returncode == 1:
        return HeadState.DETACHED
    return HeadState.UNKNOWN


def _upstream_state(path: str) -> UpstreamState:
    result = _git_read(
        path, "rev-list", "--left-right", "--count", "@{upstream}...HEAD"
    )
    if result is None:
        return UpstreamState.UNKNOWN
    if result.returncode != 0:
        stderr = (result.stderr or "").lower()
        if "no upstream" in stderr or "does not have an upstream" in stderr:
            return UpstreamState.NO_UPSTREAM
        return UpstreamState.UNKNOWN
    parts = result.stdout.split()
    if len(parts) != 2:
        return UpstreamState.UNKNOWN
    try:
        behind, ahead = int(parts[0]), int(parts[1])
    except ValueError:
        return UpstreamState.UNKNOWN
    if behind and ahead:
        return UpstreamState.DIVERGED
    if ahead:
        return UpstreamState.AHEAD
    if behind:
        return UpstreamState.BEHIND
    return UpstreamState.UP_TO_DATE


def _commit_present(primary: str, sha: str) -> bool:
    result = _git_read(primary, "cat-file", "-e", f"{sha}^{{commit}}")
    return result is not None and result.returncode == 0


def _reachability(primary: str, manifest: Optional[WorkspaceManifest]) -> ReachabilityState:
    if manifest is None:
        return ReachabilityState.UNKNOWN
    base, head = manifest.base_sha, manifest.head_sha
    if not _commit_present(primary, base) or not _commit_present(primary, head):
        return ReachabilityState.UNREACHABLE
    result = _git_read(primary, "merge-base", "--is-ancestor", base, head)
    if result is None:
        return ReachabilityState.UNKNOWN
    if result.returncode == 0:
        return ReachabilityState.REACHABLE
    if result.returncode == 1:
        return ReachabilityState.UNREACHABLE
    return ReachabilityState.UNKNOWN


# --------------------------------------------------------------------------- #
# manifest-derived signals
# --------------------------------------------------------------------------- #
def _coerce_manifest(value: Any) -> Tuple[Optional[WorkspaceManifest], bool]:
    """Return (manifest, unreadable). An unreadable manifest is not ABSENT."""
    if value is None:
        return None, False
    if isinstance(value, WorkspaceManifest):
        return value, False
    if isinstance(value, Mapping):
        try:
            return WorkspaceManifest.from_dict(value), False
        except WorkspaceManifestError:
            return None, True
    if hasattr(value, "base_sha") and hasattr(value, "lease"):
        return value, False
    return None, True


def _lease_state(
    manifest: Optional[WorkspaceManifest], unreadable: bool, now: datetime
) -> LeaseState:
    if unreadable:
        return LeaseState.UNKNOWN
    if manifest is None:
        return LeaseState.ABSENT
    lease_until = _parse_ts(getattr(getattr(manifest, "lease", None), "lease_until", None))
    if lease_until is None:
        return LeaseState.UNKNOWN
    return LeaseState.ACTIVE if lease_until > now else LeaseState.EXPIRED


def _session_state(
    manifest: Optional[WorkspaceManifest],
    unreadable: bool,
    now: datetime,
    ttl_seconds: float,
) -> EvidenceState:
    if unreadable:
        return EvidenceState.UNKNOWN
    if manifest is None:
        return EvidenceState.ABSENT
    heartbeat = _parse_ts(getattr(manifest, "heartbeat", None))
    if heartbeat is None:
        return EvidenceState.UNKNOWN
    return (
        EvidenceState.PRESENT
        if (now - heartbeat).total_seconds() <= ttl_seconds
        else EvidenceState.ABSENT
    )


def _default_pid_alive(pid: int) -> Optional[bool]:
    """Read-only liveness probe. ``None`` means the answer is unavailable."""
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _process_state(
    path: str,
    processes: Optional[Mapping[str, Sequence[int]]],
    pid_alive: Callable[[int], Optional[bool]],
) -> EvidenceState:
    if processes is None:
        return EvidenceState.UNKNOWN
    pids: Optional[Sequence[int]] = None
    for key, value in processes.items():
        if _same_location(key, path):
            pids = value
            break
    if pids is None:
        return EvidenceState.UNKNOWN
    candidates = list(pids)
    if not candidates:
        return EvidenceState.ABSENT
    saw_unknown = False
    for pid in candidates:
        try:
            alive = pid_alive(pid)
        except OSError:
            alive = None
        if alive is True:
            return EvidenceState.PRESENT
        if alive is None:
            saw_unknown = True
    return EvidenceState.UNKNOWN if saw_unknown else EvidenceState.ABSENT


# --------------------------------------------------------------------------- #
# filesystem signals
# --------------------------------------------------------------------------- #
def _existence_state(path: str) -> ExistenceState:
    try:
        return ExistenceState.PRESENT if os.path.exists(path) else ExistenceState.MISSING
    except OSError:
        return ExistenceState.UNKNOWN


def _disk_usage(path: str) -> Tuple[DiskState, Optional[int]]:
    if not os.path.exists(path):
        return DiskState.UNKNOWN, None
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
            for name in filenames:
                try:
                    total += os.lstat(os.path.join(dirpath, name)).st_size
                except OSError:
                    return DiskState.UNKNOWN, None
    except OSError:
        return DiskState.UNKNOWN, None
    return DiskState.MEASURED, total


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def _classify(row: WorkspaceRow) -> Tuple[Classification, str]:
    """Map finite signals to a finite classification plus reason.

    A *definite* adverse finding outranks unavailable evidence: a missing
    directory is MISSING even if its dirtiness cannot be read. Only with no
    definite finding does unavailable evidence make the row UNKNOWN — never
    HEALTHY.
    """
    if row.registration is RegistrationState.UNREGISTERED:
        return (
            Classification.ORPHANED,
            "workspace-like path is not registered with git",
        )
    if row.existence is ExistenceState.MISSING:
        return Classification.STALE, "registered worktree directory is missing"
    if row.reachability is ReachabilityState.UNREACHABLE:
        return (
            Classification.ORPHANED,
            "pinned base commit is not reachable from the workspace head",
        )
    if row.lease is LeaseState.EXPIRED:
        return Classification.STALE, "workspace lease has expired"
    if row.lease is LeaseState.ABSENT:
        return (
            Classification.UNMANAGED,
            "no workspace manifest: lease and session ownership are unrecorded",
        )

    unknown = [
        name
        for name, state in (
            ("registration", row.registration),
            ("existence", row.existence),
            ("dirtiness", row.dirtiness),
            ("head", row.head),
            ("upstream", row.upstream),
            ("reachability", row.reachability),
            ("lease", row.lease),
            ("process", row.process),
            ("session", row.session),
            ("disk", row.disk),
        )
        if state.value == UNKNOWN
    ]
    if unknown:
        return (
            Classification.UNKNOWN,
            "unknown/unavailable evidence: " + ", ".join(unknown),
        )

    if row.dirtiness is DirtyState.DIRTY:
        return Classification.DIRTY, "working tree has uncommitted changes (dirty)"
    if row.head is HeadState.DETACHED:
        return Classification.DETACHED, "HEAD is detached; no branch is checked out"
    if row.upstream in (UpstreamState.BEHIND, UpstreamState.DIVERGED):
        return (
            Classification.STALE,
            f"branch is {row.upstream.value} relative to its upstream",
        )
    if row.session is EvidenceState.ABSENT:
        return Classification.STALE, "session heartbeat is stale; no live owner evidence"
    return (
        Classification.HEALTHY,
        "registered, present, clean, on a branch, reachable, lease active, evidence present",
    )


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def _discover_repos(collection: str) -> List[str]:
    root = os.path.abspath(collection)
    if not os.path.isdir(root):
        return []
    repos: List[str] = []
    for name in sorted(os.listdir(root)):
        candidate = os.path.join(root, name)
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, ".git")):
            repos.append(name)
    return repos


def _scan_workspace_like(root: str) -> List[str]:
    """Directories below ``root`` that carry a ``.git`` (dir or file)."""
    found: List[str] = []

    def walk(directory: str, depth: int) -> None:
        if depth > _MAX_WORKSPACE_DEPTH:
            return
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            return
        for name in names:
            child = os.path.join(directory, name)
            if not os.path.isdir(child):
                continue
            if os.path.exists(os.path.join(child, ".git")):
                found.append(child)
            else:
                walk(child, depth + 1)

    walk(os.path.abspath(root), 1)
    return found


def _legacy_kind(path: str) -> LocationKind:
    parts = os.path.normpath(path).split(os.sep)
    if LEGACY_SW_WORKTREES_DIRNAME in parts:
        return LocationKind.LEGACY_SW_WORKTREES
    return LocationKind.LEGACY_WT


def _repo_for_legacy(collection: str, path: str, repos: Sequence[str]) -> str:
    parent = os.path.basename(os.path.dirname(os.path.normpath(path)))
    return parent if parent in repos else ""


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def inventory_workspaces(
    collection: str,
    *,
    repos: Optional[Sequence[str]] = None,
    manifests: Optional[Mapping[str, Any]] = None,
    processes: Optional[Mapping[str, Sequence[int]]] = None,
    now: Optional[str] = None,
    session_ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
    pid_alive: Optional[Callable[[int], Optional[bool]]] = None,
) -> WorkspaceInventory:
    """Inventory every workspace-like location under ``collection``.

    ``collection`` is the directory that holds the primary checkouts
    (``<collection>/<repo>``); worktrees live under
    ``<collection>/.worktrees/<repo>/<run>/<lane>``. ``repos`` restricts the
    pass; by default every immediate child carrying a ``.git`` is a repo.

    ``manifests`` maps a worktree path to a :class:`WorkspaceManifest` (or its
    mapping form) and supplies lease/session/reachability evidence.
    ``processes`` maps a worktree path to candidate PIDs; without it, process
    evidence is ``UNKNOWN`` rather than optimistically absent. ``now`` is the
    reference timestamp for lease/session freshness.

    Nothing here creates a directory or mutates git/filesystem state.
    """
    root = os.path.abspath(collection)
    inventory = WorkspaceInventory(collection=root)
    reference = _reference_now(now)
    probe = pid_alive or _default_pid_alive
    manifest_map = manifests or {}

    repo_names = list(repos) if repos is not None else _discover_repos(root)

    # Ordered, deduplicated candidate map keyed by lexical location.
    seen: List[str] = []
    candidates: List[Dict[str, Any]] = []

    def _add(path: str, repo: str, kind: LocationKind, registered: bool,
             primary: str, unknown: bool = False) -> None:
        for existing in seen:
            if _same_location(existing, path):
                return
        seen.append(path)
        candidates.append(
            {
                "path": path,
                "repo": repo,
                "kind": kind,
                "registered": registered,
                "primary": primary,
                "unknown": unknown,
            }
        )

    for repo in repo_names:
        primary = os.path.join(root, repo)
        entries, git_available = _registered_entries(primary)
        entries = entries or []

        registered_paths = [
            entry["path"]
            for entry in entries
            if not _same_location(entry["path"], primary)
        ]

        # 1. workspace-like directories under <collection>/.worktrees/<repo>
        worktree_root = os.path.join(root, WORKTREES_DIRNAME, repo)
        if os.path.isdir(worktree_root):
            for scanned in _scan_workspace_like(worktree_root):
                is_registered = any(
                    _same_location(scanned, known) for known in registered_paths
                )
                _add(
                    scanned,
                    repo,
                    LocationKind.WORKTREE if is_registered else LocationKind.UNREGISTERED,
                    is_registered,
                    primary,
                    unknown=not git_available,
                )

        # 2. registered worktrees not already covered by the scan
        for known in registered_paths:
            _add(known, repo, LocationKind.WORKTREE, True, primary, unknown=not git_available)

        # 3. legacy locations (discoverable, never moved)
        for legacy in discover_legacy_worktree_locations(root, repo=repo):
            legacy_path = str(legacy)
            if not os.path.exists(legacy_path):
                continue
            is_registered = any(
                _same_location(legacy_path, known) for known in registered_paths
            )
            _add(
                legacy_path,
                _repo_for_legacy(root, legacy_path, repo_names) or repo,
                _legacy_kind(legacy_path),
                is_registered,
                primary,
                unknown=not git_available,
            )

    for candidate in candidates:
        inventory.rows.append(
            _build_row(candidate, manifest_map, processes, probe, reference, session_ttl_seconds)
        )
    return inventory


def _build_row(
    candidate: Mapping[str, Any],
    manifests: Mapping[str, Any],
    processes: Optional[Mapping[str, Sequence[int]]],
    pid_alive: Callable[[int], Optional[bool]],
    reference: datetime,
    ttl_seconds: float,
) -> WorkspaceRow:
    path = candidate["path"]

    lookup = manifests.get(path)
    if lookup is None:
        for key, value in manifests.items():
            if _same_location(key, path):
                lookup = value
                break
    manifest, unreadable = _coerce_manifest(lookup)

    existence = _existence_state(path)
    disk_state, disk_bytes = _disk_usage(path)
    dirtiness = _dirty_state(path) if existence is ExistenceState.PRESENT else DirtyState.UNKNOWN
    head = _head_state(path) if existence is ExistenceState.PRESENT else HeadState.UNKNOWN
    # A detached HEAD has no branch and therefore no upstream: that is a
    # definite "no upstream", not unavailable evidence.
    if existence is not ExistenceState.PRESENT:
        upstream = UpstreamState.UNKNOWN
    elif head is HeadState.DETACHED:
        upstream = UpstreamState.NO_UPSTREAM
    else:
        upstream = _upstream_state(path)

    if candidate.get("unknown"):
        registration = RegistrationState.UNKNOWN
    elif candidate.get("registered"):
        registration = RegistrationState.REGISTERED
    else:
        registration = RegistrationState.UNREGISTERED

    row = WorkspaceRow(
        path=path,
        repo=candidate["repo"],
        kind=candidate["kind"],
        registration=registration,
        existence=existence,
        dirtiness=dirtiness,
        head=head,
        upstream=upstream,
        reachability=_reachability(candidate["primary"], manifest),
        lease=_lease_state(manifest, unreadable, reference),
        process=_process_state(path, processes, pid_alive),
        session=_session_state(manifest, unreadable, reference, ttl_seconds),
        disk=disk_state,
        disk_bytes=disk_bytes,
        classification=Classification.UNKNOWN,
        reason="",
    )
    classification, reason = _classify(row)
    row.classification = classification
    row.reason = reason
    return row
