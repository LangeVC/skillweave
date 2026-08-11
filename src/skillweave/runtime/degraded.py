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
        reason: Why the runtime is absent (``import failed`` / ``version mismatch``).
        missing_modules: Which modules could not be loaded.
        fallback_version: The portable SKILL.md version used instead.
    """
    active: bool = False
    reason: str = ""
    missing_modules: tuple[str, ...] = ()
    fallback_version: str = "v1.2.0"


def detect_degraded() -> DegradedSignal:
    """
    Probe whether ``skillweave.runtime`` is importable.

    Returns:
        A ``DegradedSignal``. ``active=True`` means the runtime is absent
        and the session operates in degraded (unenforced) mode.
    """
    try:
        import skillweave.runtime  # noqa: F401
        return DegradedSignal(active=False)
    except ImportError:
        return DegradedSignal(
            active=True,
            reason="skillweave.runtime not importable — pre-v1.3 or whitelabel",
            missing_modules=("skillweave.runtime",),
            fallback_version="v1.2.0",
        )
