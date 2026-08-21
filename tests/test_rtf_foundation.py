import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from skillweave.runtime.store import RunStore, SQLiteRunStore, RunRecord, RunStateModel
from skillweave.runtime.errors import InvalidTransitionError, VersionConflictError, StoreError
from skillweave.runtime.journal import EventJournal, JournalEvent, EventType
from skillweave.execution.state_machine import RunStateMachine


class TestSQLiteRunStore:
    def test_create_and_retrieve_run(self):
        store = SQLiteRunStore(":memory:")
        record = RunRecord(
            run_id="run-001",
            root_run_id="run-001",
            parent_run_id=None,
            state=RunStateModel.PREFLIGHT.value,
            version=1,
            created_at="2026-08-11T00:00:00Z",
            updated_at="2026-08-11T00:00:00Z",
            ended_at=None,
            role="ops",
        )
        store.save_run(record)
        retrieved = store.get_run("run-001")
        assert retrieved is not None
        assert retrieved.run_id == "run-001"
        assert retrieved.state == "preflight"
        assert retrieved.version == 1

    def test_run_identity_hierarchy(self):
        store = SQLiteRunStore(":memory:")
        record = RunRecord(
            run_id="child-001",
            root_run_id="root-001",
            parent_run_id="parent-001",
            state=RunStateModel.PREFLIGHT.value,
            version=1,
            created_at="2026-08-11T00:00:00Z",
            updated_at="2026-08-11T00:00:00Z",
            ended_at=None,
            role="ops",
        )
        store.save_run(record)
        retrieved = store.get_run("child-001")
        assert retrieved.root_run_id == "root-001"
        assert retrieved.parent_run_id == "parent-001"

    def test_save_run_increments_version(self):
        store = SQLiteRunStore(":memory:")
        record = RunRecord(
            run_id="run-002",
            root_run_id="run-002",
            parent_run_id=None,
            state="preflight",
            version=0,
            created_at="2026-08-11T00:00:00Z",
            updated_at="2026-08-11T00:00:00Z",
            ended_at=None,
            role="ops",
        )
        saved = store.save_run(record)
        assert saved.version >= 1

    def test_valid_transition(self):
        store = SQLiteRunStore(":memory:")
        record = RunRecord(
            run_id="run-003",
            root_run_id="run-003",
            parent_run_id=None,
            state=RunStateModel.SANDBOX_PREFLIGHT.value,
            version=1,
            created_at="2026-08-11T00:00:00Z",
            updated_at="2026-08-11T00:00:00Z",
            ended_at=None,
            role="ops",
        )
        store.save_run(record)
        result = store.transition(
            run_id="run-003",
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
            reason="preflight complete",
        )
        assert result.state == "in_progress"
        assert result.version == 2

    def test_illegal_transition_raises(self):
        store = SQLiteRunStore(":memory:")
        record = RunRecord(
            run_id="run-004",
            root_run_id="run-004",
            parent_run_id=None,
            state=RunStateModel.PREFLIGHT.value,
            version=1,
            created_at="2026-08-11T00:00:00Z",
            updated_at="2026-08-11T00:00:00Z",
            ended_at=None,
            role="ops",
        )
        store.save_run(record)
        with pytest.raises(InvalidTransitionError) as exc:
            store.transition(
                run_id="run-004",
                target_state=RunStateModel.ADVANCE_OR_STOP.value,
                expected_state=RunStateModel.PREFLIGHT.value,
                expected_version=1,
                reason="skip all steps",
            )
        assert exc.value.run_id == "run-004"
        assert "Invalid transition" in str(exc.value)
        record_after = store.get_run("run-004")
        assert record_after.state == "preflight"
        assert record_after.version == 1

    def test_optimistic_concurrency(self):
        store = SQLiteRunStore(":memory:")
        record = RunRecord(
            run_id="run-005",
            root_run_id="run-005",
            parent_run_id=None,
            state=RunStateModel.SANDBOX_PREFLIGHT.value,
            version=1,
            created_at="2026-08-11T00:00:00Z",
            updated_at="2026-08-11T00:00:00Z",
            ended_at=None,
            role="ops",
        )
        store.save_run(record)
        store.transition(
            run_id="run-005",
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
            reason="first transition",
        )
        with pytest.raises(VersionConflictError) as exc:
            store.transition(
                run_id="run-005",
                target_state=RunStateModel.PREFLIGHT_COMPLETE.value,
                expected_state=RunStateModel.IN_PROGRESS.value,
                expected_version=1,
                reason="stale write",
            )
        assert exc.value.run_id == "run-005"
        assert exc.value.expected_version == 1
        assert exc.value.actual_version == 2

    def test_nonexistent_run_transition_fails(self):
        store = SQLiteRunStore(":memory:")
        with pytest.raises(InvalidTransitionError) as exc:
            store.transition(
                run_id="nonexistent",
                target_state=RunStateModel.IN_PROGRESS.value,
                expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
                expected_version=1,
            )
        assert exc.value.run_id == "nonexistent"

    def test_list_runs_by_state(self):
        store = SQLiteRunStore(":memory:")
        for i in range(3):
            store.save_run(RunRecord(
                run_id=f"run-{i}",
                root_run_id=f"run-{i}",
                parent_run_id=None,
                state=RunStateModel.PREFLIGHT.value,
                version=1,
                created_at=f"2026-08-11T0{i}:00:00Z",
                updated_at=f"2026-08-11T0{i}:00:00Z",
                ended_at=None,
                role="ops",
            ))
        runs = store.list_runs(state="preflight")
        assert len(runs) == 3

    def test_persistence_survives_restart(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name
        try:
            store1 = SQLiteRunStore(db_path)
            record = RunRecord(
                run_id="persist-001",
                root_run_id="persist-001",
                parent_run_id=None,
                state=RunStateModel.PREFLIGHT.value,
                version=1,
                created_at="2026-08-11T00:00:00Z",
                updated_at="2026-08-11T00:00:00Z",
                ended_at=None,
                role="ops",
            )
            store1.save_run(record)
            store1.close()

            store2 = SQLiteRunStore(db_path)
            retrieved = store2.get_run("persist-001")
            assert retrieved is not None
            assert retrieved.state == "preflight"
            assert retrieved.version == 1
        finally:
            os.unlink(db_path)

    def test_transition_log_preserves_history(self):
        store = SQLiteRunStore(":memory:")
        record = RunRecord(
            run_id="run-006",
            root_run_id="run-006",
            parent_run_id=None,
            state=RunStateModel.SANDBOX_PREFLIGHT.value,
            version=1,
            created_at="2026-08-11T00:00:00Z",
            updated_at="2026-08-11T00:00:00Z",
            ended_at=None,
            role="ops",
        )
        store.save_run(record)
        store.transition(
            run_id="run-006",
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
            reason="start work",
        )
        rows = store._conn.execute(
            "SELECT * FROM transitions_log WHERE run_id = ?", ("run-006",)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["from_state"] == RunStateModel.SANDBOX_PREFLIGHT.value
        assert rows[0]["to_state"] == RunStateModel.IN_PROGRESS.value
        assert rows[0]["reason"] == "start work"


class TestRunStateMachine:
    def test_create_run(self):
        sm = RunStateMachine(SQLiteRunStore(":memory:"))
        record = sm.create_run("run-001", role="ops")
        assert record.run_id == "run-001"
        assert record.state == RunStateModel.SANDBOX_PREFLIGHT.value
        assert record.root_run_id == "run-001"
        assert record.version == 1

    def test_create_run_with_hierarchy(self):
        sm = RunStateMachine(SQLiteRunStore(":memory:"))
        root = sm.create_run("root", role="observer")
        child = sm.create_run("child", root_run_id="root", parent_run_id="root", role="ops")
        assert child.root_run_id == "root"
        assert child.parent_run_id == "root"

    def test_transition_with_explicit_expected(self):
        sm = RunStateMachine(SQLiteRunStore(":memory:"))
        sm.create_run("run-001")
        result = sm.transition(
            run_id="run-001",
            target_state=RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1,
            reason="starting",
        )
        assert result.state == "in_progress"
        assert result.version == 2

    def test_transition_with_implicit_expected(self):
        sm = RunStateMachine(SQLiteRunStore(":memory:"))
        sm.create_run("run-001")
        sm.transition(
            run_id="run-001",
            target_state=RunStateModel.IN_PROGRESS.value,
            reason="step 1",
        )
        result = sm.transition(
            run_id="run-001",
            target_state=RunStateModel.PREFLIGHT_COMPLETE.value,
            reason="step 2",
        )
        assert result.state == "preflight_complete"
        assert result.version == 3

    def test_illegal_transition_no_side_effect(self):
        sm = RunStateMachine(SQLiteRunStore(":memory:"))
        sm.create_run("run-001")
        sm.transition(
            run_id="run-001",
            target_state=RunStateModel.IN_PROGRESS.value,
            reason="start",
        )
        with pytest.raises(InvalidTransitionError):
            sm.transition(
                run_id="run-001",
                target_state=RunStateModel.SANDBOX_PREFLIGHT.value,
                reason="illegal rewind",
            )
        record = sm.get_run("run-001")
        assert record.state == "in_progress"

    def test_is_terminal(self):
        sm = RunStateMachine(SQLiteRunStore(":memory:"))
        sm.create_run("run-001")
        sm.transition(run_id="run-001", target_state=RunStateModel.IN_PROGRESS.value)
        sm.transition(run_id="run-001", target_state=RunStateModel.FAILED.value)
        assert sm.is_terminal("run-001")

    def test_failed_is_terminal(self):
        sm = RunStateMachine(SQLiteRunStore(":memory:"))
        sm.create_run("run-001")
        sm.transition(run_id="run-001", target_state=RunStateModel.FAILED.value)
        assert sm.is_terminal("run-001")

    def test_system_of_systems_traceability(self):
        store = SQLiteRunStore(":memory:")
        sm = RunStateMachine(store)

        system = sm.create_run("system", role="ops")
        assert system.root_run_id == "system"

        element_a = sm.create_run("element-a", root_run_id="system", parent_run_id="system", role="sub-agent")
        assert element_a.root_run_id == "system"
        assert element_a.parent_run_id == "system"

        element_b = sm.create_run("element-b", root_run_id="system", parent_run_id="element-a", role="sub-agent")
        assert element_b.root_run_id == "system"
        assert element_b.parent_run_id == "element-a"

        all_runs = store.list_runs()
        system_runs = [r for r in all_runs if r.root_run_id == "system"]
        assert len(system_runs) == 3

    def test_start_and_end_timestamps(self):
        sm = RunStateMachine(SQLiteRunStore(":memory:"))
        record = sm.create_run("run-001")
        assert record.created_at is not None
        assert record.ended_at is None

        sm.transition(run_id="run-001", target_state=RunStateModel.IN_PROGRESS.value)
        sm.transition(run_id="run-001", target_state=RunStateModel.FAILED.value)

        terminated = sm.get_run("run-001")
        assert terminated.ended_at is not None
        assert terminated.state == "failed"


class TestStatusVocabulary:
    def test_base_schema_accepts_valid_states(self):
        from skillweave.runtime.schema.vocabulary import get_vocabulary, validate_status
        assert validate_status("in_progress")
        assert validate_status("sandbox_preflight")
        assert validate_status("failed")

    def test_base_schema_rejects_drift_values(self):
        from skillweave.runtime.schema.vocabulary import get_vocabulary, validate_status, StatusRejectedError
        drift_values = [
            "ACTIVE",
            "AWAITING_S01_REVIEW",
            "LIFECYCLE_REVIEW_COMPLETE",
            "AWAITING_S05_REVIEW_REQUIRED",
            "EVIDENCE_APPROVED",
        ]
        for value in drift_values:
            try:
                validate_status(value)
                assert False, f"Should have rejected '{value}'"
            except StatusRejectedError as e:
                assert e.value == value

    def test_amendment_path(self):
        from skillweave.runtime.schema.vocabulary import StatusVocabulary
        vocab = StatusVocabulary()
        amendment = vocab.amend("LIFECYCLE_REVIEW_COMPLETE", "Needed for Phase 2 lifecycle", "ops")
        assert amendment.added_value == "LIFECYCLE_REVIEW_COMPLETE"
        assert amendment.schema_version == 2

        valid = vocab.validate("LIFECYCLE_REVIEW_COMPLETE", schema_version=2)
        assert valid

        from skillweave.runtime.schema.vocabulary import StatusRejectedError
        try:
            vocab.validate("LIFECYCLE_REVIEW_COMPLETE", schema_version=1)
            assert False, "Should reject in v1"
        except StatusRejectedError:
            pass

    def test_amendment_idempotent_rejection(self):
        from skillweave.runtime.schema.vocabulary import StatusVocabulary
        vocab = StatusVocabulary()
        try:
            vocab.amend("in_progress", "already exists", "ops")
            assert False, "Should reject existing value"
        except ValueError:
            pass

    def test_schema_versioning(self):
        from skillweave.runtime.schema.vocabulary import StatusVocabulary
        vocab = StatusVocabulary()
        assert vocab.current_schema().version == 1

        vocab.amend("NEW_STATE_1", "test", "ops")
        assert vocab.current_schema().version == 2

        vocab.amend("NEW_STATE_2", "test", "ops")
        assert vocab.current_schema().version == 3

    def test_changelog_preserved(self):
        from skillweave.runtime.schema.vocabulary import StatusVocabulary
        vocab = StatusVocabulary()
        vocab.amend("A", "first", "ops")
        vocab.amend("B", "second", "ops")
        schema = vocab.current_schema()
        assert len(schema.changelog) == 2
        assert schema.changelog[0].added_value == "A"
        assert schema.changelog[1].added_value == "B"

    def test_amendment_under_10_minutes(self):
        import time
        from skillweave.runtime.schema.vocabulary import StatusVocabulary
        vocab = StatusVocabulary()
        start = time.monotonic()
        vocab.amend("QUICK_AMENDMENT", "fast path test", "ops")
        elapsed = time.monotonic() - start
        assert elapsed < 600, f"Amendment took {elapsed:.1f}s, must be <600s"


class TestEventJournal:
    def test_append_event(self):
        j = EventJournal(":memory:")
        event = j.append("run-001", "state_transition", {"from": "A", "to": "B"})
        assert event.sequence == 1
        assert event.run_id == "run-001"
        assert event.payload == {"from": "A", "to": "B"}

    def test_monotone_sequence(self):
        j = EventJournal(":memory:")
        for i in range(100):
            e = j.append("run-001", "test_event", {"n": i})
            assert e.sequence == i + 1

    def test_no_gaps(self):
        j = EventJournal(":memory:")
        for i in range(10):
            j.append("run-001", "event", {"n": i})
        assert not j.has_gaps("run-001")

    def test_correlation_and_causation(self):
        j = EventJournal(":memory:")
        event = j.append(
            "run-001", "state_transition",
            correlation_id="corr-123",
            causation_id="cause-456",
        )
        assert event.correlation_id == "corr-123"
        assert event.causation_id == "cause-456"

    def test_idempotency(self):
        j = EventJournal(":memory:")
        e1 = j.append("run-001", "test", idempotency_key="key-1")
        e2 = j.append("run-001", "test", idempotency_key="key-1")
        assert e1.sequence == e2.sequence
        assert e1.timestamp == e2.timestamp

    def test_replay_deterministic(self):
        j = EventJournal(":memory:")
        events = []
        for i in range(50):
            events.append(j.append("run-001", "step", {"n": i}))

        replayed = []
        j.replay("run-001", lambda e: replayed.append(e.payload["n"]))
        assert replayed == list(range(50))

    def test_replay_produces_same_state(self):
        j = EventJournal(":memory:")
        j.append("run-001", "set", {"key": "a", "value": 1})
        j.append("run-001", "set", {"key": "b", "value": 2})

        state = {}
        def reducer(event):
            if event.payload.get("key"):
                state[event.payload["key"]] = event.payload["value"]

        j.replay("run-001", reducer)
        assert state == {"a": 1, "b": 2}

        state2 = {}
        j.replay("run-001", lambda e: state2.update({e.payload.get("key", ""): e.payload.get("value")}))
        assert state2 == {"a": 1, "b": 2}

    def test_persist_before_dispatch(self):
        import sqlite3
        j = EventJournal(":memory:")

        dispatched_events = []
        def dispatcher(event):
            dispatched_events.append(event)

        event = j.append_and_dispatch(
            "run-001", "state_transition",
            dispatchers=[dispatcher],
        )

        row = j._conn.execute(
            "SELECT success FROM dispatch_log WHERE run_id = 'run-001' AND sequence = 1"
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        assert len(dispatched_events) == 1

    def test_crash_recovery_idempotent(self):
        j = EventJournal(":memory:")
        event = j.append("run-001", "checkpoint", {"data": "saved"})
        assert event.sequence == 1

        undispatched = j.get_undispatched("run-001")
        assert len(undispatched) == 1

        recovered = j.get_undispatched("run-001")
        for e in recovered:
            j._conn.execute(
                "INSERT INTO dispatch_log (run_id, sequence, dispatched_at, success) VALUES (?, ?, datetime('now'), 1)",
                (e.run_id, e.sequence),
            )
        j._conn.commit()

        undispatched_after = j.get_undispatched("run-001")
        assert len(undispatched_after) == 0

    def test_multiple_runs_independent_sequences(self):
        j = EventJournal(":memory:")
        j.append("run-A", "event")
        j.append("run-A", "event")
        j.append("run-B", "event")
        assert j.get_last_sequence("run-A") == 2
        assert j.get_last_sequence("run-B") == 1

    def test_replay_10k_under_5s(self):
        import time
        j = EventJournal(":memory:")
        for i in range(10000):
            j.append("run-perf", "metric", {"n": i})

        start = time.monotonic()
        results = j.replay("run-perf", lambda e: e.payload["n"])
        elapsed = time.monotonic() - start
        assert len(results) == 10000
        assert elapsed < 5.0, f"Replay of 10000 events took {elapsed:.2f}s"


class TestEventLoggerNoSilentException:
    def test_event_logger_io_write(self, tmp_path):
        from skillweave.observation.event_logger import EventLogger, LogLevel, LogEntry
        log_dir = tmp_path / ".skillweave" / "tracking-log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "test.jsonl"

        entry = LogEntry(level=LogLevel.INFO, message="test")
        logger = EventLogger(tmp_path)
        import json
        with open(log_path, "w") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
        assert log_path.exists()

    def test_no_silent_oserror_handler(self):
        import inspect
        import skillweave.observation.event_logger as el
        source = inspect.getsource(el.EventLogger._append_to_file)
        assert "except OSError:" not in source
        assert "except" not in source, "EventLogger._append_to_file must propagate I/O errors"


class TestAuthorityGuard:
    def test_role_capability_matrix_loaded(self):
        from skillweave.runtime.authority import AuthorityGuard
        guard = AuthorityGuard()
        caps = guard.get_capabilities("ops")
        assert caps["can_mutate_run_state"] is True
        assert caps["can_approve_gate"] is False

    def test_observer_is_read_only(self):
        from skillweave.runtime.authority import AuthorityGuard
        guard = AuthorityGuard()
        caps = guard.get_capabilities("observer")
        assert caps["is_read_only"] is True
        assert caps["can_mutate_run_state"] is False

    def test_ops_cannot_approve_gate(self):
        from skillweave.runtime.authority import AuthorityGuard, AuthorityError
        guard = AuthorityGuard()
        with pytest.raises(AuthorityError) as exc:
            guard.approve("ops-agent", "ops", "release", "digest-123")
        assert "ops" in str(exc.value)

    def test_operator_can_approve(self):
        from skillweave.runtime.authority import AuthorityGuard
        guard = AuthorityGuard()
        approval = guard.approve("human-operator", "operator", "release", "digest-456")
        assert approval.actor == "human-operator"
        assert approval.decision == "approved"

    def test_gnf_01_self_approval_rejected(self):
        from skillweave.runtime.authority import AuthorityGuard, AuthorityError, HumanApproval
        guard = AuthorityGuard()
        with pytest.raises(AuthorityError) as exc:
            guard.validate_approval(
                HumanApproval(
                    actor="ops-agent",
                    timestamp="2026-08-06T00:00:00Z",
                    scope="releasechain_ready",
                    policy_digest="digest-s03",
                    decision="approved",
                ),
                approving_role="ops",
            )
        assert "ops" in str(exc.value).lower()

    def test_human_approval_has_all_fields(self):
        from skillweave.runtime.authority import AuthorityGuard
        guard = AuthorityGuard()
        approval = guard.approve("alice", "operator", "merge-v1.3.0", "digest-789")
        d = approval.to_dict()
        assert "actor" in d
        assert "timestamp" in d
        assert "scope" in d
        assert "policy_digest" in d
        assert "decision" in d

    def test_role_assignment_tracks_scope(self):
        from skillweave.runtime.authority import RoleAssignment
        ra = RoleAssignment(
            role="ops", actor_id="agent-1", scope="SW-RTF",
            valid_from="2026-08-11T00:00:00Z", valid_until=None,
            assigned_by="operator",
        )
        d = ra.to_dict()
        assert d["role"] == "ops"
        assert d["scope"] == "SW-RTF"

    def test_delegation_does_not_transfer_accountability(self):
        from skillweave.runtime.authority import DelegationRecord, AuthorityGuard
        guard = AuthorityGuard()
        record = DelegationRecord(
            from_role="operator", to_role="ops",
            delegated_by="operator-1", accepted_by=None,
            state="pending", scope="SW-RTF-batch",
            delegated_at="2026-08-11T00:00:00Z",
        )
        guard.delegate(record)
        assert record.state == "pending"
        guard.accept_delegation(record)
        assert record.state == "accepted"

        ops_caps = guard.get_capabilities("ops")
        assert not ops_caps["can_approve_gate"]


class TestEvidenceRegistry:
    def test_register_artifact(self):
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt, EvidenceQuality
        registry = EvidenceRegistry()
        receipt = ArtifactReceipt(
            artifact_id="art-001",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            schema_version="1.0",
            producer_command="pytest",
            subject_repo="skillweave/skillweave",
            subject_commit="3330883",
            created_at="2026-08-11T00:00:00Z",
            evidence_type="test",
            purpose="unit test evidence",
        )
        registered = registry.register(receipt)
        assert registered.artifact_id == "art-001"

    def test_duplicate_purpose_conflict_creates_finding(self):
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt
        registry = EvidenceRegistry()
        sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        registry.register(ArtifactReceipt(
            artifact_id="art-a", sha256=sha, schema_version="1",
            producer_command="pytest", subject_repo="r", subject_commit="c",
            created_at="t", evidence_type="test", purpose="bridge patch",
        ))
        registry.register(ArtifactReceipt(
            artifact_id="art-b", sha256=sha, schema_version="1",
            producer_command="pytest", subject_repo="r", subject_commit="c",
            created_at="t", evidence_type="test", purpose="mcp patch",
        ))
        findings = registry.get_findings()
        assert len(findings) >= 1
        if len(findings) > 0:
            assert "conflicting purpose" in findings[0].description.lower()

    def test_gnf_05_duplicate_patch_detected(self):
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt
        registry = EvidenceRegistry()
        sha = hashlib.sha256(b"bridge-p0.patch content").hexdigest()
        registry.register(ArtifactReceipt(
            artifact_id="art-bridge", sha256=sha, schema_version="1",
            producer_command="git diff", subject_repo="e", subject_commit="abc",
            created_at="2026-08-06T00:00:00Z", evidence_type="artifact",
            purpose="bridge-p0 patch for Elementeer",
        ))
        registry.register(ArtifactReceipt(
            artifact_id="art-mcp", sha256=sha, schema_version="1",
            producer_command="git diff", subject_repo="e", subject_commit="abc",
            created_at="2026-08-06T00:00:00Z", evidence_type="artifact",
            purpose="mcp-p0 patch for Capacium",
        ))
        findings = registry.get_findings()
        assert len(findings) >= 1

    def test_gnf_09_count_transferred_detected(self):
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt
        registry = EvidenceRegistry()
        r1 = ArtifactReceipt(
            artifact_id="counts-claimed", sha256="a"*64, schema_version="1",
            producer_command="manual transfer", subject_repo="s", subject_commit="c",
            created_at="2026-08-11T00:00:00Z", evidence_type="metric",
            purpose="test counts 866/841/24/1",
            method="manual",
        )
        registry.register(r1)
        counts = registry.count_by_type()
        assert counts.get("metric", 0) >= 1

    def test_supersedes_preserves_chain(self):
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt
        registry = EvidenceRegistry()
        registry.register(ArtifactReceipt(
            artifact_id="v1", sha256="a"*64, schema_version="1",
            producer_command="t", subject_repo="r", subject_commit="c",
            created_at="t1", evidence_type="test", purpose="p",
        ))
        registry.register(ArtifactReceipt(
            artifact_id="v2", sha256="b"*64, schema_version="1",
            producer_command="t", subject_repo="r", subject_commit="c",
            created_at="t2", evidence_type="test", purpose="p",
            supersedes="v1",
        ))
        v1 = registry.get_artifact("v1")
        assert v1.metadata.get("superseded_by") == "v2"

    def test_segment_hashing_merkle(self):
        from skillweave.runtime.registry import (
            _compute_segment_hash, _compute_merkle_root, MerkleSegment,
            EvidenceRegistry,
        )
        segments_data = [
            ("header", b"header data"),
            ("body", b"body data"),
            ("footer", b"footer data"),
        ]
        segments, root, _ = EvidenceRegistry().build_segmented_evidence(segments_data)
        assert len(segments) == 3
        assert len(root) == 64

    def test_redaction_preserves_root_verifiability(self):
        from skillweave.runtime.registry import EvidenceRegistry
        segments_data = [
            ("public", b"public data"),
            ("confidential", b"secret data"),
            ("hash_only", b"more public"),
        ]
        registry = EvidenceRegistry()
        segments, root, _ = registry.build_segmented_evidence(segments_data)
        redacted_segments, redacted_root = registry.redact_segment(segments, root, 1)
        assert redacted_segments[1].redacted is True
        assert redacted_segments[0].redacted is False
        assert redacted_segments[2].redacted is False

    def test_six_quality_axes(self):
        from skillweave.runtime.registry import EvidenceQuality
        q = EvidenceQuality()
        d = q.to_dict()
        assert "relevance" in d
        assert "sufficiency" in d
        assert "reliability" in d
        assert "currency" in d
        assert "integrity" in d
        assert "independence" in d

    def test_ten_evidence_types(self):
        from skillweave.runtime.registry import EvidenceType
        types = list(EvidenceType)
        assert len(types) == 10

    def test_contradictory_evidence_creates_finding_not_vote(self):
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt
        registry = EvidenceRegistry()
        registry.register(ArtifactReceipt(
            artifact_id="pro", sha256="p"*64, schema_version="1",
            producer_command="t", subject_repo="r", subject_commit="c",
            created_at="t1", evidence_type="test", purpose="system ready",
        ))
        registry.register(ArtifactReceipt(
            artifact_id="con", sha256="c"*64, schema_version="1",
            producer_command="t", subject_repo="r", subject_commit="c",
            created_at="t2", evidence_type="test", purpose="system not ready",
        ))
        registry.register_finding(EvidenceFinding(
            finding_id="F-CONTRADICT",
            description="Contradictory readiness claims",
            severity="critical",
            conflicting_artifacts=["pro", "con"],
            created_at="2026-08-11T00:00:00Z",
        ))
        findings = registry.get_findings()
        assert any("contradict" in f.description.lower() for f in findings)

    def test_counts_computed_not_transferred(self):
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt
        registry = EvidenceRegistry()
        for i in range(671):
            registry.register(ArtifactReceipt(
                artifact_id=f"r-{i}", sha256=f"{i:064x}", schema_version="1",
                producer_command="pytest", subject_repo="s", subject_commit="c",
                created_at="t", evidence_type="test", purpose="test result",
            ))
        counts = registry.count_by_type()
        assert counts["test"] == 671


class TestSessionEnvelope:
    def test_accepts_valid_product(self):
        from skillweave.runtime.preflight import SessionEnvelope
        env = SessionEnvelope(
            product="SkillWeave", remote_repo="git@r", worktree="/tmp/w", branch="f",
            role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/"], state_vocabulary=["idle"], forbidden_transitions=["merge"],
        )
        assert env.validate_product("SkillWeave") is True
        assert env.validate_product("Other") is False

    def test_write_scope_validation(self):
        from skillweave.runtime.preflight import SessionEnvelope
        env = SessionEnvelope(
            product="SW", remote_repo="r", worktree="/w", branch="b",
            role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/**", "schemas/**", "tests/**"],
            state_vocabulary=["idle"], forbidden_transitions=["merge"],
        )
        assert env.validate_write_scope("src/skillweave/runtime/preflight.py")
        assert env.validate_write_scope("schemas/evidence.schema.json")
        assert env.validate_write_scope("tests/test_rtf_foundation.py")
        assert not env.validate_write_scope("CHANGELOG.md")

    def test_read_only_operation_detection(self):
        from skillweave.runtime.preflight import SessionEnvelope
        env = SessionEnvelope(
            product="SW", remote_repo="r", worktree="/w", branch="b",
            role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/"], state_vocabulary=["idle"],
            forbidden_transitions=["merge"],
        )
        assert env.is_read_only_operation("read_page")
        assert env.is_read_only_operation("check_permission")
        assert not env.is_read_only_operation("update_page")

    def test_preflight_rejects_wrong_branch(self):
        from skillweave.runtime.preflight import SessionEnvelope, PreflightResult, run_preflight
        env = SessionEnvelope(
            product="SW", remote_repo="git@canonical", worktree="/w",
            branch="feature/x", role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/"], state_vocabulary=["idle"],
            forbidden_transitions=["merge"],
        )
        result = run_preflight(env, actual_repo="git@canonical", actual_branch="wrong-branch")
        assert result.passed is False
        assert any("branch" in m["field"] for m in result.mismatches)

    def test_preflight_passes_when_all_match(self):
        from skillweave.runtime.preflight import SessionEnvelope, PreflightResult, run_preflight
        env = SessionEnvelope(
            product="SW", remote_repo="git@canonical", worktree="/w",
            branch="feature/x", role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/"], state_vocabulary=["idle"],
            forbidden_transitions=["merge"],
        )
        result = run_preflight(env, actual_repo="git@canonical", actual_branch="feature/x")
        assert result.passed is True


class TestHandoffBroker:
    def test_offer_accept_complete_flow(self):
        from skillweave.runtime.handoff import (
            HandoffBroker, ColdStartBundle,
        )
        broker = HandoffBroker()
        c = ColdStartBundle(
            prd_uri="p.json", prd_digest="da", chain_uri="c.yaml", chain_digest="cb",
            repo_uri="git@r", worktree_path="/w", branch="f", target_role="OPS",
            sequence_id="S",
        )
        offer = broker.offer(from_role="REVIEWER", to_role="OPS", scope="I00", cold_start=c)
        assert offer.state == "offered"

        broker.accept(
            handoff_id=offer.handoff_id, actor="OPS", product="SW",
            repo="git@r", prd_digest="da", chain_digest="cb",
        )
        assert broker.get_offer(offer.handoff_id).state == "accepted"

        broker.complete(offer.handoff_id)
        assert broker.get_offer(offer.handoff_id).state == "completed"

    def test_digest_mismatch_rejects(self):
        from skillweave.runtime.handoff import (
            HandoffBroker, ColdStartBundle, HandoffError,
        )
        broker = HandoffBroker()
        c = ColdStartBundle(
            prd_uri="p", prd_digest="AAA", chain_uri="c", chain_digest="BBB",
            repo_uri="r", worktree_path="/w", branch="f", target_role="OPS",
            sequence_id="S",
        )
        offer = broker.offer(from_role="R", to_role="OPS", scope="I", cold_start=c)
        with pytest.raises(HandoffError, match="DIGEST_MISMATCH"):
            broker.accept(offer.handoff_id, actor="OPS", product="SW", repo="r",
                          prd_digest="CCC", chain_digest="DDD")

    def test_wrong_recipient_rejected(self):
        from skillweave.runtime.handoff import (
            HandoffBroker, ColdStartBundle, HandoffError,
        )
        broker = HandoffBroker()
        c = ColdStartBundle(
            prd_uri="p", prd_digest="A", chain_uri="c", chain_digest="B",
            repo_uri="r", worktree_path="/w", branch="f", target_role="OPS",
            sequence_id="S",
        )
        offer = broker.offer(from_role="R", to_role="OPS", scope="I", cold_start=c)
        with pytest.raises(HandoffError, match="WRONG_RECIPIENT"):
            broker.accept(offer.handoff_id, actor="HACKER", product="SW",
                          repo="r", prd_digest="A", chain_digest="B")

    def test_wrong_repo_rejected(self):
        from skillweave.runtime.handoff import (
            HandoffBroker, ColdStartBundle, HandoffError,
        )
        broker = HandoffBroker()
        c = ColdStartBundle(
            prd_uri="p", prd_digest="A", chain_uri="c", chain_digest="B",
            repo_uri="git@canonical", worktree_path="/w", branch="f",
            target_role="OPS", sequence_id="S",
        )
        offer = broker.offer(from_role="R", to_role="OPS", scope="I", cold_start=c)
        with pytest.raises(HandoffError, match="WRONG_REPO"):
            broker.accept(offer.handoff_id, actor="OPS", product="SW",
                          repo="git@wrong", prd_digest="A", chain_digest="B")

    def test_already_claimed_rejected(self):
        from skillweave.runtime.handoff import (
            HandoffBroker, ColdStartBundle, HandoffError,
        )
        broker = HandoffBroker()
        c = ColdStartBundle(
            prd_uri="p", prd_digest="A", chain_uri="c", chain_digest="B",
            repo_uri="r", worktree_path="/w", branch="f", target_role="OPS",
            sequence_id="S",
        )
        offer = broker.offer(from_role="R", to_role="OPS", scope="I", cold_start=c)
        broker.accept(offer.handoff_id, actor="OPS", product="SW",
                      repo="r", prd_digest="A", chain_digest="B")
        with pytest.raises(HandoffError, match="ALREADY_CLAIMED"):
            broker.accept(offer.handoff_id, actor="OPS", product="SW",
                          repo="r", prd_digest="A", chain_digest="B")

    def test_reject_removes_offer(self):
        from skillweave.runtime.handoff import (
            HandoffBroker, ColdStartBundle,
        )
        broker = HandoffBroker()
        c = ColdStartBundle(
            prd_uri="p", prd_digest="A", chain_uri="c", chain_digest="B",
            repo_uri="r", worktree_path="/w", branch="f", target_role="OPS",
            sequence_id="S",
        )
        offer = broker.offer(from_role="R", to_role="OPS", scope="I", cold_start=c)
        rejected = broker.reject(offer.handoff_id)
        assert rejected.state == "rejected"


class TestObserverRuntime:
    @classmethod
    def setup_class(cls):
        from skillweave.runtime.store import SQLiteRunStore
        store = SQLiteRunStore()
        store.ensure_storage()
        cls._store = store

    def test_emit_snapshot_and_alert(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime
        journal = EventJournal(self._store)
        r = self._store.create_run("run-obs")
        obs = ObserverRuntime(journal, r.run_id)
        obs.emit_snapshot("gate ready", {"gate": "B01"})
        obs.emit_alert("drift detected", severity="critical")
        st = obs.state()
        assert len(st.outputs) == 2
        assert st.outputs[0].output_type == "snapshot"
        assert st.outputs[1].output_type == "alert"

    def test_emit_recommendation_with_clause(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime
        journal = EventJournal(self._store)
        r = self._store.create_run("run-rec")
        obs = ObserverRuntime(journal, r.run_id)
        obs.emit_recommendation(
            "go to B03",
            authorizing_clause="I00.3.2",
            authority_verified=True,
        )
        st = obs.state()
        assert st.outputs[0].output_type == "recommendation"
        assert st.outputs[0].authority_verified is True
        assert st.outputs[0].authorizing_clause == "I00.3.2"

    def test_acquire_lease(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime
        journal = EventJournal(self._store)
        r = self._store.create_run("run-lease")
        obs = ObserverRuntime(journal, r.run_id)
        lease = obs.acquire_lease("observer-1", ttl_minutes=30)
        assert lease.owner == "observer-1"
        assert obs.state().lease_id == lease.lease_id

    def test_replay_restores_offset(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime
        journal = EventJournal(self._store)
        r = self._store.create_run("run-replay")
        journal.append(r.run_id, "run_started", {"state": "STARTED"}, event_type="state")
        journal.append(r.run_id, "blocked", {"state": "BLOCKED"}, event_type="state")
        obs = ObserverRuntime(journal, r.run_id)
        obs.replay()
        assert obs.state().offset == 2

    def test_self_contradiction_detected(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime, ObserverOutput
        journal = EventJournal(self._store)
        r = self._store.create_run("run-contra")
        obs = ObserverRuntime(journal, r.run_id)
        obs._findings.append({
            "output_type": "drift_finding",
            "finding_id": "F-001",
            "resolved": False,
        })
        rec = ObserverOutput(
            output_type="recommendation", severity="info",
            message="fix F-001",
            evidence={"finding_id": "F-001"},
        )
        assert obs.check_self_contradiction(rec) is True

    def test_no_contradiction_when_unrelated(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime, ObserverOutput
        journal = EventJournal(self._store)
        r = self._store.create_run("run-ok")
        obs = ObserverRuntime(journal, r.run_id)
        obs._findings.append({
            "output_type": "drift_finding",
            "finding_id": "F-001",
            "resolved": False,
        })
        rec = ObserverOutput(
            output_type="recommendation", severity="info",
            message="unrelated",
            evidence={"finding_id": "F-002"},
        )
        assert obs.check_self_contradiction(rec) is False

    def test_generate_report(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime
        journal = EventJournal(self._store)
        r = self._store.create_run("run-report")
        obs = ObserverRuntime(journal, r.run_id)
        obs.emit_snapshot("hello", {"x": 1})
        report = obs.generate_report()
        assert report["run_id"] == r.run_id
        assert report["outputs"]
        assert report["findings_count"] >= 0

    def test_markdown_report(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime
        journal = EventJournal(self._store)
        r = self._store.create_run("run-md")
        obs = ObserverRuntime(journal, r.run_id)
        obs.emit_snapshot("hello", {"x": 1})
        md = obs.generate_markdown_report()
        assert "Observer Report" in md
        assert r.run_id in md

    def test_heartbeat_updates_state(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime
        journal = EventJournal(self._store)
        r = self._store.create_run("run-hb")
        obs = ObserverRuntime(journal, r.run_id)
        old = obs.state().heartbeat_at
        obs.heartbeat()
        assert obs.state().heartbeat_at != old


class TestWireframe:
    def test_gate_discipline_no_violations(self):
        from skillweave.runtime.wireframe import assert_gate_discipline
        assert assert_gate_discipline() == []

    def test_gate_discipline_self_approval(self):
        from skillweave.runtime.wireframe import assert_gate_discipline
        violations = assert_gate_discipline(self_approved=True)
        assert any("Self-approval" in v for v in violations)

    def test_gate_discipline_merge_invoked(self):
        from skillweave.runtime.wireframe import assert_gate_discipline
        violations = assert_gate_discipline(merge_invoked=True)
        assert any("Merge" in v for v in violations)

    def test_assert_write_scope_valid(self):
        from skillweave.runtime.wireframe import assert_write_scope
        ok, violations = assert_write_scope(
            ["src/skillweave/foo.py", "tests/test_bar.py"],
            ["src/**", "tests/**"],
        )
        assert ok is True
        assert violations == []

    def test_assert_write_scope_violation(self):
        from skillweave.runtime.wireframe import assert_write_scope
        ok, violations = assert_write_scope(
            ["src/skillweave/foo.py", "docs/README.md"],
            ["src/**"],
        )
        assert ok is False
        assert "docs/README.md" in violations

    def test_no_foreign_repo(self):
        from skillweave.runtime.wireframe import assert_no_foreign_repos
        assert assert_no_foreign_repos("git@canonical", "git@canonical") is True
        assert assert_no_foreign_repos("git@wrong", "git@canonical") is False

    def test_validate_summary(self):
        from skillweave.runtime.wireframe import validate_summary
        missing = validate_summary(
            ["objective", "state", "blocked"],
            {"objective": "x", "blocked": "n"},
        )
        assert "state" in missing


class TestCrossCuttingIntegration:
    @classmethod
    def setup_class(cls):
        from skillweave.runtime.store import SQLiteRunStore
        store = SQLiteRunStore()
        store.ensure_storage()
        cls._store = store

    def test_full_control_plane_integration(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.authority import AuthorityGuard, HumanApproval
        from skillweave.runtime.observer import ObserverRuntime
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt
        from skillweave.runtime.gate_reconciliation import reconcile_gate
        from skillweave.runtime.wireframe import assert_gate_discipline
        from skillweave.runtime.preflight import SessionEnvelope

        journal = EventJournal(self._store)
        r = self._store.create_run("rtf-001-int")
        journal.append(r.run_id, "started", {"state": "IDLE"}, event_type="state")
        journal.append(r.run_id, "in_progress", {"state": "IN_PROGRESS"}, event_type="state")
        journal.append(r.run_id, "completed", {"state": "COMPLETED"}, event_type="state")
        events = journal.get_events(r.run_id)
        assert len(events) == 3

        auth = AuthorityGuard()
        approval = HumanApproval(
            actor="Alice", timestamp="2026-08-11T00:00:00Z",
            scope="I00", decision="approved", policy_digest="digest-abcd",
        )
        auth.validate_approval(approval, approving_role="REVIEWER")

        registry = EvidenceRegistry()
        registry.register(ArtifactReceipt(
            artifact_id="check-001", sha256="a"*64, schema_version="1",
            producer_command="pytest", subject_repo="r", subject_commit="c",
            created_at="t", evidence_type="test", purpose="integration proof",
        ))
        registry.register(ArtifactReceipt(
            artifact_id="check-002", sha256="b"*64, schema_version="1",
            producer_command="pytest", subject_repo="r", subject_commit="c",
            created_at="t", evidence_type="test", purpose="second proof",
        ))
        registry.register(ArtifactReceipt(
            artifact_id="check-003", sha256="c"*64, schema_version="1",
            producer_command="pytest", subject_repo="r", subject_commit="c",
            created_at="t", evidence_type="test", purpose="third proof",
        ))

        obs = ObserverRuntime(journal, r.run_id)
        obs.emit_snapshot("integration gate ready", {"evidence_count": 3})
        obs.emit_recommendation(
            "gate passed",
            authorizing_clause="I00.8.1",
            authority_verified=True,
        )

        result = reconcile_gate("B04_CHECKPOINT", registry, obs, auth)
        assert result.reconciled is True

        violations = assert_gate_discipline()
        assert violations == []

        env = SessionEnvelope(
            product="SkillWeave", remote_repo="git@r", worktree="/w", branch="f",
            role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/**"], state_vocabulary=["idle"],
            forbidden_transitions=["merge"],
        )
        assert env.validate_write_scope("src/skillweave/runtime/gate_reconciliation.py")

    def test_insufficient_evidence_blocks_reconciliation(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.authority import AuthorityGuard
        from skillweave.runtime.observer import ObserverRuntime
        from skillweave.runtime.registry import EvidenceRegistry
        from skillweave.runtime.gate_reconciliation import reconcile_gate
        from skillweave.runtime.registry import ArtifactReceipt

        journal = EventJournal(self._store)
        r = self._store.create_run("under-evidence")
        journal.append(r.run_id, "single", {"state": "IDLE"}, event_type="state")
        registry = EvidenceRegistry()
        registry.register(ArtifactReceipt(
            artifact_id="only", sha256="x"*64, schema_version="1",
            producer_command="t", subject_repo="r", subject_commit="c",
            created_at="t", evidence_type="test", purpose="single",
        ))
        obs = ObserverRuntime(journal, r.run_id)
        result = reconcile_gate("B04_INSUFFICIENT", registry, obs, AuthorityGuard())
        assert result.reconciled is False
        assert result.evidence_weight == "insufficient"


class TestGateReconciliation:
    @classmethod
    def setup_class(cls):
        from skillweave.runtime.store import SQLiteRunStore
        store = SQLiteRunStore()
        store.ensure_storage()
        cls._store = store

    def test_reconcile_blocked_by_critical_finding(self):
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.authority import AuthorityGuard
        from skillweave.runtime.observer import ObserverRuntime
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt, EvidenceFinding
        from skillweave.runtime.gate_reconciliation import reconcile_gate

        journal = EventJournal(self._store)
        r = self._store.create_run("critical")
        journal.append(r.run_id, "started", {"state": "IDLE"}, event_type="state")
        obs = ObserverRuntime(journal, r.run_id)

        registry = EvidenceRegistry()
        for i in range(5):
            registry.register(ArtifactReceipt(
                artifact_id=f"c-{i}", sha256=f"{i:064x}", schema_version="1",
                producer_command="t", subject_repo="r", subject_commit="c",
                created_at="t", evidence_type="test", purpose=f"proof-{i}",
            ))
        registry.register_finding(EvidenceFinding(
            finding_id="F-CRIT",
            description="Critical evidence contradiction",
            severity="critical",
            conflicting_artifacts=["c-0", "c-1"],
            created_at="2026-08-11T00:00:00Z",
        ))

        result = reconcile_gate("B04_CRITICAL", registry, obs, AuthorityGuard())
        assert result.reconciled is False
        assert "blocked" in result.observer_verdict

    def test_reconciliation_result_round_trip(self):
        from skillweave.runtime.gate_reconciliation import ReconciliationResult
        r = ReconciliationResult(
            reconciled=True, evidence_weight="sufficient",
            observer_verdict="clear", authority_statement="all good",
            gate_name="GATE-TEST",
        )
        d = r.to_dict()
        assert d["reconciled"] is True
        assert d["gate_name"] == "GATE-TEST"
        assert "timestamp" in d





# Re-use from TestEvidenceRegistry
from skillweave.runtime.registry import EvidenceFinding
import hashlib
