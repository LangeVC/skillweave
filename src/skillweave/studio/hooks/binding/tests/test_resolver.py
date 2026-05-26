"""Tests for the binding resolver — merge, deduplication, priority sorting."""

import pytest
from pathlib import Path

from skillweave.studio.hooks.binding.resolver import BindingResolver, SOURCE_PRECEDENCE
from skillweave.studio.hooks.binding.loader import BindingLoader
from skillweave.studio.hooks.binding.schema import HookBinding


def _write_yaml(directory: Path, filename: str, content: str) -> Path:
    path = directory / filename
    path.write_text(content)
    return path


PROJECT_YAML = """\
version: "1"
phase: build
position: pre
hooks:
  - name: project-lint
    type: shell
    command: "./lint.sh"
    priority: 100
  - name: project-test
    type: shell
    command: "./test.sh"
    priority: 200
"""

USER_YAML = """\
version: "1"
phase: build
position: pre
hooks:
  - name: user-format
    type: shell
    command: "./format.sh"
    priority: 50
  - name: user-lint
    type: shell
    command: "./lint.sh"
    priority: 150
"""


@pytest.fixture
def setup_dirs(tmp_path):
    """Create project and user hook directories."""
    project_root = tmp_path / "project"
    project_hooks = project_root / ".skillweave" / "hooks"
    project_hooks.mkdir(parents=True)

    user_dir = tmp_path / "user-hooks"
    user_dir.mkdir()

    return project_root, project_hooks, user_dir


class TestBindingResolver:
    def test_project_only(self, setup_dirs):
        project_root, project_hooks, user_dir = setup_dirs
        _write_yaml(project_hooks, "build-pre.yaml", PROJECT_YAML)

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve("build", "pre")

        assert len(result) == 2
        assert result[0].name == "project-lint"
        assert result[1].name == "project-test"

    def test_user_only(self, setup_dirs):
        project_root, project_hooks, user_dir = setup_dirs
        _write_yaml(user_dir, "build-pre.yaml", USER_YAML)

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve("build", "pre")

        assert len(result) == 2
        assert result[0].name == "user-format"  # priority 50
        assert result[1].name == "user-lint"    # priority 150

    def test_priority_sorting(self, setup_dirs):
        project_root, project_hooks, user_dir = setup_dirs
        _write_yaml(project_hooks, "build-pre.yaml", PROJECT_YAML)

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve("build", "pre")

        priorities = [h.priority for h in result]
        assert priorities == sorted(priorities)

    def test_dedup_project_over_user(self, setup_dirs):
        """Project binding with same command overrides user binding."""
        project_root, project_hooks, user_dir = setup_dirs

        # Both have a hook with command "./lint.sh" — project should win
        _write_yaml(project_hooks, "build-pre.yaml", PROJECT_YAML)
        _write_yaml(user_dir, "build-pre.yaml", USER_YAML)

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve("build", "pre")

        # Dedup key for ./lint.sh:build:pre — project-lint should override user-lint
        lint_hooks = [h for h in result if "lint.sh" in (h.command or "")]
        assert len(lint_hooks) == 1
        assert lint_hooks[0].source == "project"
        assert lint_hooks[0].name == "project-lint"

    def test_dedup_project_over_auto(self, setup_dirs):
        """Project binding overrides auto-discovered binding."""
        project_root, project_hooks, user_dir = setup_dirs
        _write_yaml(project_hooks, "build-pre.yaml", PROJECT_YAML)

        auto = [
            HookBinding(
                name="auto-lint",
                type="shell",
                command="./lint.sh",  # Same command as project-lint
                priority=50,
                source="auto",
                phase="build",
                position="pre",
            ),
        ]

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve("build", "pre", auto_bindings=auto)

        lint_hooks = [h for h in result if "lint.sh" in (h.command or "")]
        assert len(lint_hooks) == 1
        assert lint_hooks[0].source == "project"

    def test_auto_bindings_included_when_no_conflict(self, setup_dirs):
        """Auto-discovered bindings are included if no conflict."""
        project_root, project_hooks, user_dir = setup_dirs
        _write_yaml(project_hooks, "build-pre.yaml", PROJECT_YAML)

        auto = [
            HookBinding(
                name="auto-security",
                type="capacium",
                capability="security-scan",
                priority=300,
                source="auto",
            ),
        ]

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve("build", "pre", auto_bindings=auto)

        names = [h.name for h in result]
        assert "auto-security" in names

    def test_merge_from_both_sources(self, setup_dirs):
        """Non-conflicting hooks from both sources are merged."""
        project_root, project_hooks, user_dir = setup_dirs
        _write_yaml(project_hooks, "build-pre.yaml", PROJECT_YAML)
        _write_yaml(user_dir, "build-pre.yaml", USER_YAML)

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve("build", "pre")

        # project-lint and user-lint conflict (same command) -> project wins
        # project-test is unique
        # user-format is unique
        names = {h.name for h in result}
        assert "project-lint" in names
        assert "project-test" in names
        assert "user-format" in names
        assert "user-lint" not in names  # deduplicated

    def test_empty_resolution(self, setup_dirs):
        project_root, project_hooks, user_dir = setup_dirs

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve("observe", "post")

        assert result == []

    def test_resolve_all(self, setup_dirs):
        project_root, project_hooks, user_dir = setup_dirs
        _write_yaml(project_hooks, "build-pre.yaml", PROJECT_YAML)

        test_yaml = PROJECT_YAML.replace("build", "test").replace("pre", "post")
        _write_yaml(project_hooks, "test-post.yaml", test_yaml)

        loader = BindingLoader(project_root=str(project_root), user_dir=str(user_dir))
        resolver = BindingResolver(loader)
        result = resolver.resolve_all()

        assert "pre_build" in result
        assert "post_test" in result
        assert len(result) == 2


class TestSourcePrecedence:
    def test_precedence_order(self):
        assert SOURCE_PRECEDENCE["project"] < SOURCE_PRECEDENCE["user"]
        assert SOURCE_PRECEDENCE["user"] < SOURCE_PRECEDENCE["auto"]


class TestDeduplication:
    def test_same_source_keeps_first(self):
        """Within the same source, first occurrence wins."""
        bindings = [
            HookBinding(name="a", type="shell", command="./x.sh", source="project", phase="build", position="pre", priority=100),
            HookBinding(name="b", type="shell", command="./x.sh", source="project", phase="build", position="pre", priority=50),
        ]
        result = BindingResolver._deduplicate(bindings)
        assert len(result) == 1
        assert result[0].name == "a"  # first occurrence kept (same precedence)

    def test_different_dedup_keys_preserved(self):
        bindings = [
            HookBinding(name="lint", type="shell", command="./lint.sh", source="project", phase="build", position="pre"),
            HookBinding(name="test", type="shell", command="./test.sh", source="project", phase="build", position="pre"),
        ]
        result = BindingResolver._deduplicate(bindings)
        assert len(result) == 2

    def test_higher_precedence_replaces(self):
        """When auto is seen first and project comes later, project replaces."""
        bindings = [
            HookBinding(name="auto-hook", type="shell", command="./x.sh", source="auto", phase="build", position="pre"),
            HookBinding(name="proj-hook", type="shell", command="./x.sh", source="project", phase="build", position="pre"),
        ]
        result = BindingResolver._deduplicate(bindings)
        assert len(result) == 1
        assert result[0].name == "proj-hook"
        assert result[0].source == "project"
