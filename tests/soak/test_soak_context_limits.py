"""Context token limits, admission gates, and checkpoint tests (SW-SOAK-001 / SW-CONTEXT-001).

Validates token threshold profiles (120k no_new_task, 150k checkpoint, 170k stop),
task admission gating, mandatory checkpointing, and hard stop enforcement.
"""

import sys
import tempfile
from pathlib import Path
import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.core.context import (
    ContextBlock,
    ContextCheckpoint,
    ContextManager,
    ContextStopLimitExceeded,
    FileCheckpointStore,
    InMemoryCheckpointStore,
    TaskAdmissionRejected,
    TokenLimitProfile,
    TokenThresholdStatus,
    get_profile,
    list_profiles,
)


class TestSoakContextLimits:
    """Context limit enforcement tests under soak conditions."""

    def test_standard_profile_threshold_progression(self):
        """Test continuous token accumulation through OK -> NO_NEW_TASK -> CHECKPOINT -> STOP states."""
        mgr = ContextManager(session_id="soak-ctx-1", profile="standard")
        profile = mgr.profile

        # 1. OK State (< 120k)
        ass_ok = profile.evaluate(50_000)
        assert ass_ok.status == TokenThresholdStatus.OK
        assert ass_ok.can_accept_new_task is True
        assert ass_ok.checkpoint_required is False
        assert ass_ok.should_stop is False
        assert profile.can_accept_task(50_000, 10_000) is True

        # 2. NO_NEW_TASK State (>= 120k, < 150k)
        ass_no_task = profile.evaluate(125_000)
        assert ass_no_task.status == TokenThresholdStatus.NO_NEW_TASK
        assert ass_no_task.can_accept_new_task is False
        assert ass_no_task.checkpoint_required is False
        assert ass_no_task.should_stop is False
        assert profile.can_accept_task(125_000) is False

        # 3. CHECKPOINT_REQUIRED State (>= 150k, < 170k)
        ass_cp = profile.evaluate(155_000)
        assert ass_cp.status == TokenThresholdStatus.CHECKPOINT_REQUIRED
        assert ass_cp.can_accept_new_task is False
        assert ass_cp.checkpoint_required is True
        assert ass_cp.should_stop is False
        assert profile.should_checkpoint(155_000) is True

        # 4. STOP State (>= 170k)
        ass_stop = profile.evaluate(175_000)
        assert ass_stop.status == TokenThresholdStatus.STOP
        assert ass_stop.can_accept_new_task is False
        assert ass_stop.checkpoint_required is True
        assert ass_stop.should_stop is True
        assert profile.should_stop(175_000) is True

    def test_context_manager_admission_and_checkpoint_lifecycle(self):
        """Simulate a long session accumulating tokens, enforcing admission rejection and taking checkpoints."""
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(tmp)
            # Use 'fast' profile for rapid threshold crossings (8k / 12k / 15k)
            mgr = ContextManager(session_id="soak-fast-session", profile="fast", store=store)

            # Accumulate context blocks
            for i in range(5):
                mgr.add_block(
                    content=f"Subtask {i} output content " * 100,
                    role="context",
                    metadata={"source": f"worker-{i}"},
                )

            # Checkpoint capture
            cp1 = mgr.checkpoint(metadata={"description": "Checkpoint after initial batch"})
            assert cp1.checkpoint_id is not None
            assert cp1.total_tokens > 0

            # Verify checkpoint is retrievable
            restored = store.get(cp1.checkpoint_id)
            assert restored.checkpoint_id == cp1.checkpoint_id
            assert restored.total_tokens == cp1.total_tokens
            assert restored.digest == cp1.digest

            # Trigger admission rejection when approaching limit
            assert not mgr.can_accept_task(estimated_task_tokens=50_000)

            # Attempting admit_task should raise TaskAdmissionRejected
            with pytest.raises(TaskAdmissionRejected):
                mgr.admit_task(task_id="overflow-task", estimated_task_tokens=50_000)

    def test_multi_profile_reconfiguration_during_soak(self):
        """Verify dynamic reconfiguration between conservative, strict, standard, and extended profiles."""
        mgr = ContextManager(session_id="soak-reconfig-session")

        profiles_to_test = ["conservative", "strict", "fast", "extended", "standard"]
        for p_name in profiles_to_test:
            mgr.set_profile(p_name)
            assert mgr.profile.name == p_name
            assessment = mgr.evaluate()
            assert assessment.profile_name == p_name
            assert assessment.status in (
                TokenThresholdStatus.OK,
                TokenThresholdStatus.NO_NEW_TASK,
                TokenThresholdStatus.CHECKPOINT_REQUIRED,
                TokenThresholdStatus.STOP,
            )
