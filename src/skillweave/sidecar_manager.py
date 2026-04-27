import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class SidecarSpec:
    name: str
    fn: Callable[[dict], dict]
    input_data: dict = field(default_factory=dict)
    timeout: float = 120.0


@dataclass
class SidecarResult:
    name: str
    status: str  # running, completed, failed, timeout
    output: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration": self.duration,
        }


class SidecarManager:
    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root).resolve()
        self.tracking_dir = self.project_root / ".skillweave" / "tracking-log"
        self.tracking_dir.mkdir(parents=True, exist_ok=True)
        self._results: dict[str, SidecarResult] = {}
        self._threads: dict[str, threading.Thread] = {}

    def launch(self, spec: SidecarSpec) -> SidecarResult:
        result = SidecarResult(
            name=spec.name,
            status="running",
            started_at=datetime.now().isoformat(),
        )
        self._results[spec.name] = result

        def _run():
            start = time.monotonic()
            try:
                if spec.timeout > 0:
                    output = self._run_with_timeout(spec)
                else:
                    output = spec.fn(spec.input_data)
                elapsed = time.monotonic() - start
                result.status = "completed"
                result.output = output
                result.duration = elapsed
                result.completed_at = datetime.now().isoformat()
            except TimeoutError:
                elapsed = time.monotonic() - start
                result.status = "timeout"
                result.error = f"Timed out after {spec.timeout}s"
                result.duration = elapsed
                result.completed_at = datetime.now().isoformat()
            except Exception as e:
                elapsed = time.monotonic() - start
                result.status = "failed"
                result.error = str(e)
                result.duration = elapsed
                result.completed_at = datetime.now().isoformat()
            self._persist_result(result)

        thread = threading.Thread(target=_run, daemon=True, name=f"sidecar-{spec.name}")
        self._threads[spec.name] = thread
        thread.start()
        return result

    def _run_with_timeout(self, spec: SidecarSpec) -> Any:
        result_container: list = []
        exception_container: list = []

        def target():
            try:
                result_container.append(spec.fn(spec.input_data))
            except Exception as e:
                exception_container.append(e)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=spec.timeout)

        if thread.is_alive():
            raise TimeoutError(f"Timed out after {spec.timeout}s")

        if exception_container:
            raise exception_container[0]

        return result_container[0]

    def get_result(self, name: str) -> Optional[SidecarResult]:
        return self._results.get(name)

    def wait_for(self, name: str, timeout: float = 30.0) -> Optional[SidecarResult]:
        thread = self._threads.get(name)
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        return self._results.get(name)

    def wait_all(self, timeout: float = 120.0) -> list[SidecarResult]:
        for name, thread in self._threads.items():
            if thread.is_alive():
                thread.join(timeout=timeout)
            if thread.is_alive():
                result = self._results.get(name)
                if result and result.status == "running":
                    result.status = "timeout"
                    result.error = f"Timed out joining"
                    self._persist_result(result)
        return list(self._results.values())

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self._results),
            "completed": sum(1 for r in self._results.values() if r.status == "completed"),
            "failed": sum(1 for r in self._results.values() if r.status == "failed"),
            "timeout": sum(1 for r in self._results.values() if r.status == "timeout"),
            "results": [r.to_dict() for r in self._results.values()],
        }

    def _persist_result(self, result: SidecarResult) -> None:
        path = self.tracking_dir / f"sidecar-{result.name}.json"
        with open(path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
