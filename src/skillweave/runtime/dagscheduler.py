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

Later dispatches add session-boundary enforcement and ``max_parallel``.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

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
    held_claims: Sequence[WriteScopeClaim] = (),
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
