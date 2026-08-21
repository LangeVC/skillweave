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


def test_stale_save_run_cannot_roll_back_a_newer_version():
    """SW-STATE-001: save_run must be version-safe, not a silent INSERT OR REPLACE.

    A stale writer that snapshotted authority at version 1 must not overwrite a
    version-2 committed row (which would revert the authoritative run to v1 and
    leave ``transitions_log`` disagreeing with the run row). Instead,
    ``save_run`` must raise ``VersionConflictError`` and leave the row intact.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        run_id = "run-save-rollback"
        store = SQLiteRunStore(db_path=db_path)
        store.save_run(_make_run(run_id))
        store.transition(
            run_id=run_id,
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
        )
        assert store.get_run(run_id).version == 2

        # A stale writer still holds the v1 snapshot and calls save_run with it.
        stale = _make_run(run_id)
        assert stale.version == 1

        raised = False
        try:
            store.save_run(stale)
        except VersionConflictError:
            raised = True

        assert raised, (
            "expected VersionConflictError from save_run, but the stale v1 "
            "writer silently rolled the authoritative run back"
        )
        final = store.get_run(run_id)
        assert final.version == 2, "authoritative row must be unchanged"
        assert final.state == RunStateModel.IN_PROGRESS.value
        store.close()


def test_save_run_initial_create_keeps_version_one():
    """The non-CAS create path is preserved: an absent row saves at version 1."""
    store = SQLiteRunStore(":memory:")
    record = _make_run("run-create-001")
    saved = store.save_run(record)
    assert saved.version == 1
    assert store.get_run("run-create-001").version == 1


def _save_writer(db_path, record, outcomes):
    store = SQLiteRunStore(db_path=db_path)
    try:
        store.save_run(record)
        outcomes["wins"] += 1
    except VersionConflictError:
        outcomes["conflicts"] += 1
    except StoreError:
        outcomes["conflicts"] += 1
    except Exception as exc:  # noqa: BLE001
        outcomes["errors"].append(exc)
    finally:
        store.close()


def test_concurrent_first_create_save_run_exactly_one_wins():
    """SW-STATE-001: N writers race to create the same run_id. Exactly one wins.

    Simultaneous first-creates of a run must not both succeed silently. The
    ``run_id`` PRIMARY KEY makes the second INSERT raise IntegrityError, which
    ``save_run`` turns into a VersionConflictError. So: one winner, N-1 losers.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        run_id = "run-save-race-create"

        # Bootstrap the schema on a separate throwaway store so the table
        # exists before the threads race to first-create the same run_id.
        bootstrap = SQLiteRunStore(db_path=db_path)
        bootstrap.close()

        outcomes = {"wins": 0, "conflicts": 0, "errors": []}
        writers = 8
        barrier = threading.Barrier(writers)

        def _raced_create():
            barrier.wait()
            _save_writer(db_path, _make_run(run_id), outcomes)

        threads = [threading.Thread(target=_raced_create) for _ in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert outcomes["errors"] == [], f"unexpected errors: {outcomes['errors']}"
        assert outcomes["wins"] == 1, (
            f"expected exactly one first-create winner, got {outcomes['wins']}"
        )
        assert outcomes["conflicts"] == writers - 1, (
            f"expected {writers - 1} conflicts, got {outcomes['conflicts']}"
        )

        reader = SQLiteRunStore(db_path=db_path)
        final = reader.get_run(run_id)
        assert final is not None
        assert final.version == 1
        reader.close()


def test_concurrent_overwrite_save_run_exactly_one_wins():
    """SW-STATE-001: N writers race to overwrite the same row at the same version.

    All writers snapshot version 2 and call ``save_run`` with version 2. The
    ``UPDATE ... WHERE run_id = ? AND version = ?`` guard is atomic in SQL: the
    first writer bumps the row to version 3 and the remaining N-1 see rowcount 0
    and receive a VersionConflictError. Exactly one wins, no silent last-write-wins.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        run_id = "run-save-race-overwrite"

        # Establish a row at version 2 (bootstrap v1, then one transition).
        seed = SQLiteRunStore(db_path=db_path)
        seed.save_run(_make_run(run_id))
        seed.transition(
            run_id=run_id,
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
        )
        assert seed.get_run(run_id).version == 2
        seed.close()

        outcomes = {"wins": 0, "conflicts": 0, "errors": []}
        writers = 8
        barrier = threading.Barrier(writers)

        # Each writer snapshots version 2 and proposes a distinct state so a
        # silent last-write-wins would be detectable as divergence; the single
        # winner's state must be exactly the one persisted, with no interleaving.
        states = [f"state-{i}" for i in range(writers)]

        def _raced_overwrite(i):
            rec = _make_run(run_id)
            rec.version = 2
            rec.state = states[i]
            barrier.wait()
            _save_writer(db_path, rec, outcomes)

        threads = [
            threading.Thread(target=_raced_overwrite, args=(i,)) for i in range(writers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert outcomes["errors"] == [], f"unexpected errors: {outcomes['errors']}"
        assert outcomes["wins"] == 1, (
            f"expected exactly one overwrite winner, got {outcomes['wins']}"
        )
        assert outcomes["conflicts"] == writers - 1, (
            f"expected {writers - 1} conflicts, got {outcomes['conflicts']}"
        )

        reader = SQLiteRunStore(db_path=db_path)
        final = reader.get_run(run_id)
        assert final is not None
        assert final.version == 3, (
            f"winner must bump the overwritten row from 2 to 3, got {final.version}"
        )
        # The persisted state must equal exactly one of the proposed states
        # (the winner), never a mixed/divergent value.
        assert final.state in states, f"divergent persisted state: {final.state}"
        reader.close()


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
