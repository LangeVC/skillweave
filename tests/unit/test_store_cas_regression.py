"""Regression test for the run-store compare-and-swap (CAS) conflict detection.

Bug under test (P0): `SQLiteRunStore.transition` guarded its optimistic
concurrency by checking `self._conn.total_changes == 0` after the UPDATE.
`total_changes` is a CUMULATIVE per-connection counter (sqlite3), not the
row count of the last statement. So once a connection had performed any
successful change, the guard could never fire again and a CAS that matched
zero rows (a genuine concurrent-write conflict) went silently undetected.

The fix must detect the conflict on the row count of the UPDATE statement
itself (rowcount).

This test drives the code PAST the pre-check (line ~207) and directly into
the CAS, then asserts the conflict is raised. The pre-check is bypassed by
returning a stale `existing` record so that `existing.version` equals the
expected version while the underlying row has already moved on.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from skillweave.runtime.errors import VersionConflictError
from skillweave.runtime.store import SQLiteRunStore, RunRecord, RunStateModel


def _make_record(run_id: str, version: int, state: RunStateModel) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        root_run_id=run_id,
        parent_run_id=None,
        state=state.value,
        version=version,
        created_at="2026-08-16T00:00:00Z",
        updated_at="2026-08-16T00:00:00Z",
        ended_at=None,
        role="ops",
    )


def test_cas_detects_lost_update_when_row_already_moved():
    store = SQLiteRunStore(":memory:")

    run_id = "run-cas-001"
    store.save_run(_make_record(run_id, 1, RunStateModel.SANDBOX_PREFLIGHT))

    # Advance the row once so the connection's cumulative total_changes is
    # nonzero (this is exactly the condition the old guard failed on).
    store.transition(
        run_id=run_id,
        target_state=RunStateModel.IN_PROGRESS.value,
        expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
        expected_version=1,
        reason="legitimate first transition",
    )
    # Row is now at version 2.

    # Simulate a concurrent writer's stale read: the in-memory `existing`
    # record still claims version 1, while the underlying row is at 2.
    stale = _make_record(run_id, 1, RunStateModel.SANDBOX_PREFLIGHT)

    original_get_run = store.get_run
    store.get_run = lambda rid: stale if rid == run_id else original_get_run(rid)

    try:
        raised = False
        try:
            store.transition(
                run_id=run_id,
                target_state=RunStateModel.FAILED.value,
                expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
                expected_version=1,
                reason="stale concurrent write",
            )
        except VersionConflictError:
            raised = True
    finally:
        store.get_run = original_get_run

    assert raised, (
        "expected VersionConflictError from the CAS path, but the stale "
        "write was silently accepted (cumulative total_changes guard is "
        "broken)"
    )


if __name__ == "__main__":
    test_cas_detects_lost_update_when_row_already_moved()
    print("OK: CAS conflict detected")
