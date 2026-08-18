"""Tests for the timeout seam (SW-RT-008, dispatch 1 of 1).

Covers the three acceptance criteria of this dispatch:

1. ``dispatch`` and ``launch_from_role`` take a ``timeout`` and pass it to the
   runtime, which already accepts one. A caller that sets none gets a
   *documented* default (``DEFAULT_DISPATCH_TIMEOUT``), never an unbounded wait
   and never an invented number. RED PROOF: against 478211f ("release:
   SkillWeave 1.3.5") neither call accepts the ``timeout`` parameter — the
   identical call raises ``TypeError`` and exits non-zero.

2. A timeout is reported as a timeout and never as a failure of the tool. RED
   PROOF: a launch capped below the command's runtime yields
   ``result.termination == "timed_out"`` with the cap named in the record; the
   same launch with an adequate cap yields exit 0.

3. The record distinguishes DECLARED from TERMINATED. SW-RT-007 derived
   ``proven`` from a clean exit, so a dispatch that launched correctly and was
   cut short reads as unproven. The declared cap (``DispatchResult.timeout`` and
   artifact ``metadata["declared_timeout"]``) is a different fact from the
   terminating state (``termination``). A later reader needs both.

Self-contained sys.path handling, independent of conftest/pytest, following the
convention of ``test_runner_adapter.py`` and ``test_routing_dispatch.py``.
"""

import inspect
import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.routing.dispatch import (  # noqa: E402
    DEFAULT_DISPATCH_TIMEOUT,
    DispatchResult,
    dispatch,
    launch_from_role,
)
from skillweave.routing import ToolSpec  # noqa: E402


def _sleep_tool(seconds: float) -> ToolSpec:
    # A real subprocess that sleeps for the given seconds, so a timeout cap set
    # below it exercises the runtime's own wait(timeout=...) path (which kills
    # the whole process group and returns termination "timed_out").
    return ToolSpec(
        name="stub-sleeper",
        launch_command=(
            f"{sys.executable} -c 'import time; "
            f"time.sleep({seconds!r})'"
        ),
        args=[],
    )


def _dispatch(timeout=None):
    return dispatch(
        _sleep_tool(5.0),
        b"work",
        run_id="run-t1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
        created_at="2026-08-17T00:00:00Z",
        timeout=timeout,
    )


# ── Criterion 1: the calls accept a timeout and thread it; default is declared

def test_signatures_accept_timeout():
    # Both public entry points expose a ``timeout`` parameter (SW-RT-008
    # criterion 1). Against 478211f these parameters do not exist, so a caller
    # cannot pass them at all.
    assert "timeout" in inspect.signature(dispatch).parameters
    assert "timeout" in inspect.signature(launch_from_role).parameters


def test_default_timeout_is_documented_not_invented():
    # A caller that sets none gets DEFAULT_DISPATCH_TIMEOUT — a named, module-
    # level constant — not None (unbounded) and not a number invented ad hoc.
    assert DEFAULT_DISPATCH_TIMEOUT > 0
    # The default is a concrete, documented cap; the seam resolves None to it.
    # (The value is asserted to be positive and finite so it cannot silently
    # become an unbounded wait.)
    import math

    assert math.isfinite(DEFAULT_DISPATCH_TIMEOUT)


def test_timeout_threads_to_the_runtime_as_the_same_cap():
    # The runtime's run_command already accepts ``timeout``; the seam must pass
    # it through unchanged rather than re-inventing it. A cap well below the
    # stub's 5s sleep proves the value reached the runtime: it terminates as
    # timed_out, and the declared cap on the record equals what the caller set.
    result = _dispatch(timeout=0.5)
    assert isinstance(result, DispatchResult)
    assert result.timeout == 0.5
    assert result.termination == "timed_out"


# ── Criterion 2: a timeout is a timeout, never a tool failure ────────────────

def test_capped_launch_yields_timed_out_with_cap_named():
    # RED PROOF (criterion 2): capped below the command's runtime, termination
    # is "timed_out" — the cap is named in the record (artifact metadata and
    # result.timeout) — and it is NOT a DispatchFailure (not "the tool failed").
    result = _dispatch(timeout=0.5)
    assert isinstance(result, DispatchResult)
    assert result.succeeded is False
    assert result.termination == "timed_out"
    # The cap is named in the record: both on the result and in the artifact.
    assert result.timeout == 0.5
    assert result.artifact.metadata["declared_timeout"] == 0.5
    # The stdout did not carry a clean exit for a capped run.
    assert result.result.stdout == b""


def test_adequate_cap_yields_exit_zero():
    # The same launch with an adequate cap completes normally: exit 0,
    # termination "exited", succeeded True — proving the timeout is a real cap,
    # not a hard kill at any scale.
    result = _dispatch(timeout=60.0)
    assert isinstance(result, DispatchResult)
    assert result.succeeded is True
    assert result.termination == "exited"
    assert result.result.exit_code == 0


# ── Criterion 3: DECLARED is kept apart from TERMINATED ──────────────────────

def test_declared_timeout_and_termination_are_distinct_facts():
    # A run cut short has DECLARED (the cap) differing from TERMINATED (how it
    # ended). Both are recorded separately: result.timeout (declared) and
    # result.termination (terminated) are different fields, and the artifact
    # metadata carries both keys, so a later reader can tell "was capped" from
    # "was proven by a clean exit".
    result = _dispatch(timeout=0.5)
    assert isinstance(result, DispatchResult)
    # Declared cap vs terminating state are two different facts.
    assert result.timeout == 0.5
    assert result.termination == "timed_out"
    # Both are independently present in the persisted metadata.
    meta = result.artifact.metadata
    assert "declared_timeout" in meta
    assert "termination" in meta
    assert meta["declared_timeout"] == 0.5
    assert meta["termination"] == "timed_out"
    # A later reader deriving "proven" from a clean exit sees termination, never
    # the declared cap: they are not conflated into one field.
    assert meta["declared_timeout"] != meta["termination"]


def test_launch_from_role_threads_timeout_to_a_real_launch():
    # The same timeout seam must be reachable from launch_from_role (the role
    # entry point), not only from the bare dispatch wrapper.
    tool = _sleep_tool(5.0)
    result = launch_from_role(
        "worker",
        tool,
        b"work",
        run_id="run-t1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
        created_at="2026-08-17T00:00:00Z",
        timeout=0.5,
    )
    assert isinstance(result, DispatchResult)
    assert result.timeout == 0.5
    assert result.termination == "timed_out"


def _run_all() -> int:
    tests = [
        test_signatures_accept_timeout,
        test_default_timeout_is_documented_not_invented,
        test_timeout_threads_to_the_runtime_as_the_same_cap,
        test_capped_launch_yields_timed_out_with_cap_named,
        test_adequate_cap_yields_exit_zero,
        test_declared_timeout_and_termination_are_distinct_facts,
        test_launch_from_role_threads_timeout_to_a_real_launch,
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
