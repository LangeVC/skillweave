"""DagScheduler: resolve a task graph into ordered batches.

``write_scope`` (009) provides claim and release for write scopes but no
ordering. This module takes a task graph, resolves ``depends_on`` into
topologically ordered batches, and rejects cycles explicitly. It starts no
processes — that is ``runner_adapter`` (011).

Dispatch 1 scope (SW-135-010, criteria 1 and 5):
  * a graph of tasks with ``depends_on`` becomes an ordered list of batches;
  * a cyclic graph is an error, never silently dropped;
  * the result is deterministic: the same graph yields the same batches in
    the same order, regardless of input ordering.

Dispatch 2 scope (SW-135-010, criteria 2 and 9):
  * two lanes with overlapping write scopes never share a parallel batch —
    proven through the claim machinery from 009 (``paths_overlap`` over
    resolved paths), not a fresh check;
  * every lane is emitted with ``execution_mode`` ``fan-out`` or ``inline``,
    derived from write-scope overlap via the claim registry, never from a
    hand-written flag.

Dispatch 3 scope (SW-135-010, criteria 7, 8 and 10):
  * every emitted batch is a session boundary and carries the marker
    explicitly, so a consumer never has to infer where one session ends;
  * a sequence that does not declare ``session_boundary`` is refused, never
    defaulted (inventing a boundary is the defect, LVC-219);
  * red proof: the missing boundary is rejected with a message naming the
    missing key, and overlapping lanes are never emitted as fan-out.

Dispatch 4 adds ``max_parallel`` and dependent-gating.
"""

from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence

from .write_scope import resolve_scope_path, paths_overlap, WriteScopeClaim


class CyclicGraphError(Exception):
    """Raised when the task graph contains a dependency cycle.

    ``unresolved`` names every task that can never be scheduled because it
    participates in (or depends on) a cycle. Reporting them is the point: a
    cycle must surface as an error, not vanish into a missing task.
    """

    def __init__(self, unresolved: Sequence[str]):
        self.unresolved = sorted(unresolved)
        super().__init__(
            "Task graph contains a dependency cycle involving: "
            + ", ".join(self.unresolved)
        )


class UnknownDependencyError(Exception):
    """Raised when a task depends on a task that is not in the graph."""

    def __init__(self, task_id: str, missing: str):
        self.task_id = task_id
        self.missing = missing
        super().__init__(
            f"Task '{task_id}' depends on '{missing}', which is not in the graph"
        )


@dataclass
class Task:
    id: str
    depends_on: List[str] = field(default_factory=list)
    write_scope: List[str] = field(default_factory=list)
    gate: Optional[str] = None


@dataclass
class Batch:
    index: int
    tasks: List[Task]

    @property
    def task_ids(self) -> List[str]:
        return [t.id for t in self.tasks]


EXECUTION_MODE_FANOUT = "fan-out"
EXECUTION_MODE_INLINE = "inline"


@dataclass
class Lane:
    """A task annotated with the execution mode derived from write scope.

    ``execution_mode`` is ``fan-out`` when the lane may run in parallel with
    the other lanes of its batch (its write scope is disjoint from theirs and
    from every held claim); ``inline`` when its scope overlaps another lane or
    a held claim, forcing it to run alone.
    """

    task: Task
    execution_mode: str

    @property
    def task_id(self) -> str:
        return self.task.id


def build_batches(tasks: Sequence[Task]) -> List[Batch]:
    """Resolve ``tasks`` into an ordered list of batches.

    A batch is the earliest layer a task can belong to: batch 0 holds tasks
    with no dependencies, batch 1 holds tasks whose dependencies are all in
    earlier batches, and so on.

    Determinism: tasks are considered in id order at every step, so the same
    graph yields the same batches in the same order regardless of the input
    ordering.
    """
    ids = [t.id for t in tasks]
    if len(set(ids)) != len(ids):
        seen = set()
        dupes = sorted({i for i in ids if i in seen or seen.add(i)})
        raise ValueError(f"Duplicate task ids: {dupes}")

    by_id = {t.id: t for t in tasks}

    dependents = {t.id: [] for t in tasks}
    unresolved_count = {t.id: 0 for t in tasks}
    for task in tasks:
        for dep in task.depends_on:
            if dep not in by_id:
                raise UnknownDependencyError(task.id, dep)
            dependents[dep].append(task.id)
            unresolved_count[task.id] += 1

    ready = sorted(t.id for t in tasks if unresolved_count[t.id] == 0)

    batches: List[Batch] = []
    scheduled: List[str] = []

    while ready:
        batches.append(Batch(index=len(batches), tasks=[by_id[tid] for tid in ready]))
        scheduled.extend(ready)
        next_ready = []
        for tid in ready:
            for dependent in dependents[tid]:
                unresolved_count[dependent] -= 1
                if unresolved_count[dependent] == 0:
                    next_ready.append(dependent)
        ready = sorted(next_ready)

    if len(scheduled) != len(tasks):
        remaining = sorted(t.id for t in tasks if t.id not in set(scheduled))
        raise CyclicGraphError(remaining)

    return batches


