"""Tests for dependency-ready fan-out (SW-FANOUT-001).

Proves that a genuine fan-out overlaps two real processes in time and keeps
their child runs and raw artifacts separate — replacing the sequential batch
loop that waited for each worker before starting the next.

The overlap is a *measured* fact, not a claim: two workers each write their
start and end epoch timestamps to their own files, and the test asserts their
execution windows overlap. If the fan-out had fallen back to sequential
dispatch, the first worker's end would precede the second worker's start and
the overlap assertion would fail.

Self-contained sys.path handling, following the sibling-test convention.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.fanout import FanOutLaunchContext, FanOutResult, fan_out_dispatch  # noqa: E402
from skillweave.routing.modelspec import concrete, delegated  # noqa: E402


def _overlap_cmd(marker_dir: str, name: str, sleep_s: str) -> list[str]:
    # Each worker writes its own start/end epoch timestamps to its own file and
    # sleeps, so overlap between two workers is measurable from the files.
    script = (
        "import time, pathlib\n"
        "p = pathlib.Path(%r)\n"
        "open(p / %r, 'w').write(str(time.time() * 1000))\n"
        "time.sleep(%s)\n"
        "open(p / (%r + '.end'), 'w').write(str(time.time() * 1000))\n"
        "print('done')\n" % (marker_dir, name, sleep_s, name)
    )
    return [sys.executable, "-c", script]


def test_two_processes_overlap_in_time():
    marker = tempfile.mkdtemp(prefix="sw-fanout-")
    cmd_a = _overlap_cmd(marker, "a", "0.4")
    cmd_b = _overlap_cmd(marker, "b", "0.4")

    result = fan_out_dispatch(
        [cmd_a, cmd_b],
        run_id="run-fanout-1",
        subject_repo="skillweave",
        subject_commit="abc123",
        tool="opencode",
        model="model-xyz-7",
        created_at="2026-08-19T00:00:00Z",
    )

    assert isinstance(result, FanOutResult)
    assert result.overlapped is True
    assert result.succeeded is True
    assert len(result.children) == 2

    a_start = float((Path(marker) / "a").read_text())
    a_end = float((Path(marker) / "a.end").read_text())
    b_start = float((Path(marker) / "b").read_text())
    b_end = float((Path(marker) / "b.end").read_text())

    # Measured overlap: neither interval is disjoint from the other. The two
    # windows intersect iff neither ends before the other begins.
    assert a_end > b_start, "worker a finished before worker b began (sequential)"
    assert b_end > a_start, "worker b finished before worker a began (sequential)"


def test_child_runs_and_raw_artifacts_stay_separate():
    cmd = [sys.executable, "-c", "print('child-output')"]
    result = fan_out_dispatch(
        [cmd, cmd],
        run_id="run-fanout-2",
        subject_repo="skillweave",
        subject_commit="abc123",
        tool="opencode",
        model="model-xyz-7",
        created_at="2026-08-19T00:00:00Z",
    )

    # Each child has its own run identity and its own raw artifact; no two
    # children share one.
    assert result.children[0].child_run_id != result.children[1].child_run_id
    assert result.children[0].child_run_id.endswith("-0")
    assert result.children[1].child_run_id.endswith("-1")

    # Raw bytes are separate collections, each bound to its own child run.
    a0 = result.children[0].artifact
    a1 = result.children[1].artifact
    assert a0.artifact_id != a1.artifact_id
    assert a0.metadata["run_id"] != a1.metadata["run_id"]
    assert a0.metadata["run_id"] == result.children[0].child_run_id
    assert a1.metadata["run_id"] == result.children[1].child_run_id


def test_per_child_models_resolve_distinctly():
    # Two children with DIFFERENT models -> each FanOutChild.model is distinct
    # and correct; a delegated spec resolves. This is the per-child model freedom
    # (SW-FANOUT-001-MODELSPEC): no shared parent model collapses two lanes into
    # one.
    cmd = [sys.executable, "-c", "print('child')"]
    result = fan_out_dispatch(
        [cmd, cmd],
        run_id="run-fanout-modelspec",
        subject_repo="skillweave",
        subject_commit="abc123",
        tool="opencode",
        models=[
            concrete("faigate/deepseek-v4-pro"),
            delegated("faigate", "coding-fast"),
        ],
        created_at="2026-08-19T00:00:00Z",
    )

    assert len(result.children) == 2
    assert result.children[0].model == "faigate/deepseek-v4-pro"
    assert result.children[1].model == "faigate:coding-fast"
    assert result.children[0].model != result.children[1].model
    # The resolved model travels into each child's own process result/evidence,
    # not the shared parent model.
    assert result.children[0].result.model == "faigate/deepseek-v4-pro"
    assert result.children[1].result.model == "faigate:coding-fast"
    assert result.children[0].result.metadata["model"] == "faigate/deepseek-v4-pro"
    assert result.children[1].result.metadata["model"] == "faigate:coding-fast"


def test_per_child_different_routers_do_not_collapse():
    # Two children delegated to DIFFERENT routers with the SAME scenario must
    # resolve to distinct model ids; a bare-scenario resolution would collapse
    # them into one model.
    cmd = [sys.executable, "-c", "print('child')"]
    result = fan_out_dispatch(
        [cmd, cmd],
        run_id="run-fanout-router-collapse",
        subject_repo="skillweave",
        subject_commit="abc123",
        tool="opencode",
        models=[
            delegated("faigate", "auto"),
            delegated("omniroute", "auto"),
        ],
        created_at="2026-08-19T00:00:00Z",
    )
    assert len(result.children) == 2
    assert result.children[0].model != result.children[1].model


def test_single_model_backward_compatible_lifts_to_concrete():
    # A single `model: str` still works unchanged and is applied to every child.
    cmd = [sys.executable, "-c", "print('child')"]
    result = fan_out_dispatch(
        [cmd, cmd],
        run_id="run-fanout-bw",
        subject_repo="skillweave",
        subject_commit="abc123",
        tool="opencode",
        model="model-xyz-7",
        created_at="2026-08-19T00:00:00Z",
    )
    assert len(result.children) == 2
    assert all(c.model == "model-xyz-7" for c in result.children)


def test_failing_child_is_a_failure_not_a_silent_success():
    ok = [sys.executable, "-c", "print('ok')"]
    bad = [sys.executable, "-c", "import sys; sys.exit(5)"]
    result = fan_out_dispatch(
        [ok, bad],
        run_id="run-fanout-3",
        subject_repo="skillweave",
        subject_commit="abc123",
        tool="opencode",
        model="model-xyz-7",
        created_at="2026-08-19T00:00:00Z",
    )
    # One child fails -> the fan-out is not a silent success.
    assert result.children[0].result.succeeded is True
    assert result.children[1].result.succeeded is False
    assert result.children[1].result.exit_code == 5
    assert result.succeeded is False


def test_per_child_launch_context_keeps_distinct_identity():
    # A heterogeneous parallel group (mixed repos / base commits / tools / cwds)
    # must keep each child's own identity, never collapse onto group[0]. The
    # launch context is the criterion-4 seam: per-child repo/base/tool/cwd.
    wt_a = tempfile.mkdtemp(prefix="sw-fanout-ctx-a-")
    wt_b = tempfile.mkdtemp(prefix="sw-fanout-ctx-b-")
    cmd = [sys.executable, "-c", "print('child')"]
    contexts = [
        FanOutLaunchContext(
            subject_repo="skillweave/repo-a",
            subject_commit="a" * 40,
            tool="opencode",
            cwd=wt_a,
        ),
        FanOutLaunchContext(
            subject_repo="skillweave/repo-b",
            subject_commit="b" * 40,
            tool="reviewer-cli",
            cwd=wt_b,
        ),
    ]
    result = fan_out_dispatch(
        [cmd, cmd],
        run_id="run-fanout-ctx",
        subject_repo="skillweave/repo-a",
        subject_commit="a" * 40,
        tool="opencode",
        model="model-xyz-7",
        launch_contexts=contexts,
    )
    assert len(result.children) == 2
    c0, c1 = result.children
    assert c0.subject_repo == "skillweave/repo-a"
    assert c0.subject_commit == "a" * 40
    assert c0.tool == "opencode"
    assert c0.cwd == wt_a
    assert c1.subject_repo == "skillweave/repo-b"
    assert c1.subject_commit == "b" * 40
    assert c1.tool == "reviewer-cli"
    assert c1.cwd == wt_b
    assert c0.subject_repo != c1.subject_repo
    assert c0.subject_commit != c1.subject_commit
    assert c0.cwd != c1.cwd


def test_malformed_launch_context_length_starts_zero_children():
    # A launch-context list misaligned to the command list is fail-closed, like
    # the per-child models list: raise before any process starts.
    cmd = [sys.executable, "-c", "print('child')"]
    try:
        fan_out_dispatch(
            [cmd, cmd],
            run_id="run-fanout-badctx",
            subject_repo="skillweave",
            subject_commit="abc123",
            tool="opencode",
            model="model-xyz-7",
            launch_contexts=[
                FanOutLaunchContext("skillweave", "abc123", "opencode", None)
            ],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("misaligned launch_contexts must raise, not launch")


def _run_all() -> int:
    tests = [
        test_two_processes_overlap_in_time,
        test_child_runs_and_raw_artifacts_stay_separate,
        test_failing_child_is_a_failure_not_a_silent_success,
        test_per_child_models_resolve_distinctly,
        test_per_child_different_routers_do_not_collapse,
        test_single_model_backward_compatible_lifts_to_concrete,
        test_per_child_launch_context_keeps_distinct_identity,
        test_malformed_launch_context_length_starts_zero_children,
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
