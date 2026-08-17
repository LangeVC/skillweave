"""Tests for model availability resolution (SW-RT-002, dispatch 1).

Dispatch 1 criteria:

1. Model availability is resolved against what Faigate can actually serve, not
   against ``ROUTER_PROFILES``. Fixture: ``deepseek-v4-pro``. A profile pinning
   it loads, and no message claims Faigate cannot resolve it. Red proof: the
   identical profile raises ``RoutingProfileError`` against v1.3.5 (478211f).
2. When no authoritative source is reachable, an unresolvable model is reported
   as UNVERIFIED, not refused. Refusal requires a POSITIVE proof: Faigate
   answering with an error for exactly that model. Absence from ``/v1/models``
   is not evidence of non-service — the router resolves names server-side, so
   the roster under-reports (``deepseek-v4`` answers despite not being listed).
3. ``ROUTER_PROFILES`` keep their own job as the council's casting and are not
   repurposed as a registry. ``known_model_ids()`` is no longer the
   availability gate.
"""

from unittest import mock

from skillweave.routing import (
    from_dict,
    known_model_ids,
    resolve_tier,
)
from skillweave.routing import faigate_adapter as adapter


def _pin_profile(pin="deepseek-v4-pro"):
    return from_dict(
        {
            "name": "sw135",
            "tier": "balanced",
            "limits": {},
            "roles": {"ops": {"pin": pin}},
        }
    )


class _FakeFaigate(adapter.FaigateProvider):
    """A deterministic FaigateProvider whose roster is injected, not probed.

    ``served`` is the set of model ids the fake reports in its ``/v1/models``
    roster. Faigate resolves names server-side and silently substitutes a
    fallback for anything it does not recognize, so the roster is an
    under-reporting enumeration — it is NOT evidence of non-service. Refusal
    requires a positive, model-specific error, which this fake does not model
    because the real router never produces one; absence from ``served`` is
    therefore UNVERIFIED, never refused. Unreachability is modelled separately
    (``detect_providers`` returning no Faigate).
    """

    def __init__(self, served):
        self.base_url = "http://127.0.0.1:1/v1"
        self.api_key = None
        self._served = set(served)

    async def check_availability(self, models):
        return {m: (m.replace("faigate:", "") in self._served) for m in models}


# ── Criterion 1: availability resolves against Faigate, not ROUTER_PROFILES ──

def test_deepseek_v4_pro_is_not_in_the_council_cast():
    # The fixture model is a real Faigate model that ROUTER_PROFILES never cast.
    # This pins the pre-condition: if deepseek-v4-pro were already a cast model,
    # this dispatch would have nothing to prove.
    assert "deepseek-v4-pro" not in known_model_ids()


def test_pin_to_live_model_resolves_not_refused():
    # A profile pinning a model Faigate serves resolves; no message claims
    # Faigate cannot resolve it.
    profile = _pin_profile()
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["deepseek-v4-pro"])},
    ):
        resolution = resolve_tier(profile)
    assert resolution.pinned == "deepseek-v4-pro"
    assert resolution.resolved_models == ["deepseek-v4-pro"]


def test_resolution_emits_no_cannot_resolve_claim_for_live_model():
    # The resolution path for a served model never surfaces a "cannot resolve"
    # message (the v1.3.5 false-refusal symptom): it returns a record naming the
    # pinned model verbatim, without raising, so no refusal message can exist.
    profile = _pin_profile()
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["deepseek-v4-pro"])},
    ):
        resolution = resolve_tier(profile)
    assert resolution.resolved_models == ["deepseek-v4-pro"]
    assert resolution.pinned == "deepseek-v4-pro"


# ── Criterion 2: unreachable Faigate ⇒ UNVERIFIED, not refused ─────────────

def test_unreachable_faigate_leaves_model_unverified():
    # With no Faigate provider reachable there is no authoritative source, so a
    # pin is left UNVERIFIED: it resolves rather than raising, and no "cannot
    # resolve" or "unavailable" refusal is issued.
    profile = _pin_profile()
    with mock.patch.object(adapter, "detect_providers", return_value={}):
        resolution = resolve_tier(profile)
    assert resolution.pinned == "deepseek-v4-pro"
    assert resolution.resolved_models == ["deepseek-v4-pro"]


def test_not_listed_but_served_model_is_not_refused():
    # The corrected semantics: Faigate resolves names server-side and /v1/models
    # under-reports. deepseek-v4 answers live yet is missing from the roster, so
    # absence from /v1/models is NOT evidence of non-service and must never
    # refuse. A non-cast override that is absent from the roster therefore still
    # resolves (UNVERIFIED), rather than raising.
    profile = _pin_profile(pin="deepseek-v4")
    assert "deepseek-v4" in known_model_ids()  # but it is NOT in this roster
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["deepseek-v4-pro"])},
    ):
        resolution = resolve_tier(profile)
    assert resolution.pinned == "deepseek-v4"
    assert resolution.resolved_models == ["deepseek-v4"]


def test_absence_from_roster_is_never_refusal_grounds():
    # gpt-4o is the counter-proof: it serves (Faugate silently maps it) but does
    # not appear in /v1/models under that id (only under openai-gpt4o). A pin to
    # it must not be refused on that absence — refusal requires a positive error
    # for exactly this model, which the roster probe cannot produce.
    profile = _pin_profile(pin="gpt-4o")
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["openai-gpt4o", "deepseek-v4-pro"])},
    ):
        resolution = resolve_tier(profile)
    assert resolution.pinned == "gpt-4o"
    assert resolution.resolved_models == ["gpt-4o"]


# ── Criterion 3: ROUTER_PROFILES stays the cast; known_model_ids() not the gate ─

def test_known_model_ids_is_no_longer_the_availability_gate():
    # A model id outside known_model_ids() (the old gate) now resolves when
    # Faigate serves it — proving known_model_ids() is no longer consulted for
    # availability.
    profile = _pin_profile(pin="deepseek-v4-pro")
    assert "deepseek-v4-pro" not in known_model_ids()
    with mock.patch.object(
        adapter,
        "detect_providers",
        return_value={"faigate": _FakeFaigate(["deepseek-v4-pro"])},
    ):
        resolution = resolve_tier(profile)
    assert resolution.pinned == "deepseek-v4-pro"


def test_router_profiles_unchanged_and_still_cast_the_council():
    # ROUTER_PROFILES keep their casting job: the presets still name a chairman,
    # a mode, and a model pool. Nothing in the availability fix should have
    # repurposed them into a registry of served models.
    assert set(adapter.ROUTER_PROFILES) == {"default", "quick", "deep", "expert"}
    for preset in adapter.ROUTER_PROFILES.values():
        assert preset["chairman"]
        assert preset["mode"]
        assert preset["models"]


def test_deepseek_v4_still_in_cast_is_not_silently_removed():
    # The council still casts deepseek-v4 (a symbolic preset name); the fix must
    # not delete cast entries in the name of correctness. Known ids remain the
    # cast surface, unchanged.
    assert "deepseek-v4" in known_model_ids()
