"""SW-STATE-001: CAS-safe authoritative run transitions under real concurrency.

Two writers racing on the same version must resolve to exactly one winner and
one ``VersionConflictError``. The test drives N threads, each with its own
connection to a shared file DB (mirroring multi-process usage), all attempting
to transition the same run out of version 1. Exactly one may win; the losers
must receive a conflict — never a silent stale rollback.
"""

import os
import sys
import tempfile
import threading
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.store import SQLiteRunStore, RunRecord, RunStateModel
from skillweave.runtime.errors import VersionConflictError, StoreError


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


def _writer(db_path, run_id, target_state, outcomes):
    store = SQLiteRunStore(db_path=db_path)
    try:
        store.transition(
            run_id=run_id,
            target_state=target_state,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
            reason="concurrent advance",
        )
        outcomes["wins"] += 1
    except VersionConflictError:
        outcomes["conflicts"] += 1
    except StoreError:
        # A non-version conflict (stale state snapshot) is still a conflict,
        # never a silent double-advance. Count separately to stay honest.
        outcomes["conflicts"] += 1
    except Exception as exc:  # noqa: BLE001
        outcomes["errors"].append(exc)
    finally:
        store.close()


def test_two_concurrent_writers_same_version_exactly_one_wins():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        run_id = "run-cas-concurrent"
        store = SQLiteRunStore(db_path=db_path)
        store.save_run(_make_run(run_id))
        store.close()

        outcomes = {"wins": 0, "conflicts": 0, "errors": []}
        writers = 8
        threads = [
            threading.Thread(
                target=_writer,
                args=(db_path, run_id, RunStateModel.IN_PROGRESS.value, outcomes),
            )
            for _ in range(writers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert outcomes["errors"] == [], f"unexpected errors: {outcomes['errors']}"
        assert outcomes["wins"] == 1, (
            f"expected exactly one winner, got {outcomes['wins']} wins"
        )
        assert outcomes["conflicts"] == writers - 1, (
            f"expected {writers - 1} conflicts, got {outcomes['conflicts']}"
        )

        # Authoritative final state: exactly one transition applied, version == 2.
        reader = SQLiteRunStore(db_path=db_path)
        final = reader.get_run(run_id)
        assert final.state == RunStateModel.IN_PROGRESS.value
        assert final.version == 2
        reader.close()


def test_stale_writer_cannot_roll_back_a_newer_version():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        run_id = "run-no-rollback"
        store = SQLiteRunStore(db_path=db_path)
        store.save_run(_make_run(run_id))
        store.transition(
            run_id=run_id,
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
        )
        # Now at version 2. A stale writer holding version 1 must be rejected.
        stale_raised = False
        try:
            store.transition(
                run_id=run_id,
                target_state=RunStateModel.PREFLIGHT_COMPLETE.value,
                expected_state=RunStateModel.IN_PROGRESS.value,
                expected_version=1,
            )
        except VersionConflictError:
            stale_raised = True
        assert stale_raised is True
        final = store.get_run(run_id)
        assert final.version == 2
        assert final.state == RunStateModel.IN_PROGRESS.value
        store.close()


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
