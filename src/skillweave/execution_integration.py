from pathlib import Path
from typing import Any, Callable, Optional

from .checklist import Checklist, ChecklistItem, ChecklistItemStatus
from .execution.batch_planner import BatchPlanner, BatchSpec
from .execution.state_machine import RalphLoopStateMachine, RalphLoopState
from .execution.retry import RetryHandler
from .execution.gate_policy import GatePolicy, BinaryGateResult
from .execution_checklist import ChecklistLoopEngine
from .execution_memory import ExecutionMemory
from .observation.event_logger import EventLogger, LogLevel
from .observation.timing import Timer, TimingContext
from .observation.report_generator import ReportGenerator
from .sidecar_manager import SidecarManager, SidecarSpec


class ExecutionIntegration:
    def __init__(self, project_root: str | Path = ".", enabled: bool = False):
        self.project_root = Path(project_root).resolve()
        self.enabled = enabled

        self.batch_planner = BatchPlanner(project_root)
        self.state_machine = RalphLoopStateMachine()
        self.gate_policy = GatePolicy("execution_gate")
        self.retry_handler = RetryHandler(max_retries=3)
        self.checklist_loop = ChecklistLoopEngine(project_root)
        self.memory = ExecutionMemory(project_root)
        self.logger = EventLogger(project_root)
        self.timer = Timer()
        self.reporter = ReportGenerator(project_root)
        self.sidecar_manager = SidecarManager(project_root)

    def is_enabled(self) -> bool:
        return self.enabled

    def run_batch(
        self,
        batch: BatchSpec,
        executor_fn: Callable[[str, dict], bool],
        context: Optional[dict] = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "reason": "Execution system is not enabled"}

        ctx = context or {}
        results: dict[str, Any] = {"batch": batch.name, "steps": {}, "state_history": []}

        with TimingContext(self.timer, f"batch_{batch.name}"):
            self.state_machine.transition_to(RalphLoopState.PREFLIGHT, "Starting batch execution")
            results["state_history"].append(self.state_machine.summary())

            self.state_machine.transition_to(RalphLoopState.IMPLEMENT, f"Executing batch: {batch.name}")
            results["state_history"].append(self.state_machine.summary())

            for step_id in batch.steps:
                self.logger.info(f"Executing step: {step_id}", step_id=step_id, category="execution")
                step_context = ctx.get(step_id, {})

                try:
                    with TimingContext(self.timer, f"step_{step_id}"):
                        success = executor_fn(step_id, step_context)
                except Exception as e:
                    success = False
                    self.logger.error(f"Step {step_id} raised exception: {e}", step_id=step_id)

                if success:
                    self.logger.info(f"Step {step_id} completed", step_id=step_id, category="execution")
                    self.logger.metric("step_completed", 1.0, step_id=step_id)
                else:
                    self.logger.error(f"Step {step_id} failed", step_id=step_id)
                    self.logger.metric("step_failed", 1.0, step_id=step_id)

                results["steps"][step_id] = {"success": success}

            self.state_machine.transition_to(RalphLoopState.VERIFY, "Verifying batch results")
            results["state_history"].append(self.state_machine.summary())

            gate_result = self._evaluate_gate(results["steps"])
            if gate_result.passed:
                self.state_machine.transition_to(RalphLoopState.INTEGRATE, "Gate passed, integrating")
                self.state_machine.transition_to(RalphLoopState.ADVANCE_OR_STOP, "Batch complete")
            else:
                self.state_machine.transition_to(RalphLoopState.FIX_RETRY, f"Gate failed: {gate_result.reason}")
                if self.retry_handler.budget.can_retry():
                    self.retry_handler.budget.record_attempt(success=False, error=gate_result.reason)
                self.state_machine.transition_to(RalphLoopState.ADVANCE_OR_STOP, "Stopping after gate failure")

            results["state_history"].append(self.state_machine.summary())

        results["gate_result"] = gate_result.to_dict()
        results["timing"] = self.timer.summary()
        return results

    def run_checklist_loop(
        self,
        executor_fn: Callable[[str, dict], bool],
        filename: str = "",
        context: Optional[dict] = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled"}

        with TimingContext(self.timer, "checklist_loop"):
            result = self.checklist_loop.execute_loop(executor_fn, filename, context)

        for r in result.get("results", []):
            self.logger.metric(
                "checklist_item",
                1.0 if r["status"] == "passed" else 0.0,
                step_id=r.get("item", ""),
                tags={"status": r["status"]},
            )

        return result

    def record_memory(self, category: str, content: str, source: str = "", tags: Optional[list[str]] = None) -> dict:
        if not self.enabled:
            return {"status": "disabled"}
        entry = self.memory.write_entry(category, content, source, tags)
        self.logger.info(f"Memory written to {category}", category="memory")
        return entry

    def query_memory(self, query: str, category: str = "") -> list[dict]:
        if not self.enabled:
            return []
        if category:
            return self.memory.search(query, category)
        return self.memory.search(query)

    def launch_sidecar(self, name: str, fn: Callable[[dict], dict], input_data: Optional[dict] = None, timeout: float = 120.0) -> dict:
        if not self.enabled:
            return {"status": "disabled"}
        spec = SidecarSpec(name=name, fn=fn, input_data=input_data or {}, timeout=timeout)
        result = self.sidecar_manager.launch(spec)
        self.logger.info(f"Sidecar '{name}' launched", category="sidecar")
        return result.to_dict()

    def generate_report(self, session_id: str) -> dict[str, Any]:
        return self.reporter.generate_report(session_id, self.timer, self.logger)

    def _evaluate_gate(self, steps: dict[str, dict]) -> BinaryGateResult:
        failures = [sid for sid, s in steps.items() if not s.get("success")]
        if failures:
            return BinaryGateResult(
                passed=False,
                reason=f"Steps failed: {', '.join(failures)}",
                details=[f"{sid}: did not pass" for sid in failures],
            )
        return BinaryGateResult(passed=True, reason="All steps completed successfully")
