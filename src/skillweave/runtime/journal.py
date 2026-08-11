from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional
import json
import sqlite3
import uuid


class EventType(str, Enum):
    STATE_TRANSITION = "state_transition"
    BATCH_START = "batch_start"
    BATCH_COMPLETE = "batch_complete"
    GATE_EVALUATION = "gate_evaluation"
    ARTIFACT_CREATED = "artifact_created"
    HANDOFF = "handoff"
    CHECKPOINT = "checkpoint"
    OBSERVER_ALERT = "observer_alert"
    ERROR = "error"
    METRIC = "metric"
    CONTEXT_LOADED = "context_loaded"


@dataclass
class JournalEvent:
    sequence: int
    run_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "idempotency_key": self.idempotency_key,
            "timestamp": self.timestamp,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JournalEvent":
        return cls(
            sequence=data["sequence"],
            run_id=data["run_id"],
            event_type=data["event_type"],
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            idempotency_key=data.get("idempotency_key"),
            timestamp=data["timestamp"],
            version=data.get("version", 1),
        )


class EventJournal:
    def __init__(self, db_path: Any = ":memory:", store: Any = None):
        if hasattr(db_path, "db_path"):
            store = db_path
            db_path = store.db_path
        elif store is not None and hasattr(store, "db_path"):
            db_path = store.db_path
        self.db_path = db_path
        self._store = store
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER NOT NULL,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                correlation_id TEXT,
                causation_id TEXT,
                idempotency_key TEXT,
                timestamp TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (run_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS idx_events_run
                ON events(run_id, sequence);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idempotency
                ON events(run_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;
            CREATE TABLE IF NOT EXISTS dispatch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                dispatched_at TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 1
            );
        """)
        self._conn.commit()

    def _next_sequence(self, run_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return row[0]

    def _is_duplicate(self, run_id: str, idempotency_key: str) -> bool:
        if not idempotency_key:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM events WHERE run_id = ? AND idempotency_key = ?",
            (run_id, idempotency_key),
        ).fetchone()
        return row is not None

    def append(
        self,
        run_id: str,
        message: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        event_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> JournalEvent:
        if expected_version is not None:
            current = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            if current != expected_version:
                from .errors import VersionConflictError
                raise VersionConflictError(run_id, expected_version, current)
        if event_type is None:
            event_type = EventType.STATE_TRANSITION.value
        if self._is_duplicate(run_id, idempotency_key or ""):
            row = self._conn.execute(
                "SELECT * FROM events WHERE run_id = ? AND idempotency_key = ?",
                (run_id, idempotency_key),
            ).fetchone()
            return JournalEvent.from_dict(dict(row))

        sequence = self._next_sequence(run_id)
        event = JournalEvent(
            sequence=sequence,
            run_id=run_id,
            event_type=event_type,
            payload=payload or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
        )

        self._conn.execute(
            """INSERT INTO events
               (sequence, run_id, event_type, payload, correlation_id,
                causation_id, idempotency_key, timestamp, version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.sequence, event.run_id, event.event_type,
                json.dumps(event.payload),
                event.correlation_id, event.causation_id,
                event.idempotency_key, event.timestamp, event.version,
            ),
        )
        self._conn.commit()
        return event

    def append_and_dispatch(
        self,
        run_id: str,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        dispatchers: Optional[list[Callable[[JournalEvent], None]]] = None,
    ) -> JournalEvent:
        event = self.append(
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
        )

        self._conn.execute(
            "INSERT INTO dispatch_log (run_id, sequence, dispatched_at, success) VALUES (?, ?, ?, ?)",
            (run_id, event.sequence, datetime.now(timezone.utc).isoformat(), 0),
        )

        if dispatchers:
            for dispatcher in dispatchers:
                dispatcher(event)

        self._conn.execute(
            "UPDATE dispatch_log SET success = 1 WHERE run_id = ? AND sequence = ?",
            (run_id, event.sequence),
        )
        self._conn.commit()

        return event

    def get_events(
        self,
        run_id: str,
        from_sequence: int = 0,
        limit: Optional[int] = None,
    ) -> list[JournalEvent]:
        query = "SELECT * FROM events WHERE run_id = ? AND sequence > ? ORDER BY sequence"
        params = [run_id, from_sequence]
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("payload"), str):
                d["payload"] = json.loads(d["payload"])
            results.append(JournalEvent.from_dict(d))
        return results

    def get_last_sequence(self, run_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return row[0]

    def get_undispatched(self, run_id: str) -> list[JournalEvent]:
        rows = self._conn.execute(
            """SELECT e.* FROM events e
               WHERE e.run_id = ? AND e.sequence NOT IN
                 (SELECT sequence FROM dispatch_log WHERE run_id = ? AND success = 1)
               ORDER BY e.sequence""",
            (run_id, run_id),
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("payload"), str):
                d["payload"] = json.loads(d["payload"])
            results.append(JournalEvent.from_dict(d))
        return results

    def has_gaps(self, run_id: str) -> bool:
        rows = self._conn.execute(
            "SELECT sequence FROM events WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        if not rows:
            return False
        for i, row in enumerate(rows):
            if row[0] != i + 1:
                return True
        return False

    def replay(
        self,
        run_id: str,
        handler: Callable[[JournalEvent], Any],
        from_sequence: int = 0,
    ) -> list[Any]:
        events = self.get_events(run_id, from_sequence=from_sequence)
        results = []
        for event in events:
            result = handler(event)
            results.append(result)
        return results

    def close(self):
        self._conn.close()
