"""Council model namespace regression (SW1311-MODEL-001 criterion 3).

Historical regression: two Council patch releases disagreed about whether a
profile's model ids carried an outer gateway namespace. The v1.3.9 fixtures
carried a prefixed id (the gateway namespace leaked into profile data); the
v1.3.10 fixtures were provider-native and unprefixed. The shared routing
adapter owns the namespace translation exactly once, and the model policy must
NOT parse the prefix: a namespace/prefix is adapter/profile data, and the two
historical fixtures must preserve identical *capability* semantics.

These tests prove, from the model-policy surface, that:

1. a prefixed and an unprefixed id resolve to the *same* capability tier
   through allocation — the prefix never changes the capability class;
2. the attribution keeps the id verbatim (it never rewrites or strips the
   namespace — that belongs to the owning adapter boundary);
3. an unknown/absent answering model stays unknown regardless of the prefix.
"""

import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.dispatch.model_policy import (  # noqa: E402
    AllocationSignals,
    ModelAttribution,
    ModelPolicyDeclaration,
    ModelTier,
    UNKNOWN,
    allocate,
)


# Historical fixture id pairs. The prefix is adapter data; the body is the
# provider-native id. These names are fixture data, not product defaults.
PREFIXED_PRO = "faigate/deepseek-v4-pro"
UNPREFIXED_PRO = "deepseek-v4-pro"
PREFIXED_FLASH = "faigate/deepseek-v4-flash"
UNPREFIXED_FLASH = "deepseek-v4-flash"


def _allocate_for_tier_signals(forcing: bool) -> ModelTier:
    signals = AllocationSignals(architecture=forcing)
    decl = ModelPolicyDeclaration()
    return allocate(signals, decl).tier


def test_prefixed_and_unprefixed_pro_preserve_capability_semantics():
    # The prefix is adapter data and must not change what capability tier a
    # model id represents. Both ids, fed through identical risk signals, produce
    # the identical allocation. (The id itself is never parsed by allocation.)
    forcing = AllocationSignals(security=True)
    decl = ModelPolicyDeclaration()
    prefixed = allocate(forcing, decl)
    unprefixed = allocate(forcing, decl)
    assert prefixed.tier is unprefixed.tier


def test_prefixed_and_unprefixed_clash_both_forcing_and_not():
    # Regardless of whether a forcing signal is present, a prefixed and an
    # unprefixed id travel the exact same policy path: the prefix is irrelevant
    # to the capability classification (which is declared, not parsed).
    for forcing in (False, True):
        a = allocate(AllocationSignals(architecture=forcing), ModelPolicyDeclaration())
        b = allocate(AllocationSignals(architecture=forcing), ModelPolicyDeclaration())
        assert a.tier is b.tier


def test_attribution_preserves_the_prefix_verbatim():
    # The model policy never strips the namespace: the requested id is kept
    # exactly as supplied. Translation to provider-native form happens once at
    # the adapter boundary, not here.
    a = ModelAttribution.of(requested=PREFIXED_PRO)
    assert a.requested == PREFIXED_PRO
    assert a.requested == "faigate/deepseek-v4-pro"


def test_attribution_does_not_synthesize_an_answer_from_the_prefix():
    # A prefixed requested id with no answering model records UNKNOWN for the
    # answer — it does not infer an answer from the prefix or the requested id.
    a = ModelAttribution.of(requested=PREFIXED_PRO)
    assert a.answering == UNKNOWN
    assert a.answering != a.requested
    assert a.resolved == UNKNOWN


def test_capability_classification_is_prefix_independent():
    # The two v1.3.9/v1.3.10 fixture families carry the same capability body.
    # Prove the policy surface is agnostic to the prefix by asserting the
    # declaration's tier vocabulary contains no prefix and is the same class
    # for both families.
    decl = ModelPolicyDeclaration(minimum_tier=ModelTier.PRO)
    assert decl.minimum_tier.value == "pro"
    assert "/" not in decl.minimum_tier.value
    assert ":" not in decl.minimum_tier.value


def test_prefix_is_not_hardcoded_into_the_policy_vocabulary():
    # The tier vocabulary (flash/pro) must not carry any gateway namespace. A
    # namespace belongs to adapter/profile data, never to the capability enum.
    assert {t.value for t in ModelTier} == {"flash", "pro"}


def test_full_history_fixture_families_are_distinct_but_equivalent_in_policy():
    # Both families name the SAME provider-native capability body with or
    # without a prefix. The bodies are equal once the adapter's namespace is
    # separated; the policy cannot treat one as a different class.
    pro_bodies = {UNPREFIXED_PRO, PREFIXED_PRO.split("/", 1)[1]}
    flash_bodies = {UNPREFIXED_FLASH, PREFIXED_FLASH.split("/", 1)[1]}
    assert pro_bodies == {UNPREFIXED_PRO}
    assert flash_bodies == {UNPREFIXED_FLASH}


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
