"""Sibling-repository resolution for the gate_1312 suite.

The suite reads four repositories as *read-only inputs*. This module resolves
their locations from environment variables or the known sibling checkout paths,
fail-closed with an actionable message. Everything resolves to an absolute
:class:`pathlib.Path`; no resolution ever writes, clones, fetches or otherwise
mutates any repository.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

#: The tests/gate_1312 directory (where this helper lives).
GATE_ROOT = Path(__file__).resolve().parent

#: The skillweave core repository root (parent of src/, tests/).
CORE_ROOT = GATE_ROOT.parents[1]


class RepoResolutionError(FileNotFoundError):
    """A required read-only repository surface could not be resolved."""


def require(resolver, *, name: str):
    """Resolve a required read-only sibling repository, or skip the test.

    The gate suite reads sibling repositories (skillweave-sdk, skillweave-
    profiles, skillweave-packs-pro) that are *not* part of this repository's
    tracked tree — a fresh ``git archive``/clone does not carry them. When a
    required sibling is absent we ``pytest.skip`` with a named reason so the
    hermetic suite produces the same result from a clone and a dev checkout,
    rather than failing on untracked local state. When the sibling IS present
    the full native gate runs.
    """
    try:
        return resolver()
    except RepoResolutionError as exc:
        pytest.skip(f"sibling {name} is not carried by git: {exc}")


def _require_file(candidates, *, env_var: str, what: str, anchor: str) -> Path:
    """Return the first candidate directory containing ``anchor``, else raise."""
    env = os.environ.get(env_var)
    ordered: list[Path] = []
    if env:
        ordered.append(Path(env))
    ordered.extend(candidates)
    for cand in ordered:
        if (cand / anchor).is_file() or (cand / anchor).is_dir():
            return cand
    raise RepoResolutionError(
        f"could not resolve {what}; set {env_var} or expose a sibling checkout. "
        f"Searched: {', '.join(str(c) for c in ordered)} (anchor={anchor!r})"
    )


def _skillweave_home() -> Path:
    """The shared parent directory that holds every skillweave sister repo."""
    # CORE_ROOT parent == ../.. of tests/ -> the forgejo/skillweave dir holding
    # the worktree and all siblings.
    return CORE_ROOT.parent


def sdk_root() -> Path:
    """Root of the skillweave-sdk checkout (contains schema_version.toml)."""
    home = _skillweave_home()
    return _require_file(
        [
            home / "skillweave-sdk",
            home / "wt-sw1312-profile-contract-ops",
        ],
        env_var="SKILLWEAVE_SDK_DIR",
        what="the skillweave-sdk repository",
        anchor="schema_version.toml",
    )


def sdk_schemas_dir() -> Path:
    """Directory holding the SDK schemas, preferring the preview-schema tree.

    The canonical preview digest is computed over five preview schemas
    (``*-.preview.schema.json``). The SDK ``main`` branch carries only the four
    core schemas; the PROFILE-CONTRACT lane adds the five preview schemas. Both
    env-var overrides point at a repository root or a schemas dir directly.
    """
    env_schema = os.environ.get("SKILLWEAVE_SCHEMA_DIR")
    if env_schema:
        cand = Path(env_schema)
        if (cand / "lifecycle-profile.preview.schema.json").is_file():
            return cand
    env_sdk = os.environ.get("SKILLWEAVE_SDK_DIR")
    if env_sdk:
        cand = Path(env_sdk) / "schemas"
        if (cand / "lifecycle-profile.preview.schema.json").is_file():
            return cand

    root = sdk_root()
    direct = root / "schemas"
    if (direct / "lifecycle-profile.preview.schema.json").is_file():
        return direct
    raise RepoResolutionError(
        "could not resolve the SDK preview schemas (lifecycle-profile.preview.schema.json); "
        "set SKILLWEAVE_SCHEMA_DIR (schemas dir) or SKILLWEAVE_SDK_DIR (repo root) "
        "to a skillweave-sdk tree whose PROFILE-CONTRACT lane preview schemas are committed"
    )


def sdk_validator_module():
    """Import ``skillweave_sdk.validator`` from the SDK tree into ``sys.modules``.

    Returns the module object. Imported lazily so this helper stays importable
    even when the SDK tree is absent (other modules decide whether to call it).
    """
    if "skillweave_sdk.validator" in sys.modules:
        return sys.modules["skillweave_sdk.validator"]

    root = sdk_root()
    src = root / "src"
    validator_file = src / "skillweave_sdk" / "validator.py"
    if not validator_file.is_file():
        validator_file = root / "skillweave_sdk" / "validator.py"
    if not validator_file.is_file():
        raise RepoResolutionError(
            f"could not resolve skillweave_sdk/validator.py under {root}; "
            "set SKILLWEAVE_SDK_DIR to the SDK repository root"
        )
    spec = importlib.util.spec_from_file_location(
        "skillweave_sdk.validator", validator_file
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["skillweave_sdk"] = type("skillweave_sdk", (), {"validator": module})()
    sys.modules["skillweave_sdk.validator"] = module
    return module


def profiles_root() -> Path:
    """Root of the skillweave-profiles tree owning the two OSS base profiles."""
    home = _skillweave_home()
    return _require_file(
        [
            home / "skillweave-profiles",
            home / "wt-sw1312-base-profiles-ops",
        ],
        env_var="SKILLWEAVE_PROFILES_DIR",
        what="the skillweave-profiles repository",
        anchor="profiles",
    )


def base_profiles_dir() -> Path:
    """Directory holding the two OSS base preview profiles."""
    root = profiles_root()
    d = root / "profiles"
    if (d / "software-product-delivery.v1-preview.yaml").is_file():
        return d
    raise RepoResolutionError(
        f"could not resolve the base profiles under {root}/profiles; the "
        "SW1312-BASE-PROFILES-001 lane must have committed them"
    )


def packs_pro_root() -> Path:
    """Root of the skillweave-packs-pro tree owning the private CMS pack."""
    home = _skillweave_home()
    return _require_file(
        [
            home / "skillweave-packs-pro",
            home / "wt-sw1312-cms-pack-ops",
        ],
        env_var="SKILLWEAVE_PACKS_PRO_DIR",
        what="the skillweave-packs-pro repository",
        anchor="packs",
    )


def cms_pack_dir() -> Path:
    """Directory holding the private cms-ops-management pack."""
    root = packs_pro_root()
    d = root / "packs" / "cms-ops-management"
    if (d / "pack.yaml").is_file():
        return d
    raise RepoResolutionError(
        f"could not resolve packs/cms-ops-management under {root}; the "
        "SW1312-CMS-PACK-001 lane must have committed it"
    )


def cms_proof_root() -> Path:
    """Root of the skillweave-packs-pro tree owning the CMS scenario proofs."""
    home = _skillweave_home()
    return _require_file(
        [
            home / "wt-sw1312-cms-proof-ops",
            home / "skillweave-packs-pro",
        ],
        env_var="SKILLWEAVE_PACKS_PRO_SCENARIOS_DIR",
        what="the skillweave-packs-pro CMS scenario tree",
        anchor="scenarios",
    )


def cms_scenarios_dir() -> Path:
    """Directory holding the four CMS reference scenarios."""
    root = cms_proof_root()
    d = root / "scenarios"
    if (d / "cms-landing-page").is_dir():
        return d
    raise RepoResolutionError(
        f"could not resolve scenarios/ under {root}; the "
        "SW1312-CMS-PROOF-001 lane must have committed them"
    )
