from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from skillweave.runtime.journal import EventJournal, JournalEvent, EventType


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    METRIC = "metric"


@dataclass
class LogEntry:
    level: LogLevel
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context: dict[str, Any] = field(default_factory=dict)
    step_id: str = ""
    category: str = ""
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    idempotency_key: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "context": self.context,
            "step_id": self.step_id,
            "category": self.category,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "idempotency_key": self.idempotency_key,
        }


class EventLogger:
    def __init__(self, project_root: str | Path = ".", journal: Optional[EventJournal] = None):
        self.project_root = Path(project_root).resolve()
        self.log_dir = self.project_root / ".skillweave" / "tracking-log"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[LogEntry] = []
        self._session_log_path = self.log_dir / f"events-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.jsonl"
        self._journal = journal

    def _append_to_file(self, entry: LogEntry) -> None:
        import json
        with open(self._session_log_path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def _persist_to_journal(self, entry: LogEntry) -> None:
        if self._journal is None:
            return
        run_id = entry.context.get("run_id", self.project_root.name)
        event_type_map = {
            LogLevel.ERROR: EventType.ERROR.value,
            LogLevel.METRIC: EventType.METRIC.value,
            LogLevel.WARNING: "warning_logged",
            LogLevel.INFO: "info_logged",
            LogLevel.DEBUG: "debug_logged",
        }
        self._journal.append(
            run_id=run_id,
            event_type=event_type_map.get(entry.level, "log_entry"),
            payload={"level": entry.level.value, "message": entry.message, "step_id": entry.step_id},
            correlation_id=entry.correlation_id,
            causation_id=entry.causation_id,
            idempotency_key=entry.idempotency_key,
        )

    def log(self, level: LogLevel, message: str, step_id: str = "", category: str = "",
            context: Optional[dict] = None, correlation_id: Optional[str] = None,
            causation_id: Optional[str] = None, idempotency_key: Optional[str] = None) -> LogEntry:
        entry = LogEntry(
            level=level,
            message=message,
            step_id=step_id,
            category=category,
            context=context or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
        )
        self._entries.append(entry)
        self._append_to_file(entry)
        self._persist_to_journal(entry)
        return entry

    def info(self, message: str, step_id: str = "", category: str = "",
             context: Optional[dict] = None, **kwargs) -> LogEntry:
        return self.log(LogLevel.INFO, message, step_id, category, context, **kwargs)

    def debug(self, message: str, step_id: str = "", category: str = "",
              context: Optional[dict] = None, **kwargs) -> LogEntry:
        return self.log(LogLevel.DEBUG, message, step_id, category, context, **kwargs)

    def warning(self, message: str, step_id: str = "", category: str = "",
                context: Optional[dict] = None, **kwargs) -> LogEntry:
        return self.log(LogLevel.WARNING, message, step_id, category, context, **kwargs)

    def error(self, message: str, step_id: str = "", category: str = "",
              context: Optional[dict] = None, **kwargs) -> LogEntry:
        return self.log(LogLevel.ERROR, message, step_id, category, context, **kwargs)

    def metric(self, name: str, value: float, step_id: str = "",
               tags: Optional[dict] = None, **kwargs) -> LogEntry:
        return self.log(
            LogLevel.METRIC, f"{name}={value}", step_id, "metrics",
            {"metric_name": name, "metric_value": value, "tags": tags or {}},
            **kwargs,
        )

    def get_entries(self, level: Optional[LogLevel] = None, step_id: str = "",
                    limit: int = 0) -> list[LogEntry]:
        result = self._entries[:]
        if level:
            result = [e for e in result if e.level == level]
        if step_id:
            result = [e for e in result if e.step_id == step_id]
        if limit:
            result = result[-limit:]
        return result

    def clear(self) -> None:
        self._entries.clear()
