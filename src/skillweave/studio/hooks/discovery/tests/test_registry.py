"""Tests for the dismissal registry."""

import json
import pytest
from pathlib import Path

from skillweave.studio.hooks.discovery.registry import DismissalRegistry
from skillweave.studio.hooks.discovery.scanner import DiscoveredBinding


@pytest.fixture
def project_root(tmp_path):
    hooks_dir = tmp_path / ".skillweave" / "hooks"
    hooks_dir.mkdir(parents=True)
    return tmp_path


def _binding(capability="ci-gate", phase="test", position="post"):
    return DiscoveredBinding(
        capability=capability,
        phase=phase,
        position=position,
    )


class TestDismissalRegistry:
    def test_initially_empty(self, project_root):
        reg = DismissalRegistry(project_root=str(project_root))
        assert reg.dismissed_count == 0

    def test_dismiss_and_check(self, project_root):
        reg = DismissalRegistry(project_root=str(project_root))
        b = _binding()

        assert not reg.is_dismissed(b)
        reg.dismiss(b)
        assert reg.is_dismissed(b)
        assert reg.dismissed_count == 1

    def test_undismiss(self, project_root):
        reg = DismissalRegistry(project_root=str(project_root))
        b = _binding()

        reg.dismiss(b)
        assert reg.is_dismissed(b)
        reg.undismiss(b)
        assert not reg.is_dismissed(b)

    def test_persistence(self, project_root):
        b = _binding()

        reg1 = DismissalRegistry(project_root=str(project_root))
        reg1.dismiss(b)

        # New instance should load from disk
        reg2 = DismissalRegistry(project_root=str(project_root))
        assert reg2.is_dismissed(b)

    def test_filter_dismissed(self, project_root):
        reg = DismissalRegistry(project_root=str(project_root))

        b1 = _binding("ci-gate", "test", "post")
        b2 = _binding("security", "build", "pre")

        reg.dismiss(b1)

        result = reg.filter_dismissed([b1, b2])
        assert len(result) == 1
        assert result[0].capability == "security"

    def test_different_bindings_independent(self, project_root):
        reg = DismissalRegistry(project_root=str(project_root))

        b1 = _binding("a", "test", "post")
        b2 = _binding("b", "test", "post")

        reg.dismiss(b1)
        assert reg.is_dismissed(b1)
        assert not reg.is_dismissed(b2)

    def test_clear(self, project_root):
        reg = DismissalRegistry(project_root=str(project_root))

        reg.dismiss(_binding("a"))
        reg.dismiss(_binding("b"))
        assert reg.dismissed_count == 2

        reg.clear()
        assert reg.dismissed_count == 0

    def test_corrupt_file_handled(self, project_root):
        dismissed_path = project_root / ".skillweave" / "hooks" / ".dismissed.json"
        dismissed_path.write_text("not json{{{")

        # Should not raise, just start empty
        reg = DismissalRegistry(project_root=str(project_root))
        assert reg.dismissed_count == 0

    def test_missing_hooks_dir_created_on_save(self, tmp_path):
        # No .skillweave/hooks/ dir exists
        reg = DismissalRegistry(project_root=str(tmp_path))
        reg.dismiss(_binding())

        dismissed_path = tmp_path / ".skillweave" / "hooks" / ".dismissed.json"
        assert dismissed_path.exists()
