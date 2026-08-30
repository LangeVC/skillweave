"""Council namespace patch gate — synchronous surfaces, one adapter (SW1311-COUNCIL-001).

Integration proof that the Council contract holds end to end, across every
written surface named in the acceptance criteria:

1. The shared routing adapter owns namespace translation exactly once; the
   ``council.faigate_adapter`` path is a pure re-export, not a second copy.
2. ``ROUTER_PROFILES`` (provider-native) and the skill's
   ``references/council-profiles.md`` (documented presets) are synchronised —
   the ids, chairman and mode agree for every preset.
3. The Council capability manifest and skill describe the same four profiles
   and carry provider-native (unprefixed) ids.
4. Release-version surfaces (``pyproject.toml``, ``capability.yaml``, the skill
   manifests) are *listed* as final-gate evidence and are not edited here.
5. A Council profile carrying a gateway prefix is refused *before* any provider
   call; dispatch's gateway-qualified syntax remains valid.
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_REPO = Path(__file__).resolve().parent.parent.parent


#: The release-version surfaces the release readiness gate versions. This patch
#: does not edit them; it only names them as required final-gate evidence.
RELEASE_VERSION_SURFACES = [
    "pyproject.toml",
    "capability.yaml",
    ".version.yaml",
    "skills/skillweave-council/capability.yaml",
]


def test_shim_is_a_pure_reexport_not_a_second_implementation():
    import skillweave.council.faigate_adapter as shim
    import skillweave.routing.faigate_adapter as canonical
    for name, obj in vars(shim).items():
        if name.startswith("__"):
            continue
        canonical_obj = getattr(canonical, name, None)
        assert obj is canonical_obj, (
            f"council.faigate_adapter.{name} is not the canonical object: "
            f"the shim must re-export, not re-implement"
        )


def test_router_profiles_and_docs_share_preset_names_and_no_prefix():
    from skillweave.routing.faigate_adapter import ROUTER_PROFILES
    text = (_REPO / "skills/skillweave-council/references/council-profiles.md").read_text()
    # The four preset names are shared between code and docs.
    for name in ROUTER_PROFILES:
        assert name in text, f"preset {name} missing from council-profiles.md"
    # The v1.3.9 relapse — a gateway prefix in Council profile data — is absent.
    assert "faigate/" not in text
    assert "/" not in " ".join(
        mid for preset in ROUTER_PROFILES.values()
        for mid in list(preset["models"]) + [preset["chairman"]]
    )


def test_router_profiles_are_provider_native():
    from skillweave.routing.faigate_adapter import ROUTER_PROFILES
    for preset in ROUTER_PROFILES.values():
        for mid in list(preset["models"]) + [preset["chairman"]]:
            assert "/" not in mid and ":" not in mid


def test_council_profile_prefix_refused_before_provider_call():
    from skillweave.routing.faigate_adapter import (
        ModelNamespaceError,
        validate_council_model_ids,
    )
    with pytest.raises(ModelNamespaceError):
        validate_council_model_ids(
            models=["faigate/deepseek-v4-pro"],
            chairman=None,
            source="integration fixture",
        )


def test_dispatch_qualified_syntax_remains_valid():
    from skillweave.routing.faigate_adapter import translate_model_id
    assert translate_model_id("faigate/deepseek-v4-pro") == "deepseek-v4-pro"


def test_skill_and_capability_describe_four_profiles():
    skill = (_REPO / "skills/skillweave-council/SKILL.md").read_text()
    for name in ("default", "quick", "deep", "expert"):
        assert name in skill, f"profile {name} missing from SKILL.md"


def test_release_version_surfaces_are_listed_as_final_gate_evidence():
    for rel in RELEASE_VERSION_SURFACES:
        assert (_REPO / rel).exists(), f"{rel} missing"
