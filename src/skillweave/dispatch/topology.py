"""Collision-safe topology: manifest, serialization, and commit eligibility.

The operator dispatch contract (:mod:`skillweave.dispatch.contracts`) tells a
lane *what* it will mutate; it does not record *how the lanes relate*. Two
mutating lanes can therefore be let loose on the same paths or assembled from
bases that cannot meet, and a controller that does not know a lane's dependency
set or integration policy has no way to order safe integration.

This module owns the relation layer. It is deliberately decision-only — it
starts no process, does no ``git`` I/O, names no model/provider/gateway/harness
default, and imports no optional ``skillweave.runtime`` subpackage (GLE-020):
path-overlap arbitration is re-implemented locally so this module stays
decoupled and importable when ``runtime`` is physically absent. Everything it
produces is derivable from a :class:`LaneTopology` manifest and the topology as
a whole.

Three concerns live here:

* **Manifest completeness** — a mutating lane must declare a full base SHA, a
  dependency set, a write scope, an exclusive worktree, a branch, and an
  integration policy *before* dispatch (acceptance criterion 1). Missing or
  malformed fields fail closed with the field named.
* **Serialization** — two lanes whose write scopes overlap, whose bases are
  incompatible, or that share a harness state namespace may not launch in the
  same parallel batch, *unless* an explicit integration lane is declared
  (acceptance criterion 2).
* **Commit eligibility** — a lane is eligible to integrate only when its work
  is committed on the declared non-detached branch and its worktree is clean
  except for an explicit cache allowlist (acceptance criterion 3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Sequence

#: The integration policies a mutating lane may declare. ``independent`` lanes
#: land without coordination; ``requires_integrator`` lanes must be folded by an
#: explicit integration lane, not by the controller.
INTEGRATION_POLICIES = ("independent", "requires_integrator")

#: Artifacts a worktree may carry without being considered product-dirty. These
#: are cache/derived artifacts produced by reviewer or observer tooling, never
#: product edits; a lane that carries only these may still be clean.
_CACHE_ALLOWLIST = (
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "*.pyc",
    "*.pyo",
)


def _resolve_scope_path(raw_path: str) -> str:
    """Resolve a single scope string to an absolute directory path.

    Mirrors ``skillweave.runtime.write_scope.resolve_scope_path`` so this module
    stays free of the optional ``runtime`` subpackage (GLE-020): a trailing
    ``**`` marks a recursive scope and is stripped; everything else is resolved
    with ``os.path.abspath`` (lexical resolution, not ``realpath``). The root
    ``/`` is represented by ``os.sep``.
    """
    cleaned = raw_path.replace("**", "").rstrip("/")
    if cleaned == "":
        return os.sep
    return os.path.abspath(cleaned)


def _paths_overlap(resolved_a: str, resolved_b: str) -> bool:
    """True when two resolved scope paths overlap (root overlaps everything).

    Mirrors ``skillweave.runtime.write_scope.paths_overlap`` locally for the
    same reason: two paths overlap when equal, or when one is an ancestor of the
    other with a separator boundary (so ``/a/foobar`` and ``/a/foo`` do not
    overlap). The filesystem root overlaps everything below it.
    """
    if resolved_a == os.sep or resolved_b == os.sep:
        return True
    if resolved_a == resolved_b:
        return True
    if resolved_a.startswith(resolved_b + os.sep):
        return True
    if resolved_b.startswith(resolved_a + os.sep):
        return True
    return False


class TopologyError(ValueError):
    """A topology manifest or relation failed a fail-closed check.

    ``field`` names the offending manifest field where present, mirroring the
    dispatch contract's :class:`ContractError`.
    """

    def __init__(self, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


class ManifestError(TopologyError):
    """A mutating lane's manifest is incomplete or malformed."""


