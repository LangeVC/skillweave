"""Dual-review attestation gates package (SW1312-ATTESTATION-STRICT-001)."""

from .attestation import (
    REVIEW_PASS,
    AttestationError,
    DualReviewAttestation,
    canonicalize,
    validate,
    load_schema,
)

__all__ = [
    "REVIEW_PASS",
    "AttestationError",
    "DualReviewAttestation",
    "canonicalize",
    "validate",
    "load_schema",
]
