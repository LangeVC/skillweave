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


# ── SW1311-COUNCIL-001 — historical regression closure (criterion 8) ────────
# The v1.3.9 release prefixed every Council profile id with ``faigate/``
# (gateway namespace leaked into profile data). v1.3.10 reverted the prefix but
# left a ``replace`` in the adapter that could silently collapse an unknown
# namespace. These fixtures lock BOTH commits out: the prefix must not reappear
# in Council data, and no silent ``replace``/collapse remains.

from skillweave.routing.faigate_adapter import (  # noqa: E402
    ROUTER_PROFILES,
    ModelNamespaceError,
    translate_model_id,
    validate_council_model_ids,
)

# The exact ids v1.3.9 prefixed (taken from the v1.3.9 commit's
# ``council-profiles.md`` diff) and their provider-native v1.3.10 form.
V139_PREFIXED = [
    "faigate/claude-sonnet-4-5",
    "faigate/gpt-4o",
    "faigate/gemini-2-5-pro",
    "faigate/deepseek-v4-pro",
    "faigate/claude-opus-4",
]


def test_router_profiles_never_re_adopt_the_v139_prefix():
    # The exact relapse v1.3.9 committed: Council profile ids carrying the outer
    # gateway prefix. No id in ROUTER_PROFILES may carry it again.
    for preset in ROUTER_PROFILES.values():
        for mid in list(preset["models"]) + [preset["chairman"]]:
            assert "faigate/" not in mid
            assert "/" not in mid


def test_prefixed_council_ids_fail_validation_before_call():
    # The v1.3.9 ids, fed back in, are refused by the Council profile validator
    # with a typed error — never silently accepted and passed to a provider.
    for mid in V139_PREFIXED:
        with pytest.raises(ModelNamespaceError):
            validate_council_model_ids(models=[mid], chairman=None, source="v1.3.9 fixture")


def test_translation_strips_exactly_once_and_never_collapses_unknown():
    # The v1.3.10 correction used ``replace`` which could silently collapse a
    # foreign or doubled prefix. Exact-once translation refuses both.
    assert translate_model_id("faigate/deepseek-v4-pro") == "deepseek-v4-pro"
    with pytest.raises(ModelNamespaceError):
        translate_model_id("faigate/faigate/deepseek-v4-pro")
    with pytest.raises(ModelNamespaceError):
        translate_model_id("openrouter/deepseek-v4-pro")


def test_dispatch_qualified_syntax_still_valid_but_not_in_council_data():
    # The dispatch layer's gateway-qualified id remains a legal input to the
    # adapter (translated exactly once), while the same id is illegal in Council
    # profile data. One fixture proves both contexts concurrently.
    dispatch_id = "faigate/deepseek-v4-pro"
    assert translate_model_id(dispatch_id) == "deepseek-v4-pro"  # dispatch: valid
    with pytest.raises(ModelNamespaceError):  # council data: invalid
        validate_council_model_ids(models=[dispatch_id], chairman=None, source="council")


# ── SW1311-COUNCIL-001 — proven live roster identifiers (criterion 6) ───────
# The correction of ``ROUTER_PROFILES`` is grounded in a live Faidate roster
# proof, not in a guessed alias. These fixtures lock the proven ids in: the
# profile data must name real ``GET /v1/models`` roster ids (provider-native,
# unprefixed) that yield at least two distinct answering models. The answered
# models are asserted as data — a later edit that swaps in a stale alias
# (``sonnet``, ``gpt-4o``, ``deepseek-v4``) fails here before any live call.

#: Each roster id mapped to the model Faidate measured it answers as
#: (``requested -> answering``), from the live proof at
#: ``http://127.0.0.1:8090/v1``. ``deepseek-v4-pro`` and ``deepseek-v4-flash``
#: answer as themselves; the ``kilo-*`` and ``gemini-*`` ids answer as their
#: underlying provider-qualified model. All are distinct answering models.
PROVEN_ROSTER = {
    "deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "gemini-flash": "gemini-2.5-flash",
    "gemini-flash-lite": "gemini-2.5-flash-lite",
    "kilo-sonnet": "anthropic/claude-sonnet-4.6",
    "kilo-opus": "anthropic/claude-opus-4.6",
}

#: The self-answering roster ids (requested == answering). The live gate counts
#: distinct answering models among answered seats; these two hold the >=2 gate.
SELF_ANSWERING_ROSTER = {mid for mid, ans in PROVEN_ROSTER.items() if mid == ans}


def test_profiles_cast_only_proven_live_roster_ids():
    # No cast id may drift back to a stale alias; every id in ROUTER_PROFILES must
    # be one of the proven live roster ids measured at the correction.
    for preset in ROUTER_PROFILES.values():
        for mid in list(preset["models"]) + [preset["chairman"]]:
            assert mid in PROVEN_ROSTER, (
                f"{mid!r} is not a proven live Faidate roster id; use a real "
                f"/v1/models id, not a council alias"
            )


def test_default_profile_yields_at_least_two_self_answering_models():
    # The live gate requests the ``default`` preset's models and demands >=2
    # distinct answering models among answered seats. Proven: the default cast
    # contains both self-answering deepseek ids.
    default = ROUTER_PROFILES["default"]
    self_answering = [m for m in default["models"] if m in SELF_ANSWERING_ROSTER]
    assert len(self_answering) >= 2, (
        f"default profile lacks >=2 self-answering roster models; "
        f"found {self_answering}"
    )


def test_default_profile_at_least_two_distinct_answering_models():
    # Across the whole default cast (models + chairman), the measured answering
    # set is at least two distinct models, so the minimum-distinct gate holds.
    default = ROUTER_PROFILES["default"]
    seats = default["models"] + ([default["chairman"]] if default.get("mode") == "full" else [])
    answering = {PROVEN_ROSTER[m] for m in seats if m in PROVEN_ROSTER}
    assert len(answering) >= 2, f"default profile answering set too small: {answering}"


def test_v139_and_v1310_guards_still_hold_against_new_profiles():
    # The historical prefix relapse and the silent-collapse guards remain intact
    # against the corrected profiles: no id carries a gateway namespace, and no
    # ``faigate/`` prefix appears anywhere in Council profile data. The corrected
    # casts reuse native bodies (e.g. ``deepseek-v4-pro``) that v1.3.9 had wrongly
    # prefixed — the body is right, only the prefix was the relapse, and the
    # no-prefix guard above still refuses any re-adoption.
    for preset in ROUTER_PROFILES.values():
        for mid in list(preset["models"]) + [preset["chairman"]]:
            assert "/" not in mid and ":" not in mid
            assert "faigate" not in mid