def _resolved_scopes(task: Task) -> List[str]:
    return [resolve_scope_path(p) for p in task.write_scope]


def _scope_conflicts(
    scopes: Sequence[str],
    others: Sequence[str],
) -> bool:
    """True when any path in ``scopes`` overlaps any path in ``others``.

    Overlap is decided by ``write_scope.paths_overlap`` (009) over resolved
    absolute paths — never by a hand-written string comparison. This is the
    same arbitration primitive the claim registry uses.
    """
    for own in scopes:
        for other in others:
            if paths_overlap(own, other):
                return True
    return False


def build_lanes(
    tasks: Sequence[Task],
    held_claims: tuple[WriteScopeClaim, ...] = (),
) -> List[List[Lane]]:
    """Build write-scope-aware lanes into parallel batches.

    Extends ``build_batches`` with two guarantees from 009's claim machinery:

    * two lanes whose write scopes overlap are never placed in the same batch;
    * every lane is emitted with ``execution_mode`` ``fan-out`` (disjoint from
      all siblings and every held claim) or ``inline`` (overlaps a sibling or a
      held claim, so it must run alone).

    ``held_claims`` are the claims already held by other runs, as returned by
    ``store.list_write_scope_claims``. A lane overlapping a held claim is
    forced ``inline`` so it cannot fan out on top of a scope owned elsewhere.
    """
    batches = build_batches(tasks)
    held_scopes = [c.resolved_path for c in held_claims] if held_claims else []

    result: List[List[Lane]] = []
    for batch in batches:
        ordered = sorted(batch.tasks, key=lambda t: t.id)
        scopes = {t.id: _resolved_scopes(t) for t in ordered}

        inline_ids: List[str] = []
        fanout_ids: List[str] = []
        for task in ordered:
            own = scopes[task.id]
            siblings = [
                p for other in ordered if other.id != task.id
                for p in scopes[other.id]
            ]
            overlaps_sibling = _scope_conflicts(own, siblings)
            overlaps_held = _scope_conflicts(own, held_scopes)
            if overlaps_sibling or overlaps_held:
                inline_ids.append(task.id)
            else:
                fanout_ids.append(task.id)

        by_id = {t.id: t for t in ordered}

        # Fan-out lanes are mutually disjoint by construction and may share one
        # batch; each inline lane gets its own batch so no two overlapping
        # write scopes ever sit in the same batch. Id order keeps it
        # deterministic.
        group: List[Lane] = [Lane(task=by_id[tid], execution_mode=EXECUTION_MODE_FANOUT)
                              for tid in fanout_ids]
        if group:
            result.append(group)
        for tid in inline_ids:
            result.append([Lane(task=by_id[tid], execution_mode=EXECUTION_MODE_INLINE)])

    return result


class MissingSessionBoundaryError(Exception):
    """Raised when a sequence does not declare ``session_boundary``.

    This error exists so a boundary is never invented. LVC-219: defaulting a
    boundary is the defect, not a convenience — a caller that forgets the key
    must be stopped, not silently given a wrong session split.
    """

    def __init__(self):
        super().__init__(
            "Sequence does not declare the required key 'session_boundary'; "
            "refusing rather than inventing a session boundary"
        )


@dataclass
class Sequence:
    """A run to schedule: the tasks plus the session boundary they belong to.

    ``session_boundary`` is required. A missing boundary is refused by
    ``build_sessions`` (``MissingSessionBoundaryError``), never defaulted.
    """

    tasks: List[Task] = field(default_factory=list)
    session_boundary: Optional[str] = None


@dataclass
class SessionBatch:
    """A batch that IS a session boundary.

    ``session_boundary`` is carried explicitly on the batch so a consumer
    reads the marker instead of inferring where one session ends and the next
    begins.
    """

    index: int
    lanes: List[Lane]
    session_boundary: str

    @property
    def task_ids(self) -> List[str]:
        return [lane.task_id for lane in self.lanes]


