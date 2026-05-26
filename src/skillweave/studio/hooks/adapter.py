"""Abstract base class for Python-based hook adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import PhaseContext, HookResult


class HookAdapter(ABC):
    """Contract that every Python hook must implement.

    Lifecycle:
        1. ``should_run(ctx)`` — decide if this hook applies.
        2. ``execute(ctx)``   — perform the hook action.
        3. ``rollback(ctx)``  — undo side-effects on failure (optional).
    """

    @abstractmethod
    def should_run(self, ctx: PhaseContext) -> bool:
        """Return True if this hook should execute for the given context."""
        ...

    @abstractmethod
    async def execute(self, ctx: PhaseContext) -> HookResult:
        """Execute the hook and return a result."""
        ...

    async def rollback(self, ctx: PhaseContext) -> None:
        """Undo side-effects.  Default is no-op."""
        pass
