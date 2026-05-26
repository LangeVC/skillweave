"""Tests for HookAdapter ABC contract."""

import pytest
from skillweave.studio.hooks.adapter import HookAdapter
from skillweave.studio.hooks.models import PhaseContext, HookResult, Phase, Position


class AlwaysRunHook(HookAdapter):
    """Concrete test implementation."""

    def __init__(self, result_status: str = "pass"):
        self._status = result_status

    def should_run(self, ctx: PhaseContext) -> bool:
        return True

    async def execute(self, ctx: PhaseContext) -> HookResult:
        return HookResult(status=self._status, message=f"mock-{self._status}")


class ConditionalHook(HookAdapter):
    """Only runs during build phase."""

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.phase == Phase.BUILD

    async def execute(self, ctx: PhaseContext) -> HookResult:
        return HookResult(status="pass", message="build hook ran")

    async def rollback(self, ctx: PhaseContext) -> None:
        pass  # explicit rollback implementation


class TestHookAdapter:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            HookAdapter()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_always_run_pass(self):
        hook = AlwaysRunHook("pass")
        ctx = PhaseContext(phase=Phase.BUILD, position=Position.PRE)
        assert hook.should_run(ctx)
        result = await hook.execute(ctx)
        assert result.passed
        assert result.message == "mock-pass"

    @pytest.mark.asyncio
    async def test_always_run_fail(self):
        hook = AlwaysRunHook("fail")
        ctx = PhaseContext(phase=Phase.TEST, position=Position.POST)
        result = await hook.execute(ctx)
        assert result.failed

    @pytest.mark.asyncio
    async def test_conditional_runs_for_build(self):
        hook = ConditionalHook()
        build_ctx = PhaseContext(phase=Phase.BUILD, position=Position.PRE)
        test_ctx = PhaseContext(phase=Phase.TEST, position=Position.PRE)
        assert hook.should_run(build_ctx)
        assert not hook.should_run(test_ctx)

    @pytest.mark.asyncio
    async def test_default_rollback_is_noop(self):
        hook = AlwaysRunHook()
        ctx = PhaseContext(phase=Phase.BUILD, position=Position.PRE)
        await hook.rollback(ctx)  # should not raise

    @pytest.mark.asyncio
    async def test_explicit_rollback(self):
        hook = ConditionalHook()
        ctx = PhaseContext(phase=Phase.BUILD, position=Position.PRE)
        await hook.rollback(ctx)  # should not raise
