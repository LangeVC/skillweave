"""Root-DAG coordinator (SW-COORD-001).

The coordinator is the *sole* writer of the root DAG cursor. Workers and
reviewers must never be able to mutate the root cursor; only a coordinator
(ops role holding the coordinator capability) may advance it. A fresh
coordinator — spawned after the previous one died without cleanup — resumes
from the persisted cursor rather than starting over, because the cursor is a
durable, authority-guarded record, not an in-process variable.

The module owns the cursor record and its access control. It does not schedule
work (``dagscheduler``) or run processes (``runner_adapter``/``fanout``); it
records and guards the *root* of the DAG — the single authoritative pointer
that everything else branches from.
"""

from .coordinator import (
    Coordinator,
    CoordinatorAccessError,
    RootDAGCursor,
    root_dag_cursor_table_sql,
)

__all__ = [
    "Coordinator",
    "CoordinatorAccessError",
    "RootDAGCursor",
    "root_dag_cursor_table_sql",
]
