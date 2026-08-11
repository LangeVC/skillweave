from __future__ import annotations

import hashlib
from typing import Dict

from .evidence import (
    CapabilityProvider,
    EvidenceVerificationResult,
    EvidenceVerificationStatus,
    VerificationRequest,
)


_REGISTRY: Dict[str, CapabilityProvider] = {}


def register_provider(provider_id: str, provider: CapabilityProvider) -> None:
    if not provider_id:
        raise ValueError("Provider ID must not be empty")
    _REGISTRY[provider_id] = provider


def unregister_provider(provider_id: str) -> None:
    _REGISTRY.pop(provider_id, None)


def list_providers() -> dict[str, CapabilityProvider]:
    return dict(_REGISTRY)


def get_provider(provider_id: str) -> CapabilityProvider | None:
    return _REGISTRY.get(provider_id)


def verify_evidence(
    request: VerificationRequest,
    provider_id: str = "skillweave-local-verifier",
) -> EvidenceVerificationResult:
    provider = _REGISTRY.get(provider_id)
    if provider is None:
        return EvidenceVerificationResult(
            EvidenceVerificationStatus.UNAVAILABLE,
            detail=f"No provider registered for {provider_id!r}",
        )
    try:
        return provider.verify(request)
    except Exception as exc:
        return EvidenceVerificationResult(
            EvidenceVerificationStatus.INCONCLUSIVE,
            detail=f"Provider {provider_id!r} raised: {exc}",
        )


class LocalEvidenceVerificationProvider:
    def __init__(self, known_digests: dict[str, EvidenceVerificationStatus] | None = None) -> None:
        self._known = dict(known_digests) if known_digests else {}

    def register_digest(self, digest: str, status: EvidenceVerificationStatus) -> None:
        self._known[digest] = status

    def verify(self, request: VerificationRequest) -> EvidenceVerificationResult:
        digest = request.evidence_digest
        status = self._known.get(digest)
        if status is None:
            return EvidenceVerificationResult(
                EvidenceVerificationStatus.UNKNOWN_KEY,
                detail=f"Digest not in local registry: {digest}",
            )
        return EvidenceVerificationResult(status, detail=f"Local verification: {digest}")


class NoOpVerificationProvider:
    def verify(self, request: VerificationRequest) -> EvidenceVerificationResult:
        return EvidenceVerificationResult(
            EvidenceVerificationStatus.UNAVAILABLE,
            detail="No-op provider: verification disabled",
        )
