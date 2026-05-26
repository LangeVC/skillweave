"""Tests for binding schema validation."""

import pytest
from skillweave.studio.hooks.binding.schema import (
    HookBinding,
    BindingConfig,
    BindingValidationError,
)


class TestHookBinding:
    def test_valid_python_binding(self):
        b = HookBinding(
            name="lint",
            type="python",
            module="myproject.hooks.LintHook",
            priority=100,
        )
        b.validate()
        assert b.dedup_key == "myproject.hooks.LintHook:None:None"

    def test_valid_shell_binding(self):
        b = HookBinding(
            name="test-runner",
            type="shell",
            command="./run-tests.sh",
            priority=200,
        )
        b.validate()

    def test_valid_skill_md_binding(self):
        b = HookBinding(
            name="mentoring",
            type="skill_md",
            skill_md="./lean-startup.md",
            priority=50,
        )
        b.validate()

    def test_valid_capacium_binding(self):
        b = HookBinding(
            name="ci-gate",
            type="capacium",
            capability="ci-gate-tool",
            priority=300,
        )
        b.validate()

    def test_missing_name_raises(self):
        b = HookBinding(name="", type="shell", command="echo hi")
        with pytest.raises(BindingValidationError, match="requires a 'name'"):
            b.validate()

    def test_invalid_type_raises(self):
        b = HookBinding(name="bad", type="invalid")
        with pytest.raises(BindingValidationError, match="Invalid hook type"):
            b.validate()

    def test_invalid_failure_mode_raises(self):
        b = HookBinding(name="bad", type="shell", command="echo", failureMode="explode")
        with pytest.raises(BindingValidationError, match="Invalid failureMode"):
            b.validate()

    def test_python_without_module_raises(self):
        b = HookBinding(name="no-mod", type="python")
        with pytest.raises(BindingValidationError, match="no 'module' field"):
            b.validate()

    def test_shell_without_command_raises(self):
        b = HookBinding(name="no-cmd", type="shell")
        with pytest.raises(BindingValidationError, match="no 'command' field"):
            b.validate()

    def test_skill_md_without_path_raises(self):
        b = HookBinding(name="no-md", type="skill_md")
        with pytest.raises(BindingValidationError, match="no 'skill_md' field"):
            b.validate()

    def test_capacium_without_capability_raises(self):
        b = HookBinding(name="no-cap", type="capacium")
        with pytest.raises(BindingValidationError, match="no 'capability' field"):
            b.validate()

    def test_negative_priority_raises(self):
        b = HookBinding(name="neg", type="shell", command="echo", priority=-1)
        with pytest.raises(BindingValidationError, match="negative priority"):
            b.validate()

    def test_zero_timeout_raises(self):
        b = HookBinding(name="zero", type="shell", command="echo", timeout_sec=0)
        with pytest.raises(BindingValidationError, match="non-positive timeout"):
            b.validate()

    def test_dedup_key_with_phase_position(self):
        b = HookBinding(
            name="lint",
            type="shell",
            command="./lint.sh",
            phase="build",
            position="pre",
        )
        assert b.dedup_key == "./lint.sh:build:pre"

    def test_default_values(self):
        b = HookBinding(name="test", type="shell", command="echo")
        assert b.priority == 500
        assert b.failureMode == "block"
        assert b.source == "project"
        assert b.timeout_sec == 300
        assert b.retry_count == 1
        assert b.config == {}


