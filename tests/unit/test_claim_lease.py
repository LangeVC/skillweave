"""SW-CLAIM-001: write-scope claims carry a lease, heartbeat, and expiry.

Competing coordinators claim a lane exactly once; an expired (or released)
claim is controllably takeover-able, but a live claim is never silently stolen.
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.store import SQLiteRunStore
from skillweave.runtime.write_scope import ScopeConflictError


def test_competing_coordinators_claim_a_lane_exactly_once():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        store.claim_write_scope("coord-a", ["src/lane1"], claim_id="lane1")
        try:
            store.claim_write_scope("coord-b", ["src/lane1"], claim_id="lane1-b")
            assert False, "second coordinator must not claim the same live lane"
        except ScopeConflictError:
            pass
        store.close()


def test_expired_claim_is_controllably_takeoverable():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        claims = store.claim_write_scope("coord-a", ["src/lane1"], claim_id="lane1", ttl_seconds=1)
        cid = claims[0].claim_id

        # Manually expire the lease: set lease_until into the past.
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        store._conn.execute(
            "UPDATE write_scope_claims SET lease_until = ? WHERE claim_id = ?",
            (past, cid),
        )
        store._conn.commit()

        # A second coordinator claims the same scope; expired claim no longer blocks.
        claims_b = store.claim_write_scope("coord-b", ["src/lane1"])
        assert len(claims_b) == 1
        assert claims_b[0].run_id == "coord-b"
        store.close()


def test_live_claim_is_never_silently_stolen():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        claims = store.claim_write_scope("coord-a", ["src/lane1"], claim_id="lane1", ttl_seconds=3600)
        cid = claims[0].claim_id
        # A live (unexpired) claim cannot be taken over.
        assert store.try_takeover(cid, "coord-b") is False
        row = store._conn.execute(
            "SELECT run_id FROM write_scope_claims WHERE claim_id = ?", (cid,)
        ).fetchone()
        assert row["run_id"] == "coord-a"
        store.close()


def test_heartbeat_renews_lease():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        claims = store.claim_write_scope("coord-a", ["src/lane1"], claim_id="lane1", ttl_seconds=60)
        cid = claims[0].claim_id
        original = store.list_write_scope_claims(run_id="coord-a")[0].lease_until
        assert store.heartbeat_claim(cid, ttl_seconds=600) is True
        renewed = store.list_write_scope_claims(run_id="coord-a")[0].lease_until
        assert renewed != original
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
