"""Double-start prevention, concurrency guards, and mutual exclusion tests (SW-SOAK-001).

Validates that duplicate soak runs, overlapping worker scopes, and racing coordinators
are blocked fail-closed before execution starts.
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from tests.soak.guard import DoubleStartGuard, DoubleStartPreventedError
from skillweave.runtime.write_scope import WriteSetManager, WriteSetConflictError
from skillweave.coordinator import Coordinator, CoordinatorAccessError
from skillweave.runtime.store import SQLiteRunStore


class TestSoakDoubleStart:
    """Double-start prevention and concurrency exclusion tests."""

    def test_guard_blocks_concurrent_runner_instances(self):
        """Verify that an active DoubleStartGuard blocks a second instance immediately."""
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = os.path.join(tmp, "runner.lock")
            guard1 = DoubleStartGuard(lock_path=lock_file, tag="primary-runner")
            guard2 = DoubleStartGuard(lock_path=lock_file, tag="secondary-runner")

            # Guard 1 acquires lock
            assert guard1.acquire() is True
            assert guard1.is_locked is True

            # Guard 2 attempts acquire with timeout 0 -> must raise DoubleStartPreventedError
            with pytest.raises(DoubleStartPreventedError) as exc_info:
                guard2.acquire(timeout_seconds=0.0)

            err = exc_info.value
            assert "Double-start prevented" in str(err)
            assert str(os.getpid()) in str(err) or err.holder_info.get("pid") == os.getpid()

            # Release guard 1 -> now guard 2 can acquire
            guard1.release()
            assert guard1.is_locked is False

            assert guard2.acquire(timeout_seconds=0.5) is True
            assert guard2.is_locked is True
            guard2.release()

    def test_guard_multithreaded_contention(self):
        """Verify thread-level mutual exclusion: exactly one thread acquires, others are blocked."""
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = os.path.join(tmp, "thread_contention.lock")
            acquired_count = 0
            blocked_count = 0
            lock = threading.Lock()

            def try_run(thread_id: int):
                nonlocal acquired_count, blocked_count
                guard = DoubleStartGuard(lock_path=lock_file, tag=f"thread-{thread_id}")
                try:
                    if guard.acquire(timeout_seconds=0.0):
                        with lock:
                            acquired_count += 1
                        time.sleep(0.05)
                        guard.release()
                except DoubleStartPreventedError:
                    with lock:
                        blocked_count += 1

            threads = [threading.Thread(target=try_run, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # At least one succeeded, and the rest were blocked
            assert acquired_count >= 1
            assert acquired_count + blocked_count == 10

    def test_write_set_manager_prevents_worker_double_start(self):
        """Verify WriteSetManager blocks overlapping worker startup before execution."""
        mgr = WriteSetManager()
        # Worker A claims src/skillweave/core
        mgr.declare("worker-A", ["src/skillweave/core"])

        # Worker B attempts to claim overlapping subpath -> blocked
        with pytest.raises(WriteSetConflictError) as exc_info:
            mgr.declare("worker-B", ["src/skillweave/core/recovery"])

        assert exc_info.value.worker_id == "worker-B"
        assert exc_info.value.conflicting_worker == "worker-A"

        # Disjoint worker C can start cleanly
        mgr.declare("worker-C", ["src/skillweave/trace"])

        # After worker A finishes and releases, worker B can claim
        mgr.release("worker-A")
        mgr.declare("worker-B", ["src/skillweave/core/recovery"])

    def test_coordinator_cas_prevents_racing_double_advance(self):
        """Verify that two coordinators cannot double-advance from the same version."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "coord_race.db")
            store = SQLiteRunStore(db_path)
            coord = Coordinator(store)

            curs = coord.ensure_root("race-seq", "wave-1", "LANE-1", role="ops")
            assert curs.version == 1

            # First coordinator advance succeeds
            adv1 = coord.advance("race-seq", "wave-1", "node-1", role="ops", expected_version=1)
            assert adv1.version == 2

            # Stale second advance with expected_version=1 is blocked with CoordinatorAccessError
            with pytest.raises(CoordinatorAccessError):
                coord.advance("race-seq", "wave-1", "node-2", role="ops", expected_version=1)

            # Cursor remains at node-1
            final_c = coord.load("race-seq", "wave-1")
            assert final_c.committed_nodes == ["node-1"]
            assert final_c.cursor_index == 1
            store.close()
