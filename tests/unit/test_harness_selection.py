"""Tests for the harness record and profile-location loading (SW-RT-003, dispatch 1).

Dispatch 1 criteria:

1. The executing harness is determined and recorded on the run. Determination
   is explicit: either the caller set it or it was detected, and the record says
   which. A detected harness that was actually guessed must not read as a
   declared one.
2. Profiles are loaded from a declared location, and a harness maps to one or
   more profile names as DATA — adding a harness or profile changes data, never
   a branch.
"""

import pytest

from skillweave.routing import (
    HarnessSource,
    HarnessError,
    HarnessDetermination,
    HarnessProfileMap,
    determine_harness,
    load_profiles_from_location,
    attach_harness,
)

# ── Criterion 1: explicit determination, source recorded ────────────────


def test_declared_harness_is_recorded_as_declared():
    d = determine_harness(declared="opencode")
    assert d.name == "opencode"
    assert d.source is HarnessSource.DECLARED


def test_detected_harness_is_recorded_as_detected():
    d = determine_harness(
        env={"SKILLWEAVE_HARNESS": "claude-code"}, env_key="SKILLWEAVE_HARNESS"
    )
    assert d.name == "claude-code"
    assert d.source is HarnessSource.DETECTED


def test_detected_never_reads_as_declared():
    d = determine_harness(
        env={"SKILLWEAVE_HARNESS": "ghost"}, env_key="SKILLWEAVE_HARNESS"
    )
    # A detection, even a guessed one, must never be mistaken for a declaration.
    assert d.source is HarnessSource.DETECTED
    assert d.to_dict()["source"] == "detected"


def test_declared_wins_over_environment():
    d = determine_harness(
        declared="opencode",
        env={"SKILLWEAVE_HARNESS": "something-else"},
        env_key="SKILLWEAVE_HARNESS",
    )
    assert d.name == "opencode"
    assert d.source is HarnessSource.DECLARED


def test_no_source_results_in_empty_detected_not_declared():
    d = determine_harness(env={}, env_key="SKILLWEAVE_HARNESS")
    # Nothing was supplied, so it must not pretend the caller set it.
    assert d.name == ""
    assert d.source is HarnessSource.DETECTED


def test_empty_declared_value_is_refused():
    with pytest.raises(HarnessError):
        determine_harness(declared="   ")


# ── Criteria 1+2 together: the record travels with the run ──────────────


class _FakeRecord:
    def __init__(self):
        self.metadata = {}


def test_attach_harness_persists_source_on_record():
    rec = _FakeRecord()
    d = determine_harness(declared="opencode")
    meta = attach_harness(rec, d)
    assert meta["harness"]["name"] == "opencode"
    assert meta["harness"]["source"] == "declared"


def test_attach_harness_keeps_detected_distinct_on_record():
    rec = _FakeRecord()
    d = determine_harness(
        env={"SKILLWEAVE_HARNESS": "ghost"}, env_key="SKILLWEAVE_HARNESS"
    )
    meta = attach_harness(rec, d)
    assert meta["harness"]["source"] == "detected"


# ── Criterion 2: profiles from a declared location, mapping as data ─────


@pytest.fixture
def profile_file(tmp_path):
    path = tmp_path / "profiles.yaml"
    path.write_text(
        """
default:
  name: default
  tier: balanced
  limits: {}
  roles:
    ops: {model: sonnet}
quick:
  name: quick
  tier: fast
  limits: {}
  roles:
    worker: {model: deepseek-v4}
""",
        encoding="utf-8",
    )
    return path


def test_profiles_load_from_declared_location(profile_file):
    profiles = load_profiles_from_location(profile_file)
    assert set(profiles) == {"default", "quick"}


def test_missing_location_is_refused(tmp_path):
    with pytest.raises(HarnessError):
        load_profiles_from_location(tmp_path / "nope.yaml")


def test_harness_map_is_data_and_takes_many_profiles():
    m = HarnessProfileMap.from_dict(
        {"opencode": ["default", "quick"], "claude-code": "default"}
    )
    assert m.profiles_for("opencode") == ["default", "quick"]
    assert m.profiles_for("claude-code") == ["default"]
    assert m.profiles_for("unknown") == []


def test_harness_map_roundtrips_to_data():
    data = {"opencode": ["default"], "claude-code": ["quick", "default"]}
    m = HarnessProfileMap.from_dict(data)
    assert m.to_dict() == data


def test_harness_map_rejects_non_string_names():
    with pytest.raises(HarnessError):
        HarnessProfileMap.from_dict({123: ["default"]})
