"""
Tests fuer R1- und R2-geforderte Aenderungen: PreflightInterceptor,
AuthorityGuard-Verdrahtung, Checkpoint/Resume, Context, Coverage.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


class TestPreflightInterceptor:
    def test_interceptor_blocks_on_mismatched_repo(self):
        from skillweave.runtime.preflight import (
            SessionEnvelope, PreflightInterceptor, PreflightError,
        )
        env = SessionEnvelope(
            product="SW", remote_repo="git@canonical", worktree="/w",
            branch="feature/x", role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/"], state_vocabulary=["idle"],
            forbidden_transitions=["merge"],
        )
        interceptor = PreflightInterceptor(
            env, repo="git@canonical", branch="feature/x", product="SW",
        )
        assert interceptor.passed is True

        interceptor2 = PreflightInterceptor(
            env, repo="git@wrong", branch="feature/x", product="SW",
        )
        assert interceptor2.passed is False

        def mock_mutating_call(*args, **kwargs):
            return "should not run"

        with pytest.raises(PreflightError, match="INTERCEPTOR_BLOCKED"):
            interceptor2.guard(mock_mutating_call)

    def test_interceptor_passes_call_on_clean_preflight(self):
        from skillweave.runtime.preflight import (
            SessionEnvelope, PreflightInterceptor,
        )
        env = SessionEnvelope(
            product="SW", remote_repo="git@canonical", worktree="/w",
            branch="feature/x", role="OPS", prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/"], state_vocabulary=["idle"],
            forbidden_transitions=["merge"],
        )
        interceptor = PreflightInterceptor(
            env, repo="git@canonical", branch="feature/x", product="SW",
        )
        def fn(x, y):
            return x + y
        result = interceptor.guard(fn, 3, 4)
        assert result == 7


class TestAuthorityGuardWired:
    def test_observer_blocked_from_transition(self):
        from skillweave.runtime.store import SQLiteRunStore, RunRecord, RunStateModel
        from skillweave.runtime.authority import AuthorityGuard, AuthorityError

        store = SQLiteRunStore()
        r = RunRecord(
            run_id="obs-block", root_run_id="obs-block", parent_run_id=None,
            state=RunStateModel.SANDBOX_PREFLIGHT.value, version=1,
            created_at="t", updated_at="t", ended_at=None, role="observer",
        )
        store.save_run(r)

        guard = AuthorityGuard()
        store.set_authority_guard(guard)

        with pytest.raises(AuthorityError, match="lacks mutate_run_state"):
            store.transition(
                "obs-block", RunStateModel.IN_PROGRESS.value,
                expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
                expected_version=1, role="observer",
            )

    def test_ops_can_transition_with_role(self):
        from skillweave.runtime.store import SQLiteRunStore, RunRecord, RunStateModel

        store = SQLiteRunStore()
        r = RunRecord(
            run_id="ops-ok", root_run_id="ops-ok", parent_run_id=None,
            state=RunStateModel.SANDBOX_PREFLIGHT.value, version=1,
            created_at="t", updated_at="t", ended_at=None, role="ops",
        )
        store.save_run(r)
        result = store.transition(
            "ops-ok", RunStateModel.IN_PROGRESS.value,
            expected_state=RunStateModel.SANDBOX_PREFLIGHT.value,
            expected_version=1, role="ops",
        )
        assert result.state == RunStateModel.IN_PROGRESS.value


class TestCheckpointResume:
    def test_environment_fingerprint_capture(self):
        from skillweave.runtime.checkpoint import capture_environment
        fp = capture_environment(branch="feature/x", commit_sha="abc123")
        assert fp.hostname
        assert fp.os_name
        assert fp.python_version
        assert fp.branch == "feature/x"
        assert fp.commit_sha == "abc123"
        assert len(fp.digest()) == 64

    def test_fingerprint_validation(self):
        from skillweave.runtime.checkpoint import EnvironmentFingerprint
        a = EnvironmentFingerprint(
            hostname="h1", os_name="darwin", python_version="3.12",
            branch="f", commit_sha="a",
        )
        b = EnvironmentFingerprint(
            hostname="h1", os_name="darwin", python_version="3.12",
            branch="f", commit_sha="a",
        )
        c = EnvironmentFingerprint(
            hostname="h2", os_name="darwin", python_version="3.12",
            branch="f", commit_sha="a",
        )
        assert a.validate_against(b) is True
        assert a.validate_against(c) is False

    def test_fingerprint_diff(self):
        from skillweave.runtime.checkpoint import EnvironmentFingerprint
        a = EnvironmentFingerprint(
            hostname="h1", os_name="darwin", python_version="3.12",
            branch="f", commit_sha="a",
        )
        b = EnvironmentFingerprint(
            hostname="h2", os_name="linux", python_version="3.12",
            branch="f", commit_sha="a",
        )
        diff = a.diff(b)
        assert "hostname" in diff
        assert "os_name" in diff

    def test_create_checkpoint(self):
        from skillweave.runtime.checkpoint import (
            EnvironmentFingerprint, create_checkpoint,
        )
        env = EnvironmentFingerprint(
            hostname="h", os_name="d", python_version="3",
            branch="f", commit_sha="a",
        )
        cp = create_checkpoint("run-1", "run-1", 42, env)
        assert cp.journal_offset == 42
        assert cp.run_id == "run-1"
        assert cp.root_run_id == "run-1"

    def test_resume_revalidation_required(self):
        from skillweave.runtime.checkpoint import (
            EnvironmentFingerprint, create_checkpoint, validate_resume,
            ResumeRevalidationRequired,
        )
        env1 = EnvironmentFingerprint(
            hostname="h1", os_name="d", python_version="3",
            branch="f", commit_sha="a",
        )
        cp = create_checkpoint("run-1", "run-1", 0, env1)

        env2 = EnvironmentFingerprint(
            hostname="h2", os_name="d", python_version="3",
            branch="f", commit_sha="a",
        )
        with pytest.raises(ResumeRevalidationRequired):
            validate_resume(cp, env2)

    def test_resume_passes_unchanged_environment(self):
        from skillweave.runtime.checkpoint import (
            EnvironmentFingerprint, create_checkpoint, validate_resume,
        )
        env = EnvironmentFingerprint(
            hostname="h", os_name="d", python_version="3",
            branch="f", commit_sha="a",
        )
        cp = create_checkpoint("run-1", "run-1", 0, env)
        valid = validate_resume(cp, env)
        assert valid is True


class TestVerifiedContext:
    def test_digest_bound_reference_valid(self):
        import hashlib
        from skillweave.runtime.context import VerifiedContext
        vc = VerifiedContext()
        content = "digest-bound artefact data"
        digest = hashlib.sha256(content.encode()).hexdigest()
        block = vc.load_block("artefact-registry", content, digest)
        assert block.is_authoritative() is True

    def test_digest_mismatch_rejected(self):
        import hashlib
        from skillweave.runtime.context import VerifiedContext, ContextRejectedError
        vc = VerifiedContext()
        content = "actual content"
        wrong_digest = hashlib.sha256(b"different content").hexdigest()
        with pytest.raises(ContextRejectedError, match="Digest mismatch"):
            vc.load_block("source", content, wrong_digest)

    def test_prose_summary_rejected_as_binding(self):
        import hashlib
        from skillweave.runtime.context import VerifiedContext, ContextRejectedError
        vc = VerifiedContext()
        content = "This is a summary of what happened."
        digest = hashlib.sha256(content.encode()).hexdigest()
        with pytest.raises(ContextRejectedError, match="Prose summaries"):
            vc.load_block("subagent-summary-report", content, digest)

    def test_prose_allowed_when_explicit(self):
        import hashlib
        from skillweave.runtime.context import VerifiedContext
        vc = VerifiedContext()
        content = "summary narrative"
        digest = hashlib.sha256(content.encode()).hexdigest()
        block = vc.load_block(
            "subagent-summary", content, digest, allow_prose=True,
        )
        assert block.is_authoritative() is True

    def test_context_digest_aggregate(self):
        import hashlib
        from skillweave.runtime.context import VerifiedContext
        vc = VerifiedContext()
        c1 = "block one"
        c2 = "block two"
        vc.load_block("s1", c1, hashlib.sha256(c1.encode()).hexdigest())
        vc.load_block("s2", c2, hashlib.sha256(c2.encode()).hexdigest())
        expected = hashlib.sha256((c1 + c2).encode()).hexdigest()
        assert vc.get_digest() == expected

    def test_clear_removes_all_blocks(self):
        import hashlib
        from skillweave.runtime.context import VerifiedContext
        vc = VerifiedContext()
        c = "data"
        vc.load_block("s", c, hashlib.sha256(c.encode()).hexdigest())
        assert len(vc.get_blocks()) == 1
        vc.clear()
        assert len(vc.get_blocks()) == 0


class TestVocabularyAmendment:
    def test_stopped_before_b06_is_valid_state(self):
        from skillweave.runtime.store import RunStateModel
        assert RunStateModel.STOPPED_BEFORE_B06.value == "STOPPED_BEFORE_B06"

    def test_stopped_before_b06_in_legal_transitions(self):
        from skillweave.runtime.store import RunStateModel
        allowed = RunStateModel.legal_transitions(
            RunStateModel.STOPPED_BEFORE_B06
        )
        assert RunStateModel.IN_PROGRESS in allowed

    def test_coverage_status_externally_satisfied(self):
        from skillweave.runtime.schema.vocabulary import RUN_STATE_COVERAGE_STATUSES
        assert "externally_satisfied" in RUN_STATE_COVERAGE_STATUSES
        assert "not_applicable" in RUN_STATE_COVERAGE_STATUSES

    def test_validate_rejects_drift_across_all_five(self):
        from skillweave.runtime.schema.vocabulary import validate_status, StatusRejectedError
        drift = [
            "ACTIVE", "AWAITING_S01_REVIEW", "LIFECYCLE_REVIEW_COMPLETE",
            "AWAITING_S05_REVIEW_REQUIRED", "EVIDENCE_APPROVED",
        ]
        rejected = 0
        for v in drift:
            try:
                validate_status(v)
            except StatusRejectedError:
                rejected += 1
        assert rejected == 5
