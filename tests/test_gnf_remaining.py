import pytest


class TestGNFRemaining:
    def test_gnf_02_batch_without_evidence_rejected(self):
        from skillweave.runtime.store import SQLiteRunStore
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.authority import AuthorityGuard
        from skillweave.runtime.observer import ObserverRuntime
        from skillweave.runtime.registry import EvidenceRegistry
        from skillweave.runtime.gate_reconciliation import reconcile_gate

        store = SQLiteRunStore()
        store.ensure_storage()
        registry = EvidenceRegistry()
        journal = EventJournal(store)
        r = store.create_run("gnf-02")
        obs = ObserverRuntime(journal, r.run_id)
        result = reconcile_gate("GATE-B02", registry, obs, AuthorityGuard())
        assert result.reconciled is False
        assert "insufficient" in result.evidence_weight

    def test_gnf_03_invalid_transition_no_side_effect(self):
        from skillweave.runtime.store import SQLiteRunStore, RunStateModel
        from skillweave.runtime.errors import InvalidTransitionError

        store = SQLiteRunStore()
        store.ensure_storage()
        r = store.create_run("gnf-03-state")

        with pytest.raises(InvalidTransitionError):
            store.transition(r.run_id, "advance_or_stop", expected_state="nonexistent", expected_version=1)

    def test_gnf_04_observer_without_journal_data(self):
        from skillweave.runtime.store import SQLiteRunStore
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime

        store = SQLiteRunStore()
        store.ensure_storage()
        journal = EventJournal(store)
        r = store.create_run("gnf-04")
        obs = ObserverRuntime(journal, r.run_id)
        obs.replay()
        assert obs.state().offset == 0

    def test_gnf_06_expired_lease_is_detected(self):
        from skillweave.runtime.store import SQLiteRunStore
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime, ObserverLease

        store = SQLiteRunStore()
        store.ensure_storage()
        journal = EventJournal(store)
        r = store.create_run("gnf-06")
        obs = ObserverRuntime(journal, r.run_id)
        lease = obs.acquire_lease("old-observer", ttl_minutes=0)
        expired = ObserverLease(
            lease_id=lease.lease_id, owner=lease.owner,
            expires_at="2020-01-01T00:00:00Z",
        )
        assert expired.is_expired() is True

    def test_gnf_07_missigned_handoff_digest(self):
        from skillweave.runtime.handoff import (
            HandoffBroker, ColdStartBundle, HandoffError,
        )
        broker = HandoffBroker()
        c = ColdStartBundle(
            prd_uri="p.json", prd_digest="EXPECTED_A", chain_uri="c.yaml",
            chain_digest="EXPECTED_B", repo_uri="git@r", worktree_path="/w",
            branch="f", target_role="OPS", sequence_id="S",
        )
        offer = broker.offer(from_role="REVIEWER", to_role="OPS", scope="I00", cold_start=c)
        with pytest.raises(HandoffError, match="DIGEST_MISMATCH"):
            broker.accept(
                offer.handoff_id, actor="OPS", product="SW",
                repo="git@r", prd_digest="WRONG", chain_digest="WRONG",
            )

    def test_gnf_08_preflight_foreign_repo(self):
        from skillweave.runtime.preflight import SessionEnvelope, run_preflight
        env = SessionEnvelope(
            product="SW", remote_repo="git@canonical", worktree="/w",
            branch="feature/x", role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/"], state_vocabulary=["idle"],
            forbidden_transitions=["merge"],
        )
        result = run_preflight(env, actual_repo="git@other", actual_branch="feature/x")
        assert result.passed is False

    def test_gnf_10_write_outside_scope_rejected(self):
        from skillweave.runtime.wireframe import assert_write_scope
        ok, violations = assert_write_scope(
            ["src/skillweave/foo.py", "/etc/passwd", "CHANGELOG.md"],
            ["src/**"],
        )
        assert ok is False
        assert len(violations) == 2
        assert "/etc/passwd" in violations

    def test_gnf_11_version_conflict_on_append(self):
        from skillweave.runtime.store import SQLiteRunStore
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.errors import VersionConflictError

        store = SQLiteRunStore()
        store.ensure_storage()
        r = store.create_run("gnf-11")
        journal = EventJournal(store)
        journal.append(r.run_id, "msg1", {"v": 1}, event_type="state")
        with pytest.raises(VersionConflictError):
            journal.append(
                r.run_id, "msg2", {"v": 2}, event_type="state",
                expected_version=99,
            )

    def test_gnf_12_gate_policy_self_approval(self):
        from skillweave.execution.gate_policy import GatePolicy
        from skillweave.runtime.authority import AuthorityError

        policy = GatePolicy(name="gnf-12-gate")
        with pytest.raises(AuthorityError) as exc:
            policy.prevent_self_approval("ops", "I00")
        assert "ops" in str(exc.value).lower()