def _is_full_sha(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def default_cache_allowlist() -> tuple[str, ...]:
    """The default cache allowlist a caller may attach to a lane manifest."""
    return _CACHE_ALLOWLIST


@dataclass
class LaneTopology:
    """The full topology manifest of one mutating lane.

    Every field is a mandatory, fail-closed declaration made *before* dispatch
    (acceptance criterion 1):

    * ``lane_id`` — the lane this manifest describes.
    * ``base`` — the full 40-hex base SHA the lane is built from.
    * ``depends_on`` — the lane ids whose integrated outcome this lane needs.
    * ``write_scope`` — the resolved paths this lane is allowed to mutate.
    * ``worktree`` — the exclusive worktree path assigned to this lane.
    * ``branch`` — the non-detached branch the lane commits to.
    * ``integration_policy`` — ``independent`` or ``requires_integrator``.
    * ``harness_state_namespace`` — optional named state the lane claims (two
      lanes sharing a namespace serialize).
    """

    lane_id: str
    base: str
    depends_on: List[str] = field(default_factory=list)
    write_scope: List[str] = field(default_factory=list)
    worktree: Optional[str] = None
    branch: Optional[str] = None
    integration_policy: str = "independent"
    harness_state_namespace: Optional[str] = None

    @property
    def resolved_write_scope(self) -> List[str]:
        return [_resolve_scope_path(p) for p in self.write_scope]

    def validate(self) -> None:
        """Raise :class:`ManifestError` on any incomplete or malformed field."""
        if not self.lane_id:
            raise ManifestError("lane_id must be a non-empty string", field="lane_id")
        if not _is_full_sha(self.base):
            raise ManifestError(
                f"lane '{self.lane_id}' base must be a full 40-hex SHA, got {self.base!r}",
                field=f"{self.lane_id}.base",
            )
        if self.depends_on is None:
            raise ManifestError(
                f"lane '{self.lane_id}' must declare a dependency set (may be empty)",
                field=f"{self.lane_id}.depends_on",
            )
        if not self.write_scope:
            raise ManifestError(
                f"lane '{self.lane_id}' must declare a non-empty write scope",
                field=f"{self.lane_id}.write_scope",
            )
        if not self.worktree:
            raise ManifestError(
                f"lane '{self.lane_id}' must declare an exclusive worktree",
                field=f"{self.lane_id}.worktree",
            )
        if not self.branch:
            raise ManifestError(
                f"lane '{self.lane_id}' must declare a branch",
                field=f"{self.lane_id}.branch",
            )
        if self.branch in ("HEAD", "@"):
            raise ManifestError(
                f"lane '{self.lane_id}' branch must be non-detached, got {self.branch!r}",
                field=f"{self.lane_id}.branch",
            )
        if self.integration_policy not in INTEGRATION_POLICIES:
            raise ManifestError(
                f"lane '{self.lane_id}' integration_policy must be one of "
                f"{list(INTEGRATION_POLICIES)}, got {self.integration_policy!r}",
                field=f"{self.lane_id}.integration_policy",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "base": self.base,
            "depends_on": list(self.depends_on),
            "write_scope": list(self.write_scope),
            "worktree": self.worktree,
            "branch": self.branch,
            "integration_policy": self.integration_policy,
            "harness_state_namespace": self.harness_state_namespace,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LaneTopology":
        return cls(
            lane_id=str(data.get("lane_id", "")),
            base=str(data.get("base", "") or ""),
            depends_on=list(data.get("depends_on") or []),
            write_scope=list(data.get("write_scope") or []),
            worktree=data.get("worktree"),
            branch=data.get("branch"),
            integration_policy=str(data.get("integration_policy") or "independent"),
            harness_state_namespace=data.get("harness_state_namespace"),
        )


@dataclass
class SerializationPlan:
    """The launch ordering a topology yields.

    ``groups`` is a list of batches (each a list of lane ids) in dispatch order.
    Lanes in the same group are safe to launch in parallel; lanes that collide
    in write scope, base, or harness namespace are placed in separate groups
    (serialized) unless an explicit integration lane absorbs them.
    """

    groups: List[List[str]] = field(default_factory=list)
    serialized: List[str] = field(default_factory=list)

    @property
    def flat(self) -> List[str]:
        return [lid for group in self.groups for lid in group]


def _bases_compatible(a: LaneTopology, b: LaneTopology) -> bool:
    """Two bases are compatible when identical.

    A stricter notion of compatibility (e.g. descendant-of) is a transport
    concern and does not belong here; the fail-closed condition is exact
    equality. Anything else is reported as incompatible and serialized.
    """
    return a.base == b.base


def _namespaces_shared(a: LaneTopology, b: LaneTopology) -> bool:
    if not a.harness_state_namespace or not b.harness_state_namespace:
        return False
    return a.harness_state_namespace == b.harness_state_namespace


@dataclass
class Collision:
    """One detected collision between two lanes that forces serialization."""

    lane_a: str
    lane_b: str
    reason: str


def detect_collisions(
    topologies: Sequence[LaneTopology],
) -> List[Collision]:
    """Return every collision between pairs of lanes.

    A collision exists when two lanes overlap in write scope, have incompatible
    bases, or share a harness state namespace. The result is the full list of
    *predicted* collisions — this is the relation, not the resolution.
    """
    collisions: List[Collision] = []
    for i, a in enumerate(topologies):
        for b in topologies[i + 1:]:
            a_scope, b_scope = a.resolved_write_scope, b.resolved_write_scope
            scope_overlap = any(
                _paths_overlap(x, y) for x in a_scope for y in b_scope
            )
            if scope_overlap:
                collisions.append(
                    Collision(a.lane_id, b.lane_id, "write_scope_overlap")
                )
                continue
            if not _bases_compatible(a, b):
                collisions.append(
                    Collision(a.lane_id, b.lane_id, "incompatible_base")
                )
                continue
            if _namespaces_shared(a, b):
                collisions.append(
                    Collision(a.lane_id, b.lane_id, "shared_harness_state_namespace")
                )
    return collisions


def build_serialization_plan(
    topologies: Sequence[LaneTopology],
    *,
    integration_lanes: Optional[Sequence[str]] = None,
) -> SerializationPlan:
    """Order lanes into collision-free batches, honoring integration lanes.

    Lanes are grouped greedily by id order; a lane joins a group only if it
    collides with no member of that group. Colliding lanes are serialized into
    their own later groups — *unless* one member of the colliding pair is an
    integration lane, which is permitted to absorb the conflict.

    ``integration_lanes`` names the lanes that are *explicitly* declared as the
    integration lanes (acceptance criterion 2): a collision between two plain
    lanes is never folded into one batch by fiat.
    """
    integrations = set(integration_lanes or [])
    by_id = {t.lane_id: t for t in topologies}
    for t in topologies:
        t.validate()

    groups: List[List[str]] = []
    for t in sorted(topologies, key=lambda t: t.lane_id):
        if not groups:
            groups.append([t.lane_id])
            continue
        placed = False
        for group in groups:
            ok = True
            for other_id in group:
                other = by_id[other_id]
                if _collides(t, other) and not (
                    t.lane_id in integrations or other_id in integrations
                ):
                    ok = False
                    break
            if ok:
                group.append(t.lane_id)
                placed = True
                break
        if not placed:
            groups.append([t.lane_id])

    serialized = [lid for group in groups if len(group) == 1 for lid in group]
    return SerializationPlan(groups=groups, serialized=serialized)


def _collides(a: LaneTopology, b: LaneTopology) -> bool:
    a_scope, b_scope = a.resolved_write_scope, b.resolved_write_scope
    if any(_paths_overlap(x, y) for x in a_scope for y in b_scope):
        return True
    if not _bases_compatible(a, b):
        return True
    if _namespaces_shared(a, b):
        return True
    return False


@dataclass
class WorktreeState:
    """The observable state of a lane's worktree at assessment time.

    ``committed_sha`` is the full SHA of the head of the declared branch;
    ``detached`` records whether the worktree is on a detached HEAD;
    ``dirty_paths`` lists every product-dirty path (cache allowlist already
    excluded by the caller); ``on_branch`` and ``branch`` name the checked-out
    branch.
    """

    committed_sha: Optional[str] = None
    detached: bool = False
    on_branch: Optional[str] = None
    dirty_paths: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.dirty_paths


def _is_cache_path(path: str, allowlist: Sequence[str]) -> bool:
    cleaned = path.rstrip("/")
    for pattern in allowlist:
        if pattern.startswith("*"):
            if cleaned.endswith(pattern.lstrip("*")):
                return True
        elif cleaned == pattern or cleaned.startswith(pattern + "/") or pattern in cleaned.split("/"):
            return True
    return False


def assess_eligibility(
    lane: LaneTopology,
    state: WorktreeState,
    *,
    cache_allowlist: Optional[Sequence[str]] = None,
) -> List[str]:
    """Return the list of reasons ``lane`` is *not* eligible to integrate.

    An empty list means eligible. A lane is eligible only when (acceptance
    criterion 3):

    * its work is committed on the declared, non-detached branch; and
    * its worktree is clean except for the cache allowlist.

    The allowlist is passed by the caller (defaulting to the module's cache
    allowlist) so a reviewer/observer cache artifact never makes the worktree
    appear product-dirty.
    """
    lane.validate()
    allowlist = cache_allowlist if cache_allowlist is not None else _CACHE_ALLOWLIST
    reasons: List[str] = []

    if state.detached:
        reasons.append(f"worktree is on a detached HEAD (declared branch {lane.branch!r})")
    elif state.on_branch != lane.branch:
        reasons.append(
            f"worktree is on branch {state.on_branch!r}, not the declared {lane.branch!r}"
        )

    if not state.committed_sha:
        reasons.append("no committed work on the declared branch")
    elif not _is_full_sha(state.committed_sha):
        reasons.append(
            f"committed SHA {state.committed_sha!r} is not a full 40-hex SHA"
        )

    for path in state.dirty_paths:
        if not _is_cache_path(path, allowlist):
            reasons.append(f"worktree is product-dirty at {path!r}")

    return reasons


def is_eligible(
    lane: LaneTopology,
    state: WorktreeState,
    *,
    cache_allowlist: Optional[Sequence[str]] = None,
) -> bool:
    """True when ``assess_eligibility`` returns no reason."""
    return not assess_eligibility(lane, state, cache_allowlist=cache_allowlist)


__all__ = [
    "TopologyError",
    "ManifestError",
    "LaneTopology",
    "SerializationPlan",
    "Collision",
    "WorktreeState",
    "INTEGRATION_POLICIES",
    "detect_collisions",
    "build_serialization_plan",
    "assess_eligibility",
    "is_eligible",
    "default_cache_allowlist",
]
