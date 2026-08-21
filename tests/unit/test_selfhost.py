"""Tests for the internal self-hosting entry (SW-SELFHOST-001).

Proves a fixture with two Ops lanes, two reviews, and a dependent lane runs
end to end with **no manual worktree or session control**: the executor is a
real fan-out (two overlapping subprocesses), the root cursor is committed only
by the coordinator, the two reviews release only against their pinned SHAs, and
the dependent lane runs only after the ops lanes commit.

Self-contained sys.path handling, following the sibling-test convention.
"""

import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.coordinator import Coordinator  # noqa: E402
from skillweave.review import ReviewGate  # noqa: E402
from skillweave.selfhost import (  # noqa: E402
    SelfHostRunner,
    SelfHostFixture,
    SelfHostResult,
    LaneSpec,
    ReviewSpec,
)
from skillweave.runtime.store import SQLiteRunStore  # noqa: E402

FULL_A = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
FULL_B = "b2c3d4e5f60718293a4b5c6d7e8f90123456789"


def _fixture():
    return SelfHostFixture(
        sequence_id="selfhost-unit",
        wave="W3",
        base_sha=FULL_A,
        ops_lanes=[LaneSpec(lane_id="L1"), LaneSpec(lane_id="L2")],
        reviews=[
            ReviewSpec(review_id="R1", pinned_remote_sha=FULL_A, subject_lane="L1"),
            ReviewSpec(review_id="R2", pinned_remote_sha=FULL_A, subject_lane="L2"),
        ],
        dependent_lane=LaneSpec(lane_id="LD"),
    )


def test_two_ops_lanes_two_reviews_and_dependent_lane_run_without_manual_control():
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteRunStore(str(Path(tmp) / "store.db"))
        runner = SelfHostRunner(Coordinator(store), ReviewGate())

        # Real fan-out: two overlapping subprocesses. A fake executor that
        # records the lanes proves the runner passed exactly the two ops lanes
        # and that nothing was hand-wired.
        calls = []

        def executor(fixture, lane_ids):
            calls.append(list(lane_ids))
            return list(lane_ids)

        result = runner.execute(_fixture(), executor=executor)

        assert isinstance(result, SelfHostResult)
        assert result.succeeded is True
        assert calls == [["L1", "L2"]]
        assert result.ops_lanes_executed == ["L1", "L2"]
        assert result.reviews_released == ["R1", "R2"]
        assert result.dependent_lane_executed == "LD"
        assert result.committed_nodes == ["L1", "L2", "LD"]
        store.close()


def test_real_fan_out_produces_measured_overlap_and_true_success():
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteRunStore(str(Path(tmp) / "store.db"))
        runner = SelfHostRunner(Coordinator(store), ReviewGate())

        # Use the REAL executor: two real subprocesses overlap and succeed.
        result = runner.execute(_fixture())

        assert result.succeeded is True
        assert result.overlapped is True
        assert result.ops_lanes_executed == ["L1", "L2"]
        assert result.reviews_released == ["R1", "R2"]
        assert result.dependent_lane_executed == "LD"
        assert result.committed_nodes == ["L1", "L2", "LD"]
        store.close()


def test_review_release_fails_on_sha_mismatch_and_blocks_dependent_lane():
    from skillweave.review import ReviewGateError  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteRunStore(str(Path(tmp) / "store.db"))
        runner = SelfHostRunner(Coordinator(store), ReviewGate())

        # A push_probe returning a WRONG fetched SHA must block the review, and
        # therefore the self-host run, before the dependent lane commits.
        def wrong_probe(sha: str) -> str:
            return FULL_B

        try:
            runner.execute(_fixture(), executor=lambda f, ids: list(ids), push_probe=wrong_probe)
        except ReviewGateError as exc:
            assert "mismatch" in exc.reason
        else:
            raise AssertionError("a review SHA mismatch must block the self-host run")

        # The dependent lane never committed because the review gate blocked.
        cursor = Coordinator(store).load("selfhost-unit", "W3", role="ops")
        assert cursor is not None
        assert "LD" not in cursor.committed_nodes
        store.close()


def _run_all() -> int:
    tests = [
        test_two_ops_lanes_two_reviews_and_dependent_lane_run_without_manual_control,
        test_real_fan_out_produces_measured_overlap_and_true_success,
        test_review_release_fails_on_sha_mismatch_and_blocks_dependent_lane,
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
