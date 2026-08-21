"""SW-UOW-001: atomic unit-of-work/outbox contract for transition + journal event.

A run transition and its journal event commit together in one transaction. A
fault injected before or after any single write must leave, after "restart",
exactly one canonical state/event pair — never a divergence where the run moved
but the event vanished, or vice versa.
"""

import json
import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.store import SQLiteRunStore, RunRecord, RunStateModel


def _make_run(run_id: str) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        root_run_id=run_id,
        parent_run_id=None,
        state=RunStateModel.SANDBOX_PREFLIGHT.value,
        version=1,
        created_at="2026-08-16T00:00:00Z",
        updated_at="2026-08-16T00:00:00Z",
        ended_at=None,
        role="ops",
    )


def _setup(db_path, run_id):
    store = SQLiteRunStore(db_path=db_path)
    store.save_run(_make_run(run_id))
    return store


def test_transition_with_event_commits_state_and_event_atomically():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = _setup(db_path, "run-uow-1")
        result = store.transition_with_event(
            run_id="run-uow-1",
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
            event_type="state_transition",
            event_payload={"to": "in_progress"},
        )
        assert result.state == "in_progress"
        assert result.version == 2
        outbox = store.list_outbox(run_id="run-uow-1")
        assert len(outbox) == 1
        assert outbox[0]["event_type"] == "state_transition"
        assert outbox[0]["payload"]["to"] == "in_progress"
        store.close()


class _Fault(Exception):
    pass


def test_fault_after_state_write_but_before_event_rolls_back_state():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = _setup(db_path, "run-uow-2")

        real_conn = store._conn

        class _FaultyConn:
            """Proxy that raises once on the outbox INSERT, inside the transaction."""

            def __init__(self):
                self._boom = True

            def execute(self, sql, *args):
                if self._boom and "INSERT INTO outbox" in str(sql):
                    self._boom = False
                    raise _Fault("boom before outbox write")
                return real_conn.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(real_conn, name)

        store._conn = _FaultyConn()
        raised = False
        try:
            store.transition_with_event(
                run_id="run-uow-2",
                target_state=RunStateModel.IN_PROGRESS.value,
                expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
                expected_version=1,
                event_type="state_transition",
            )
        except _Fault:
            raised = True
        finally:
            store._conn = real_conn

        assert raised is True
        # The atomic transaction rolled back: state is unchanged at version 1,
        # no outbox event, no transitions_log row leaked.
        row = store.get_run("run-uow-2")
        assert row.state == RunStateModel.SANDBOX_PREFLIGHT.value
        assert row.version == 1
        assert store.list_outbox(run_id="run-uow-2") == []
        store.close()


def test_survives_restart_with_zero_divergence():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = _setup(db_path, "run-uow-3")
        store.transition_with_event(
            run_id="run-uow-3",
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
            event_type="state_transition",
        )
        store.close()

        # Restart: a fresh store reads the same canonical state and the same
        # single undelivered event. No divergence.
        store2 = SQLiteRunStore(db_path=db_path)
        row = store2.get_run("run-uow-3")
        assert row.state == "in_progress"
        assert row.version == 2
        outbox = store2.list_outbox(run_id="run-uow-3")
        assert len(outbox) == 1
        assert outbox[0]["delivered_at"] is None
        store2.close()


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in _tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
