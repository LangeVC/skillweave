import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TimingRecord:
    name: str
    start: float
    end: Optional[float] = None
    elapsed: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def stop(self) -> float:
        self.end = time.monotonic()
        self.elapsed = self.end - self.start
        return self.elapsed

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "elapsed": self.elapsed,
            "metadata": self.metadata,
        }


class Timer:
    def __init__(self):
        self.records: list[TimingRecord] = []
        self._active: Optional[TimingRecord] = None

    def start(self, name: str, metadata: Optional[dict] = None) -> TimingRecord:
        record = TimingRecord(name=name, start=time.monotonic(), metadata=metadata or {})
        self._active = record
        self.records.append(record)
        return record

    def stop(self) -> float:
        if self._active is None:
            return 0.0
        elapsed = self._active.stop()
        self._active = None
        return elapsed

    def lap(self, name: str) -> TimingRecord:
        if self._active:
            self._active.stop()
        return self.start(name)

    def total_elapsed(self) -> float:
        if not self.records:
            return 0.0
        first_start = self.records[0].start
        last_end = self.records[-1].end or time.monotonic()
        return last_end - first_start

    def summary(self) -> dict[str, Any]:
        return {
            "total_records": len(self.records),
            "total_elapsed": self.total_elapsed(),
            "records": [r.to_dict() for r in self.records if r.elapsed is not None],
        }


class TimingContext:
    def __init__(self, timer: Timer, name: str, metadata: Optional[dict] = None):
        self.timer = timer
        self.name = name
        self.metadata = metadata

    def __enter__(self) -> TimingRecord:
        return self.timer.start(self.name, self.metadata)

    def __exit__(self, *args) -> None:
        self.timer.stop()
