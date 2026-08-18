import inspect
"""Tests that the routing package exports every module in its surface (SW-RT-005).

The gap this closes: four lanes and a gate passed without anything checking the
package surface itself. ``harness`` was re-exported from ``skillweave.routing``;
``dispatch`` was not — and the dispatch test imported the module directly
(``from skillweave.routing.dispatch import ...``), so by construction it could
never see the omission. This test imports the package, reads ``__all__``, and
pulls every declared name through the public surface. If any name is missing
(or ``__all__`` is missing a name the module defines and the peer modules
export), the import fails.

Self-contained sys.path handling, independent of conftest, following the
convention of ``test_routing_dispatch.py``.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import skillweave.routing as routing  # noqa: E402


def test_every_name_in_all_is_importable_from_the_package():
    # The surface itself is the contract: every name declared in __all__ must
    # resolve through the package. A missing symbol raises AttributeError here,
    # which is the point — the omission cannot hide behind a direct module path.
    assert routing.__all__
    for name in routing.__all__:
        assert hasattr(routing, name), f"{name!r} is in __all__ but not importable"


def test_dispatch_module_is_re_exported():
    # Criterion 1: BOTH new modules are exported. The harness block has been
    # present since the three-way merge; dispatch must not be the one omission.
    from skillweave.routing.dispatch import (  # noqa: F401
        DispatchFailure,
        DispatchResult,
        InPlaceRecord,
        RoleOutcome,
        dispatch,
        launch_from_role,
        run_in_place,
        tokenize_launch,
    )

    for name in (
        "DispatchFailure",
        "DispatchResult",
        "InPlaceRecord",
        "RoleOutcome",
        "launch_from_role",
        "run_in_place",
        "tokenize_launch",
    ):
        assert name in routing.__all__, f"{name!r} missing from routing.__all__"
        assert getattr(routing, name) is getattr(
            sys.modules["skillweave.routing.dispatch"], name
        )


    # dispatch_role is the function; the module of the same name must stay
    # reachable. Re-exporting the function as `dispatch` shadowed the module —
    # `from skillweave.routing import dispatch` handed back the function and the
    # module could only be reached through importlib. This pins both.
    import skillweave.routing.dispatch as dispatch_module

    assert routing.dispatch_role is dispatch_module.dispatch
    assert "dispatch_role" in routing.__all__
    assert inspect.ismodule(routing.dispatch), (
        "routing.dispatch must be the module, not a shadowing re-export"
    )

def test_harness_module_remains_re_exported():
    # The harness block must stay as it was; this guards that the dispatch
    # addition did not disturb the existing surface.
    for name in (
        "HarnessSource",
        "HarnessError",
        "HarnessDetermination",
        "HarnessProfileMap",
        "determine_harness",
        "load_profiles_from_location",
        "attach_harness",
    ):
        assert name in routing.__all__, f"{name!r} missing from routing.__all__"


def _run_all() -> int:
    tests = [
        test_every_name_in_all_is_importable_from_the_package,
        test_dispatch_module_is_re_exported,
        test_harness_module_remains_re_exported,
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
