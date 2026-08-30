"""Effective-profile resolution package (SW1312-PROFILE-RESOLVE-001).

Holds the immutable effective-profile snapshot resolver. See
:mod:`skillweave.profiles.effective` for the resolver and snapshot types.
"""

from .effective import (  # noqa: F401
    EffectiveProfileError,
    SchemaBindingError,
    ConflictError,
    PreviewExecutionError,
    ProfileSource,
    SOURCE_KINDS,
    SDK_PREVIEW_SCHEMA_VERSION,
    SDK_EXPECTED_SCHEMA_DIGEST,
    PREVIEW_DIMENSIONS,
    resolve_effective_profile,
    EffectiveProfileSnapshot,
    content_digest,
    canonical_json_bytes,
)

__all__ = [
    "EffectiveProfileError",
    "SchemaBindingError",
    "ConflictError",
    "PreviewExecutionError",
    "ProfileSource",
    "SOURCE_KINDS",
    "SDK_PREVIEW_SCHEMA_VERSION",
    "SDK_EXPECTED_SCHEMA_DIGEST",
    "PREVIEW_DIMENSIONS",
    "resolve_effective_profile",
    "EffectiveProfileSnapshot",
    "content_digest",
    "canonical_json_bytes",
]
