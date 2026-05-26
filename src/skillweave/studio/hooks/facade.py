"""Public facade for the hook binding engine.

This module provides the single entry point that existing SkillWeave skills
call at phase boundaries.  It handles binding resolution, tier gating,
execution chain, and result reporting — the calling skill only needs to
pass the phase, position, and project root.

Usage in existing skills::

    from skillweave.studio.hooks.facade import run_hooks

    # At a phase boundary:
    result = await run_hooks("build", "pre", project_root="/path/to/project")
    if result and not result.all_passed:
        # Handle gate failure
        ...
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from .models import Phase, Position, PhaseContext
from .binding.loader import BindingLoader
from .binding.resolver import BindingResolver
from .binding.schema import HookBinding
from .engine.chain import ExecutionChain, ChainResult
from .discovery.scanner import TriggerScanner
from .discovery.registry import DismissalRegistry
from ..licensing.tier_gate import TierGate, Tier

logger = logging.getLogger(__name__)


async def run_hooks(
    phase: str,
    position: str,
    project_root: str = ".",
    config: Optional[dict] = None,
    gate_decision: Optional[bool] = None,
    gate: Optional[TierGate] = None,
    include_auto_discovered: bool = True,
) -> Optional[ChainResult]:
    """Run all resolved hooks for a phase+position.

    This is the primary public API.  Existing skills call this at
    each phase boundary.

    Args:
        phase: Lifecycle phase (e.g. "build", "test", "release").
        position: "pre" or "post".
        project_root: Absolute path to the project root.
        config: Optional resolved SkillWeave config dict.
        gate_decision: Upstream gate result (passed from prior hook chain).
        gate: Optional TierGate instance (uses default if not provided).
        include_auto_discovered: Whether to include auto-discovered bindings.

    Returns:
        ChainResult if hooks were executed, None if no hooks were found
        or if the tier gate blocked execution.
    """
    # Tier gate check
    _gate = gate or TierGate()
    try:
        _gate.check(phase=phase, position=position)
    except Exception as exc:
        logger.debug(
            "Tier gate blocked hooks for %s_%s: %s",
            position, phase, exc,
        )
        # pre_discovery is free tier — if gate blocks, no hooks to run
        # for Studio phases, we should raise or return None
        return None

    # Load and resolve bindings
    loader = BindingLoader(project_root=project_root)
    resolver = BindingResolver(loader)

    auto_bindings: Optional[List[HookBinding]] = None
    if include_auto_discovered:
        try:
            scanner = TriggerScanner()
            registry = DismissalRegistry(project_root=project_root)
            discovered = scanner.scan()
            active = registry.filter_dismissed(discovered)
            auto_bindings = [d.to_hook_binding() for d in active]
        except Exception as exc:
            logger.debug("Auto-discovery failed (non-blocking): %s", exc)

    bindings = resolver.resolve(phase, position, auto_bindings)

    if not bindings:
        logger.debug("No hooks found for %s_%s", position, phase)
        return None

    # Build context
    ctx = PhaseContext(
        phase=Phase(phase),
        position=Position(position),
        gate_decision=gate_decision,
        project_root=project_root,
        config=config or {},
    )

    # Execute chain
    chain = ExecutionChain(ctx, bindings)
    result = await chain.run()

    # Log summary
    logger.info(
        "Hooks %s_%s: %d/%d passed, %d skipped%s",
        position,
        phase,
        result.pass_count,
        result.hook_count,
        len(result.skipped),
        " [ABORTED]" if result.aborted else "",
    )

    return result


def run_hooks_sync(
    phase: str,
    position: str,
    project_root: str = ".",
    config: Optional[dict] = None,
    gate_decision: Optional[bool] = None,
    gate: Optional[TierGate] = None,
    include_auto_discovered: bool = True,
) -> Optional[ChainResult]:
    """Synchronous wrapper for run_hooks.

    For use in skills that don't have an event loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an async context — create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                run_hooks(
                    phase, position, project_root,
                    config, gate_decision, gate,
                    include_auto_discovered,
                ),
            )
            return future.result()
    else:
        return asyncio.run(
            run_hooks(
                phase, position, project_root,
                config, gate_decision, gate,
                include_auto_discovered,
            )
        )


def list_hooks(
    project_root: str = ".",
    phase: Optional[str] = None,
    include_auto_discovered: bool = True,
) -> dict:
    """List all configured hooks for display purposes.

    Returns:
        Dict with keys: bindings (list), summary (str).
    """
    loader = BindingLoader(project_root=project_root)
    resolver = BindingResolver(loader)

    auto_bindings: Optional[List[HookBinding]] = None
    if include_auto_discovered:
        try:
            scanner = TriggerScanner()
            registry = DismissalRegistry(project_root=project_root)
            discovered = scanner.scan()
            active = registry.filter_dismissed(discovered)
            auto_bindings = [d.to_hook_binding() for d in active]
        except Exception:
            pass

    if phase:
        from .models import Position
        all_bindings: List[HookBinding] = []
        for pos in Position:
            bindings = resolver.resolve(phase, pos.value, auto_bindings)
            all_bindings.extend(bindings)
    else:
        all_result = resolver.resolve_all(auto_bindings)
        all_bindings = []
        for hooks in all_result.values():
            all_bindings.extend(hooks)

    return {
        "bindings": [
            {
                "name": b.name,
                "type": b.type,
                "phase": b.phase,
                "position": b.position,
                "priority": b.priority,
                "source": b.source,
                "failureMode": b.failureMode,
            }
            for b in all_bindings
        ],
        "summary": f"{len(all_bindings)} hook(s) configured",
    }
