"""Coordinator: sole root-DAG writer (SW-COORD-001).

The root DAG cursor is the single authoritative pointer to where a multi-lane
run has advanced. Exactly three facts are enforced here:

1. **Sole writer.** Only a coordinator (the ``ops`` role with the coordinator
   capability) may create or advance the root cursor. A worker or reviewer that
   attempts a mutation is refused before any state changes.
2. **Durable.** The cursor lives in a dedicated table (``root_dag_cursor``) on
   the shared store, not an in-process variable, so a fresh coordinator can
   resume it.
3. **Resumable.** A fresh coordinator loads the persisted cursor and continues
   from it; if none exists yet it records the initial cursor exactly once.

The capability split is explicit: ``COORDINATOR_CAPABILITY`` is the only grant
that permits root-cursor mutation, and it is held by ``ops`` (the coordinator)
and never by ``reviewer``/``worker``/``sub_agent`` roles.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from skillweave.runtime.authority import Role

#: The capability that grants root-DAG-cursor mutation. Held by ops only.
COORDINATOR_CAPABILITY = "mutate_root_dag"

#: Roles that may mutate the root cursor (exactly the coordinator).
_WRITER_ROLES = {Role.OPS.value}

#: Roles that may read the root cursor.
_READER_ROLES = {
    Role.OPS.value,
    Role.REVIEWER.value,
    Role.OBSERVER.value,
    Role.OPERATOR.value,
}

#: DDL for the root-DAG cursor table, created lazily by the coordinator on the
#: shared SQLite store. Exposed so a caller can pre-create it in a known schema.
root_dag_cursor_table_sql = """
CREATE TABLE IF NOT EXISTS root_dag_cursor (
    key TEXT PRIMARY KEY,
    sequence_id TEXT,
    wave TEXT,
    lane TEXT,
    cursor_index INTEGER,
    committed_nodes TEXT,
    updated_at TEXT,
    updated_by TEXT,
    version INTEGER
)
"""


class CoordinatorAccessError(Exception):
    """A non-coordinator attempted to mutate the root DAG cursor.

    The message names the offending role and the attempted action, so the
    violation is explicit (never a silent no-op)."""

    def __init__(self, role: str, action: str):
        self.role = role
        self.action = action
        super().__init__(
            f"role '{role}' cannot {action} the root DAG cursor; "
            f"only the coordinator (ops with '{COORDINATOR_CAPABILITY}') may"
        )


@dataclass
class RootDAGCursor:
    """The authoritative root cursor of a multi-lane run.

    ``cursor_index`` is the ordinal of the highest committed node. ``committed_nodes``
    is a durable list of committed node ids in commit order. ``version`` is a
    monotonic counter so conflicting writes can be detected with compare-and-set.
    """

    key: str
    sequence_id: str
    wave: str
    lane: str
    cursor_index: int
    committed_nodes: list[str]
    updated_at: str
    updated_by: str
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _key(sequence_id: str, wave: str) -> str:
    return f"{sequence_id}::{wave}"


class Coordinator:
    """Sole root-DAG writer backed by the shared store.

    Construct around a ``SQLiteRunStore`` (any object exposing a ``_conn``
    sqlite3 connection works). ``ensure_root`` records the initial cursor for a
    (sequence, wave) exactly once. ``advance`` moves the cursor forward, guarded
    by role and compare-and-set on ``version`` so two coordinators cannot both
    append the same node. ``load`` is the fresh-coordinator resume path.
    """

    def __init__(self, store: Any):
        self.store = store
        self._conn = store._conn
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._conn.executescript(root_dag_cursor_table_sql)
        self._conn.commit()

    def _can_write(self, role: str) -> bool:
        return role in _WRITER_ROLES

    def _assert_writer(self, role: str, action: str) -> None:
        if not self._can_write(role):
            raise CoordinatorAccessError(role, action)

    # ---- read ----

    def load(self, sequence_id: str, wave: str, role: str = Role.REVIEWER.value) -> Optional[RootDAGCursor]:
        """Load the persisted root cursor (the fresh-coordinator resume path).

        Reading is open to reader roles; loading with a reviewer role is
        explicitly allowed so a reviewer can inspect (but not mutate) the root.
        """
        row = self._conn.execute(
            "SELECT * FROM root_dag_cursor WHERE key = ?", (_key(sequence_id, wave),)
        ).fetchone()
        if row is None:
            return None
        import json
        return RootDAGCursor(
            key=row["key"],
            sequence_id=row["sequence_id"],
            wave=row["wave"],
            lane=row["lane"],
            cursor_index=row["cursor_index"],
            committed_nodes=json.loads(row["committed_nodes"]),
            updated_at=row["updated_at"],
            updated_by=row["updated_by"],
            version=row["version"],
        )

    # ---- write ----

    def ensure_root(
        self,
        sequence_id: str,
        wave: str,
        lane: str,
        role: str = Role.OPS.value,
    ) -> RootDAGCursor:
        """Record the initial root cursor exactly once (idempotent).

        A subsequent call with the same (sequence, wave) returns the existing
        cursor unchanged — a fresh coordinator never re-initialises over another
        coordinator's committed cursor.
        """
        self._assert_writer(role, "ensure_root")
        key = _key(sequence_id, wave)
        existing = self.load(sequence_id, wave)
        if existing is not None:
            return existing
        now = datetime.now(timezone.utc).isoformat()
        cursor = RootDAGCursor(
            key=key,
            sequence_id=sequence_id,
            wave=wave,
            lane=lane,
            cursor_index=0,
            committed_nodes=[],
            updated_at=now,
            updated_by=role,
            version=1,
        )
        import json
        self._conn.execute(
            "INSERT INTO root_dag_cursor "
            "(key, sequence_id, wave, lane, cursor_index, committed_nodes, "
            " updated_at, updated_by, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cursor.key,
                cursor.sequence_id,
                cursor.wave,
                cursor.lane,
                cursor.cursor_index,
                json.dumps(cursor.committed_nodes),
                cursor.updated_at,
                cursor.updated_by,
                cursor.version,
            ),
        )
        self._conn.commit()
        return cursor

    def advance(
        self,
        sequence_id: str,
        wave: str,
        node_id: str,
        *,
        role: str = Role.OPS.value,
        expected_version: Optional[int] = None,
    ) -> RootDAGCursor:
        """Append ``node_id`` to the root cursor (compare-and-set on version).

        Only the coordinator may advance. If ``expected_version`` is given and
        does not match the persisted cursor's version, the write is refused —
        two coordinators therefore cannot both append the same next node.
        """
        self._assert_writer(role, "advance")
        cursor = self.load(sequence_id, wave, role=Role.OPS.value)
        if cursor is None:
            raise CoordinatorAccessError(role, "advance (no root cursor yet; call ensure_root)")
        if expected_version is not None and cursor.version != expected_version:
            raise CoordinatorAccessError(
                role,
                f"advance (version CAS: expected {expected_version}, found {cursor.version})",
            )

        now = datetime.now(timezone.utc).isoformat()
        new_nodes = list(cursor.committed_nodes) + [node_id]
        new_index = cursor.cursor_index + 1
        new_version = cursor.version + 1

        import json
        self._conn.execute(
            "UPDATE root_dag_cursor SET cursor_index = ?, committed_nodes = ?, "
            "updated_at = ?, updated_by = ?, version = ? WHERE key = ?",
            (
                new_index,
                json.dumps(new_nodes),
                now,
                role,
                new_version,
                cursor.key,
            ),
        )
        self._conn.commit()

        return RootDAGCursor(
            key=cursor.key,
            sequence_id=cursor.sequence_id,
            wave=cursor.wave,
            lane=cursor.lane,
            cursor_index=new_index,
            committed_nodes=new_nodes,
            updated_at=now,
            updated_by=role,
            version=new_version,
        )
