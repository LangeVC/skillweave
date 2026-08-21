"""SW-IDEMP-001: atomic idempotency for journal, evidence, and handoff.

Twenty concurrent writers submitting the SAME idempotency key must produce
exactly one canonical result, never 20 rows and never a lost write.
"""

import sys
import tempfile
import threading
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.journal import EventJournal
from skillweave.runtime.store import SQLiteRunStore
from skillweave.runtime.registry import ArtifactReceipt
from skillweave.runtime.handoff import HandoffOffer, ColdStartBundle


def _make_receipt() -> ArtifactReceipt:
    return ArtifactReceipt(
        artifact_id="evd-same",
        sha256="b" * 64,
        schema_version="1",
        producer_command="pytest",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-16T00:00:00Z",
        evidence_type="test",
        purpose="idem",
    )


def _make_handoff() -> HandoffOffer:
    return HandoffOffer(
        handoff_id="ho-same",
        from_role="dev",
        to_role="ops",
        scope="feature",
        cold_start_bundle=ColdStartBundle(
            prd_uri="file:///prd.md", prd_digest="d1", chain_uri="file:///c",
            chain_digest="d2", repo_uri="git@x", worktree_path="/tmp/wt",
            branch="b", target_role="ops", sequence_id="s",
        ),
        allowed_actions=["accept"],
    )


def test_twenty_concurrent_journal_keys_produce_one_canonical_event():
    writers = 20
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "journal.db")
        EventJournal(db_path).close()  # init schema

        def write():
            j = EventJournal(db_path)
            try:
                j.append(
                    run_id="run-idem",
                    payload={"n": 1},
                    idempotency_key="key-journal",
                )
            finally:
                j.close()

        threads = [threading.Thread(target=write) for _ in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        j = EventJournal(db_path)
        events = j.get_events("run-idem")
        j.close()
        assert len(events) == 1, f"expected 1 canonical event, got {len(events)}"


def test_twenty_concurrent_evidence_keys_produce_one_canonical_receipt():
    writers = 20
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        SQLiteRunStore(db_path=db_path).close()  # init schema on one connection

        def write():
            store = SQLiteRunStore(db_path=db_path)
            try:
                store.save_evidence(_make_receipt(), idempotency_key="key-evidence")
            finally:
                store.close()

        threads = [threading.Thread(target=write) for _ in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        store = SQLiteRunStore(db_path=db_path)
        rows = store._conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE idempotency_key = ?",
            ("key-evidence",),
        ).fetchone()[0]
        store.close()
        assert rows == 1, f"expected 1 canonical receipt, got {rows}"


def test_twenty_concurrent_handoff_keys_produce_one_canonical_handoff():
    writers = 20
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        SQLiteRunStore(db_path=db_path).close()  # init schema on one connection

        def write():
            store = SQLiteRunStore(db_path=db_path)
            try:
                store.save_handoff(_make_handoff(), idempotency_key="key-handoff")
            finally:
                store.close()

        threads = [threading.Thread(target=write) for _ in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        store = SQLiteRunStore(db_path=db_path)
        rows = store._conn.execute(
            "SELECT COUNT(*) FROM handoffs WHERE idempotency_key = ?",
            ("key-handoff",),
        ).fetchone()[0]
        store.close()
        assert rows == 1, f"expected 1 canonical handoff, got {rows}"


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
