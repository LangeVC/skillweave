"""Tests for the binding loader."""

import pytest
from pathlib import Path

from skillweave.studio.hooks.binding.loader import BindingLoader
from skillweave.studio.hooks.binding.schema import BindingValidationError


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temp project with .skillweave/hooks/ directory."""
    hooks_dir = tmp_path / ".skillweave" / "hooks"
    hooks_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def tmp_user_dir(tmp_path):
    """Create a temp user hooks directory."""
    user_dir = tmp_path / "user-hooks"
    user_dir.mkdir()
    return user_dir


def _write_yaml(directory: Path, filename: str, content: str) -> Path:
    path = directory / filename
    path.write_text(content)
    return path


VALID_YAML = """\
version: "1"
phase: build
position: pre
hooks:
  - name: lint
    type: shell
    command: "./lint.sh"
    priority: 100
  - name: typecheck
    type: shell
    command: "./typecheck.sh"
    priority: 200
"""

INVALID_YAML_BAD_SYNTAX = """\
version: "1"
phase: build
position: pre
hooks:
  - name: bad
    type: [invalid yaml
"""

INVALID_YAML_BAD_SCHEMA = """\
version: "1"
phase: build
position: pre
hooks:
  - name: ""
    type: shell
    command: echo
"""


class TestBindingLoader:
    def test_load_valid_file(self, tmp_project):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        path = _write_yaml(hooks_dir, "build-pre.yaml", VALID_YAML)

        loader = BindingLoader(project_root=str(tmp_project))
        config = loader.load_file(path, source="project")

        assert config.phase == "build"
        assert config.position == "pre"
        assert len(config.hooks) == 2
        assert config.hooks[0].name == "lint"
        assert config.hooks[0].source == "project"
        assert config.hooks[1].name == "typecheck"

    def test_load_file_not_found_raises(self, tmp_project):
        loader = BindingLoader(project_root=str(tmp_project))
        with pytest.raises(FileNotFoundError):
            loader.load_file(Path("/nonexistent/path.yaml"))

    def test_load_invalid_yaml_raises(self, tmp_project):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        path = _write_yaml(hooks_dir, "bad.yaml", INVALID_YAML_BAD_SYNTAX)

        loader = BindingLoader(project_root=str(tmp_project))
        with pytest.raises(BindingValidationError, match="Invalid YAML"):
            loader.load_file(path)

    def test_load_invalid_schema_raises(self, tmp_project):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        path = _write_yaml(hooks_dir, "bad-schema.yaml", INVALID_YAML_BAD_SCHEMA)

        loader = BindingLoader(project_root=str(tmp_project))
        with pytest.raises(BindingValidationError, match="requires a 'name'"):
            loader.load_file(path)

    def test_load_empty_yaml_raises(self, tmp_project):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        path = _write_yaml(hooks_dir, "empty.yaml", "")

        loader = BindingLoader(project_root=str(tmp_project))
        with pytest.raises(BindingValidationError, match="Empty YAML"):
            loader.load_file(path)

    def test_load_for_phase_project_only(self, tmp_project, tmp_user_dir):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        _write_yaml(hooks_dir, "build-pre.yaml", VALID_YAML)

        loader = BindingLoader(
            project_root=str(tmp_project),
            user_dir=str(tmp_user_dir),
        )
        result = loader.load_for_phase("build", "pre")

        assert len(result["project"]) == 1
        assert len(result["user"]) == 0

    def test_load_for_phase_user_only(self, tmp_project, tmp_user_dir):
        _write_yaml(tmp_user_dir, "test-post.yaml", VALID_YAML.replace("build", "test").replace("pre", "post"))

        loader = BindingLoader(
            project_root=str(tmp_project),
            user_dir=str(tmp_user_dir),
        )
        result = loader.load_for_phase("test", "post")

        assert len(result["project"]) == 0
        assert len(result["user"]) == 1

    def test_load_for_phase_both_sources(self, tmp_project, tmp_user_dir):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        _write_yaml(hooks_dir, "build-pre.yaml", VALID_YAML)
        _write_yaml(tmp_user_dir, "build-pre.yaml", VALID_YAML)

        loader = BindingLoader(
            project_root=str(tmp_project),
            user_dir=str(tmp_user_dir),
        )
        result = loader.load_for_phase("build", "pre")

        assert len(result["project"]) == 1
        assert len(result["user"]) == 1

    def test_load_for_phase_no_files(self, tmp_project, tmp_user_dir):
        loader = BindingLoader(
            project_root=str(tmp_project),
            user_dir=str(tmp_user_dir),
        )
        result = loader.load_for_phase("release", "post")

        assert len(result["project"]) == 0
        assert len(result["user"]) == 0

    def test_load_for_phase_skips_invalid(self, tmp_project, tmp_user_dir):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        _write_yaml(hooks_dir, "build-pre.yaml", INVALID_YAML_BAD_SYNTAX)

        loader = BindingLoader(
            project_root=str(tmp_project),
            user_dir=str(tmp_user_dir),
        )
        result = loader.load_for_phase("build", "pre")

        # Invalid files are skipped with a warning, not raising
        assert len(result["project"]) == 0

    def test_load_all(self, tmp_project, tmp_user_dir):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        _write_yaml(hooks_dir, "build-pre.yaml", VALID_YAML)

        test_yaml = VALID_YAML.replace("build", "test").replace("pre", "post")
        _write_yaml(tmp_user_dir, "test-post.yaml", test_yaml)

        loader = BindingLoader(
            project_root=str(tmp_project),
            user_dir=str(tmp_user_dir),
        )
        configs = loader.load_all()

        assert len(configs) == 2
        phases = {c.phase for c in configs}
        assert phases == {"build", "test"}

    def test_source_tagging(self, tmp_project, tmp_user_dir):
        hooks_dir = tmp_project / ".skillweave" / "hooks"
        _write_yaml(hooks_dir, "build-pre.yaml", VALID_YAML)
        _write_yaml(tmp_user_dir, "build-pre.yaml", VALID_YAML)

        loader = BindingLoader(
            project_root=str(tmp_project),
            user_dir=str(tmp_user_dir),
        )
        result = loader.load_for_phase("build", "pre")

        for hook in result["project"][0].hooks:
            assert hook.source == "project"
        for hook in result["user"][0].hooks:
            assert hook.source == "user"
