"""Dependency-ready fan-out (SW-FANOUT-001)."""

from .dispatch import (
    FanOutChild,
    FanOutLaunchContext,
    FanOutResult,
    fan_out_dispatch,
)

__all__ = [
    "FanOutChild",
    "FanOutLaunchContext",
    "FanOutResult",
    "fan_out_dispatch",
]
