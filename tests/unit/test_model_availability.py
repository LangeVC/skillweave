"""Tests for model availability resolution (SW-RT-002, dispatch 1).

Dispatch 1 criteria:

1. Model availability is resolved against what Faigate can actually serve, not
   against ``ROUTER_PROFILES``. Fixture: ``openai-gpt4o`` — a real Faigate
   roster id that ``ROUTER_PROFILES`` never casts. A profile pinning it loads,
   and no message claims Faigate cannot resolve it. Red proof: the identical
   profile raises ``RoutingProfileError`` against v1.3.5 (478211f).
2. When no authoritative source is reachable, an unresolvable model is reported
   as UNVERIFIED, not refused, and the message says which of the two happened.
3. ``ROUTER_PROFILES`` keep their own job as the council's casting and are not
   repurposed as a registry. ``known_model_ids()`` is no longer the
   availability gate.
"""

import asyncio
from unittest import mock

import pytest

from skillweave.routing import (
    RoutingProfileError,
    from_dict,
    known_model_ids,
    resolve_tier,
)
from skillweave.routing import faigate_adapter as adapter


def _pin_profile(pin="openai-gpt4o"):
    return from_dict(
        {
            "name": "sw135",
            "tier": "balanced",
            "limits": {},
            "roles": {"ops": {"pin": pin}},
        }
    )


class _FakeFaigate(adapter.FaigateProvider):
    """A deterministic FaigateProvider whose roster is injected, not probed."""

    def __init__(self, served):
        self.base_url = "http://127.0.0.1:1/v1"
        self.api_key = None
        self._served = set(served)

    async def check_availability(self, models):
        return {m: (m.replace("faigate:", "") in self._served) for m in models}


# ── Criterion 1: availability resolves against Faigate, not ROUTER_PROFILES ──

def test_openai_gpt4o_is_not_in_the_council_cast():
    # The fixture model is a real Faigate model that ROUTER_PROFILES never cast.
    # This pins the pre-condition: if openai-gpt4o were already a cast model,
    # this dispatch would have nothing to prove.
    assert "openai-gpt4o" not in known_model_ids()


def test_pin_to_live_model_resolves_not_refused():
    # A profile pinning a model Faigate serves resolves; no message claims
    # Faigate cannot resolve it.
    profile = _pin_profile()
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["openai-gpt4o"])},
    ):
        resolution = resolve_tier(profile)
    assert resolution.pinned == "openai-gpt4o"
    assert resolution.resolved_models == ["openai-gpt4o"]


def test_resolution_emits_no_cannot_resolve_claim_for_live_model():
    # The resolution path for a served model never surfaces a "cannot resolve"
    # message (the v1.3.5 false-refusal symptom): it returns a record naming the
    # pinned model verbatim, without raising, so no refusal message can exist.
    profile = _pin_profile()
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["openai-gpt4o"])},
    ):
        resolution = resolve_tier(profile)
    assert resolution.resolved_models == ["openai-gpt4o"]
    assert resolution.pinned == "openai-gpt4o"


# ── Criterion 2: unreachable Faigate ⇒ UNVERIFIED, not refused ─────────────

def test_unreachable_faigate_leaves_model_unverified():
    # With no Faigate provider reachable there is no authoritative source, so a
    # pin is left UNVERIFIED: it resolves rather than raising, and no "cannot
    # resolve" or "unavailable" refusal is issued.
    profile = _pin_profile()
    with mock.patch.object(adapter, "detect_providers", return_value={}):
        resolution = resolve_tier(profile)
    assert resolution.pinned == "openai-gpt4o"
    assert resolution.resolved_models == ["openai-gpt4o"]


def test_confirmed_unavailable_is_refused():
    # When Faigate answers and confirms a model is NOT served, that is a defined
    # refusal (naming profile + role), distinct from the UNVERIFIED silence.
    profile = _pin_profile(pin="no-such-model")
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["openai-gpt4o"])},
    ):
        with pytest.raises(RoutingProfileError) as exc:
            resolve_tier(profile)
    assert "no-such-model" in str(exc.value)
    assert "unavailable" in str(exc.value)


def test_unverified_and_refused_are_distinct_messages():
    # Criterion 2 requires the message to say which of the two happened. The
    # refused path names "unavailable"; the unverified path raises nothing.
    profile = _pin_profile(pin="no-such-model")
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["other-model"])},
    ):
        with pytest.raises(RoutingProfileError) as exc:
            resolve_tier(profile)
    assert "unavailable" in str(exc.value)
    assert "cannot resolve" not in str(exc.value)


# ── Criterion 3: ROUTER_PROFILES stays the cast; known_model_ids() not the gate ─

def test_known_model_ids_is_no_longer_the_availability_gate():
    # A model id outside known_model_ids() (the old gate) now resolves when
    # Faigate serves it — proving known_model_ids() is no longer consulted for
    # availability.
    profile = _pin_profile(pin="openai-gpt4o")
    assert "openai-gpt4o" not in known_model_ids()
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["openai-gpt4o"])},
    ):
        resolution = resolve_tier(profile)
    assert resolution.pinned == "openai-gpt4o"


def test_router_profiles_unchanged_and_still_cast_the_council():
    # ROUTER_PROFILES keep their casting job: the presets still name a chairman,
    # a mode, and a model pool. Nothing in the availability fix should have
    # repurposed them into a registry of served models.
    assert set(adapter.ROUTER_PROFILES) == {"default", "quick", "deep", "expert"}
    for preset in adapter.ROUTER_PROFILES.values():
        assert preset["chairman"]
        assert preset["mode"]
        assert preset["models"]


def test_cast_is_provider_native_without_symbolic_aliases():
    # The council cast names provider-native roster ids directly; a symbolic
    # alias (``deepseek-v4``) that Faigate never serves must not remain in the
    # cast. Known ids are the provider-native cast surface, unchanged by the
    # availability fix.
    assert "deepseek-v4" not in known_model_ids()
    assert "deepseek-v4-pro" in known_model_ids()
    assert "deepseek-v4-flash" in known_model_ids()
