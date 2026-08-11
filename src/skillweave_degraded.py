"""
Runtime availability guard with degraded-mode signalling.

When ``skillweave.runtime`` can be imported, the system operates with full
control-plane guarantees. When it cannot (pre-v1.3 installations, or
whitelabel consumers that embed only portable SKILL.md support), every
session is marked ``degraded`` so operators and agents can distinguish
between enforced and unenforced execution.

Degraded is NOT an error — it is a transparency signal. A degraded session
still runs; it just runs without the Runtime Foundation guarantees.
"""
import importlib.util
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class DegradedSignal:
    """
    Emitted when the Runtime Foundation is not available.

    A consumer reads this once at bootstrap and surfaces it in the session
    header, agent prompt, and any generated logs.

    Attributes:
        active: True when running without runtime guarantees.
        reason: Why the runtime is absent.
        missing_modules: Which modules could not be loaded.
        fallback_version: The portable SKILL.md version used instead.
    """
    active: bool = False
    reason: str = ""
    missing_modules: tuple[str, ...] = ()
    fallback_version: str = "v1.2.0"


def detect_degraded() -> DegradedSignal:
    """
    Probe whether ``skillweave.runtime`` is available.

    IMPORTANT: We do NOT use ``find_spec("skillweave.runtime")`` because
    that triggers an import of the parent package (``skillweave``), and
    ``skillweave/__init__.py`` eagerly imports ``.execution`` →
    ``state_machine`` → ``skillweave.runtime.store``. Once GLE-020 (lazy
    ``__init__``) lands, ``find_spec`` on a submodule becomes safe, but
    until then it crashes in exactly the case this function is meant to
    detect. Do not revert to ``find_spec`` on the submodule without also
    resolving GLE-020.

    Instead we check whether the parent package exists and, if so, whether
    the ``runtime/`` directory lives beside it.  All three states are
    handled:

      - *Parent absent* → ``active=True`` (SkillWeave not installed at all).
      - *Parent present, runtime/ absent* → ``active=True`` (pre‑v1.3 or
        whitelabel embedding without runtime).
      - *Parent present, runtime/ present* → import ``skillweave.runtime``
        and return ``active=False``. If the import still fails (corrupt
        installation), the ``ModuleNotFoundError`` is propagated to the
        caller — a degrade signal for a broken install would mask a real
        problem.

    Returns:
        A ``DegradedSignal``.
    """
    parent = importlib.util.find_spec("skillweave")
    if parent is None or not parent.origin:
        return DegradedSignal(
            active=True,
            reason="skillweave package not found",
            missing_modules=("skillweave",),
            fallback_version="v1.2.0",
        )

    runtime_dir = os.path.join(os.path.dirname(parent.origin), "runtime")
    if not os.path.isdir(runtime_dir):
        return DegradedSignal(
            active=True,
            reason="skillweave.runtime not present — pre-v1.3 or whitelabel",
            missing_modules=("skillweave.runtime",),
            fallback_version="v1.2.0",
        )

    import skillweave.runtime  # noqa: F401 — present, must succeed
    return DegradedSignal(active=False)
