"""Context manager coordinating token monitoring, limit gates, and checkpoints (SW-CONTEXT-001).

Acceptance Criteria:
1. Implement context check-pointing in `src/skillweave/core/context/`.
2. Introduce profiles for token limits (e.g. 120k for no new task, 150k for checkpoint, 170k for stop).
3. Ensure the profiles are configurable.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

from .checkpoint import (
    CheckpointError,
    CheckpointIntegrityError,
    CheckpointNotFoundError,
    CheckpointStore,
    ContextBlock,
    ContextCheckpoint,
    InMemoryCheckpointStore,
)
from .config import resolve_profile
from .limits import (
    ContextLimitAssessment,
    ProfileConfigurationError,
    TokenLimitProfile,
    TokenThresholdStatus,
)


class ContextLimitError(Exception):
    """Base exception for context limit violations."""


class ContextStopLimitExceeded(ContextLimitError):
    """Raised when token count exceeds the hard stop ceiling."""

    def __init__(self, message: str, assessment: Optional[ContextLimitAssessment] = None):
        super().__init__(message)
        self.assessment = assessment


class TaskAdmissionRejected(ContextLimitError):
    """Raised when a new task or subtask is rejected due to no-new-task limit."""

    def __init__(self, message: str, assessment: Optional[ContextLimitAssessment] = None):
        super().__init__(message)
        self.assessment = assessment


def estimate_tokens(text: str) -> int:
    """Heuristic token estimation: ~4 chars per token plus word boundary weight."""
    if not text:
        return 0
    # Words + non-whitespace chunks heuristic
    words = len(re.findall(r"\S+", text))
    chars = len(text)
    # Average between char-based and word-based estimation
    char_estimate = int(chars / 3.8)
    word_estimate = int(words * 1.3)
    return max(1, int((char_estimate + word_estimate) / 2))


class ContextManager:
    """Coordinates context blocks, token limits, admission gates, and checkpoints.

    Enforces three primary thresholds from its active TokenLimitProfile:
    1. ``no_new_task_limit`` (e.g. 120k): reject new tasks/subtasks while allowing current unit to finish.
    2. ``checkpoint_limit`` (e.g. 150k): mandate taking a context checkpoint snapshot.
    3. ``stop_limit`` (e.g. 170k): hard stop halting execution.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        profile: Optional[Union[str, TokenLimitProfile, Mapping[str, Any]]] = None,
        store: Optional[CheckpointStore] = None,
        sequence_id: Optional[str] = None,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.session_id: str = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self.sequence_id: Optional[str] = sequence_id
        self.profile: TokenLimitProfile = resolve_profile(profile)
        self.store: CheckpointStore = store or InMemoryCheckpointStore()
        self._blocks: List[ContextBlock] = []
        self._state: Dict[str, Any] = dict(initial_state or {})
        self._last_checkpoint_id: Optional[str] = None
        self._listeners: List[Callable[[ContextLimitAssessment], None]] = []

    def set_profile(self, profile: Union[str, TokenLimitProfile, Mapping[str, Any]]) -> None:
        """Switch or configure the active TokenLimitProfile."""
        self.profile = resolve_profile(profile)

    def add_listener(self, callback: Callable[[ContextLimitAssessment], None]) -> None:
        """Register a callback for assessment events."""
        self._listeners.append(callback)

    def add_block(
        self,
        content: str,
        role: str = "context",
        tokens: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextBlock:
        """Append a context block and check stop limit."""
        token_count = tokens if tokens is not None else estimate_tokens(content)
        block = ContextBlock(
            content=content,
            role=role,
            tokens=token_count,
            metadata=metadata or {},
        )
        self._blocks.append(block)

        # Notify listeners
        assessment = self.evaluate()
        for listener in self._listeners:
            try:
                listener(assessment)
            except Exception:
                pass

        return block

    def add_system_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> ContextBlock:
        """Convenience method to add a system message."""
        return self.add_block(content=content, role="system", metadata=metadata)

    def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> ContextBlock:
        """Convenience method to add a user message."""
        return self.add_block(content=content, role="user", metadata=metadata)

    def add_assistant_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> ContextBlock:
        """Convenience method to add an assistant message."""
        return self.add_block(content=content, role="assistant", metadata=metadata)

    def add_tool_output(self, content: str, tool_name: str, metadata: Optional[Dict[str, Any]] = None) -> ContextBlock:
        """Convenience method to add a tool execution result block."""
        meta = dict(metadata or {})
        meta["tool_name"] = tool_name
        return self.add_block(content=content, role="tool", metadata=meta)

    def get_blocks(self, role: Optional[str] = None) -> List[ContextBlock]:
        """Return list of context blocks, optionally filtered by role."""
        if role is None:
            return list(self._blocks)
        return [b for b in self._blocks if b.role == role]

    def set_state_value(self, key: str, value: Any) -> None:
        """Set a value in the context runtime state snapshot."""
        self._state[key] = value

    def get_state_value(self, key: str, default: Any = None) -> Any:
        """Get a value from the context runtime state snapshot."""
        return self._state.get(key, default)

    def update_state(self, values: Mapping[str, Any]) -> None:
        """Update multiple keys in runtime state snapshot."""
        self._state.update(values)

    def get_state(self) -> Dict[str, Any]:
        """Return a copy of the current state snapshot."""
        return dict(self._state)

    @property
    def total_tokens(self) -> int:
        """Calculate aggregate tokens across all blocks."""
        return sum(b.tokens for b in self._blocks)

    def evaluate(self) -> ContextLimitAssessment:
        """Evaluate current token consumption against active profile."""
        return self.profile.evaluate(self.total_tokens)

    def can_accept_task(self, estimated_task_tokens: int = 0) -> bool:
        """Check if a new task can be accepted under the no_new_task_limit threshold."""
        return self.profile.can_accept_task(self.total_tokens, estimated_task_tokens)

    def admit_task(self, task_id: str, estimated_task_tokens: int = 0) -> ContextLimitAssessment:
        """Admit a new task or raise TaskAdmissionRejected if limit exceeded."""
        assessment = self.evaluate()
        projected = self.total_tokens + max(0, estimated_task_tokens)

        if projected >= self.profile.no_new_task_limit:
            msg = (
                f"Cannot admit task '{task_id}': total tokens ({self.total_tokens:,}) + projected "
                f"({estimated_task_tokens:,}) = {projected:,}, which meets or exceeds the "
                f"no-new-task limit ({self.profile.no_new_task_limit:,}) in profile '{self.profile.name}'."
            )
            raise TaskAdmissionRejected(msg, assessment=assessment)

        return assessment

    def should_checkpoint(self) -> bool:
        """Return True if token consumption requires a checkpoint."""
        return self.profile.should_checkpoint(self.total_tokens)

    def should_stop(self) -> bool:
        """Return True if token consumption reached or exceeded stop limit."""
        return self.profile.should_stop(self.total_tokens)

    def ensure_within_stop_limit(self) -> None:
        """Verify token consumption is below stop limit, raising ContextStopLimitExceeded if reached."""
        assessment = self.evaluate()
        if assessment.should_stop:
            raise ContextStopLimitExceeded(
                f"Context token stop limit exceeded ({assessment.current_tokens:,} >= {self.profile.stop_limit:,}) "
                f"under profile '{self.profile.name}'. Halting execution.",
                assessment=assessment,
            )

    def checkpoint(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> ContextCheckpoint:
        """Create and store an immutable context checkpoint snapshot.

        If ``force`` is False, will still create the checkpoint, but links to parent checkpoint.
        """
        assessment = self.evaluate()
        cp = ContextCheckpoint(
            session_id=self.session_id,
            sequence_id=self.sequence_id,
            total_tokens=self.total_tokens,
            profile_name=self.profile.name,
            status=assessment.status,
            blocks=[ContextBlock.from_dict(b.to_dict()) for b in self._blocks],
            state=dict(self._state),
            parent_checkpoint_id=self._last_checkpoint_id,
            metadata=dict(metadata or {}),
        )

        self.store.save(cp)
        self._last_checkpoint_id = cp.checkpoint_id
        return cp

    def restore(self, checkpoint_id: str) -> ContextCheckpoint:
        """Restore context state and blocks from a stored checkpoint."""
        cp = self.store.get(checkpoint_id)
        if cp is None:
            raise CheckpointNotFoundError(f"Checkpoint '{checkpoint_id}' not found.")

        if not cp.verify_integrity():
            raise CheckpointIntegrityError(f"Checkpoint '{checkpoint_id}' failed integrity check.")

        self.session_id = cp.session_id
        self.sequence_id = cp.sequence_id
        self.profile = resolve_profile(cp.profile_name)
        self._blocks = [ContextBlock.from_dict(b.to_dict()) for b in cp.blocks]
        self._state = dict(cp.state)
        self._last_checkpoint_id = cp.checkpoint_id
        return cp

    def compact(
        self,
        target_tokens: Optional[int] = None,
        keep_system: bool = True,
        preserve_recent: int = 4,
    ) -> int:
        """Compact context blocks by pruning older non-system blocks until target tokens is met.

        Returns number of removed blocks.
        """
        target = target_tokens or self.profile.no_new_task_limit
        if self.total_tokens <= target:
            return 0

        # Preserve system blocks and the last `preserve_recent` blocks
        removable_indices: List[int] = []
        for i, b in enumerate(self._blocks):
            if keep_system and b.role == "system":
                continue
            if i >= len(self._blocks) - preserve_recent:
                continue
            removable_indices.append(i)

        removed_count = 0
        # Remove from earliest removable
        for idx in sorted(removable_indices, reverse=True):
            if self.total_tokens <= target:
                break
            self._blocks.pop(idx)
            removed_count += 1

        return removed_count

    def clear(self) -> None:
        """Clear all in-memory context blocks and state."""
        self._blocks.clear()
        self._state.clear()
        self._last_checkpoint_id = None
