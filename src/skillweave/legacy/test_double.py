"""Explicit Test-Double for Simulated Execution (SW-DEPR-001).

This module provides an explicit test-double implementation for unit testing
and offline test simulations:
- Replaces the legacy quarantined executor with an explicit Test-Double.
- MUST NOT be used on the canonical runtime or self-hosting execution path.
- Emits visible warnings when invoked directly.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
import time
from typing import Any, Callable, Dict, List, Optional
import warnings

from skillweave.models import PromptSequence, StepSpec, WorkflowContext


class TestDoubleWarning(UserWarning):
    """Warning emitted when an explicit simulation test-double is invoked."""
    __test__ = False


_WARNING_TEXT = (
    "WARNING(SW-DEPR-001): an explicit simulation test-double was invoked. "
    "This produces fabricated in-process results for testing only and is "
    "NOT part of the canonical self-hosting or production execution path. "
    "Use RunService ('skillweave.runsvc.service') or PromptChain ('skillweave.promptchain.execute') "
    "for real execution."
)


def test_double_warning() -> str:
    """Emit the test-double warning and return the banner string."""
    warnings.warn(_WARNING_TEXT, TestDoubleWarning, stacklevel=3)
    return _WARNING_TEXT


def _get_next_level_from_context(context: WorkflowContext) -> Optional[Any]:
    """Extract SkillWeaveNextLevel instance from context metadata if available."""
    next_level = context.metadata.get("next_level")
    if next_level and hasattr(next_level, "get_max_parallel_tasks"):
        return next_level
    return None


def simulate_step(step: StepSpec, context: WorkflowContext) -> dict:
    """Test-double: simulate a single step (sequential mode)."""
    test_double_warning()
    context.current_step_id = step.id
    result = {
        "step_id": step.id,
        "step_name": step.name,
        "status": "completed",
        "output": f"Executed step: {step.name}",
        "execution_time": 1.0,
    }
    context.step_outputs[step.id] = result
    context.completed_steps.append(step.id)
    return result


def simulate_step_parallel(
    steps: List[StepSpec],
    context: WorkflowContext,
    max_workers: int = 3,
    timeout: int = 300,
) -> Dict[str, Dict]:
    """Test-double: simulate multiple steps in parallel using a thread pool."""
    test_double_warning()
    results = {}

    def _execute_single(step: StepSpec) -> Dict[str, Any]:
        try:
            execution_time = 0.5 + (hash(step.id) % 10) / 20.0
            time.sleep(execution_time)
            return {
                "step_id": step.id,
                "step_name": step.name,
                "status": "completed",
                "output": f"Parallel executed step: {step.name}",
                "execution_time": execution_time,
            }
        except Exception as e:
            return {
                "step_id": step.id,
                "step_name": step.name,
                "status": "failed",
                "output": f"Error executing step {step.name}: {str(e)}",
                "error": str(e),
                "execution_time": 0.0,
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_step = {executor.submit(_execute_single, step): step for step in steps}
        for future in future_to_step:
            try:
                result = future.result(timeout=timeout)
                step_id = result["step_id"]
                results[step_id] = result
                context.step_outputs[step_id] = result
                if result["status"] == "completed":
                    context.completed_steps.append(step_id)
            except TimeoutError:
                step = future_to_step[future]
                error_result = {
                    "step_id": step.id,
                    "step_name": step.name,
                    "status": "timeout",
                    "output": f"Step {step.name} timed out after {timeout} seconds",
                    "execution_time": timeout,
                }
                results[step.id] = error_result
                context.step_outputs[step.id] = error_result
                context.errors.append(f"Step {step.id} timed out")
            except Exception as e:
                step = future_to_step[future]
                error_result = {
                    "step_id": step.id,
                    "step_name": step.name,
                    "status": "failed",
                    "output": f"Error executing step {step.name}: {str(e)}",
                    "error": str(e),
                    "execution_time": 0.0,
                }
                results[step.id] = error_result
                context.step_outputs[step.id] = error_result
                context.errors.append(f"Step {step.id} failed: {str(e)}")

    return results


def execute_with_dependency_awareness(
    sequence_steps: List[StepSpec],
    context: WorkflowContext,
    max_parallel: int = 3,
    step_timeout: int = 300,
) -> Dict[str, Any]:
    """Test-double: execute steps with dependency awareness and parallelization."""
    from skillweave.orchestrator import get_execution_groups

    test_double_warning()
    next_level = _get_next_level_from_context(context)
    if next_level:
        max_parallel = min(max_parallel, next_level.get_max_parallel_tasks())

    dummy_sequence = PromptSequence(
        metadata={"id": "parallel_execution"},
        objective="Parallel step execution",
        success_criteria=["All steps completed"],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=sequence_steps,
        final_assembly="",
        validation_rules=[],
        failure_handling="continue",
        final_deliverable_format="",
    )

    execution_groups = get_execution_groups(dummy_sequence)
    total_steps = len(sequence_steps)
    completed_steps = 0
    failed_steps = 0
    execution_start = time.time()

    for group in execution_groups:
        ready_steps = [step for step in group if step.id not in context.completed_steps]
        if not ready_steps:
            continue

        group_results = simulate_step_parallel(
            ready_steps,
            context,
            max_workers=min(max_parallel, len(ready_steps)),
            timeout=step_timeout,
        )

        for step_id, result in group_results.items():
            completed_steps += 1
            if result["status"] in ["failed", "timeout"]:
                failed_steps += 1

    total_time = time.time() - execution_start

    return {
        "total_steps": total_steps,
        "completed": completed_steps,
        "failed": failed_steps,
        "success_rate": (completed_steps - failed_steps) / completed_steps if completed_steps > 0 else 0,
        "total_time": total_time,
        "parallel_groups_executed": len(execution_groups),
        "context_updates": {
            "completed_steps": len(context.completed_steps),
            "errors": len(context.errors),
            "step_outputs": len(context.step_outputs),
        },
    }


def simulate_subagent_execution(step: StepSpec, subagent_type: str = "general") -> Dict[str, Any]:
    """Test-double: simulate subagent execution for testing."""
    test_double_warning()
    complexity_score = len(step.instructions) / 100.0
    execution_time = 1.0 + complexity_score * 2.0
    success = hash(step.id) % 10 != 0

    if success:
        return {
            "step_id": step.id,
            "step_name": step.name,
            "subagent_type": subagent_type,
            "status": "completed",
            "output": f"Subagent ({subagent_type}) executed: {step.name}",
            "execution_time": execution_time,
            "artifacts": [f"output_{step.id}.md"],
            "logs": ["Started execution", f"Completed in {execution_time:.2f}s"],
        }
    else:
        return {
            "step_id": step.id,
            "step_name": step.name,
            "subagent_type": subagent_type,
            "status": "failed",
            "output": f"Subagent ({subagent_type}) failed on: {step.name}",
            "execution_time": execution_time,
            "error": "Simulated failure for testing",
            "logs": ["Started execution", f"Failed after {execution_time:.2f}s"],
        }


class SimulatedExecutorTestDouble:
    """Class wrapper representing the explicit simulated executor test double."""

    def __init__(self, max_workers: int = 3, timeout: int = 300):
        self.max_workers = max_workers
        self.timeout = timeout

    def execute_step(self, step: StepSpec, context: WorkflowContext) -> dict:
        return simulate_step(step, context)

    def execute_parallel(self, steps: List[StepSpec], context: WorkflowContext) -> Dict[str, Dict]:
        return simulate_step_parallel(steps, context, max_workers=self.max_workers, timeout=self.timeout)

    def execute_subagent(self, step: StepSpec, subagent_type: str = "general") -> Dict[str, Any]:
        return simulate_subagent_execution(step, subagent_type=subagent_type)

    def execute_sequence(self, sequence_steps: List[StepSpec], context: WorkflowContext) -> Dict[str, Any]:
        return execute_with_dependency_awareness(sequence_steps, context, max_parallel=self.max_workers, step_timeout=self.timeout)


def call_test_double(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a test-double function with the explicit test double warning."""
    test_double_warning()
    return func(*args, **kwargs)


__all__ = [
    "TestDoubleWarning",
    "test_double_warning",
    "simulate_step",
    "simulate_step_parallel",
    "execute_with_dependency_awareness",
    "simulate_subagent_execution",
    "SimulatedExecutorTestDouble",
    "call_test_double",
]
