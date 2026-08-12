"""
RTF-011: Verifiable Context Retrieval.

Binding artefacts are loaded only through resolvable, digest-bound references.
Every context block carries source, digest, and load time.
A prose summary cannot set a binding fact.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


class ContextRejectedError(ValueError):
    def __init__(self, reason: str, block: Optional[dict] = None):
        self.reason = reason
        self.block = block
        super().__init__(f"Context rejected: {reason}")


@dataclass
class ContextBlock:
    source: str
    content: str
    digest: str
    loaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    content_type: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_authoritative(self) -> bool:
        import hashlib
        computed = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        return computed == self.digest

    def is_prose_only(self) -> bool:
        prose_markers = ["summary", "narrative", "recap", "overview"]
        source_lower = self.source.lower()
        return any(m in source_lower for m in prose_markers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "digest": self.digest,
            "loaded_at": self.loaded_at,
            "content_type": self.content_type,
            "authoritative": self.is_authoritative(),
            "is_prose_only": self.is_prose_only(),
            "metadata": self.metadata,
        }


class VerifiedContext:
    def __init__(self):
        self._blocks: list[ContextBlock] = []

    def load_block(
        self,
        source: str,
        content: str,
        expected_digest: str,
        content_type: str = "text",
        allow_prose: bool = False,
    ) -> ContextBlock:
        block = ContextBlock(
            source=source,
            content=content,
            digest=expected_digest,
            content_type=content_type,
        )
        if not block.is_authoritative():
            raise ContextRejectedError(
                "Digest mismatch — content does not match expected digest",
                block.to_dict(),
            )
        if not allow_prose and block.is_prose_only():
            raise ContextRejectedError(
                "Prose summaries cannot set binding facts — use digest-bound references",
                block.to_dict(),
            )
        self._blocks.append(block)
        return block

    def get_blocks(self) -> list[ContextBlock]:
        return list(self._blocks)

    def get_digest(self) -> str:
        import hashlib
        all_content = "".join(b.content for b in self._blocks)
        return hashlib.sha256(all_content.encode("utf-8")).hexdigest()

    def clear(self):
        self._blocks.clear()
