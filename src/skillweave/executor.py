"""DEPRECATION & MIGRATION NOTICE (SW-DEPR-001).

The public module ``skillweave.executor`` is DEPRECATED and has been removed from
the public runtime surface. No public executor name points to simulation:

- For real execution on the canonical self-hosting path, use
  ``skillweave.runsvc.service.RunService`` or ``skillweave.promptchain.execute``.
- For unit testing, offline testing, or simulation test-doubles, use
  ``skillweave.legacy.test_double`` (or ``skillweave.legacy``).

This module exists solely as a backward-compatibility forwarding shim for legacy
tests. Any import or use emits a visible deprecation warning.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

from skillweave.legacy.test_double import (
    SimulatedExecutorTestDouble,
    TestDoubleWarning,
    execute_with_dependency_awareness as _test_double_execute_with_dependency_awareness,
    simulate_step as _test_double_simulate_step,
    simulate_step_parallel as _test_double_simulate_step_parallel,
    simulate_subagent_execution as _test_double_simulate_subagent_execution,
)
from skillweave.models import StepSpec, WorkflowContext

MIGRATION_NOTICE = (
    "DEPRECATION NOTICE (SW-DEPR-001): 'skillweave.executor' is deprecated. "
    "No public executor name points to simulation. Real execution is handled by "
    "RunService ('skillweave.runsvc.service') or PromptChain ('skillweave.promptchain.execute'). "
    "For unit testing simulation, migrate imports to 'skillweave.legacy.test_double'."
)

# Emit deprecation warning on module import
warnings.warn(MIGRATION_NOTICE, DeprecationWarning, stacklevel=2)


def simulate_step(step: StepSpec, context: WorkflowContext) -> dict:
    """[DEPRECATED: SW-DEPR-001] Forward to skillweave.legacy.test_double.simulate_step."""
    warnings.warn(
        "'skillweave.executor.simulate_step' is deprecated. Use 'skillweave.legacy.test_double.simulate_step'.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _test_double_simulate_step(step, context)


def simulate_step_parallel(
    steps: List[StepSpec],
    context: WorkflowContext,
    max_workers: int = 3,
    timeout: int = 300,
) -> Dict[str, Dict]:
    """[DEPRECATED: SW-DEPR-001] Forward to skillweave.legacy.test_double.simulate_step_parallel."""
    warnings.warn(
        "'skillweave.executor.simulate_step_parallel' is deprecated. Use 'skillweave.legacy.test_double.simulate_step_parallel'.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _test_double_simulate_step_parallel(steps, context, max_workers=max_workers, timeout=timeout)


def execute_with_dependency_awareness(
    sequence_steps: List[StepSpec],
    context: WorkflowContext,
    max_parallel: int = 3,
    step_timeout: int = 300,
) -> Dict[str, Any]:
    """[DEPRECATED: SW-DEPR-001] Forward to skillweave.legacy.test_double.execute_with_dependency_awareness."""
    warnings.warn(
        "'skillweave.executor.execute_with_dependency_awareness' is deprecated. Use 'skillweave.legacy.test_double.execute_with_dependency_awareness'.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _test_double_execute_with_dependency_awareness(
        sequence_steps, context, max_parallel=max_parallel, step_timeout=step_timeout
    )


def simulate_subagent_execution(step: StepSpec, subagent_type: str = "general") -> Dict[str, Any]:
    """[DEPRECATED: SW-DEPR-001] Forward to skillweave.legacy.test_double.simulate_subagent_execution."""
    warnings.warn(
        "'skillweave.executor.simulate_subagent_execution' is deprecated. Use 'skillweave.legacy.test_double.simulate_subagent_execution'.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _test_double_simulate_subagent_execution(step, subagent_type=subagent_type)


__all__ = [
    "MIGRATION_NOTICE",
    "simulate_step",
    "simulate_step_parallel",
    "execute_with_dependency_awareness",
    "simulate_subagent_execution",
]
