"""Dependency-ready fan-out (SW-FANOUT-001)."""

from .dispatch import (
    FanOutChild,
    FanOutResult,
    fan_out_dispatch,
)

__all__ = [
    "FanOutChild",
    "FanOutResult",
    "fan_out_dispatch",
]
