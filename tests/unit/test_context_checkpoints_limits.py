"""Unit and integration tests for Context Checkpointing and Token Limits (SW-CONTEXT-001).

Validates Acceptance Criteria:
1. Implement context check-pointing in `src/skillweave/core/context/`.
2. Introduce profiles for token limits (e.g. 120k for no new task, 150k for checkpoint, 170k for stop).
3. Ensure the profiles are configurable.
"""

import os
import tempfile
from pathlib import Path
import pytest

from skillweave.core.context import (
    BUILTIN_PROFILES,
    CONSERVATIVE_PROFILE,
    DEFAULT_PROFILE,
    EXTENDED_PROFILE,
    FAST_PROFILE,
    STANDARD_PROFILE,
    STRICT_PROFILE,
    CheckpointIntegrityError,
    CheckpointNotFoundError,
    ContextBlock,
    ContextCheckpoint,
    ContextLimitAssessment,
    ContextLimitError,
    ContextManager,
    ContextStopLimitExceeded,
    FileCheckpointStore,
    InMemoryCheckpointStore,
    ProfileConfigurationError,
    TaskAdmissionRejected,
    TokenLimitProfile,
    TokenLimitProfileRegistry,
    TokenThresholdStatus,
    estimate_tokens,
    get_profile,
    get_profile_registry,
    list_profiles,
    load_profile_from_dict,
    load_profile_from_env,
    load_profile_from_yaml,
    load_profiles_from_yaml_file,
    register_profile,
    resolve_profile,
)


class TestTokenLimitProfile:
    """Tests for TokenLimitProfile definitions and threshold validation."""

    def test_default_profile_thresholds(self):
        profile = TokenLimitProfile()
        assert profile.name == "default"
        assert profile.no_new_task_limit == 120_000
        assert profile.checkpoint_limit == 150_000
        assert profile.stop_limit == 170_000
        assert profile.max_context_limit == 200_000

    def test_threshold_ordering_validation(self):
        # no_new_task > checkpoint should fail
        with pytest.raises(ProfileConfigurationError):
            TokenLimitProfile(name="bad", no_new_task_limit=160_000, checkpoint_limit=150_000, stop_limit=170_000)

        # checkpoint > stop should fail
        with pytest.raises(ProfileConfigurationError):
            TokenLimitProfile(name="bad", no_new_task_limit=120_000, checkpoint_limit=180_000, stop_limit=170_000)

        # stop > max_context should fail
        with pytest.raises(ProfileConfigurationError):
            TokenLimitProfile(
                name="bad",
                no_new_task_limit=120_000,
                checkpoint_limit=150_000,
                stop_limit=170_000,
                max_context_limit=160_000,
            )

        # zero or negative limits should fail
        with pytest.raises(ProfileConfigurationError):
            TokenLimitProfile(name="bad", no_new_task_limit=0)

    def test_evaluate_status_transitions(self):
        profile = TokenLimitProfile(
            name="test-profile",
            no_new_task_limit=120_000,
            checkpoint_limit=150_000,
            stop_limit=170_000,
            max_context_limit=200_000,
        )

        # Below 120k -> OK
        res_ok = profile.evaluate(100_000)
        assert res_ok.status == TokenThresholdStatus.OK
        assert res_ok.can_accept_new_task is True
        assert res_ok.checkpoint_required is False
        assert res_ok.should_stop is False
        assert res_ok.remaining_to_no_new_task == 20_000
        assert res_ok.remaining_to_checkpoint == 50_000
        assert res_ok.remaining_to_stop == 70_000
        assert res_ok.utilization == 0.5

        # At 120k to 149,999 -> NO_NEW_TASK
        res_no_new = profile.evaluate(130_000)
        assert res_no_new.status == TokenThresholdStatus.NO_NEW_TASK
        assert res_no_new.can_accept_new_task is False
        assert res_no_new.checkpoint_required is False
        assert res_no_new.should_stop is False
        assert res_no_new.remaining_to_no_new_task == 0
        assert res_no_new.remaining_to_checkpoint == 20_000

        # At 150k to 169,999 -> CHECKPOINT_REQUIRED
        res_cp = profile.evaluate(155_000)
        assert res_cp.status == TokenThresholdStatus.CHECKPOINT_REQUIRED
        assert res_cp.can_accept_new_task is False
        assert res_cp.checkpoint_required is True
        assert res_cp.should_stop is False
        assert res_cp.remaining_to_checkpoint == 0
        assert res_cp.remaining_to_stop == 15_000

        # At or above 170k -> STOP
        res_stop = profile.evaluate(175_000)
        assert res_stop.status == TokenThresholdStatus.STOP
        assert res_stop.can_accept_new_task is False
        assert res_stop.checkpoint_required is True
        assert res_stop.should_stop is True
        assert res_stop.remaining_to_stop == 0

    def test_profile_to_dict_and_from_dict(self):
        original = TokenLimitProfile(
            name="custom",
            no_new_task_limit=50_000,
            checkpoint_limit=70_000,
            stop_limit=85_000,
            max_context_limit=100_000,
            compact_limit=60_000,
            description="Custom profile",
            metadata={"tier": "custom"},
        )
        d = original.to_dict()
        assert d["name"] == "custom"
        assert d["no_new_task_limit"] == 50_000
        assert d["checkpoint_limit"] == 70_000
        assert d["stop_limit"] == 85_000

        restored = TokenLimitProfile.from_dict(d)
        assert restored.name == original.name
        assert restored.no_new_task_limit == original.no_new_task_limit
        assert restored.checkpoint_limit == original.checkpoint_limit
        assert restored.stop_limit == original.stop_limit
        assert restored.compact_limit == original.compact_limit
        assert restored.metadata == original.metadata


