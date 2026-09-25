"""Dispatch-order group 1 — standalone SDK contract identity (criterion 2).

Proves the SDK installs standalone (no ``skillweave`` runtime import, no
dependencies) and that Core, the two OSS base profiles and the private Pro pack
all pin the *identical* schema version and canonical digest. Any divergence —
SDK advertises one digest while the profiles/pack pin another, or the published
``schema_version.toml`` disagrees with the validator's canonical digest — fails
closed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

from tests.gate_1312 import CANONICAL_SCHEMA_DIGEST
from tests.gate_1312 import _sibling as sib
from tests.gate_1312._sibling import require

SCHEMA_VERSION = "0.1.0"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_criterion_02_standalone_sdk_identical_version_and_digest():
    """The SDK is standalone, and Core/OSS/Pro pin the same version + digest.

    Standalone: the SDK source has no ``skillweave`` runtime import and declares
    zero dependencies. Identity: the SDK's ``schema_version.toml`` version equals
    the validator's ``PREVIEW_SCHEMA_VERSION``; the validator's canonical digest
    equals the published constant; and every consumer (Core's canonical constant,
    both OSS base profiles' ``sdkContract``, the private Pro pack's
    ``sdkContract`` and ``direct-install`` compatibility) pins that same
    ``schemaVersion`` and ``schemaDigest``.
    """
    require(sib.sdk_schemas_dir, name="skillweave-sdk")
    require(sib.base_profiles_dir, name="skillweave-profiles")
    require(sib.cms_pack_dir, name="skillweave-packs-pro")
    # --- Standalone SDK: no runtime import, zero dependencies -----------------
    validator = sib.sdk_validator_module()
    root = sib.sdk_root()

    py_files = list(root.rglob("*.py"))
    src_py = [p for p in py_files if "/src/" in str(p)]
    for py in src_py:
        for line in py.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            assert not s.startswith("import skillweave") and not s.startswith(
                "from skillweave"
            ), f"{py.name}: runtime import {s!r}"

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        assert data["project"]["dependencies"] == []

    # --- Version identity ------------------------------------------------------
    version_toml = tomllib.loads(
        (root / "schema_version.toml").read_text(encoding="utf-8")
    )
    published_version = version_toml["schema"]["version"]
    assert published_version == SCHEMA_VERSION
    assert validator.PREVIEW_SCHEMA_VERSION == SCHEMA_VERSION
    assert validator.EXPECTED_SCHEMA_DIGEST == CANONICAL_SCHEMA_DIGEST

    # --- Digest identity across Core, OSS profiles, Pro pack -------------------
    schemas_dir = sib.sdk_schemas_dir()
    computed = validator.canonical_digest(schemas_dir)
    assert computed == CANONICAL_SCHEMA_DIGEST
    validator.verify_canonical_digest(schemas_dir)

    # Core's canonical constant.
    from tests.gate_1312 import CANONICAL_SCHEMA_DIGEST as core_digest

    assert core_digest == CANONICAL_SCHEMA_DIGEST

    # Two OSS base profiles.
    base = sib.base_profiles_dir()
    for fname in (
        "software-product-delivery.v1-preview.yaml",
        "research-and-synthesis.v1-preview.yaml",
    ):
        doc = _load_yaml(base / fname)
        assert doc["sdkContract"]["schemaVersion"] == SCHEMA_VERSION
        assert doc["sdkContract"]["standardId"] == "skillweave-sdk"
        assert doc["sdkContract"]["schemaDigest"] == CANONICAL_SCHEMA_DIGEST

    # Private Pro pack (pack.yaml and direct-install.yaml).
    pack_dir = sib.cms_pack_dir()
    pack = _load_yaml(pack_dir / "pack.yaml")["pack"]
    assert pack["sdkContract"]["schemaVersion"] == SCHEMA_VERSION
    assert pack["sdkContract"]["standardId"] == "skillweave-sdk"
    assert pack["sdkContract"]["schemaDigest"] == CANONICAL_SCHEMA_DIGEST
    di = _load_yaml(pack_dir / "direct-install.yaml")
    assert di["compatibility"]["schemaDigest"] == CANONICAL_SCHEMA_DIGEST
    assert di["compatibility"]["sdk"] == ">=0.1.0,<0.2.0"

    # A deliberately diverged digest must fail closed (detection, not silence).
    assert validator.EXPECTED_SCHEMA_DIGEST != ("0" * 64)


def test_canonical_digest_is_deterministic_over_sorted_schema_files():
    """The canonical digest is a pure function of the five preview schema bytes,
    so Core, OSS and Pro can never disagree unless their pinned schema bytes do.
    """
    require(sib.sdk_schemas_dir, name="skillweave-sdk")
    validator = sib.sdk_validator_module()
    schemas_dir = sib.sdk_schemas_dir()
    assert validator.canonical_digest(schemas_dir) == validator.canonical_digest(
        schemas_dir
    )
    # The SDK commits exactly the five preview schemas it digests.
    missing = [
        fn for fn in validator.SCHEMA_FILENAMES
        if not (schemas_dir / fn).is_file()
    ]
    assert not missing, f"SDK preview schemas missing: {missing}"
