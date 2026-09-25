"""Quarantine and deprecation wrapper for the simulating executor (SW-LEGACY-EXEC-001, SW-DEPR-001).

The canonical self-hosting path (Run Application Service, self-hosting entry)
must contain zero ``simulate_*`` references: an import/callgraph test proves it.
A *direct legacy* caller still gets a visible warning — loud, explicit, and
traceable — before any simulated step is produced, so a legacy call can never be
mistaken for a real run.

Under SW-DEPR-001, the quarantined legacy executor has been converted to an
explicit Test-Double in ``skillweave.legacy.test_double``. This module provides
backward compatibility for legacy quarantine hooks and callgraph scanners.

The warning is emitted both as ``warnings.warn`` (machine-visible, category
``skillweave.legacy.LegacyExecutorWarning``) and as a host-visible banner string,
so a human reading legacy invocation output sees it immediately.
"""

from __future__ import annotations

import warnings
from typing import Any, Callable, List

from .test_double import (
    TestDoubleWarning,
    simulate_step,
    simulate_step_parallel,
    simulate_subagent_execution,
    execute_with_dependency_awareness,
)

#: The name-bound simulated entry points that constitute the legacy, quarantined
#: executor. Referenced by name so the quarantine stays intact even if the module
#: underneath changes shape.
simulate_functions = [
    "simulate_step",
    "simulate_step_parallel",
    "simulate_subagent_execution",
]


class LegacyExecutorWarning(UserWarning):
    """A direct legacy simulator call was made; it is not a real run."""


_WARNING_TEXT = (
    "WARNING(SW-LEGACY-EXEC-001): a direct call to the legacy simulating "
    "executor was made. This produces fabricated, in-process results and is "
    "NOT part of the canonical self-hosting path. Use the Run Application "
    "Service or the self-hosting entry for a real, evidence-backed run. "
    "(Migration note SW-DEPR-001: For testing, use skillweave.legacy.test_double)."
)


def quarantine_warning() -> str:
    """Return the visible legacy-executor warning banner (and emit it once).

    The banner is the human-visible contract: a direct legacy caller must not
    go unnoticed. It also raises ``LegacyExecutorWarning`` via ``warnings.warn``
    so tooling can detect it programmatically.
    """
    warnings.warn(_WARNING_TEXT, LegacyExecutorWarning, stacklevel=3)
    return _WARNING_TEXT


def call_legacy_simulator(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a legacy ``simulate_*`` function with the mandatory visible warning.

    This is the only sanctioned route to the simulator. It warns loudly, then
    delegates. The canonical path must never call this; it exists so that a
    *direct legacy* invocation is both possible and unmistakable.
    """
    quarantine_warning()
    return func(*args, **kwargs)


def legacy_simulator_names() -> List[str]:
    """The names a callgraph scanner should treat as legacy/simulated."""
    return list(simulate_functions)


__all__ = [
    "LegacyExecutorWarning",
    "TestDoubleWarning",
    "quarantine_warning",
    "call_legacy_simulator",
    "legacy_simulator_names",
    "simulate_functions",
    "simulate_step",
    "simulate_step_parallel",
    "simulate_subagent_execution",
    "execute_with_dependency_awareness",
]
