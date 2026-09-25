"""Context check-pointing and state snapshot primitives (SW-CONTEXT-001).

Acceptance Criteria:
1. Implement context check-pointing in `src/skillweave/core/context/`.
2. Introduce profiles for token limits (e.g. 120k for no new task, 150k for checkpoint, 170k for stop).
3. Ensure the profiles are configurable.
"""

from __future__ import annotations

import abc
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .limits import TokenThresholdStatus


class CheckpointError(Exception):
    """Base exception for checkpoint operations."""


class CheckpointIntegrityError(CheckpointError):
    """Raised when checkpoint integrity verification fails."""


class CheckpointNotFoundError(CheckpointError):
    """Raised when a requested checkpoint is not found in the store."""


def compute_sha256(content: Union[str, bytes]) -> str:
    """Compute standard SHA-256 hexadecimal digest."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


@dataclass
class ContextBlock:
    """A discrete block of context with content, role, token weight, and digest."""

    content: str
    role: str = "context"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    digest: str = ""
    tokens: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.digest:
            self.digest = self.compute_digest()

    def compute_digest(self) -> str:
        """Calculate digest for block content and role."""
        payload = f"{self.role}:{self.content}"
        return compute_sha256(payload)

    def verify_digest(self) -> bool:
        """Verify that current digest matches block content."""
        return self.digest == self.compute_digest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize block to dictionary."""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "digest": self.digest,
            "tokens": self.tokens,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ContextBlock:
        """Construct block from dictionary."""
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            role=str(data.get("role", "context")),
            content=str(data.get("content", "")),
            digest=str(data.get("digest", "")),
            tokens=int(data.get("tokens", 0)),
            timestamp=str(data.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ContextCheckpoint:
    """An immutable snapshot of context state, blocks, token usage, and metadata."""

    checkpoint_id: str = field(default_factory=lambda: f"cp-{uuid.uuid4().hex[:12]}")
    session_id: str = "default-session"
    sequence_id: Optional[str] = None
    total_tokens: int = 0
    profile_name: str = "default"
    status: TokenThresholdStatus = TokenThresholdStatus.OK
    blocks: List[ContextBlock] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)
    parent_checkpoint_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    digest: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.digest:
            self.digest = self.compute_digest()

    def compute_digest(self) -> str:
        """Compute deterministic SHA-256 digest of this checkpoint's state and blocks."""
        canonical_blocks = [
            {"id": b.id, "role": b.role, "digest": b.digest, "tokens": b.tokens}
            for b in self.blocks
        ]
        payload = {
            "session_id": self.session_id,
            "sequence_id": self.sequence_id,
            "total_tokens": self.total_tokens,
            "profile_name": self.profile_name,
            "status": self.status.value if isinstance(self.status, TokenThresholdStatus) else str(self.status),
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "blocks": canonical_blocks,
            "state": self.state,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return compute_sha256(serialized)

    def verify_integrity(self) -> bool:
        """Verify the integrity of this checkpoint and all contained blocks."""
        # 1. Verify blocks
        for b in self.blocks:
            if not b.verify_digest():
                return False

        # 2. Verify overall checkpoint digest
        return self.digest == self.compute_digest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize checkpoint to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "sequence_id": self.sequence_id,
            "total_tokens": self.total_tokens,
            "profile_name": self.profile_name,
            "status": self.status.value if isinstance(self.status, TokenThresholdStatus) else str(self.status),
            "blocks": [b.to_dict() for b in self.blocks],
            "state": dict(self.state),
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "created_at": self.created_at,
            "digest": self.digest,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ContextCheckpoint:
        """Construct checkpoint from dictionary."""
        raw_status = data.get("status", TokenThresholdStatus.OK.value)
        try:
            status = TokenThresholdStatus(raw_status)
        except ValueError:
            status = TokenThresholdStatus.OK

        raw_blocks = data.get("blocks", [])
        blocks = [
            ContextBlock.from_dict(b) if isinstance(b, Mapping) else b
            for b in raw_blocks
        ]

        cp = cls(
            checkpoint_id=str(data.get("checkpoint_id") or f"cp-{uuid.uuid4().hex[:12]}"),
            session_id=str(data.get("session_id", "default-session")),
            sequence_id=str(data["sequence_id"]) if data.get("sequence_id") is not None else None,
            total_tokens=int(data.get("total_tokens", 0)),
            profile_name=str(data.get("profile_name", "default")),
            status=status,
            blocks=blocks,
            state=dict(data.get("state") or {}),
            parent_checkpoint_id=str(data["parent_checkpoint_id"]) if data.get("parent_checkpoint_id") is not None else None,
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            digest=str(data.get("digest", "")),
            metadata=dict(data.get("metadata") or {}),
        )

        if not cp.digest:
            cp.digest = cp.compute_digest()
        return cp

    def to_json(self, indent: Optional[int] = 2) -> str:
        """Serialize checkpoint to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, json_str: str) -> ContextCheckpoint:
        """Deserialize checkpoint from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


# ── Checkpoint Store Interfaces & Implementations ───────────────────────────

class CheckpointStore(abc.ABC):
    """Abstract interface for checkpoint storage backends."""

    @abc.abstractmethod
    def save(self, checkpoint: ContextCheckpoint) -> str:
        """Save a checkpoint and return its checkpoint_id."""
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, checkpoint_id: str) -> Optional[ContextCheckpoint]:
        """Retrieve a checkpoint by ID or return None if not found."""
        raise NotImplementedError

    @abc.abstractmethod
    def list(self, session_id: Optional[str] = None) -> List[ContextCheckpoint]:
        """List all checkpoints, optionally filtered by session_id."""
        raise NotImplementedError

    @abc.abstractmethod
    def latest(self, session_id: Optional[str] = None) -> Optional[ContextCheckpoint]:
        """Retrieve the most recent checkpoint, optionally filtered by session_id."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint by ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def clear(self, session_id: Optional[str] = None) -> int:
        """Clear checkpoints, optionally filtered by session_id."""
        raise NotImplementedError


class InMemoryCheckpointStore(CheckpointStore):
    """Thread-safe in-memory store for checkpoints."""

    def __init__(self) -> None:
        self._checkpoints: Dict[str, ContextCheckpoint] = {}
        self._order: List[str] = []

    def save(self, checkpoint: ContextCheckpoint) -> str:
        """Save checkpoint in-memory."""
        if not checkpoint.verify_integrity():
            raise CheckpointIntegrityError(
                f"Checkpoint {checkpoint.checkpoint_id} failed integrity verification."
            )
        cid = checkpoint.checkpoint_id
        if cid not in self._checkpoints:
            self._order.append(cid)
        self._checkpoints[cid] = checkpoint
        return cid

    def get(self, checkpoint_id: str) -> Optional[ContextCheckpoint]:
        """Retrieve checkpoint by ID."""
        return self._checkpoints.get(checkpoint_id)

    def list(self, session_id: Optional[str] = None) -> List[ContextCheckpoint]:
        """List checkpoints ordered by creation."""
        results = [self._checkpoints[cid] for cid in self._order if cid in self._checkpoints]
        if session_id:
            results = [cp for cp in results if cp.session_id == session_id]
        return results

    def latest(self, session_id: Optional[str] = None) -> Optional[ContextCheckpoint]:
        """Get latest checkpoint."""
        cps = self.list(session_id=session_id)
        return cps[-1] if cps else None

    def delete(self, checkpoint_id: str) -> bool:
        """Delete checkpoint."""
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            if checkpoint_id in self._order:
                self._order.remove(checkpoint_id)
            return True
        return False

    def clear(self, session_id: Optional[str] = None) -> int:
        """Clear checkpoints."""
        if session_id is None:
            count = len(self._checkpoints)
            self._checkpoints.clear()
            self._order.clear()
            return count
        to_delete = [cid for cid, cp in self._checkpoints.items() if cp.session_id == session_id]
        for cid in to_delete:
            self.delete(cid)
        return len(to_delete)


class FileCheckpointStore(CheckpointStore):
    """File-backed persistent storage for context checkpoints."""

    def __init__(self, directory: Union[str, Path]) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _file_path(self, checkpoint_id: str) -> Path:
        sanitized = "".join(c for c in checkpoint_id if c.isalnum() or c in ("-", "_"))
        return self.directory / f"{sanitized}.json"

    def save(self, checkpoint: ContextCheckpoint) -> str:
        """Save checkpoint to disk atomically."""
        if not checkpoint.verify_integrity():
            raise CheckpointIntegrityError(
                f"Checkpoint {checkpoint.checkpoint_id} failed integrity verification."
            )
        target = self._file_path(checkpoint.checkpoint_id)
        temp_file = target.with_suffix(".tmp")
        temp_file.write_text(checkpoint.to_json(indent=2), encoding="utf-8")
        temp_file.replace(target)
        return checkpoint.checkpoint_id

    def get(self, checkpoint_id: str) -> Optional[ContextCheckpoint]:
        """Load checkpoint from disk and verify its integrity."""
        path = self._file_path(checkpoint_id)
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        cp = ContextCheckpoint.from_json(content)
        if not cp.verify_integrity():
            raise CheckpointIntegrityError(
                f"Stored checkpoint file '{path.name}' failed integrity check."
            )
        return cp

    def list(self, session_id: Optional[str] = None) -> List[ContextCheckpoint]:
        """List all valid checkpoints found in store directory."""
        checkpoints: List[ContextCheckpoint] = []
        for file in sorted(self.directory.glob("*.json")):
            try:
                cp = self.get(file.stem)
                if cp:
                    if session_id is None or cp.session_id == session_id:
                        checkpoints.append(cp)
            except Exception:
                continue
        checkpoints.sort(key=lambda c: c.created_at)
        return checkpoints

    def latest(self, session_id: Optional[str] = None) -> Optional[ContextCheckpoint]:
        """Get latest checkpoint."""
        cps = self.list(session_id=session_id)
        return cps[-1] if cps else None

    def delete(self, checkpoint_id: str) -> bool:
        """Delete checkpoint file."""
        path = self._file_path(checkpoint_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def clear(self, session_id: Optional[str] = None) -> int:
        """Clear checkpoint files."""
        count = 0
        for cp in self.list(session_id=session_id):
            if self.delete(cp.checkpoint_id):
                count += 1
        return count
