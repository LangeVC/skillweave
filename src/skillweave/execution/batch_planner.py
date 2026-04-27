import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class BatchSpec:
    name: str
    steps: list[str]
    mode: str = "sequential"
    gate_after: bool = True


@dataclass
class BatchPlan:
    batches: list[BatchSpec] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "batches": [
                {"name": b.name, "steps": b.steps, "mode": b.mode, "gate_after": b.gate_after}
                for b in self.batches
            ],
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BatchPlan":
        batches = [
            BatchSpec(name=b["name"], steps=b["steps"], mode=b.get("mode", "sequential"), gate_after=b.get("gate_after", True))
            for b in data.get("batches", [])
        ]
        return cls(batches=batches, created_at=data.get("created_at", ""), metadata=data.get("metadata", {}))

    def to_json_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json_file(cls, path: Path) -> "BatchPlan":
        with open(path) as f:
            return cls.from_dict(json.load(f))


class BatchPlanner:
    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root).resolve()
        self.tracking_dir = self.project_root / ".skillweave" / "tracking-log"

    def create_plan(self, batches: list[BatchSpec], metadata: dict | None = None) -> BatchPlan:
        plan = BatchPlan(batches=batches, metadata=metadata or {})
        path = self.tracking_dir / "batch-plan.json"
        plan.to_json_file(path)
        return plan

    def load_plan(self) -> BatchPlan | None:
        path = self.tracking_dir / "batch-plan.json"
        if not path.exists():
            return None
        return BatchPlan.from_json_file(path)

    def get_current_batch(self, completed: list[str]) -> BatchSpec | None:
        plan = self.load_plan()
        if not plan:
            return None
        for batch in plan.batches:
            steps_done = all(s in completed for s in batch.steps)
            if not steps_done:
                return batch
        return None
