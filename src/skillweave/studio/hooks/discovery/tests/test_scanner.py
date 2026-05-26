"""Tests for the Capacium trigger scanner."""

import pytest
from skillweave.studio.hooks.discovery.scanner import TriggerScanner, DiscoveredBinding


def _cap_with_trigger(name="ci-gate", phase="test", position="post"):
    return {
        "name": name,
        "version": "1.0",
        "triggers": [
            {
                "type": "dev.skillweave.hook",
                "source": "skillweave",
                "filter": {
                    "phase": phase,
                    "position": position,
                },
            },
        ],
    }


def _cap_without_trigger(name="no-trigger"):
    return {"name": name, "version": "1.0"}


def _cap_with_non_skillweave_trigger(name="other"):
    return {
        "name": name,
        "triggers": [
            {
                "type": "dev.other.event",
                "source": "github",
                "filter": {"repo": "test"},
            },
        ],
    }


class TestTriggerScanner:
    def test_finds_skillweave_triggers(self):
        scanner = TriggerScanner(
            capabilities_data=[
                _cap_with_trigger("ci-gate", "test", "post"),
                _cap_with_trigger("security-scan", "build", "pre"),
            ]
        )
        result = scanner.scan()

        assert len(result) == 2
        assert result[0].capability == "ci-gate"
        assert result[0].phase == "test"
        assert result[0].position == "post"
        assert result[1].capability == "security-scan"
        assert result[1].phase == "build"
        assert result[1].position == "pre"

    def test_ignores_non_skillweave_triggers(self):
        scanner = TriggerScanner(
            capabilities_data=[
                _cap_with_non_skillweave_trigger("other"),
            ]
        )
        result = scanner.scan()
        assert len(result) == 0

    def test_ignores_capabilities_without_triggers(self):
        scanner = TriggerScanner(
            capabilities_data=[
                _cap_without_trigger("no-trigger"),
            ]
        )
        result = scanner.scan()
        assert len(result) == 0

    def test_mixed_capabilities(self):
        scanner = TriggerScanner(
            capabilities_data=[
                _cap_with_trigger("ci-gate"),
                _cap_without_trigger("plain"),
                _cap_with_non_skillweave_trigger("github-hook"),
            ]
        )
        result = scanner.scan()
        assert len(result) == 1
        assert result[0].capability == "ci-gate"

    def test_missing_filter_fields_skipped(self):
        scanner = TriggerScanner(
            capabilities_data=[
                {
                    "name": "broken",
                    "triggers": [
                        {
                            "type": "dev.skillweave.hook",
                            "source": "skillweave",
                            "filter": {"phase": "build"},  # missing position
                        },
                    ],
                },
            ]
        )
        result = scanner.scan()
        assert len(result) == 0

    def test_multiple_triggers_per_capability(self):
        scanner = TriggerScanner(
            capabilities_data=[
                {
                    "name": "multi",
                    "triggers": [
                        {
                            "type": "dev.skillweave.hook",
                            "source": "skillweave",
                            "filter": {"phase": "build", "position": "pre"},
                        },
                        {
                            "type": "dev.skillweave.hook",
                            "source": "skillweave",
                            "filter": {"phase": "test", "position": "post"},
                        },
                    ],
                },
            ]
        )
        result = scanner.scan()
        assert len(result) == 2

    def test_empty_capabilities_list(self):
        scanner = TriggerScanner(capabilities_data=[])
        result = scanner.scan()
        assert len(result) == 0

    def test_scan_as_bindings(self):
        scanner = TriggerScanner(
            capabilities_data=[
                _cap_with_trigger("ci-gate", "test", "post"),
            ]
        )
        bindings = scanner.scan_as_bindings()
        assert len(bindings) == 1
        assert bindings[0].name == "auto:ci-gate"
        assert bindings[0].type == "capacium"
        assert bindings[0].capability == "ci-gate"
        assert bindings[0].source == "auto"
        assert bindings[0].failureMode == "warn"

    def test_no_capabilities_dir(self, tmp_path):
        scanner = TriggerScanner(
            capabilities_dir=str(tmp_path / "nonexistent")
        )
        result = scanner.scan()
        assert len(result) == 0

    def test_malformed_triggers_field(self):
        scanner = TriggerScanner(
            capabilities_data=[
                {"name": "bad", "triggers": "not-a-list"},
            ]
        )
        result = scanner.scan()
        assert len(result) == 0


class TestDiscoveredBinding:
    def test_to_hook_binding(self):
        db = DiscoveredBinding(
            capability="ci-gate",
            phase="test",
            position="post",
        )
        hb = db.to_hook_binding()

        assert hb.name == "auto:ci-gate"
        assert hb.type == "capacium"
        assert hb.capability == "ci-gate"
        assert hb.source == "auto"
        assert hb.phase == "test"
        assert hb.position == "post"
        assert hb.priority == 900
        assert hb.failureMode == "warn"

    def test_custom_priority(self):
        db = DiscoveredBinding(
            capability="custom",
            phase="build",
            position="pre",
        )
        hb = db.to_hook_binding(priority=100)
        assert hb.priority == 100

    def test_metadata_passthrough(self):
        db = DiscoveredBinding(
            capability="meta",
            phase="build",
            position="pre",
            metadata={"version": "1.0", "author": "test"},
        )
        hb = db.to_hook_binding()
        assert hb.config == {"version": "1.0", "author": "test"}
