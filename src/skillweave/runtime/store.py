from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from .errors import InvalidTransitionError, VersionConflictError

import sqlite3


class RunStateModel(str, Enum):
    PREFLIGHT = "preflight"
    BATCH_SELECTION = "batch_selection"
    LANE_PLAN = "lane_plan"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    REVIEW_GATE = "review_gate"
    FIX_RETRY = "fix_retry"
    INTEGRATE = "integrate"
    ADVANCE_OR_STOP = "advance_or_stop"
    SANDBOX_PREFLIGHT = "SANDBOX_PREFLIGHT"
    IN_PROGRESS = "IN_PROGRESS"
    PREFLIGHT_COMPLETE = "PREFLIGHT_COMPLETE"
    BLOCKED_WAITING_FOR_GATE = "BLOCKED_WAITING_FOR_GATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"
    STOPPED_BEFORE_B06 = "STOPPED_BEFORE_B06"

    @classmethod
    def legal_transitions(cls, from_state):
        transition_map = {
            cls.PREFLIGHT: [cls.BATCH_SELECTION],
            cls.BATCH_SELECTION: [cls.LANE_PLAN, cls.ADVANCE_OR_STOP],
            cls.LANE_PLAN: [cls.IMPLEMENT],
            cls.IMPLEMENT: [cls.VERIFY],
            cls.VERIFY: [cls.REVIEW_GATE, cls.FIX_RETRY],
            cls.REVIEW_GATE: [cls.INTEGRATE, cls.FIX_RETRY, cls.ADVANCE_OR_STOP],
            cls.FIX_RETRY: [cls.IMPLEMENT, cls.REVIEW_GATE, cls.ADVANCE_OR_STOP],
            cls.INTEGRATE: [cls.VERIFY, cls.ADVANCE_OR_STOP],
            cls.ADVANCE_OR_STOP: [],
            cls.SANDBOX_PREFLIGHT: [cls.IN_PROGRESS, cls.FAILED],
            cls.IN_PROGRESS: [cls.PREFLIGHT_COMPLETE, cls.BLOCKED_WAITING_FOR_GATE, cls.REVIEW_REQUIRED, cls.FAILED],
            cls.PREFLIGHT_COMPLETE: [cls.IN_PROGRESS, cls.REVIEW_REQUIRED, cls.FAILED],
            cls.BLOCKED_WAITING_FOR_GATE: [cls.IN_PROGRESS, cls.REVIEW_REQUIRED, cls.FAILED],
            cls.REVIEW_REQUIRED: [cls.IN_PROGRESS, cls.FAILED],
            cls.FAILED: [cls.SANDBOX_PREFLIGHT],
            cls.STOPPED_BEFORE_B06: [cls.IN_PROGRESS],
        }
        from_state = cls(from_state) if isinstance(from_state, str) else from_state
        return transition_map.get(from_state, [])


@dataclass
class RunRecord:
    run_id: str
    root_run_id: str
    parent_run_id: Optional[str]
    state: str
    version: int
    created_at: str
    updated_at: str
    ended_at: Optional[str]
    role: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class RunStore(ABC):
    @abstractmethod
    def get_run(self, run_id: str) -> Optional[RunRecord]:
        ...

    @abstractmethod
    def save_run(self, record: RunRecord) -> RunRecord:
        ...

    @abstractmethod
    def transition(
        self,
        run_id: str,
        target_state: str,
        expected_state: str,
        expected_version: int,
        reason: str = "",
        role: Optional[str] = None,
    ) -> RunRecord:
        ...

    @abstractmethod
    def list_runs(self, state: Optional[str] = None, limit: int = 100) -> list[RunRecord]:
        ...


