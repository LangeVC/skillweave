from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import hashlib
import json


class EvidenceType(str, Enum):
    RECORD = "record"
    ARTIFACT = "artifact"
    OBSERVATION = "observation"
    TEST = "test"
    INTERVIEW = "interview"
    DECISION = "decision"
    RUNTIME_TRACE = "runtime_trace"
    EXTERNAL_ATTESTATION = "external_attestation"
    METRIC = "metric"
    REVIEW = "review"


class EvidenceQualityAxis(str, Enum):
    RELEVANCE = "relevance"
    SUFFICIENCY = "sufficiency"
    RELIABILITY = "reliability"
    CURRENCY = "currency"
    INTEGRITY = "integrity"
    INDEPENDENCE = "independence"


@dataclass
class EvidenceQuality:
    relevance: str = "medium"
    sufficiency: str = "medium"
    reliability: str = "medium"
    currency: str = "medium"
    integrity: str = "medium"
    independence: str = "medium"

    def to_dict(self):
        return {
            "relevance": self.relevance,
            "sufficiency": self.sufficiency,
            "reliability": self.reliability,
            "currency": self.currency,
            "integrity": self.integrity,
            "independence": self.independence,
        }


@dataclass
class ArtifactReceipt:
    artifact_id: str
    sha256: str
    schema_version: str
    producer_command: str
    subject_repo: str
    subject_commit: str
    created_at: str
    evidence_type: str
    purpose: str
    method: str = ""
    system_source: str = ""
    sensitivity: str = "internal"
    retention: str = "permanent"
    transformation_history: list[str] = field(default_factory=list)
    quality: EvidenceQuality = field(default_factory=EvidenceQuality)
    supersedes: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "schema_version": self.schema_version,
            "producer_command": self.producer_command,
            "subject_repo": self.subject_repo,
            "subject_commit": self.subject_commit,
            "created_at": self.created_at,
            "evidence_type": self.evidence_type,
            "purpose": self.purpose,
            "method": self.method,
            "system_source": self.system_source,
            "sensitivity": self.sensitivity,
            "retention": self.retention,
            "transformation_history": self.transformation_history,
            "quality": self.quality.to_dict(),
            "supersedes": self.supersedes,
            "metadata": self.metadata,
        }


@dataclass
class EvidenceFinding:
    finding_id: str
    description: str
    severity: str
    conflicting_artifacts: list[str]
    created_at: str
    resolved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "finding_id": self.finding_id,
            "description": self.description,
            "severity": self.severity,
            "conflicting_artifacts": self.conflicting_artifacts,
            "created_at": self.created_at,
            "resolved": self.resolved,
            "metadata": self.metadata,
        }


@dataclass
class MerkleSegment:
    index: int
    label: str
    content_hash: str
    redacted: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "index": self.index,
            "label": self.label,
            "content_hash": self.content_hash,
            "redacted": self.redacted,
            "metadata": self.metadata,
        }


def _compute_segment_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ArtifactIntegrityError(Exception):
    """Raised when a raw artifact's stored bytes do not match its digest.

    ``resolve`` fails closed: a missing or mutated artifact never yields bytes
    and is never silently treated as the addressed content."""
    pass


class RawArtifactStore:
    """Content-addressed raw byte store with immutable-resolution semantics.

    Bytes are stored under their own sha256 digest. ``resolve`` returns the
    bytes only if the stored content still hashes to the requested digest;
    otherwise it raises :class:`ArtifactIntegrityError`. A receipt therefore
    *resolves* to its raw bytes, and mutation or absence closes the resolution
    path rather than returning wrong data.
    """

    def __init__(self):
        self._blobs: dict[str, bytes] = {}

    def put(self, data: bytes) -> str:
        digest = _compute_segment_hash(data)
        self._blobs[digest] = bytes(data)
        return digest

    def resolve(self, sha256: str) -> bytes:
        if sha256 not in self._blobs:
            raise ArtifactIntegrityError(f"artifact '{sha256[:12]}' is missing")
        data = self._blobs[sha256]
        if _compute_segment_hash(data) != sha256:
            raise ArtifactIntegrityError(
                f"artifact '{sha256[:12]}' failed digest verification (mutated)"
            )
        return data

    def resolve_receipt(self, receipt: ArtifactReceipt) -> bytes:
        return self.resolve(receipt.sha256)

    def mock_mutate(self, sha256: str, replacement: bytes) -> None:
        """Test seam: corrupt a stored blob without changing its key."""
        self._blobs[sha256] = bytes(replacement)

    def delete(self, sha256: str) -> None:
        """Test seam: remove a stored blob, simulating loss."""
        self._blobs.pop(sha256, None)



