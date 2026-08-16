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

Later dispatches add write-scope fan-out/inline, session-boundary
enforcement, and ``max_parallel`` — none of which belong to batch building
itself.
"""

from dataclasses import dataclass, field
from typing import List, Sequence


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


@dataclass
class Batch:
    index: int
    tasks: List[Task]

    @property
    def task_ids(self) -> List[str]:
        return [t.id for t in self.tasks]


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
