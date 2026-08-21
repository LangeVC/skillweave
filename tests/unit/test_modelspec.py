"""Tests for the per-child ModelSpec type (SW-FANOUT-001-MODELSPEC).

Proves the constructor/API surface falls closed: an ambiguous or empty value is
refused at construction, concrete and delegated variants round-trip through
``to_dict`` without collapsing into each other, and ``resolve_model_spec`` is
pure/deterministic given the spec (concrete returns unchanged; delegated resolves
deterministically without inventing a provider).

Self-contained sys.path handling, following the sibling-test convention.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.routing.modelspec import (  # noqa: E402
    ModelSpec,
    ModelSpecError,
    concrete,
    delegated,
    from_value,
)
from skillweave.routing.faigate_adapter import (  # noqa: E402
    resolve_model_spec,
    resolve_model_spec_record,
)


def test_concrete_rejects_empty_or_whitespace():
    for bad in ("", "   ", None):
        try:
            if bad is None:
                concrete(bad)
            else:
                concrete(bad)
        except ModelSpecError:
            pass
        else:
            raise AssertionError(f"concrete({bad!r}) did not raise ModelSpecError")


def test_delegated_rejects_empty_router_or_scenario():
    for router, scenario in (("", "auto"), ("faigate", ""), ("   ", "x"), ("x", "   ")):
        try:
            delegated(router, scenario)
        except ModelSpecError:
            pass
        else:
            raise AssertionError(
                f"delegated({router!r}, {scenario!r}) did not raise ModelSpecError"
            )


def test_concrete_and_delegated_are_distinct_variants():
    c = concrete("faigate/deepseek-v4-flash")
    d = delegated("faigate", "auto")
    assert c.kind == "concrete"
    assert d.kind == "delegated"
    assert c.model == "faigate/deepseek-v4-flash"
    assert c.router is None and c.scenario is None
    assert d.router == "faigate" and d.scenario == "auto"
    assert d.model is None


def test_to_dict_round_trip_does_not_collapse_variants():
    c = concrete("faigate/deepseek-v4-flash").to_dict()
    d = delegated("faigate", "coding-fast").to_dict()
    assert c == {"kind": "concrete", "model": "faigate/deepseek-v4-flash"}
    assert d == {"kind": "delegated", "router": "faigate", "scenario": "coding-fast"}


def test_from_value_lifts_a_string_and_passes_a_spec():
    assert from_value("faigate/deepseek-v4-pro").kind == "concrete"
    spec = delegated("faigate", "auto")
    assert from_value(spec) is spec
    try:
        from_value(None)
    except ModelSpecError:
        pass
    else:
        raise AssertionError("from_value(None) did not raise ModelSpecError")


def test_resolve_model_spec_is_deterministic():
    # concrete -> unchanged
    c = concrete("faigate/deepseek-v4-flash")
    assert resolve_model_spec(c) == "faigate/deepseek-v4-flash"
    assert resolve_model_spec(c) == resolve_model_spec(c)
    # delegated faigate -> scenario (auto), deterministic across calls
    d = delegated("faigate", "auto")
    assert resolve_model_spec(d) == "auto"
    assert resolve_model_spec(d) == resolve_model_spec(d)
    # delegated non-faigate, non-detected -> "<router>:<scenario>", deterministic,
    # no network. (A detected router hands the scenario through directly.)
    e = delegated("nonesuch-router", "coding-fast")
    assert resolve_model_spec(e) == "nonesuch-router:coding-fast"


def test_resolve_model_spec_record_keeps_requested_and_resolved():
    record = resolve_model_spec_record(delegated("faigate", "auto"))
    assert record.resolved == "auto"
    assert record.requested.kind == "delegated"


def _run_all() -> int:
    tests = [
        test_concrete_rejects_empty_or_whitespace,
        test_delegated_rejects_empty_router_or_scenario,
        test_concrete_and_delegated_are_distinct_variants,
        test_to_dict_round_trip_does_not_collapse_variants,
        test_from_value_lifts_a_string_and_passes_a_spec,
        test_resolve_model_spec_is_deterministic,
        test_resolve_model_spec_record_keeps_requested_and_resolved,
    ]
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
