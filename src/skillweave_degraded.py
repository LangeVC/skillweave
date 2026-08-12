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

    Since GLE-020 (lazy ``skillweave/__init__.py``) ``find_spec`` on the
    submodule is safe: probing ``skillweave.runtime`` no longer forces the
    runtime-dependent parts of the ``skillweave`` package to load, so it no
    longer crashes in exactly the case this function is meant to detect.
    ``find_spec`` is pure metadata lookup and never imports the target.

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

    runtime_spec = importlib.util.find_spec("skillweave.runtime")
    if runtime_spec is None:
        return DegradedSignal(
            active=True,
            reason="skillweave.runtime not present — pre-v1.3 or whitelabel",
            missing_modules=("skillweave.runtime",),
            fallback_version="v1.2.0",
        )

    import skillweave.runtime  # noqa: F401 — present, must succeed
    return DegradedSignal(active=False)
