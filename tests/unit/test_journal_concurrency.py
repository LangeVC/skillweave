"""
Regression test for SW-135: sequence allocation in EventJournal must be
collision-free under concurrent writers.

The bug: `_next_sequence` computes MAX(sequence)+1 in one statement and the
INSERT happens separately. Under concurrent writers sharing a file this
read-then-write window drops/loses appends. Eight writers doing 200 appends
persisted only 33 events (167 IntegrityError/OperationalError).

This test drives eight threads against a single shared file (each writer its
own connection, mirroring production multi-process/multi-connection usage)
and asserts 200 persisted events with a gapless, collision-free sequence.
"""

import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from skillweave.runtime.journal import EventJournal


def _writer_worker(db_path, run_id, start, count, results):
    journal = EventJournal(db_path)
    try:
        for i in range(start, start + count):
            journal.append(run_id=run_id, payload={"n": i})
            results["ok"] += 1
    except Exception as exc:
        results["errors"].append(exc)
    finally:
        journal.close()


def _run_concurrency_test(db_path, run_id, writers, appends_per_writer):
    results = {"ok": 0, "errors": []}
    with ThreadPoolExecutor(max_workers=writers) as pool:
        futures = [
            pool.submit(
                _writer_worker, db_path, run_id,
                w * appends_per_writer, appends_per_writer, results,
            )
            for w in range(writers)
        ]
        for f in futures:
            f.result()
    return results


def test_concurrent_appends_persist_all_without_collisions():
    writers = 8
    appends_per_writer = 200
    total = writers * appends_per_writer
    run_id = "run-concurrency-1"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "journal.sqlite")
        # Init schema on its own connection first.
        init = EventJournal(db_path)
        init.close()

        results = _run_concurrency_test(db_path, run_id, writers, appends_per_writer)

        # Re-open and read persisted state.
        journal = EventJournal(db_path)
        events = journal.get_events(run_id)
        journal.close()

        sequence = [e.sequence for e in events]

        # 1. All 200 appends must be persisted.
        assert results["ok"] == total, (
            f"expected {total} successful appends, got {results['ok']}; "
            f"errors={[str(e) for e in results['errors'][:5]]}"
        )
        assert len(sequence) == total, (
            f"expected {total} persisted events, got {len(sequence)}"
        )

        # 2. No collisions.
        assert len(set(sequence)) == len(sequence), "duplicate sequence values detected"

        # 3. Gapless: sequences must be exactly 1..total.
        assert sorted(sequence) == list(range(1, total + 1)), (
            "sequence is not gapless"
        )
