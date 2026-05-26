"""Tests for the hooks CLI commands."""

import pytest
import yaml
from pathlib import Path

from skillweave.studio.cli.hooks_cli import hooks_main


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
"""


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    hooks_dir = tmp_path / ".skillweave" / "hooks"
    hooks_dir.mkdir(parents=True)
    _write_yaml(hooks_dir, "build-pre.yaml", VALID_YAML)
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestHooksList:
    def test_list_shows_hooks(self, project_root, capsys):
        ret = hooks_main(["list"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "lint" in captured.out

    def test_list_json(self, project_root, capsys):
        ret = hooks_main(["list", "--json"])
        assert ret == 0
        captured = capsys.readouterr()
        import json
        data = json.loads(captured.out)
        assert len(data["bindings"]) >= 1

    def test_list_filter_phase(self, project_root, capsys):
        ret = hooks_main(["list", "--phase", "build"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "lint" in captured.out

    def test_list_empty_phase(self, project_root, capsys):
        ret = hooks_main(["list", "--phase", "observe"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "No hooks configured" in captured.out


class TestHooksBind:
    def test_bind_creates_yaml(self, project_root):
        ret = hooks_main(["bind", "security-scan", "test", "post"])
        assert ret == 0

        filepath = project_root / ".skillweave" / "hooks" / "test-post.yaml"
        assert filepath.exists()

        with open(filepath) as f:
            data = yaml.safe_load(f)

        assert len(data["hooks"]) == 1
        assert data["hooks"][0]["name"] == "security-scan"
        assert data["hooks"][0]["type"] == "capacium"

    def test_bind_appends_to_existing(self, project_root):
        ret = hooks_main(["bind", "typecheck", "build", "pre", "--priority", "200"])
        assert ret == 0

        filepath = project_root / ".skillweave" / "hooks" / "build-pre.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)

        names = {h["name"] for h in data["hooks"]}
        assert "lint" in names
        assert "typecheck" in names

    def test_bind_duplicate_rejected(self, project_root, capsys):
        ret = hooks_main(["bind", "lint", "build", "pre"])
        assert ret == 1
        captured = capsys.readouterr()
        assert "already exists" in captured.out

    def test_bind_with_type(self, project_root):
        ret = hooks_main(["bind", "./test.sh", "test", "pre", "--type", "shell"])
        assert ret == 0

        filepath = project_root / ".skillweave" / "hooks" / "test-pre.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)

        assert data["hooks"][0]["type"] == "shell"
        assert data["hooks"][0]["command"] == "./test.sh"


class TestHooksUnbind:
    def test_unbind_removes_hook(self, project_root):
        ret = hooks_main(["unbind", "lint", "build"])
        assert ret == 0

        filepath = project_root / ".skillweave" / "hooks" / "build-pre.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)

        assert len(data["hooks"]) == 0

    def test_unbind_not_found(self, project_root, capsys):
        ret = hooks_main(["unbind", "nonexistent", "build"])
        assert ret == 1
        captured = capsys.readouterr()
        assert "No binding found" in captured.out


class TestHooksDiscover:
    def test_discover_no_capabilities(self, project_root, capsys):
        ret = hooks_main(["discover"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "No SkillWeave triggers" in captured.out


class TestHooksHelp:
    def test_no_command_shows_help(self, capsys):
        ret = hooks_main([])
        assert ret == 0

    def test_help_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            hooks_main(["--help"])
        assert exc.value.code == 0
