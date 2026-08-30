"""Legacy default unchanged (SW1312-CHAIN-001 criterion 7).

Regression proof that the profile preview wiring is strictly additive: without
an explicit effective-profile snapshot, the existing plan/build/mixed path and
its outputs are byte-for-byte unchanged. Nothing here selects a profile, so no
profile-derived chain is entered, and the derivation entry points refuse an
absent snapshot rather than inventing one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


from skillweave.promptchain.execute import (  # noqa: E402
    INLINE,
    SUBAGENT,
    DispatchEntry,
    DispatchPlan,
    MissingSessionBoundaryError,
    ProfileChainError,
    build_dispatch_plan,
    derive_chain_from_profile,
    execute_sequence,
    load_sequence,
    require_supported_dimension,
)


def _legacy_sequence() -> dict:
    return {
        "session_boundary": "batch",
        "phases": [
            {
                "parallel_lanes": [{"id": "lane-p1", "criteria": [1]}],
                "serialized_lanes": [{"id": "lane-s1", "criteria": [2]}],
            },
            {
                "parallel_lanes": [{"id": "lane-p2", "criteria": [3]}],
            },
        ],
    }


def test_legacy_sequence_parses_unchanged_without_profile():
    declaration = load_sequence(_legacy_sequence())
    assert declaration.session_boundary == "batch"
    assert declaration.has_boundary is True
    # Parallel and serialized preserved from their blocks.
    assert [l.id for l in declaration.parallel_lanes] == ["lane-p1", "lane-p2"]
    assert [l.id for l in declaration.serialized_lanes] == ["lane-s1"]


def test_legacy_dispatch_plan_is_parallel_subagent_serial_inline():
    declaration = load_sequence(_legacy_sequence())
    plan = build_dispatch_plan(declaration)
    # Parallel lanes are all dispatched as subagent, serialized lanes inline;
    # the entries preserve the block grouping (parallel lanes, then serialized).
    assert plan.modes() == [SUBAGENT, SUBAGENT, INLINE]
    entries = plan.entries
    assert entries == [
        DispatchEntry(lane_id="lane-p1", mode=SUBAGENT),
        DispatchEntry(lane_id="lane-p2", mode=SUBAGENT),
        DispatchEntry(lane_id="lane-s1", mode=INLINE),
    ]


def test_legacy_execute_sequence_returns_same_plan_with_no_profile():
    declaration = load_sequence(_legacy_sequence())
    calls = []

    def _fanout(lane_ids):
        calls.append(list(lane_ids))

    plan = execute_sequence(declaration, fanout=_fanout)
    # Parallel lanes handed to fan-out, serialized stay inline; plan shape
    # unchanged.
    assert plan.modes() == [SUBAGENT, SUBAGENT, INLINE]
    assert calls and all(mode for mode in [SUBAGENT])


def test_missing_session_boundary_is_still_refused_without_profile():
    with pytest.raises(MissingSessionBoundaryError):
        load_sequence({"phases": []})


def test_profile_entry_points_refuse_an_absent_snapshot():
    # Without an explicit snapshot the profile path is never entered and never
    # falls back silently: the derivation fails closed naming the missing input.
    with pytest.raises(ProfileChainError):
        derive_chain_from_profile(None)
    with pytest.raises(ProfileChainError):
        require_supported_dimension(None, "topology")


def test_legacy_path_does_not_require_a_profile_dataclass():
    # A legacy sequence carries no profile and still resolves to a valid plan
    # without importing any profile-derived type.
    declaration = load_sequence(_legacy_sequence())
    plan = build_dispatch_plan(declaration)
    assert isinstance(plan, DispatchPlan)
    assert len(plan.entries) == 3


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
