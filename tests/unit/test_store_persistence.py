"""
SW-135-005: Checkpoint / Evidence / Handoff Persistenz im selben Runtime-Store.

Roundtrip save -> load fuer die drei Typen. Der Beweis, dass Daten den Prozess
ueberleben, laeuft ueber einen Store, der am selben db_path NEU geoeffnet wird
(erstes `close()`, dann ein frischer `SQLiteRunStore(db_path=...)`).

Eigenes sys.path-Handling (unabhaengig von conftest/pytest).
"""

import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.store import SQLiteRunStore
from skillweave.runtime.checkpoint import Checkpoint, EnvironmentFingerprint
from skillweave.runtime.registry import ArtifactReceipt, EvidenceQuality
from skillweave.runtime.handoff import HandoffOffer, ColdStartBundle


def _make_checkpoint() -> Checkpoint:
    env = EnvironmentFingerprint(
        hostname="lane-005",
        os_name="TestOS 1.0",
        python_version="3.14.7",
        branch="ops/SW-135-vertraege",
        commit_sha="abc123",
        key_hashes={"k1": "h1"},
    )
    return Checkpoint(
        run_id="run-cp-1",
        root_run_id="root-1",
        parent_run_id=None,
        journal_offset=42,
        environment=env,
        metadata={"step": "implement"},
    )


def _make_evidence() -> ArtifactReceipt:
    return ArtifactReceipt(
        artifact_id="evd-001",
        sha256="a" * 64,
        schema_version="1",
        producer_command="pytest",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-16T00:00:00Z",
        evidence_type="test",
        purpose="roundtrip",
        method="unit",
        transformation_history=["raw", "normalized"],
        quality=EvidenceQuality(reliability="high"),
        supersedes=None,
        metadata={"k": "v"},
    )


def _make_handoff() -> HandoffOffer:
    bundle = ColdStartBundle(
        prd_uri="file:///prd.md",
        prd_digest="d1",
        chain_uri="file:///chain.yaml",
        chain_digest="d2",
        repo_uri="git@example.com:org/repo.git",
        worktree_path="/tmp/wt-sw135",
        branch="ops/SW-135-vertraege",
        target_role="ops",
        sequence_id="seq-1",
    )
    return HandoffOffer(
        handoff_id="ho-001",
        from_role="dev",
        to_role="ops",
        scope="feature",
        cold_start_bundle=bundle,
        allowed_actions=["accept"],
        input_digests={"prd": "d1"},
        metadata={"lane": "005"},
    )


def test_checkpoint_roundtrip_survives_reopen():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        store.save_checkpoint(_make_checkpoint())
        store.close()

        store2 = SQLiteRunStore(db_path=db_path)
        cp = store2.get_checkpoint("run-cp-1")
        assert cp is not None
        assert cp.run_id == "run-cp-1"
        assert cp.root_run_id == "root-1"
        assert cp.parent_run_id is None
        assert cp.journal_offset == 42
        assert cp.environment.hostname == "lane-005"
        assert cp.environment.branch == "ops/SW-135-vertraege"
        assert cp.environment.key_hashes == {"k1": "h1"}
        assert cp.metadata == {"step": "implement"}
        store2.close()


def test_evidence_roundtrip_survives_reopen():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        store.save_evidence(_make_evidence())
        store.close()

        store2 = SQLiteRunStore(db_path=db_path)
        ev = store2.get_evidence("evd-001")
        assert ev is not None
        assert ev.artifact_id == "evd-001"
        assert ev.sha256 == "a" * 64
        assert ev.evidence_type == "test"
        assert ev.purpose == "roundtrip"
        assert ev.transformation_history == ["raw", "normalized"]
        assert ev.quality.reliability == "high"
        assert ev.quality.sufficiency == "medium"
        assert ev.supersedes is None
        assert ev.metadata == {"k": "v"}
        store2.close()


def test_handoff_roundtrip_survives_reopen():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        store.save_handoff(_make_handoff())
        store.close()

        store2 = SQLiteRunStore(db_path=db_path)
        ho = store2.get_handoff("ho-001")
        assert ho is not None
        assert ho.handoff_id == "ho-001"
        assert ho.from_role == "dev"
        assert ho.to_role == "ops"
        assert ho.scope == "feature"
        assert ho.state == "offered"
        assert ho.allowed_actions == ["accept"]
        assert ho.input_digests == {"prd": "d1"}
        bundle = ho.cold_start_bundle
        assert bundle.prd_uri == "file:///prd.md"
        assert bundle.chain_digest == "d2"
        assert bundle.repo_uri == "git@example.com:org/repo.git"
        assert bundle.target_role == "ops"
        assert bundle.sequence_id == "seq-1"
        assert ho.metadata == {"lane": "005"}
        store2.close()


def test_evidence_table_has_unique_on_artifact_id():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        row = store._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence'"
        ).fetchone()
        assert row is not None
        sql = row["sql"]
        assert "UNIQUE" in sql
        assert "artifact_id" in sql
        store.close()


def _run_all() -> int:
    tests = [
        test_checkpoint_roundtrip_survives_reopen,
        test_evidence_roundtrip_survives_reopen,
        test_handoff_roundtrip_survives_reopen,
        test_evidence_table_has_unique_on_artifact_id,
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
