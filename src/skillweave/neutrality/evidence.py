from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class EvidenceVerificationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    KEY_EXPIRED = "KEY_EXPIRED"
    KEY_REVOKED = "KEY_REVOKED"
    UNKNOWN_KEY = "UNKNOWN_KEY"
    MALFORMED = "MALFORMED"
    UNSUPPORTED_ALGORITHM = "UNSUPPORTED_ALGORITHM"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNAVAILABLE = "UNAVAILABLE"

    def is_verified(self) -> bool:
        return self == EvidenceVerificationStatus.VALID

    def to_skillweave_status(self) -> str:
        mapping = {
            EvidenceVerificationStatus.VALID: "PASS",
            EvidenceVerificationStatus.INVALID: "FAIL",
            EvidenceVerificationStatus.KEY_EXPIRED: "FAIL",
            EvidenceVerificationStatus.KEY_REVOKED: "FAIL",
            EvidenceVerificationStatus.UNKNOWN_KEY: "FAIL",
            EvidenceVerificationStatus.MALFORMED: "FAIL",
            EvidenceVerificationStatus.UNSUPPORTED_ALGORITHM: "FAIL",
            EvidenceVerificationStatus.INCONCLUSIVE: "INCONCLUSIVE",
            EvidenceVerificationStatus.UNAVAILABLE: "UNAVAILABLE",
        }
        return mapping[self]


_EVR_STATES_VALID_VERIFIED = {
    EvidenceVerificationStatus.VALID,
}

_EVR_STATES_EXPLICITLY_FAILED = {
    EvidenceVerificationStatus.INVALID,
    EvidenceVerificationStatus.KEY_EXPIRED,
    EvidenceVerificationStatus.KEY_REVOKED,
    EvidenceVerificationStatus.UNKNOWN_KEY,
    EvidenceVerificationStatus.MALFORMED,
    EvidenceVerificationStatus.UNSUPPORTED_ALGORITHM,
}

_EVR_STATES_NEITHER_PASS_NOR_FAIL = {
    EvidenceVerificationStatus.INCONCLUSIVE,
    EvidenceVerificationStatus.UNAVAILABLE,
}

CANONICAL_EVR_STATUSES = frozenset(s for s in EvidenceVerificationStatus)


class ParserError(Exception):
    pass


class EvidenceVerificationResult:
    __slots__ = ("_status", "_detail")

    def __init__(self, status: EvidenceVerificationStatus, detail: str = "") -> None:
        if not isinstance(status, EvidenceVerificationStatus):
            raise TypeError(f"Expected EvidenceVerificationStatus, got {type(status)}")
        self._status = status
        self._detail = detail

    @property
    def status(self) -> EvidenceVerificationStatus:
        return self._status

    @property
    def detail(self) -> str:
        return self._detail

    def is_verified(self) -> bool:
        return self._status.is_verified()

    def is_explicit_failure(self) -> bool:
        return self._status in _EVR_STATES_EXPLICITLY_FAILED

    def is_inconclusive(self) -> bool:
        return self._status in _EVR_STATES_NEITHER_PASS_NOR_FAIL

    @classmethod
    def from_dict(cls, data: dict) -> EvidenceVerificationResult:
        raw_status = data.get("status")
        detail = data.get("detail", "")
        if not raw_status:
            raise ParserError("Missing status in EvidenceVerificationResult")
        if not isinstance(raw_status, str):
            raise ParserError(f"Status must be string, got {type(raw_status)}")
        try:
            status = EvidenceVerificationStatus(raw_status)
        except ValueError:
            raise ParserError(f"Unknown EvidenceVerificationStatus: {raw_status}")
        if detail and not isinstance(detail, str):
            raise ParserError(f"Detail must be string, got {type(detail)}")
        return cls(status, detail)

    def to_dict(self) -> dict:
        return {"status": self._status.value, "detail": self._detail}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EvidenceVerificationResult):
            return NotImplemented
        return self._status == other._status and self._detail == other._detail

    def __hash__(self) -> int:
        return hash((self._status, self._detail))

    def __repr__(self) -> str:
        return f"EvidenceVerificationResult({self._status.value!r}, detail={self._detail!r})"


@dataclass(frozen=True)
class VerificationRequest:
    evidence_digest: str
    provider: object | None = None
    extra: dict = field(default_factory=dict)


class CapabilityProvider(Protocol):
    def verify(self, request: VerificationRequest) -> EvidenceVerificationResult: ...
