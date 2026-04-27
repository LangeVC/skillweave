from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


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
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    context: dict[str, Any] = field(default_factory=dict)
    step_id: str = ""
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "context": self.context,
            "step_id": self.step_id,
            "category": self.category,
        }


class EventLogger:
    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root).resolve()
        self.log_dir = self.project_root / ".skillweave" / "tracking-log"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[LogEntry] = []
        self._session_log_path = self.log_dir / f"events-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"

    def log(self, level: LogLevel, message: str, step_id: str = "", category: str = "", context: Optional[dict] = None) -> LogEntry:
        entry = LogEntry(
            level=level,
            message=message,
            step_id=step_id,
            category=category,
            context=context or {},
        )
        self._entries.append(entry)
        self._append_to_file(entry)
        return entry

    def info(self, message: str, step_id: str = "", category: str = "", context: Optional[dict] = None) -> LogEntry:
        return self.log(LogLevel.INFO, message, step_id, category, context)

    def debug(self, message: str, step_id: str = "", category: str = "", context: Optional[dict] = None) -> LogEntry:
        return self.log(LogLevel.DEBUG, message, step_id, category, context)

    def warning(self, message: str, step_id: str = "", category: str = "", context: Optional[dict] = None) -> LogEntry:
        return self.log(LogLevel.WARNING, message, step_id, category, context)

    def error(self, message: str, step_id: str = "", category: str = "", context: Optional[dict] = None) -> LogEntry:
        return self.log(LogLevel.ERROR, message, step_id, category, context)

    def metric(self, name: str, value: float, step_id: str = "", tags: Optional[dict] = None) -> LogEntry:
        return self.log(LogLevel.METRIC, f"{name}={value}", step_id, "metrics", {"metric_name": name, "metric_value": value, "tags": tags or {}})

    def get_entries(self, level: Optional[LogLevel] = None, step_id: str = "", limit: int = 0) -> list[LogEntry]:
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

    def _append_to_file(self, entry: LogEntry) -> None:
        import json
        try:
            with open(self._session_log_path, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except OSError:
            pass
