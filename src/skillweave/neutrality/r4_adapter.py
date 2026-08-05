from __future__ import annotations

import hashlib

from .evidence import (
    EvidenceVerificationResult,
    EvidenceVerificationStatus,
    VerificationRequest,
)

FROZEN_R4_EVIDENCE_DIGEST = (
    "1cf259cfe38a05bbc4830b86d456841732a03fb868b8896ac29a61c0849b145d"
)

FROZEN_R4_BYTES = (
    b'{"r4_version":"4.0.0","signature":"placeholder-sig-legacy","'
    b'"claims":{"trust_anchor":"legacy-r4-anchor","profile":"LEGACY_REFERRENCE_PROFILE_V1ALPHA1"},'
    b'"policy_reference":"r4-legacy-policy-v1"}'
)


class R4CompatibilityAdapter:
    def __init__(self, frozen_bytes: bytes | None = None) -> None:
        self._frozen_bytes = frozen_bytes or FROZEN_R4_BYTES
        self._frozen_digest = hashlib.sha256(self._frozen_bytes).hexdigest()
        if self._frozen_digest != FROZEN_R4_EVIDENCE_DIGEST:
            raise ValueError(
                f"R4 frozen digest mismatch: got {self._frozen_digest}, "
                f"expected {FROZEN_R4_EVIDENCE_DIGEST}"
            )

    @property
    def frozen_digest(self) -> str:
        return self._frozen_digest

    @property
    def frozen_bytes(self) -> bytes:
        return self._frozen_bytes

    def verify(self, request: VerificationRequest) -> EvidenceVerificationResult:
        evidence_digest = request.evidence_digest

        if evidence_digest == self._frozen_digest:
            return EvidenceVerificationResult(
                EvidenceVerificationStatus.INVALID,
                detail=(
                    "LEGACY_REFERRENCE_PROFILE_V1ALPHA1: frozen R4 evidence "
                    "with placeholder signature — legacy provenance preserved, "
                    "NOT promoted to VALID"
                ),
            )

        return EvidenceVerificationResult(
            EvidenceVerificationStatus.UNKNOWN_KEY,
            detail=f"Evidence digest {evidence_digest!r} not recognized as frozen R4 evidence",
        )
