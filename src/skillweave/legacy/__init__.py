"""Legacy executor quarantine and Test-Double package (SW-LEGACY-EXEC-001, SW-DEPR-001).

The simulating executor (formerly ``skillweave.executor``) was a pre-runtime placeholder
that fabricated step results in-process with ``time.sleep``. Under SW-DEPR-001:
1. The simulating executor has been removed from the public executor namespace and
   renamed/converted to an explicit Test-Double in ``skillweave.legacy.test_double``.
2. No public executor name points to simulation. Real execution is handled by
   ``skillweave.runsvc.service.RunService`` and ``skillweave.promptchain.execute``.
3. For unit testing, offline dry-runs, or test harness isolation, the explicit
   Test-Double is available via ``skillweave.legacy.test_double`` or ``skillweave.legacy``.

MIGRATION NOTICE (SW-DEPR-001):
If your code imports ``skillweave.executor`` for testing purposes, migrate your import to:
    ``from skillweave.legacy.test_double import simulate_step, simulate_step_parallel, ...``
or
    ``from skillweave.legacy import SimulatedExecutorTestDouble``
"""

from .quarantine import (
    LegacyExecutorWarning,
    call_legacy_simulator,
    legacy_simulator_names,
    quarantine_warning,
    simulate_functions,
)
from .test_double import (
    SimulatedExecutorTestDouble,
    TestDoubleWarning,
    call_test_double,
    execute_with_dependency_awareness,
    simulate_step,
    simulate_step_parallel,
    simulate_subagent_execution,
    test_double_warning,
)

MIGRATION_NOTICE = (
    "MIGRATION NOTICE (SW-DEPR-001): The simulating executor has been deprecated and "
    "converted to an explicit Test-Double in 'skillweave.legacy.test_double'. No public "
    "executor name points to simulation. Use 'skillweave.runsvc.service.RunService' or "
    "'skillweave.promptchain.execute' for real execution."
)

__all__ = [
    "MIGRATION_NOTICE",
    "LegacyExecutorWarning",
    "TestDoubleWarning",
    "call_legacy_simulator",
    "call_test_double",
    "quarantine_warning",
    "test_double_warning",
    "legacy_simulator_names",
    "simulate_functions",
    "SimulatedExecutorTestDouble",
    "simulate_step",
    "simulate_step_parallel",
    "simulate_subagent_execution",
    "execute_with_dependency_awareness",
]
