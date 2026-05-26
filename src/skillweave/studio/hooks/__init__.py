"""Hook system — core abstractions, binding engine, execution chain."""

from .models import PhaseContext, HookResult, HookStatus, Phase, Position
from .adapter import HookAdapter
from .facade import run_hooks, list_hooks, run_hooks_sync

__all__ = [
    "PhaseContext",
    "HookResult",
    "HookStatus",
    "Phase",
    "Position",
    "HookAdapter",
    "run_hooks",
    "list_hooks",
    "run_hooks_sync",
]