def _compute_merkle_root(segments: list[MerkleSegment]) -> str:
    if not segments:
        return hashlib.sha256(b"").hexdigest()
    hashes = [bytes.fromhex(s.content_hash) for s in segments]
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])
        next_level = []
        for i in range(0, len(hashes), 2):
            combined = hashes[i] + hashes[i + 1]
            next_level.append(hashlib.sha256(combined).digest())
        hashes = next_level
    return hashes[0].hex()


class EvidenceRegistry:
    def __init__(self):
        self._artifacts: dict[str, ArtifactReceipt] = {}
        self._findings: list[EvidenceFinding] = []

    def register(self, receipt: ArtifactReceipt) -> ArtifactReceipt:
        same_hash = [
            a for a in self._artifacts.values()
            if a.sha256 == receipt.sha256 and a.artifact_id != receipt.artifact_id
        ]
        for existing in same_hash:
            if existing.purpose != receipt.purpose:
                finding = EvidenceFinding(
                    finding_id=f"F-{len(self._findings) + 1:04d}",
                    description=f"Duplicate hash {receipt.sha256[:12]} with conflicting purpose: "
                               f"'{existing.purpose}' vs '{receipt.purpose}'",
                    severity="high",
                    conflicting_artifacts=[existing.artifact_id, receipt.artifact_id],
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                self._findings.append(finding)

        if receipt.supersedes:
            superseded = self._artifacts.get(receipt.supersedes)
            if superseded:
                superseded.metadata["superseded_by"] = receipt.artifact_id

        self._artifacts[receipt.artifact_id] = receipt
        return receipt

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactReceipt]:
        return self._artifacts.get(artifact_id)

    def list_artifacts(
        self,
        evidence_type: Optional[str] = None,
        since: Optional[str] = None,
    ) -> list[ArtifactReceipt]:
        results = list(self._artifacts.values())
        if evidence_type:
            results = [a for a in results if a.evidence_type == evidence_type]
        if since:
            results = [a for a in results if a.created_at >= since]
        return results

    def count_by_type(self) -> dict[str, int]:
        counts = {}
        for a in self._artifacts.values():
            counts[a.evidence_type] = counts.get(a.evidence_type, 0) + 1
        return counts

    def get_findings(self, resolved: Optional[bool] = None) -> list[EvidenceFinding]:
        if resolved is None:
            return list(self._findings)
        return [f for f in self._findings if f.resolved == resolved]

    def register_finding(self, finding: EvidenceFinding) -> EvidenceFinding:
        existing = [f for f in self._findings if f.finding_id == finding.finding_id]
        if existing:
            has_lower = any(
                f.severity == "critical" and finding.severity != "critical"
                for f in existing
            )
            if has_lower:
                return finding
        self._findings.append(finding)
        return finding

    def build_segmented_evidence(
        self,
        segments_data: list[tuple[str, bytes]],
        artifact_id_prefix: str = "evd",
    ) -> tuple[list[MerkleSegment], str, ArtifactReceipt]:
        segments = []
        for i, (label, data) in enumerate(segments_data):
            seg = MerkleSegment(
                index=i,
                label=label,
                content_hash=_compute_segment_hash(data),
            )
            segments.append(seg)

        root = _compute_merkle_root(segments)
        return segments, root, None

    def redact_segment(
        self,
        segments: list[MerkleSegment],
        merkle_root: str,
        index: int,
    ) -> tuple[list[MerkleSegment], str]:
        new_segments = list(segments)
        if 0 <= index < len(new_segments):
            new_segments[index] = MerkleSegment(
                index=index,
                label=new_segments[index].label,
                content_hash=new_segments[index].content_hash,
                redacted=True,
            )

        leaf_hashes = []
        for s in new_segments:
            if s.redacted:
                leaf_hashes.append(b"\x00" * 32)
            else:
                leaf_hashes.append(bytes.fromhex(s.content_hash))

        while len(leaf_hashes) > 1:
            if len(leaf_hashes) % 2 == 1:
                leaf_hashes.append(leaf_hashes[-1])
            next_level = []
            for i in range(0, len(leaf_hashes), 2):
                combined = leaf_hashes[i] + leaf_hashes[i + 1]
                next_level.append(hashlib.sha256(combined).digest())
            leaf_hashes = next_level

        redacted_root = leaf_hashes[0].hex() if leaf_hashes else ""
        return new_segments, redacted_root
