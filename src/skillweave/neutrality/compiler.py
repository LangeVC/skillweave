from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum

from .evidence import (
    EvidenceVerificationResult,
    EvidenceVerificationStatus,
    ParserError,
)


class CapaciumKind(str, Enum):
    WORKFLOW = "workflow"
    BUNDLE = "bundle"


@dataclass(frozen=True)
class ProcessDefinition:
    definition_id: str
    version: str
    name: str
    capabilities: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)

    def is_single(self) -> bool:
        return len(self.capabilities) <= 1


@dataclass(frozen=True)
class ProcessPack:
    pack_id: str
    version: str
    definitions: tuple[ProcessDefinition, ...]
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.definitions:
            raise ValueError("ProcessPack must contain at least one ProcessDefinition")

    def is_single(self) -> bool:
        return len(self.definitions) == 1

    def compile_kind(self) -> CapaciumKind:
        if self.is_single():
            return CapaciumKind.WORKFLOW
        return CapaciumKind.BUNDLE


@dataclass(frozen=True)
class CompiledDefinition:
    capacium_kind: CapaciumKind
    qualified_interface: dict
    owner_payload: dict
    compatibility_metadata: dict

    def __post_init__(self) -> None:
        if isinstance(self.capacium_kind, str):
            object.__setattr__(self, "capacium_kind", CapaciumKind(self.capacium_kind))
        if self.capacium_kind not in (CapaciumKind.WORKFLOW, CapaciumKind.BUNDLE):
            raise ValueError(
                f"Invalid CapaciumKind: {self.capacium_kind!r}. "
                f"Only 'workflow' and 'bundle' are allowed. 'process' is forbidden."
            )

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> CompiledDefinition:
        data = json.loads(raw)
        return cls(
            capacium_kind=CapaciumKind(data["capacium_kind"]),
            qualified_interface=data["qualified_interface"],
            owner_payload=data["owner_payload"],
            compatibility_metadata=data["compatibility_metadata"],
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


def compile_process(process: ProcessPack) -> CompiledDefinition:
    kind = process.compile_kind()
    qualified_interface = {
        "interface_id": f"skillweave.xyz/process/{process.pack_id}",
        "version": process.version,
        "kind": kind.value,
        "definition_count": len(process.definitions),
    }
    owner_payload = {
        "pack_id": process.pack_id,
        "pack_version": process.version,
        "definition_ids": [d.definition_id for d in process.definitions],
        "skillweave_profile_version": "1.0.0",
    }
    compatibility_metadata = {
        "sw_compiler_version": "1.0.0",
        "source_sha256": hashlib.sha256(
            json.dumps(asdict(process), sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }
    return CompiledDefinition(
        capacium_kind=kind,
        qualified_interface=qualified_interface,
        owner_payload=owner_payload,
        compatibility_metadata=compatibility_metadata,
    )


_VALUE_ERROR = frozenset({
    EvidenceVerificationStatus.MALFORMED,
    EvidenceVerificationStatus.UNSUPPORTED_ALGORITHM,
    EvidenceVerificationStatus.INVALID,
})


@dataclass(frozen=True)
class ParserFailureClassification:
    is_parser_error: bool
    status: EvidenceVerificationStatus | None
    detail: str

    @classmethod
    def classify_exception(cls, exc: Exception) -> ParserFailureClassification:
        if isinstance(exc, ParserError):
            return cls(
                is_parser_error=True,
                status=None,
                detail=f"Parser error (before EVR exists): {exc}",
            )
        if isinstance(exc, ValueError):
            return cls(
                is_parser_error=True,
                status=None,
                detail=f"Value error (before EVR exists): {exc}",
            )
        if isinstance(exc, KeyError):
            return cls(
                is_parser_error=True,
                status=None,
                detail=f"Missing field (before EVR exists): {exc}",
            )
        return cls(
            is_parser_error=True,
            status=None,
            detail=f"Unexpected error (before EVR exists): {exc}",
        )
