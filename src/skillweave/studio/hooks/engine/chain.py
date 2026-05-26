"""Hook execution chain — runs bindings in priority order with failure handling.

Supports 4 execution types:
  1. python  — instantiates a HookAdapter subclass and calls execute()
  2. shell   — runs a subprocess with PhaseContext as env vars
  3. skill_md — injects a SKILL.md file as context (returns content)
  4. capacium — executes a Capacium capability via ``cap run``

Failure modes:
  - block:  stop the chain on failure
  - warn:   log a warning and continue
  - ignore: silently continue
  - retry:  retry up to retry_count times, then apply block behavior
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import PhaseContext, HookResult
from ..adapter import HookAdapter
from ..binding.schema import HookBinding
from .condition import evaluate_condition, ConditionError

logger = logging.getLogger(__name__)


@dataclass
class ChainResult:
    """Aggregated result of running all hooks in a chain.

    Attributes:
        results: List of (binding, result) tuples for each executed hook.
        skipped: List of bindings that were skipped (condition false or skip status).
        final_gate: The aggregated gate decision (True if all passed, False if any failed
                    with block mode, None if no hooks had gate_override).
        aborted: Whether the chain was aborted due to a blocking failure.
        abort_reason: Human-readable reason for the abort.
    """

    results: List[tuple[HookBinding, HookResult]] = field(default_factory=list)
    skipped: List[HookBinding] = field(default_factory=list)
    final_gate: Optional[bool] = None
    aborted: bool = False
    abort_reason: str = ""

    @property
    def all_passed(self) -> bool:
        return all(r.passed for _, r in self.results) and not self.aborted

    @property
    def hook_count(self) -> int:
        return len(self.results) + len(self.skipped)

    @property
    def pass_count(self) -> int:
        return sum(1 for _, r in self.results if r.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for _, r in self.results if r.failed)

    def _compute_gate(self) -> Optional[bool]:
        """Compute the final gate decision from individual results.

        The last gate_override wins.  If no hooks set gate_override,
        the gate is True iff all hooks passed.
        """
        gate: Optional[bool] = None
        has_any = False
        for _, result in self.results:
            has_any = True
            if result.gate_override is not None:
                gate = result.gate_override

        if gate is not None:
            return gate
        if has_any:
            return self.all_passed
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "hook_count": self.hook_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "skipped_count": len(self.skipped),
            "final_gate": self.final_gate,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "results": [
                {"name": b.name, "status": r.status, "message": r.message}
                for b, r in self.results
            ],
        }


class ExecutionChain:
    """Executes a list of hook bindings in order, handling failures.

    Args:
        ctx: The PhaseContext for this execution.
        bindings: Resolved and sorted list of HookBinding objects.
    """

    def __init__(self, ctx: PhaseContext, bindings: List[HookBinding]):
        self._ctx = ctx
        self._bindings = bindings

    async def run(self) -> ChainResult:
        """Execute all bindings and return the aggregated result."""
        chain_result = ChainResult()

        for binding in self._bindings:
            # Evaluate condition
            if binding.condition:
                try:
                    ctx_vars = {
                        "phase": self._ctx.phase.value,
                        "position": self._ctx.position.value,
                        "gate_decision": self._ctx.gate_decision,
                    }
                    if not evaluate_condition(binding.condition, ctx_vars):
                        logger.debug("Condition false for %s, skipping", binding.name)
                        chain_result.skipped.append(binding)
                        continue
                except ConditionError as exc:
                    logger.warning("Condition error for %s: %s", binding.name, exc)
                    chain_result.skipped.append(binding)
                    continue

            # Execute with timeout
            result = await self._execute_with_retry(binding)

            chain_result.results.append((binding, result))

            # Handle failure modes
            if result.failed:
                if binding.failureMode == "block":
                    chain_result.aborted = True
                    chain_result.abort_reason = (
                        f"Hook '{binding.name}' failed with block mode: {result.message}"
                    )
                    break
                elif binding.failureMode == "warn":
                    logger.warning(
                        "Hook '%s' failed (warn mode): %s",
                        binding.name,
                        result.message,
                    )
                elif binding.failureMode == "ignore":
                    logger.debug("Hook '%s' failed (ignore mode)", binding.name)
                # retry is handled in _execute_with_retry

        chain_result.final_gate = chain_result._compute_gate()
        return chain_result

    async def _execute_with_retry(self, binding: HookBinding) -> HookResult:
        """Execute a single binding, retrying if failureMode is retry."""
        max_attempts = binding.retry_count + 1 if binding.failureMode == "retry" else 1
        last_result: Optional[HookResult] = None

        for attempt in range(1, max_attempts + 1):
            try:
                last_result = await asyncio.wait_for(
                    self._execute_one(binding),
                    timeout=binding.timeout_sec,
                )
                if last_result.passed or last_result.status == "skip":
                    return last_result
                if attempt < max_attempts:
                    logger.info(
                        "Retrying hook '%s' (attempt %d/%d)",
                        binding.name,
                        attempt + 1,
                        max_attempts,
                    )
            except asyncio.TimeoutError:
                last_result = HookResult(
                    status="fail",
                    message=f"Hook '{binding.name}' timed out after {binding.timeout_sec}s",
                )
                if attempt < max_attempts:
                    logger.info(
                        "Retrying hook '%s' after timeout (attempt %d/%d)",
                        binding.name,
                        attempt + 1,
                        max_attempts,
                    )
            except Exception as exc:
                last_result = HookResult(
                    status="fail",
                    message=f"Hook '{binding.name}' raised: {exc}",
                )
                if attempt < max_attempts:
                    logger.info(
                        "Retrying hook '%s' after error (attempt %d/%d)",
                        binding.name,
                        attempt + 1,
                        max_attempts,
                    )

        return last_result or HookResult(status="fail", message="No result produced")

    async def _execute_one(self, binding: HookBinding) -> HookResult:
        """Dispatch to the correct executor based on binding type."""
        if binding.type == "python":
            return await self._run_python(binding)
        elif binding.type == "shell":
            return await self._run_shell(binding)
        elif binding.type == "skill_md":
            return await self._run_skill_md(binding)
        elif binding.type == "capacium":
            return await self._run_capacium(binding)
        else:
            return HookResult(
                status="fail",
                message=f"Unknown hook type: {binding.type}",
            )

    async def _run_python(self, binding: HookBinding) -> HookResult:
        """Import and execute a Python HookAdapter."""
        module_path = binding.module
        if not module_path:
            return HookResult(status="fail", message="No module path specified")

        try:
            parts = module_path.rsplit(".", 1)
            if len(parts) != 2:
                return HookResult(
                    status="fail",
                    message=f"Module path must be 'package.ClassName', got: {module_path}",
                )

            mod = importlib.import_module(parts[0])
            cls = getattr(mod, parts[1])

            if not (isinstance(cls, type) and issubclass(cls, HookAdapter)):
                return HookResult(
                    status="fail",
                    message=f"{module_path} is not a HookAdapter subclass",
                )

            adapter: HookAdapter = cls()

            # Build context with hook-specific config
            ctx = PhaseContext(
                phase=self._ctx.phase,
                position=self._ctx.position,
                gate_decision=self._ctx.gate_decision,
                project_root=self._ctx.project_root,
                config=self._ctx.config,
                hook_config=binding.config,
            )

            if not adapter.should_run(ctx):
                return HookResult(status="skip", message=f"{binding.name}: should_run=False")

            return await adapter.execute(ctx)

        except ImportError as exc:
            return HookResult(
                status="fail",
                message=f"Failed to import {module_path}: {exc}",
            )
        except Exception as exc:
            return HookResult(
                status="fail",
                message=f"Python hook '{binding.name}' failed: {exc}",
            )

    async def _run_shell(self, binding: HookBinding) -> HookResult:
        """Execute a shell command with PhaseContext as env vars."""
        command = binding.command
        if not command:
            return HookResult(status="fail", message="No command specified")

        try:
            env = self._ctx.as_env()
            # Add hook-specific config as env vars
            for key, val in binding.config.items():
                env[f"HOOK_{key.upper()}"] = str(val)

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**dict(__import__("os").environ), **env},
                cwd=self._ctx.project_root,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return HookResult(
                    status="pass",
                    message=stdout.decode(errors="replace").strip() or f"{binding.name}: OK",
                )
            else:
                return HookResult(
                    status="fail",
                    message=(
                        stderr.decode(errors="replace").strip()
                        or stdout.decode(errors="replace").strip()
                        or f"{binding.name}: exit code {proc.returncode}"
                    ),
                )

        except Exception as exc:
            return HookResult(
                status="fail",
                message=f"Shell hook '{binding.name}' failed: {exc}",
            )

    async def _run_skill_md(self, binding: HookBinding) -> HookResult:
        """Read a SKILL.md file and return its content as an artifact."""
        skill_path = binding.skill_md
        if not skill_path:
            return HookResult(status="fail", message="No skill_md path specified")

        try:
            # Resolve relative to project root
            full_path = Path(self._ctx.project_root) / skill_path
            if not full_path.exists():
                # Try absolute path
                full_path = Path(skill_path)

            if not full_path.exists():
                return HookResult(
                    status="fail",
                    message=f"SKILL.md not found: {skill_path}",
                )

            content = full_path.read_text(encoding="utf-8")
            return HookResult(
                status="pass",
                message=f"Injected SKILL.md: {full_path.name} ({len(content)} chars)",
                artifacts=[str(full_path)],
            )

        except Exception as exc:
            return HookResult(
                status="fail",
                message=f"SKILL.md hook '{binding.name}' failed: {exc}",
            )

    async def _run_capacium(self, binding: HookBinding) -> HookResult:
        """Execute a Capacium capability via ``cap run``."""
        capability = binding.capability
        if not capability:
            return HookResult(status="fail", message="No capability specified")

        try:
            cmd = ["cap", "run", capability]

            # Pass PhaseContext as env vars
            env = self._ctx.as_env()
            for key, val in binding.config.items():
                env[f"HOOK_{key.upper()}"] = str(val)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**dict(__import__("os").environ), **env},
                cwd=self._ctx.project_root,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return HookResult(
                    status="pass",
                    message=stdout.decode(errors="replace").strip() or f"cap run {capability}: OK",
                )
            else:
                return HookResult(
                    status="fail",
                    message=(
                        stderr.decode(errors="replace").strip()
                        or f"cap run {capability}: exit code {proc.returncode}"
                    ),
                )

        except FileNotFoundError:
            return HookResult(
                status="fail",
                message=f"Capacium CLI not found. Install with: pip install capacium",
            )
        except Exception as exc:
            return HookResult(
                status="fail",
                message=f"Capacium hook '{binding.name}' failed: {exc}",
            )
