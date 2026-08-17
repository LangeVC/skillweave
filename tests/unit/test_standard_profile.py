"""The standard case shipped as loadable data, not a test-built fixture (SW-RT-006).

Three acceptance criteria, nothing else:

1. A profile file exists in the repository as data and loads through
   ``load_profiles_from_location``. It declares the operator's standard case:
   the observer in place, ops and reviewer to OpenCode on deepseek-v4-pro.
   RED PROOF: loading it from a declared path yields the same role outcomes
   the gate reproduced by hand.

2. Harness and profile stay separate (SW-RT-003 AK 3): the file carries no
   ``harness`` field, and the harness-to-profile mapping is its own declaration.
   Four harnesses referencing three profiles must stay three profiles plus a
   mapping, not twelve entries.

3. The file documents where it is looked for, so a declared location that only
   the code knows is not a location the operator cannot use.
"""

import sys
from pathlib import Path

import pytest

from skillweave.routing import load_profiles_from_location

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_REPO = Path(__file__).resolve().parent.parent.parent
_PROFILE_PATH = _REPO / "profiles" / "langevc-standard.yaml"


def test_profile_file_exists_in_repository():
    # The profile is a real file in the tree, not a fixture a test constructs.
    assert _PROFILE_PATH.is_file()


def test_standard_case_loads_from_declared_path():
    # Criterion 1: load from the declared path, not a dict handed in.
    profiles = load_profiles_from_location(_PROFILE_PATH)
    assert "langevc-standard" in profiles
    profile = profiles["langevc-standard"]

    # observer is in place: a real role, wired as observer, carrying no tool.
    observer = profile.role("observer")
    assert observer is not None
    assert observer.is_observer is True
    assert observer.tool is None

    # ops and reviewer resolve to OpenCode on deepseek-v4-pro.
    assert profile.model_for("ops") == "deepseek-v4-pro"
    assert profile.model_for("reviewer") == "deepseek-v4-pro"

    ops_tool = profile.tool_for("ops")
    assert ops_tool is not None
    assert ops_tool.name == "opencode"
    assert ops_tool.launch_command == "/opt/homebrew/bin/opencode run --model deepseek-v4-pro"

    reviewer_tool = profile.tool_for("reviewer")
    assert reviewer_tool is not None
    assert reviewer_tool.name == "opencode"
    assert reviewer_tool.launch_command == "/opt/homebrew/bin/opencode run --model deepseek-v4-pro"


def test_observer_in_place_keeps_self_approval_split():
    # The standard case keeps the ops/reviewer separation intact: ops mutates
    # run state, reviewer approves the gate, neither holds both.
    profile = load_profiles_from_location(_PROFILE_PATH)["langevc-standard"]
    assert profile.role_can("ops", "can_mutate_run_state") is True
    assert profile.role_can("ops", "can_approve_gate") is False
    assert profile.role_can("reviewer", "can_approve_gate") is True
    assert profile.role_can("reviewer", "can_mutate_run_state") is False


def test_profile_file_carries_no_harness_field():
    # Criterion 2: the file is profile-only. A harness field would be refused at
    # load time (RoutingProfile.from_dict), so the check is on the DATA, not on
    # the prose: the parsed profile must carry no harness key, and adding one
    # must be refused with the field named. The relationship belongs to
    # HarnessProfileMap, never to the profile record.
    import yaml

    raw = yaml.safe_load(_PROFILE_PATH.read_text(encoding="utf-8"))
    assert "harness" not in raw
    assert "harness" not in raw.get("roles", {})
    assert "harness" not in raw.get("roles", {}).get("ops", {})
    assert "harness" not in raw.get("roles", {}).get("reviewer", {})

    from skillweave.routing.profile import RoutingProfileError

    polluted = dict(raw, harness="opencode")
    with pytest.raises(RoutingProfileError, match="'harness'"):
        from skillweave.routing.profile import RoutingProfile
        RoutingProfile.from_dict(polluted)


def test_one_mapping_stays_profiles_plus_mapping_not_cross_product():
    # Criterion 2, restated as arithmetic: the file declares exactly one profile,
    # so four harnesses referencing it map to that one profile via a table — the
    # cross-product is never materialised into the file.
    profiles = load_profiles_from_location(_PROFILE_PATH)
    assert set(profiles) == {"langevc-standard"}


def test_location_is_documented_in_the_file():
    # Criterion 3: the header names the lookup location, so the operator knows
    # where the file is read from without reading library code.
    text = _PROFILE_PATH.read_text(encoding="utf-8")
    assert "load_profiles_from_location" in text
    assert "profiles/langevc-standard.yaml" in text


if __name__ == "__main__":
    tests = [
        test_profile_file_exists_in_repository,
        test_standard_case_loads_from_declared_path,
        test_observer_in_place_keeps_self_approval_split,
        test_profile_file_carries_no_harness_field,
        test_one_mapping_stays_profiles_plus_mapping_not_cross_product,
        test_location_is_documented_in_the_file,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    sys.exit(1 if failed else 0)
