"""Tests for the hook system facade — the public API for skill integration."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import time

from skillweave.studio.hooks.facade import run_hooks, list_hooks, run_hooks_sync
from skillweave.studio.hooks.engine.chain import ChainResult
from skillweave.studio.licensing.tier_gate import TierGate, Tier
from skillweave.studio.licensing.jwt_validator import LicenseValidator, LicensePayload


def _write_yaml(directory: Path, filename: str, content: str) -> Path:
    path = directory / filename
    path.write_text(content)
    return path


VALID_BUILD_PRE_YAML = """\
version: "1"
phase: build
position: pre
hooks:
  - name: echo-test
    type: shell
    command: "echo hook-executed"
    priority: 100
    failureMode: warn
"""

VALID_DISCOVERY_PRE_YAML = """\
version: "1"
phase: discovery
position: pre
hooks:
  - name: mentor-hook
    type: shell
    command: "echo mentoring"
    priority: 100
    failureMode: warn
"""


def _make_studio_payload() -> LicensePayload:
    return LicensePayload(
        sub="test@studio.com",
        tier="studio",
        iat=int(time.time()),
        exp=int(time.time()) + 3600,
    )


@pytest.fixture
def project_with_hooks(tmp_path):
    hooks_dir = tmp_path / ".skillweave" / "hooks"
    hooks_dir.mkdir(parents=True)
    _write_yaml(hooks_dir, "build-pre.yaml", VALID_BUILD_PRE_YAML)
    _write_yaml(hooks_dir, "discovery-pre.yaml", VALID_DISCOVERY_PRE_YAML)
    return tmp_path


@pytest.fixture
def studio_gate():
    validator = MagicMock(spec=LicenseValidator)
    validator.load_from_disk.return_value = _make_studio_payload()
    return TierGate(validator=validator)


class TestRunHooks:
    @pytest.mark.asyncio
    async def test_runs_hooks_with_studio_license(self, project_with_hooks, studio_gate):
        result = await run_hooks(
            phase="build",
            position="pre",
            project_root=str(project_with_hooks),
            gate=studio_gate,
            include_auto_discovered=False,
        )

        assert result is not None
        assert result.pass_count == 1
        assert result.all_passed

    @pytest.mark.asyncio
    async def test_no_hooks_returns_none(self, project_with_hooks, studio_gate):
        result = await run_hooks(
            phase="observe",
            position="post",
            project_root=str(project_with_hooks),
            gate=studio_gate,
            include_auto_discovered=False,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_tier_gate_blocks_studio_phases(self, project_with_hooks):
        # No license → tier gate blocks build hooks
        result = await run_hooks(
            phase="build",
            position="pre",
            project_root=str(project_with_hooks),
            include_auto_discovered=False,
        )

        assert result is None  # Blocked by tier gate

    @pytest.mark.asyncio
    async def test_pre_discovery_free_tier(self, project_with_hooks):
        # pre_discovery should work without Studio license
        result = await run_hooks(
            phase="discovery",
            position="pre",
            project_root=str(project_with_hooks),
            include_auto_discovered=False,
        )

        # pre_discovery is Free tier → TierGate allows it
        assert result is not None
        assert result.pass_count == 1


class TestListHooks:
    def test_lists_configured_hooks(self, project_with_hooks):
        result = list_hooks(
            project_root=str(project_with_hooks),
            include_auto_discovered=False,
        )

        assert len(result["bindings"]) >= 1
        names = {b["name"] for b in result["bindings"]}
        assert "echo-test" in names

    def test_filter_by_phase(self, project_with_hooks):
        result = list_hooks(
            project_root=str(project_with_hooks),
            phase="build",
            include_auto_discovered=False,
        )

        for b in result["bindings"]:
            assert b["phase"] == "build"

    def test_empty_project(self, tmp_path):
        (tmp_path / ".skillweave" / "hooks").mkdir(parents=True)
        result = list_hooks(
            project_root=str(tmp_path),
            include_auto_discovered=False,
        )

        assert len(result["bindings"]) == 0


class TestRunHooksSync:
    def test_sync_wrapper(self, project_with_hooks, studio_gate):
        result = run_hooks_sync(
            phase="build",
            position="pre",
            project_root=str(project_with_hooks),
            gate=studio_gate,
            include_auto_discovered=False,
        )

        assert result is not None
        assert result.all_passed


class TestIntegrationPoints:
    """Tests that verify the 4 injection points work correctly."""

    @pytest.mark.asyncio
    async def test_pre_discovery_injection(self, project_with_hooks):
        """pre_discovery — mentoring hooks, Free tier."""
        result = await run_hooks(
            phase="discovery",
            position="pre",
            project_root=str(project_with_hooks),
            include_auto_discovered=False,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_pre_build_injection(self, project_with_hooks, studio_gate):
        """pre_build — CI setup, env validation. Studio tier."""
        result = await run_hooks(
            phase="build",
            position="pre",
            project_root=str(project_with_hooks),
            gate=studio_gate,
            include_auto_discovered=False,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_post_test_injection(self, project_with_hooks, studio_gate):
        """post_test — quality gates, coverage. Studio tier."""
        # No hooks configured for test-post, so result is None
        result = await run_hooks(
            phase="test",
            position="post",
            project_root=str(project_with_hooks),
            gate=studio_gate,
            include_auto_discovered=False,
        )
        assert result is None  # No hooks configured

    @pytest.mark.asyncio
    async def test_post_release_injection(self, project_with_hooks, studio_gate):
        """post_release — deploy triggers, notifications. Studio tier."""
        result = await run_hooks(
            phase="release",
            position="post",
            project_root=str(project_with_hooks),
            gate=studio_gate,
            include_auto_discovered=False,
        )
        assert result is None  # No hooks configured