def build_sessions(
    sequence: Sequence,
    held_claims: tuple[WriteScopeClaim, ...] = (),
) -> List[SessionBatch]:
    """Build session boundary batches from a declared ``Sequence``.

    Each emitted batch is a session boundary and carries ``session_boundary``
    explicitly (criterion 7). Write-scope arbitration from ``build_lanes`` is
    preserved end to end, so a batch whose lanes overlap in write scope is
    never emitted as fan-out (criterion 10).

    A sequence whose ``session_boundary`` is missing or empty is refused with
    ``MissingSessionBoundaryError`` naming the key (criteria 8 and 10) — a
    boundary is never invented.
    """
    if not sequence.session_boundary:
        raise MissingSessionBoundaryError()

    lane_groups = build_lanes(sequence.tasks, held_claims=held_claims)

    sessions: List[SessionBatch] = []
    for index, group in enumerate(lane_groups):
        sessions.append(SessionBatch(
            index=index,
            lanes=group,
            session_boundary=sequence.session_boundary,
        ))
    return sessions


@dataclass
class Schedule:
    """A gated, parallel-capped session schedule.

    ``batches`` are the session boundary batches that may run, in order.
    ``blocked`` names every task (sorted) that was never released because one
    of its dependencies carried a gate that did not pass — transitively, so a
    task downstream of a blocked task is itself blocked. Blocked tasks are
    reported, never silently dropped (same philosophy as ``CyclicGraphError``).
    """

    batches: List[SessionBatch]
    blocked: List[str]


def _split_by_max_parallel(
    lane_groups: tuple[tuple[Lane, ...], ...],
    max_parallel: int,
) -> List[List[Lane]]:
    """Cap the number of lanes per group at ``max_parallel``.

    Only fan-out groups can hold more than one lane; inline groups hold exactly
    one and are left untouched. ``max_parallel`` is guaranteed >= 1 by the
    caller. Id order is preserved, so the split is deterministic.
    """
    split: List[List[Lane]] = []
    for group in lane_groups:
        group = list(group)
        if len(group) <= max_parallel:
            split.append(group)
            continue
        for start in range(0, len(group), max_parallel):
            split.append(group[start:start + max_parallel])
    return split


def build_schedule(
    sequence: Sequence,
    gate_results: Optional[Mapping[str, bool]] = None,
    max_parallel: Optional[int] = None,
    held_claims: tuple[WriteScopeClaim, ...] = (),
) -> Schedule:
    """Build a gated, parallel-capped schedule from a ``Sequence``.

    Extends ``build_sessions`` with dispatch-4 guarantees:

    * ``max_parallel`` caps how many lanes share one fan-out batch (criterion
      3). When unset there is no cap; a value < 1 is refused.
    * a lane whose ``gate`` did not pass (missing or ``False`` in
      ``gate_results``) does NOT release its dependents (criterion 4). Blocked
      tasks — and anything downstream of them — are returned in
      ``Schedule.blocked`` rather than vanishing from the plan.

    The scheduler still starts no process and knows no runner (criterion 6):
    gating and parallelism are decided here declaratively, never by
    executing work.
    """
    if not sequence.session_boundary:
        raise MissingSessionBoundaryError()
    if max_parallel is not None and max_parallel < 1:
        raise ValueError(
            f"max_parallel must be >= 1 or None, got {max_parallel}"
        )

    results = dict(gate_results) if gate_results else {}

    # Layering, cycle/dupe/unknown-dep validation, and determinism come from
    # build_batches. Gating is a release condition layered on top: a dependent
    # is released only when every dependency is scheduled AND its gate passed.
    batches = build_batches(sequence.tasks)
    by_id = {t.id: t for t in sequence.tasks}

    blocked: set = set()
    for batch in batches:
        for task in batch.tasks:
            if task.id in blocked:
                continue
            for dep in task.depends_on:
                dep_task = by_id[dep]
                dep_blocked = dep in blocked
                gate = dep_task.gate
                gate_failed = gate is not None and not results.get(gate, False)
                if dep_blocked or gate_failed:
                    blocked.add(task.id)
                    break

    unblocked = [t for t in sequence.tasks if t.id not in blocked]
    lane_groups = build_lanes(unblocked, held_claims=held_claims)
    if max_parallel is not None:
        lane_groups = _split_by_max_parallel(lane_groups, max_parallel)

    session_batches = [
        SessionBatch(index=i, lanes=list(group),
                     session_boundary=sequence.session_boundary)
        for i, group in enumerate(lane_groups)
    ]
    return Schedule(batches=session_batches, blocked=sorted(blocked))
