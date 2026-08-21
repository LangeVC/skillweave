"""Legacy executor quarantine (SW-LEGACY-EXEC-001).

The simulating executor (``skillweave.executor`` and its ``simulate_*`` leaf
functions) is a pre-runtime placeholder that fabricates step results in-process
with ``time.sleep``. It must not appear on the canonical self-hosting path: the
Run Application Service and the self-hosting entry drive *real* subprocesses via
``runner_adapter``/``fanout``, never the simulator.

This package is the quarantine: the one, loudly marked surface through which a
legacy ``simulate_*`` call may still be reached, and only with a visible warning.
The canonical path contains no import of it, and an import/callgraph check proves
zero ``simulate_*`` references inside RunService/Self-Hosting.
"""

from .quarantine import (
    LegacyExecutorWarning,
    call_legacy_simulator,
    quarantine_warning,
    simulate_functions,
)

__all__ = [
    "LegacyExecutorWarning",
    "call_legacy_simulator",
    "quarantine_warning",
    "simulate_functions",
]
