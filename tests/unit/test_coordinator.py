"""Tests for the root-DAG coordinator (SW-COORD-001).

Proves three guarantees:

1. **Sole writer.** A worker and a reviewer cannot mutate the root cursor —
   every mutation is refused with ``CoordinatorAccessError`` before any state
   changes. Only the coordinator (ops) may create/advance it.
2. **CAS on version.** Two coordinators that race on the same expected version
   cannot both append; the loser's write is refused.
3. **Fresh resume.** A fresh ``Coordinator`` over the same store loads the
   persisted cursor and continues from it (cursor_index, committed_nodes,
   version preserved), rather than starting over.

Self-contained sys.path handling, following the sibling-test convention.
"""

import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.coordinator import Coordinator, CoordinatorAccessError  # noqa: E402
from skillweave.runtime.store import SQLiteRunStore  # noqa: E402


def _coordinator(tmp: str):
    store = SQLiteRunStore(tmp)
    return Coordinator(store), store


def test_coordinator_is_sole_writer_workers_reviewers_cannot_mutate():
    with tempfile.TemporaryDirectory() as tmp:
        coord, store = _coordinator(str(Path(tmp) / "store.db"))
        coord.ensure_root("seq1", "wave1", "W3-L1", role="ops")

        # A worker and a reviewer must not mutate the root cursor.
        for role in ("worker", "reviewer", "sub_agent"):
            for action, call in (
                ("ensure_root", lambda r=role: coord.ensure_root("seq1", "wave1", "W3-L1", role=r)),
                ("advance", lambda r=role: coord.advance("seq1", "wave1", "n1", role=r)),
            ):
                try:
                    call()
                except CoordinatorAccessError as exc:
                    assert exc.role == role
                else:
                    raise AssertionError(f"{role} {action} must be refused")

        # Nothing changed: the cursor is still the coordinator's initial state.
        cursor = coord.load("seq1", "wave1")
        assert cursor.cursor_index == 0
        assert cursor.committed_nodes == []
        store.close()


def test_cas_on_version_prevents_double_commit():
    with tempfile.TemporaryDirectory() as tmp:
        coord, store = _coordinator(str(Path(tmp) / "store.db"))
        curs = coord.ensure_root("seq1", "wave1", "W3-L1", role="ops")

        # Coordinator A appends from version 1.
        a = coord.advance("seq1", "wave1", "node-a", role="ops", expected_version=curs.version)
        assert a.version == 2

        # A second coordinator trying to append from the stale version 1 is
        # refused: the write is CAS-guarded.
        try:
            coord.advance("seq1", "wave1", "node-b", role="ops", expected_version=1)
        except CoordinatorAccessError:
            pass
        else:
            raise AssertionError("stale-version advance must be refused")

        cursor = coord.load("seq1", "wave1")
        assert cursor.committed_nodes == ["node-a"]
        assert cursor.cursor_index == 1
        store.close()


def test_fresh_coordinator_resumes_from_persisted_cursor():
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "store.db")
        coord, store = _coordinator(db)
        coord.ensure_root("seq1", "wave1", "W3-L1", role="ops")
        coord.advance("seq1", "wave1", "node-1", role="ops")
        coord.advance("seq1", "wave1", "node-2", role="ops")
        store.close()

        # A fresh coordinator over the *same* store resumes the cursor.
        store2 = SQLiteRunStore(db)
        coord2 = Coordinator(store2)
        cursor = coord2.load("seq1", "wave1", role="ops")
        assert cursor is not None
        assert cursor.cursor_index == 2
        assert cursor.committed_nodes == ["node-1", "node-2"]

        # And it can continue, not restart.
        nxt = coord2.advance("seq1", "wave1", "node-3", role="ops", expected_version=cursor.version)
        assert nxt.version == 4
        assert coord2.load("seq1", "wave1").committed_nodes[-1] == "node-3"
        store2.close()


def test_ensure_root_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        coord, store = _coordinator(str(Path(tmp) / "store.db"))
        first = coord.ensure_root("seq1", "wave1", "W3-L1", role="ops")
        second = coord.ensure_root("seq1", "wave1", "W3-L1", role="ops")
        assert first.version == second.version == 1
        assert second.committed_nodes == []
        store.close()


def _run_all() -> int:
    tests = [
        test_coordinator_is_sole_writer_workers_reviewers_cannot_mutate,
        test_cas_on_version_prevents_double_commit,
        test_fresh_coordinator_resumes_from_persisted_cursor,
        test_ensure_root_is_idempotent,
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