class TestProfileRegistryAndLoading:
    """Tests for profile registry, file loaders, and environment resolution."""

    def test_builtin_presets_exist(self):
        assert "default" in BUILTIN_PROFILES
        assert "standard" in BUILTIN_PROFILES
        assert "conservative" in BUILTIN_PROFILES
        assert "extended" in BUILTIN_PROFILES
        assert "strict" in BUILTIN_PROFILES
        assert "fast" in BUILTIN_PROFILES

        assert CONSERVATIVE_PROFILE.no_new_task_limit == 60_000
        assert EXTENDED_PROFILE.stop_limit == 750_000
        assert FAST_PROFILE.no_new_task_limit == 8_000

    def test_registry_operations(self):
        registry = TokenLimitProfileRegistry()
        custom = TokenLimitProfile(
            name="my-custom",
            no_new_task_limit=10_000,
            checkpoint_limit=12_000,
            stop_limit=14_000,
        )
        registry.register(custom)
        assert registry.has_profile("my-custom")
        assert registry.get("my-custom").no_new_task_limit == 10_000

        # Duplicate without override
        with pytest.raises(ProfileConfigurationError):
            registry.register(custom, override=False)

    def test_load_profile_from_yaml_string(self):
        yaml_content = """
        name: test-yaml
        no_new_task_limit: 90000
        checkpoint_limit: 110000
        stop_limit: 130000
        description: YAML test profile
        """
        profile = load_profile_from_yaml(yaml_content)
        assert profile.name == "test-yaml"
        assert profile.no_new_task_limit == 90_000
        assert profile.checkpoint_limit == 110_000
        assert profile.stop_limit == 130_000

    def test_load_profiles_from_yaml_file(self):
        profiles_file = Path(__file__).resolve().parent.parent.parent / "src" / "skillweave" / "assets" / "profiles" / "context.yaml"

        loaded = load_profiles_from_yaml_file(profiles_file)
        assert "default" in loaded
        assert "conservative" in loaded
        assert "extended" in loaded
        assert loaded["default"].no_new_task_limit == 120_000
        assert loaded["default"].checkpoint_limit == 150_000
        assert loaded["default"].stop_limit == 170_000

    def test_load_profile_from_environment(self, monkeypatch):
        monkeypatch.setenv("SW_CONTEXT_PROFILE", "conservative")
        monkeypatch.setenv("SW_TOKEN_STOP_LIMIT", "98000")

        profile = load_profile_from_env()
        assert profile.no_new_task_limit == 60_000
        assert profile.checkpoint_limit == 80_000
        assert profile.stop_limit == 98_000

    def test_resolve_profile_helper(self):
        # Resolve by instance
        p = TokenLimitProfile(name="direct", no_new_task_limit=1000, checkpoint_limit=2000, stop_limit=3000)
        assert resolve_profile(p) == p

        # Resolve by name
        assert resolve_profile("standard").no_new_task_limit == 120_000
        assert resolve_profile("conservative").no_new_task_limit == 60_000

        # Resolve by dict
        dict_prof = resolve_profile({"name": "from-dict", "no_new_task_limit": 5000, "checkpoint_limit": 6000, "stop_limit": 7000})
        assert dict_prof.name == "from-dict"
        assert dict_prof.stop_limit == 7000


