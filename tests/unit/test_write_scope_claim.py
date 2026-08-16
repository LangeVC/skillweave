"""
SW-135-009: Write-Scopes werden beansprucht, nicht nur geprueft.

Claim, Konflikt, Freigabe auf geloesten Pfaden, persistent im vorhandenen
Store. Kein Scheduler hier — nur Anspruch / Konflikt / Freigabe.

Eigenes sys.path-Handling (unabhaengig von conftest/pytest).
"""

import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.store import SQLiteRunStore, RunRecord
from skillweave.runtime.write_scope import ScopeConflictError


def _make_run(run_id: str) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        root_run_id=run_id,
        parent_run_id=None,
        state="IN_PROGRESS",
        version=1,
        created_at="2026-08-16T00:00:00Z",
        updated_at="2026-08-16T00:00:00Z",
        ended_at=None,
        role="ops",
    )


def test_claim_and_release_persist_across_reopen():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        claims = store.claim_write_scope("run-1", ["src/"])
        assert len(claims) == 1
        assert claims[0].run_id == "run-1"
        assert claims[0].held is True
        cid = claims[0].claim_id
        store.close()

        store2 = SQLiteRunStore(db_path=db_path)
        held = store2.list_write_scope_claims()
        assert len(held) == 1
        assert held[0].claim_id == cid
        assert held[0].held is True
        assert store2.release_write_scope(cid) is True
        assert store2.list_write_scope_claims() == []
        store2.close()


def test_second_claim_on_overlapping_scope_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        store.claim_write_scope("run-1", ["src/skillweave/"])
        try:
            store.claim_write_scope("run-2", ["src/"])
            assert False, "expected ScopeConflictError"
        except ScopeConflictError as e:
            assert e.run_id == "run-2"
            assert e.holder_run_id == "run-1"
        # nothing was persisted for run-2
        run2 = store.list_write_scope_claims(run_id="run-2")
        assert run2 == []
        store.close()


def test_overlap_is_resolved_not_string_prefix():
    # "src" (resolved -> .../src) must NOT overlap "src2".
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        store.claim_write_scope("run-1", ["src"])
        # "src2" shares the string prefix "src" but is a peer directory.
        claims = store.claim_write_scope("run-2", ["src2"])
        assert len(claims) == 1
        store.close()


def test_orphaned_claim_is_recognized_and_released():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        store.save_run(_make_run("run-alive"))
        store.claim_write_scope("run-alive", ["src/"])
        # run-ghost holds a claim but has no run row -> orphaned.
        store.claim_write_scope("run-ghost", ["tests/"])

        released = store.resolve_orphaned_claims()
        assert "run-ghost" not in released  # claim_ids, not run_ids
        assert len(released) == 1

        # ghost claim is gone; alive claim still held.
        held = store.list_write_scope_claims()
        assert [c.run_id for c in held] == ["run-alive"]
        store.close()


def _run_all() -> int:
    tests = [
        test_claim_and_release_persist_across_reopen,
        test_second_claim_on_overlapping_scope_is_rejected,
        test_overlap_is_resolved_not_string_prefix,
        test_orphaned_claim_is_recognized_and_released,
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
    failed = _run_all()
    sys.exit(1 if failed else 0)
