"""Tests for reference capabilities."""

import pytest
from skillweave.studio.hooks.models import PhaseContext, Phase, Position
from skillweave.studio.reference.ci_gate import CIGateHook, MANIFEST


class TestCIGateHook:
    @pytest.fixture
    def hook(self):
        return CIGateHook()

    def test_should_run_post_test(self, hook):
        ctx = PhaseContext(phase=Phase.TEST, position=Position.POST)
        assert hook.should_run(ctx) is True

    def test_should_not_run_pre_build(self, hook):
        ctx = PhaseContext(phase=Phase.BUILD, position=Position.PRE)
        assert hook.should_run(ctx) is False

    @pytest.mark.asyncio
    async def test_execute_returns_pass(self, hook):
        ctx = PhaseContext(
            phase=Phase.TEST,
            position=Position.POST,
            hook_config={"min_coverage": 90},
        )
        result = await hook.execute(ctx)
        assert result.passed
        assert "90" in result.message

    @pytest.mark.asyncio
    async def test_execute_default_config(self, hook):
        ctx = PhaseContext(phase=Phase.TEST, position=Position.POST)
        result = await hook.execute(ctx)
        assert result.passed
        assert "80" in result.message  # Default min_coverage

    @pytest.mark.asyncio
    async def test_rollback_noop(self, hook):
        ctx = PhaseContext(phase=Phase.TEST, position=Position.POST)
        await hook.rollback(ctx)  # Should not raise


class TestCIGateManifest:
    def test_manifest_has_triggers(self):
        assert "triggers" in MANIFEST
        triggers = MANIFEST["triggers"]
        assert len(triggers) == 1
        assert triggers[0]["source"] == "skillweave"
        assert triggers[0]["filter"]["phase"] == "test"
        assert triggers[0]["filter"]["position"] == "post"

    def test_manifest_has_config_schema(self):
        assert "config_schema" in MANIFEST
        assert "min_coverage" in MANIFEST["config_schema"]
        assert "require_green" in MANIFEST["config_schema"]