class TestBindingConfig:
    def _valid_data(self, **overrides):
        data = {
            "version": "1",
            "phase": "build",
            "position": "pre",
            "hooks": [
                {
                    "name": "lint",
                    "type": "shell",
                    "command": "./lint.sh",
                    "priority": 100,
                },
            ],
        }
        data.update(overrides)
        return data

    def test_valid_config_from_dict(self):
        config = BindingConfig.from_dict(self._valid_data(), source_path="test.yaml")
        assert config.version == "1"
        assert config.phase == "build"
        assert config.position == "pre"
        assert len(config.hooks) == 1
        assert config.hooks[0].name == "lint"
        assert config.hooks[0].phase == "build"
        assert config.hooks[0].position == "pre"

    def test_unsupported_version_raises(self):
        with pytest.raises(BindingValidationError, match="Unsupported binding config version"):
            BindingConfig.from_dict(self._valid_data(version="99"))

    def test_invalid_phase_raises(self):
        with pytest.raises(BindingValidationError, match="Invalid phase"):
            BindingConfig.from_dict(self._valid_data(phase="nonexistent"))

    def test_invalid_position_raises(self):
        with pytest.raises(BindingValidationError, match="Invalid position"):
            BindingConfig.from_dict(self._valid_data(position="middle"))

    def test_missing_version_raises(self):
        data = self._valid_data()
        del data["version"]
        with pytest.raises(BindingValidationError, match="Missing required 'version'"):
            BindingConfig.from_dict(data)

    def test_missing_phase_raises(self):
        data = self._valid_data()
        del data["phase"]
        with pytest.raises(BindingValidationError, match="Missing required 'phase'"):
            BindingConfig.from_dict(data)

    def test_missing_position_raises(self):
        data = self._valid_data()
        del data["position"]
        with pytest.raises(BindingValidationError, match="Missing required 'position'"):
            BindingConfig.from_dict(data)

    def test_hooks_not_list_raises(self):
        with pytest.raises(BindingValidationError, match="'hooks' must be a list"):
            BindingConfig.from_dict(self._valid_data(hooks="not-a-list"))

    def test_hook_entry_not_dict_raises(self):
        with pytest.raises(BindingValidationError, match="must be a mapping"):
            BindingConfig.from_dict(self._valid_data(hooks=["string-entry"]))

    def test_duplicate_hook_names_raises(self):
        data = self._valid_data(hooks=[
            {"name": "dup", "type": "shell", "command": "echo 1"},
            {"name": "dup", "type": "shell", "command": "echo 2"},
        ])
        with pytest.raises(BindingValidationError, match="Duplicate hook name"):
            BindingConfig.from_dict(data)

    def test_non_dict_top_level_raises(self):
        with pytest.raises(BindingValidationError, match="Expected YAML mapping"):
            BindingConfig.from_dict("just a string")

    def test_empty_hooks_list_valid(self):
        config = BindingConfig.from_dict(self._valid_data(hooks=[]))
        assert len(config.hooks) == 0

    def test_multiple_hooks(self):
        data = self._valid_data(hooks=[
            {"name": "lint", "type": "shell", "command": "./lint.sh", "priority": 100},
            {"name": "typecheck", "type": "shell", "command": "./typecheck.sh", "priority": 200},
            {"name": "security", "type": "python", "module": "hooks.SecurityHook", "priority": 300},
        ])
        config = BindingConfig.from_dict(data)
        assert len(config.hooks) == 3
        assert [h.name for h in config.hooks] == ["lint", "typecheck", "security"]

    def test_all_phases_valid(self):
        for phase in ["discovery", "blueprint", "build", "test", "release", "launch", "observe"]:
            config = BindingConfig.from_dict(self._valid_data(phase=phase))
            assert config.phase == phase

    def test_both_positions_valid(self):
        for pos in ["pre", "post"]:
            config = BindingConfig.from_dict(self._valid_data(position=pos))
            assert config.position == pos

    def test_hook_config_passthrough(self):
        data = self._valid_data(hooks=[
            {
                "name": "custom",
                "type": "shell",
                "command": "./run.sh",
                "config": {"strict": True, "threshold": 80},
            },
        ])
        config = BindingConfig.from_dict(data)
        assert config.hooks[0].config == {"strict": True, "threshold": 80}

    def test_condition_passthrough(self):
        data = self._valid_data(hooks=[
            {
                "name": "conditional",
                "type": "shell",
                "command": "./lint.sh",
                "condition": "phase == 'build'",
            },
        ])
        config = BindingConfig.from_dict(data)
        assert config.hooks[0].condition == "phase == 'build'"