class TestContextCheckpointAndStore:
    """Tests for ContextBlock, ContextCheckpoint, and storage implementations."""

    def test_context_block_digest_and_verification(self):
        block = ContextBlock(role="user", content="Hello world", tokens=4)
        assert block.digest != ""
        assert block.verify_digest() is True

        # Tampering with content invalidates digest
        block.content = "Tampered content"
        assert block.verify_digest() is False

    def test_checkpoint_integrity_verification(self):
        block1 = ContextBlock(role="system", content="You are an assistant.", tokens=5)
        block2 = ContextBlock(role="user", content="Execute plan.", tokens=3)
        cp = ContextCheckpoint(
            session_id="s1",
            total_tokens=8,
            profile_name="default",
            status=TokenThresholdStatus.OK,
            blocks=[block1, block2],
            state={"step": 1, "status": "in_progress"},
        )

        assert cp.verify_integrity() is True
        assert cp.digest != ""

        # Tampering with block invalidates checkpoint
        block1.content = "Tampered instructions"
        assert cp.verify_integrity() is False

    def test_checkpoint_serialization_roundtrip(self):
        block = ContextBlock(role="user", content="Sample step input", tokens=10)
        cp = ContextCheckpoint(
            session_id="session-42",
            sequence_id="seq-1",
            total_tokens=10,
            profile_name="conservative",
            status=TokenThresholdStatus.OK,
            blocks=[block],
            state={"var": "val"},
            parent_checkpoint_id="cp-prev",
        )

        json_str = cp.to_json()
        restored = ContextCheckpoint.from_json(json_str)

        assert restored.checkpoint_id == cp.checkpoint_id
        assert restored.session_id == cp.session_id
        assert restored.sequence_id == cp.sequence_id
        assert restored.total_tokens == 10
        assert restored.parent_checkpoint_id == "cp-prev"
        assert restored.verify_integrity() is True

    def test_in_memory_checkpoint_store(self):
        store = InMemoryCheckpointStore()
        cp1 = ContextCheckpoint(session_id="s1", total_tokens=100)
        cp2 = ContextCheckpoint(session_id="s1", total_tokens=200, parent_checkpoint_id=cp1.checkpoint_id)
        cp3 = ContextCheckpoint(session_id="s2", total_tokens=50)

        store.save(cp1)
        store.save(cp2)
        store.save(cp3)

        assert store.get(cp1.checkpoint_id) == cp1
        assert len(store.list()) == 3
        assert len(store.list(session_id="s1")) == 2
        assert store.latest(session_id="s1").checkpoint_id == cp2.checkpoint_id

        assert store.delete(cp1.checkpoint_id) is True
        assert store.get(cp1.checkpoint_id) is None
        assert len(store.list(session_id="s1")) == 1

        store.clear(session_id="s1")
        assert len(store.list(session_id="s1")) == 0
        assert len(store.list(session_id="s2")) == 1

    def test_file_checkpoint_store(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FileCheckpointStore(tmp_dir)
            block = ContextBlock(role="assistant", content="Plan created", tokens=12)
            cp = ContextCheckpoint(session_id="file-sess", total_tokens=12, blocks=[block])

            cid = store.save(cp)
            assert cid == cp.checkpoint_id

            # Verify file exists on disk
            target_path = Path(tmp_dir) / f"{cid}.json"
            assert target_path.exists()

            loaded = store.get(cid)
            assert loaded is not None
            assert loaded.checkpoint_id == cid
            assert loaded.verify_integrity() is True
            assert loaded.blocks[0].content == "Plan created"

            # Check list and latest
            assert len(store.list()) == 1
            assert store.latest().checkpoint_id == cid

            # Delete
            assert store.delete(cid) is True
            assert not target_path.exists()
            assert store.get(cid) is None


class TestContextManager:
    """Tests for ContextManager coordinating context, token limits, and checkpoints."""

    def test_token_estimation_helper(self):
        tokens = estimate_tokens("This is a simple prompt containing several words.")
        assert tokens > 0
        assert estimate_tokens("") == 0

    def test_adding_messages_and_state(self):
        manager = ContextManager(session_id="sess-1", profile="default")
        manager.add_system_message("System instruction.")
        manager.add_user_message("User request.")
        manager.add_assistant_message("Assistant response.")
        manager.add_tool_output("result data", tool_name="run_command")

        assert len(manager.get_blocks()) == 4
        assert len(manager.get_blocks(role="system")) == 1
        assert len(manager.get_blocks(role="tool")) == 1
        assert manager.total_tokens > 0

        manager.set_state_value("phase", "implementation")
        assert manager.get_state_value("phase") == "implementation"

    def test_admission_control_under_token_limits(self):
        # Use fast profile: 8k no new task, 12k checkpoint, 15k stop
        manager = ContextManager(profile="fast")

        # Below 8k: can accept task
        manager.add_block(content="A" * 4000, tokens=2000)
        assert manager.can_accept_task(estimated_task_tokens=1000) is True
        assessment = manager.admit_task("task-1", estimated_task_tokens=1000)
        assert assessment.status == TokenThresholdStatus.OK

        # Exceed 8k threshold -> TaskAdmissionRejected
        manager.add_block(content="B" * 25000, tokens=6500)
        # Total tokens = 8500 >= 8000
        assert manager.can_accept_task() is False
        with pytest.raises(TaskAdmissionRejected) as excinfo:
            manager.admit_task("task-2")
        assert "no-new-task limit" in str(excinfo.value)

    def test_checkpoint_trigger_and_restoration(self):
        store = InMemoryCheckpointStore()
        manager = ContextManager(session_id="sess-cp", profile="fast", store=store)

        manager.add_system_message("System prompt.")
        manager.set_state_value("counter", 1)

        # Create checkpoint
        cp1 = manager.checkpoint(metadata={"milestone": "init"})
        assert cp1.checkpoint_id in [c.checkpoint_id for c in store.list()]
        assert cp1.state["counter"] == 1

        # Mutate manager context
        manager.add_user_message("Next step.")
        manager.set_state_value("counter", 2)
        assert len(manager.get_blocks()) == 2
        assert manager.get_state_value("counter") == 2

        # Restore checkpoint 1
        restored = manager.restore(cp1.checkpoint_id)
        assert restored.checkpoint_id == cp1.checkpoint_id
        assert len(manager.get_blocks()) == 1
        assert manager.get_state_value("counter") == 1

    def test_stop_limit_enforcement(self):
        # Fast profile stop limit = 15,000
        manager = ContextManager(profile="fast")
        manager.add_block(content="Large block", tokens=16_000)

        assert manager.should_stop() is True
        assessment = manager.evaluate()
        assert assessment.status == TokenThresholdStatus.STOP
        assert assessment.should_stop is True

        with pytest.raises(ContextStopLimitExceeded):
            manager.ensure_within_stop_limit()

    def test_compaction_prunes_older_blocks_preserving_system(self):
        manager = ContextManager(profile="fast")
        manager.add_system_message("Important system prompt.", metadata={"important": True})
        for i in range(10):
            manager.add_user_message(f"Message {i}", metadata={"idx": i})

        initial_tokens = manager.total_tokens
        initial_blocks = len(manager.get_blocks())
        assert initial_blocks == 11

        # Compact targeting small token count
        removed = manager.compact(target_tokens=initial_tokens // 2, preserve_recent=2)
        assert removed > 0
        assert len(manager.get_blocks()) < initial_blocks
        # Ensure system block was preserved
        assert manager.get_blocks(role="system")[0].content == "Important system prompt."
