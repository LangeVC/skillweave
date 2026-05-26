"""Tests for the hook execution chain."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from skillweave.studio.hooks.engine.chain import ExecutionChain, ChainResult
from skillweave.studio.hooks.models import PhaseContext, HookResult, Phase, Position
from skillweave.studio.hooks.adapter import HookAdapter
from skillweave.studio.hooks.binding.schema import HookBinding


@pytest.fixture
def ctx(tmp_path):
    return PhaseContext(
        phase=Phase.BUILD,
        position=Position.PRE,
        gate_decision=None,
        project_root=str(tmp_path),
    )


def _shell_binding(
    name="test-hook",
    command="echo ok",
    priority=100,
    failure_mode="block",
    condition=None,
    timeout_sec=30,
    retry_count=1,
) -> HookBinding:
    return HookBinding(
        name=name,
        type="shell",
        command=command,
        priority=priority,
        failureMode=failure_mode,
        condition=condition,
        timeout_sec=timeout_sec,
        retry_count=retry_count,
        phase="build",
        position="pre",
    )


class TestChainResult:
    def test_empty_chain_all_passed(self):
        r = ChainResult()
        assert r.all_passed is True
        assert r.hook_count == 0

    def test_all_passed(self):
        r = ChainResult(results=[
            (_shell_binding(), HookResult(status="pass")),
            (_shell_binding(name="b"), HookResult(status="pass")),
        ])
        assert r.all_passed is True
        assert r.pass_count == 2
        assert r.fail_count == 0

    def test_one_failed(self):
        r = ChainResult(results=[
            (_shell_binding(), HookResult(status="pass")),
            (_shell_binding(name="b"), HookResult(status="fail")),
        ])
        assert r.all_passed is False
        assert r.fail_count == 1

    def test_aborted_not_all_passed(self):
        r = ChainResult(aborted=True, abort_reason="blocked")
        assert r.all_passed is False

    def test_compute_gate_with_override(self):
        r = ChainResult(results=[
            (_shell_binding(), HookResult(status="fail", gate_override=True)),
        ])
        assert r._compute_gate() is True

    def test_compute_gate_no_override(self):
        r = ChainResult(results=[
            (_shell_binding(), HookResult(status="pass")),
        ])
        assert r._compute_gate() is True

    def test_compute_gate_empty(self):
        r = ChainResult()
        assert r._compute_gate() is None

    def test_to_dict(self):
        r = ChainResult(results=[
            (_shell_binding(), HookResult(status="pass", message="ok")),
        ])
        d = r.to_dict()
        assert d["all_passed"] is True
        assert d["hook_count"] == 1
        assert len(d["results"]) == 1


class TestExecutionChainShell:
    @pytest.mark.asyncio
    async def test_successful_shell(self, ctx):
        binding = _shell_binding(command="echo hello")
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        assert result.all_passed
        assert result.pass_count == 1
        assert "hello" in result.results[0][1].message

    @pytest.mark.asyncio
    async def test_failing_shell_block(self, ctx):
        binding = _shell_binding(command="exit 1", failure_mode="block")
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        assert not result.all_passed
        assert result.aborted
        assert result.fail_count == 1

    @pytest.mark.asyncio
    async def test_failing_shell_warn(self, ctx):
        bindings = [
            _shell_binding(name="fail-hook", command="exit 1", failure_mode="warn", priority=100),
            _shell_binding(name="ok-hook", command="echo ok", priority=200),
        ]
        chain = ExecutionChain(ctx, bindings)
        result = await chain.run()

        # Chain should NOT abort — warn mode continues
        assert not result.aborted
        assert result.fail_count == 1
        assert result.pass_count == 1

    @pytest.mark.asyncio
    async def test_failing_shell_ignore(self, ctx):
        bindings = [
            _shell_binding(name="fail-hook", command="exit 1", failure_mode="ignore", priority=100),
            _shell_binding(name="ok-hook", command="echo ok", priority=200),
        ]
        chain = ExecutionChain(ctx, bindings)
        result = await chain.run()

        assert not result.aborted
        assert result.pass_count == 1

    @pytest.mark.asyncio
    async def test_failing_shell_retry(self, ctx):
        # retry_count=1 means max 2 attempts total
        binding = _shell_binding(
            command="exit 1",
            failure_mode="retry",
            retry_count=1,
        )
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        # Should fail after retries
        assert result.fail_count == 1

    @pytest.mark.asyncio
    async def test_multiple_hooks_priority_order(self, ctx):
        bindings = [
            _shell_binding(name="second", command="echo second", priority=200),
            _shell_binding(name="first", command="echo first", priority=100),
        ]
        # Sort by priority (chain expects pre-sorted)
        bindings.sort(key=lambda b: b.priority)
        chain = ExecutionChain(ctx, bindings)
        result = await chain.run()

        assert result.pass_count == 2
        assert result.results[0][0].name == "first"
        assert result.results[1][0].name == "second"

    @pytest.mark.asyncio
    async def test_block_stops_chain(self, ctx):
        bindings = [
            _shell_binding(name="blocker", command="exit 1", failure_mode="block", priority=100),
            _shell_binding(name="never-runs", command="echo hi", priority=200),
        ]
        chain = ExecutionChain(ctx, bindings)
        result = await chain.run()

        assert result.aborted
        assert len(result.results) == 1  # Only blocker ran
        assert result.results[0][0].name == "blocker"


class TestExecutionChainCondition:
    @pytest.mark.asyncio
    async def test_condition_true_runs(self, ctx):
        binding = _shell_binding(
            command="echo yes",
            condition="phase == 'build'",
        )
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        assert result.pass_count == 1
        assert len(result.skipped) == 0

    @pytest.mark.asyncio
    async def test_condition_false_skips(self, ctx):
        binding = _shell_binding(
            command="echo no",
            condition="phase == 'test'",
        )
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        assert result.pass_count == 0
        assert len(result.skipped) == 1

    @pytest.mark.asyncio
    async def test_invalid_condition_skips(self, ctx):
        binding = _shell_binding(
            command="echo no",
            condition="invalid syntax ==",
        )
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        assert len(result.skipped) == 1


class TestExecutionChainSkillMd:
    @pytest.mark.asyncio
    async def test_skill_md_success(self, ctx, tmp_path):
        skill_file = tmp_path / "test.md"
        skill_file.write_text("# Test Skill\nContent here")

        binding = HookBinding(
            name="skill-test",
            type="skill_md",
            skill_md=str(skill_file),
            phase="build",
            position="pre",
        )
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        assert result.all_passed
        assert "test.md" in result.results[0][1].message
        assert len(result.results[0][1].artifacts) == 1

    @pytest.mark.asyncio
    async def test_skill_md_not_found(self, ctx):
        binding = HookBinding(
            name="missing",
            type="skill_md",
            skill_md="/nonexistent/path.md",
            phase="build",
            position="pre",
        )
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        assert result.fail_count == 1
        assert "not found" in result.results[0][1].message


class TestExecutionChainTimeout:
    @pytest.mark.asyncio
    async def test_timeout_enforcement(self, ctx):
        binding = _shell_binding(
            command="sleep 10",
            timeout_sec=1,
        )
        chain = ExecutionChain(ctx, [binding])
        result = await chain.run()

        assert result.fail_count == 1
        assert "timed out" in result.results[0][1].message