class SQLiteRunStore(RunStore):
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                root_run_id TEXT NOT NULL,
                parent_run_id TEXT,
                state TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                ended_at TEXT,
                role TEXT NOT NULL DEFAULT 'ops',
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS transitions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'ops'
            );
        """)
        self._conn.commit()

    def _row_to_record(self, row) -> RunRecord:
        import json
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return RunRecord(
            run_id=row["run_id"],
            root_run_id=row["root_run_id"],
            parent_run_id=row["parent_run_id"],
            state=row["state"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            ended_at=row["ended_at"],
            role=row["role"],
            metadata=meta,
        )

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def save_run(self, record: RunRecord) -> RunRecord:
        import json
        now = datetime.now(timezone.utc).isoformat()
        if record.created_at is None:
            record.created_at = now
        record.updated_at = now
        if record.version < 1:
            record.version = 1

        self._conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, root_run_id, parent_run_id, state, version,
                created_at, updated_at, ended_at, role, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.run_id, record.root_run_id, record.parent_run_id,
                record.state, record.version,
                record.created_at, record.updated_at, record.ended_at,
                record.role, json.dumps(record.metadata),
            ),
        )
        self._conn.commit()
        return record

    def set_authority_guard(self, guard) -> None:
        self._authority_guard = guard

    def transition(
        self,
        run_id: str,
        target_state: str,
        expected_state: str,
        expected_version: int,
        reason: str = "",
        role: Optional[str] = None,
    ) -> RunRecord:
        existing = self.get_run(run_id)
        if existing is None:
            raise InvalidTransitionError(
                "nonexistent", target_state, run_id,
                extra={"reason": "run does not exist"},
            )

        if expected_state is not None and existing.state != expected_state:
            raise InvalidTransitionError(
                existing.state, target_state, run_id,
                extra={
                    "expected": expected_state,
                    "actual": existing.state,
                    "reason": "run is not in the expected state",
                },
            )

        if expected_version is not None and existing.version != expected_version:
            raise VersionConflictError(run_id, expected_version, existing.version)

        if role and hasattr(self, '_authority_guard') and self._authority_guard is not None:
            from skillweave.runtime.authority import can_mutate_run_state
            if not can_mutate_run_state(role):
                from skillweave.runtime.authority import AuthorityError
                raise AuthorityError(role, "transition", f"Role '{role}' lacks mutate_run_state")

        allowed = RunStateModel.legal_transitions(existing.state)
        allowed_values = [s.value if isinstance(s, RunStateModel) else s for s in allowed]
        if target_state not in allowed_values:
            raise InvalidTransitionError(
                existing.state, target_state, run_id,
                extra={"allowed": allowed_values},
            )

        now = datetime.now(timezone.utc).isoformat()
        new_version = existing.version + 1
        ended_at = existing.ended_at
        if target_state in ("advance_or_stop", "FAILED"):
            ended_at = now

        cur = self._conn.execute(
            """UPDATE runs SET state = ?, version = ?, updated_at = ?, ended_at = ?,
               role = COALESCE(?, role)
               WHERE run_id = ? AND version = ?""",
            (target_state, new_version, now, ended_at, role, run_id, expected_version),
        )

        if cur.rowcount == 0:
            raise VersionConflictError(run_id, expected_version, existing.version)

        self._conn.execute(
            """INSERT INTO transitions_log
               (run_id, from_state, to_state, reason, version, timestamp, role)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, existing.state, target_state, reason, new_version, now, role or existing.role),
        )
        self._conn.commit()

        return self.get_run(run_id)

    def list_runs(self, state: Optional[str] = None, limit: int = 100) -> list[RunRecord]:
        if state:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def ensure_storage(self):
        pass

    def create_run(self, run_id: str, **kwargs) -> RunRecord:
        from datetime import datetime, timezone
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        record = RunRecord(
            run_id=run_id,
            root_run_id=run_id,
            parent_run_id=None,
            state="preflight",
            version=1,
            created_at=now,
            updated_at=now,
            ended_at=None,
            role="ops",
            metadata=kwargs,
        )
        return self.save_run(record)

    def close(self):
        self._conn.close()
