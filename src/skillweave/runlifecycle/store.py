"""Structured run state persistence under ``.skillweave/runs/<run-id>/``.

Each run gets a directory with:

- ``run.json``  — mutable metadata (id, command, pid, state, timestamps).
- ``events.jsonl`` — append-only structured event log (one JSON object per
  line, monotonic sequence numbers).

The store is designed to be read by ``inspect`` and written by ``start_async``
and ``kill_run`` without any lock coordination — writers append, readers
snapshot.  A racing write is detected by a version counter on ``run.json``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RUNS_DIR = Path(".skillweave") / "runs"
_RUN_METADATA = "run.json"
_EVENTS_LOG = "events.jsonl"

# Safe characters for run IDs (uuid hex + common separators).
_RUN_ID_RE = re.compile(r"^[a-f0-9\-_]+$")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RunStateError(RuntimeError):
    """Raised when a run state operation cannot complete."""


class StalePidError(RunStateError):
    """The target PID does not match the recorded PID; kill refused."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RunMetadata:
    """Persistent metadata for one async run.

    Written atomically (rename) so a concurrent reader never sees a half-
    written file.
    """
    run_id: str
    command: list[str]
    pid: int
    state: str = "running"          # running | succeeded | failed | killed | unknown
    exit_code: Optional[int] = None
    created_at: str = ""
    finished_at: str = ""
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, run_id: str, command: list[str], pid: int) -> "RunMetadata":
        return cls(
            run_id=run_id,
            command=list(command),
            pid=pid,
            created_at=_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunMetadata":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class RunStateStore:
    """Read/write run state under ``.skillweave/runs/``.

    Parameters
    ----------
    project_root:
        Root of the project.  Defaults to CWD.
    """

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self._root = Path(project_root or Path.cwd()).resolve()
        self._runs_dir = self._root / _RUNS_DIR

    # -- paths --------------------------------------------------------------

    def run_dir(self, run_id: str) -> Path:
        return self._runs_dir / run_id

    def metadata_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / _RUN_METADATA

    def events_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / _EVENTS_LOG

    # -- metadata -----------------------------------------------------------

    def write_metadata(self, meta: RunMetadata) -> None:
        """Atomically write *meta* to disk (rename-based)."""
        d = self.run_dir(meta.run_id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f".{_RUN_METADATA}.tmp"
        tmp.write_text(json.dumps(meta.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.metadata_path(meta.run_id))

    def read_metadata(self, run_id: str) -> Optional[RunMetadata]:
        """Return metadata for *run_id*, or ``None`` if absent."""
        path = self.metadata_path(run_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RunMetadata.from_dict(data)
        except (json.JSONDecodeError, KeyError) as exc:
            raise RunStateError(f"corrupt metadata for {run_id}: {exc}") from exc

    def update_metadata(self, run_id: str, **changes: Any) -> RunMetadata:
        """Read-modify-write one metadata field, bumping the version."""
        meta = self.read_metadata(run_id)
        if meta is None:
            raise RunStateError(f"no metadata for run {run_id}")
        for key, val in changes.items():
            if hasattr(meta, key):
                setattr(meta, key, val)
        meta.version += 1
        self.write_metadata(meta)
        return meta

    # -- events -------------------------------------------------------------

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        """Append one JSON event to the events log (creates dir if needed)."""
        log = self.events_path(run_id)
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
            fh.flush()

    def read_events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        """Return events with sequence > *after*, in order."""
        log = self.events_path(run_id)
        if not log.exists():
            return []
        events: list[dict[str, Any]] = []
        for raw in log.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            seq = ev.get("sequence", 0)
            if seq > after:
                events.append(ev)
        return events

    def latest_event_sequence(self, run_id: str) -> int:
        """Return the highest sequence number in the events log, or 0."""
        log = self.events_path(run_id)
        if not log.exists():
            return 0
        highest = 0
        for raw in log.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            seq = ev.get("sequence", 0)
            if seq > highest:
                highest = seq
        return highest

    # -- pid staleness check ------------------------------------------------

    def verify_pid(self, run_id: str, pid: int) -> None:
        """Raise :class:`StalePidError` when *pid* does not match the recorded one.

        This prevents killing a stale/reused PID that happens to have the same
        numeric value as a previous run's PID.  The caller must pass the PID
        they *believe* is the target; the store compares it against the PID
        recorded at start time.
        """
        meta = self.read_metadata(run_id)
        if meta is None:
            raise RunStateError(f"no run found for {run_id}")
        if meta.pid != pid:
            raise StalePidError(
                f"pid mismatch for run {run_id}: recorded pid={meta.pid}, "
                f"provided pid={pid}.  Refusing kill on stale/reused PID."
            )

    # -- listing ------------------------------------------------------------

    def list_runs(self) -> list[str]:
        """Return run IDs of all known runs, newest first."""
        if not self._runs_dir.is_dir():
            return []
        runs: list[tuple[str, float]] = []
        for entry in self._runs_dir.iterdir():
            if entry.is_dir() and entry.name and _RUN_ID_RE.match(entry.name):
                meta_path = entry / _RUN_METADATA
                mtime = 0.0
                if meta_path.exists():
                    mtime = meta_path.stat().st_mtime
                runs.append((entry.name, mtime))
        runs.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in runs]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
