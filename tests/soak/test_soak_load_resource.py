"""Load, concurrency, and resource leak tests under sustained soak (SW-SOAK-001).

Validates that high concurrency, multi-worker fanout, and repeated state transitions
operate cleanly without memory leaks, descriptor leaks, or throughput degradation.
"""

import gc
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

from tests.soak.config import SoakConfig, SoakLimits
from tests.soak.monitor import ResourceTracker
from skillweave.runtime.store import SQLiteRunStore, RunStateModel
from skillweave.runtime.journal import EventJournal, EventType
from skillweave.runtime.write_scope import WriteSetManager, WriteSetConflictError
from skillweave.coordinator import Coordinator
from skillweave.fanout import fan_out_dispatch


class TestSoakLoadResource:
    """Load and resource stability tests."""

    def test_sustained_store_and_journal_load_no_leaks(self):
        """Test hundreds of runs through SQLiteRunStore and EventJournal with resource tracking."""
        tracker = ResourceTracker(SoakLimits(max_memory_growth_mb=40.0, max_open_files=128))

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "soak_load.db")
            store = SQLiteRunStore(db_path)
            journal = EventJournal(db_path)

            initial_fds = tracker.get_open_fds()
            iterations = 250

            for i in range(iterations):
                op_start = time.time()
                run_id = f"load-run-{i:05d}"
                store.create_run(run_id)
                rec = store.get_run(run_id)

                # State progression
                for from_s, to_s in [
                    (RunStateModel.PREFLIGHT.value, RunStateModel.BATCH_SELECTION.value),
                    (RunStateModel.BATCH_SELECTION.value, RunStateModel.LANE_PLAN.value),
                    (RunStateModel.LANE_PLAN.value, RunStateModel.IMPLEMENT.value),
                    (RunStateModel.IMPLEMENT.value, RunStateModel.VERIFY.value),
                    (RunStateModel.VERIFY.value, RunStateModel.REVIEW_GATE.value),
                    (RunStateModel.REVIEW_GATE.value, RunStateModel.ADVANCE_OR_STOP.value),
                ]:
                    store.transition(
                        run_id,
                        to_s,
                        expected_state=from_s,
                        expected_version=rec.version,
                        role="ops",
                        reason=f"step {from_s}->{to_s}",
                    )
                    rec = store.get_run(run_id)

                journal.append(
                    run_id,
                    event_type=EventType.GATE_EVALUATION.value,
                    payload={"iteration": i, "state": rec.state},
                )
                tracker.record_op(time.time() - op_start, success=True)

            store.close()
            gc.collect()

            tracker.record_sample()
            summary = tracker.get_summary()

            assert summary["operations_total"] == iterations
            assert summary["errors_total"] == 0
            assert summary["memory_growth_mb"] < 40.0
            # Open FDs should not have blown up
            if initial_fds > 0:
                assert tracker.get_open_fds() <= initial_fds + 15

    def test_concurrent_multi_worker_load_with_disjoint_scopes(self):
        """Simulate concurrent worker threads executing parallel tasks with disjoint write scopes."""
        tracker = ResourceTracker(SoakLimits(max_memory_growth_mb=50.0))
        write_mgr = WriteSetManager()
        errors = []
        threads_count = 6
        ops_per_thread = 40

        def worker_lane(lane_id: int):
            for i in range(ops_per_thread):
                op_start = time.time()
                worker_name = f"lane-{lane_id}-w-{i}"
                scope = [f"src/lane_{lane_id}/file_{i % 5}"]
                try:
                    write_mgr.declare(worker_name, scope)
                    # Simulate processing
                    time.sleep(0.001)
                    write_mgr.release(worker_name)
                    tracker.record_op(time.time() - op_start, success=True)
                except Exception as exc:
                    tracker.record_op(time.time() - op_start, success=False)
                    errors.append(exc)

        threads = [threading.Thread(target=worker_lane, args=(i,)) for i in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        summary = tracker.get_summary()
        assert summary["operations_total"] == threads_count * ops_per_thread
        assert summary["errors_total"] == 0
        assert summary["latency_ms"]["p95_ms"] < 1000.0

    def test_coordinator_root_dag_progression_under_load(self):
        """Test continuous coordinator root cursor advancement under heavy iteration load."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "coord_load.db")
            store = SQLiteRunStore(db_path)
            coord = Coordinator(store)

            curs = coord.ensure_root("soak-dag-seq", "wave-alpha", "LANE-1", role="ops")
            assert curs.version == 1

            iterations = 100
            for i in range(iterations):
                c = coord.load("soak-dag-seq", "wave-alpha")
                assert c is not None
                adv = coord.advance(
                    "soak-dag-seq",
                    "wave-alpha",
                    f"node-{i:04d}",
                    role="ops",
                    expected_version=c.version,
                )
                assert adv.version == c.version + 1

            final_cursor = coord.load("soak-dag-seq", "wave-alpha")
            assert final_cursor.cursor_index == iterations
            assert len(final_cursor.committed_nodes) == iterations
            assert final_cursor.committed_nodes[-1] == f"node-{iterations - 1:04d}"
            store.close()
