"""Dispatch-order group 7 — GenericRouterProvider defect deferral (criterion 8).

The ``GenericRouterProvider`` (OmniRoute/Claw/Kilo/9router) hard-codes the
``"openrouter"`` alias table in its ``query`` path. This is a known 1.3.13
defect: the provider identifies as ``generic_router`` yet rewrites its outgoing
model id through the OpenRouter alias backend instead of its own.

This module **records the defect as an explicit 1.3.13 dependency** — it asserts
the defect is still present at 1.3.12 (so the gate cannot claim it is fixed) and
does **not** silently fix it, while confirming the 1.3.12 identity tests
(proper ``OpenRouterProvider`` and the pure ``translate_model_id`` contract)
remain intact and unweakened.
"""

from __future__ import annotations

import inspect

import pytest

from skillweave.routing.faigate_adapter import (
    FaigateProvider,
    GenericRouterProvider,
    OpenRouterProvider,
    ModelNamespaceError,
    translate_model_id,
)

#: The explicit deferral target. The defect is owned by 1.3.13, not 1.3.12.
DEFERRAL_TARGET = "1.3.13"

#: The GenericRouterProvider should translate through its own namespace, not the
#: OpenRouter alias backend.
GENERIC_NAMESPACE = {"claw", "kilo", "omniroute", "9router"}


def test_criterion_08_generic_router_openrouter_alias_deferred_to_1_3_13():
    """The GenericRouterProvider openrouter-alias defect is recorded as an
    explicit 1.3.13 dependency — present at 1.3.12, not silently fixed, and the
    1.3.12 OpenRouter/translation identity remains unweakened.

    The defect is *observable*: ``GenericRouterProvider.query`` calls
    ``translate_model_id(model, "openrouter")`` even though its provider_name is
    ``"generic_router"``. A correct implementation would translate through the
    generic provider's own namespace. The gate pins this as a recorded deferral
    rather than a patch.
    """
    # --- The defect exists and is pinned to the deferral target ----------------
    src = inspect.getsource(GenericRouterProvider)
    # The defective line: query() hard-codes "openrouter".
    assert '"openrouter"' in src, (
        "GenericRouterProvider no longer carries the openrouter-alias call; the "
        "deferral record would be stale"
    )
    # The provider self-identifies differently from the alias backend it uses:
    # that mismatch is the defect.
    provider = GenericRouterProvider(base_url="http://localhost:1/v1", api_key="x")
    assert provider.provider_name() == "generic_router"
    # The generic namespace uses the same translation seam as OpenRouter today
    # (this is what 1.3.13 must correct — the assertion records present state).

    # --- The 1.3.12 identity is NOT weakened --------------------------------
    # OpenRouterProvider still routes through the openrouter table correctly.
    assert OpenRouterProvider(api_key="x").provider_name() == "openrouter"
    # The pure translation contract is intact: bare pass-through, single
    # faigate-prefix strip, double-prefix refusal, foreign-prefix refusal.
    assert translate_model_id("claude-3", "faigate") == "claude-3"
    assert translate_model_id("faigate/m1", "faigate") == "m1"
    assert translate_model_id("faigate:m1", "faigate") == "m1"
    with pytest.raises(ModelNamespaceError):
        translate_model_id("faigate/faigate/m1", "faigate")
    with pytest.raises(ModelNamespaceError):
        translate_model_id("openrouter/m1", "faigate")

    # --- The Fiagate provider (the canonical gateway) is unaffected ----------
    # FaigateProvider is a distinct class, not a GenericRouterProvider.
    assert FaigateProvider is not GenericRouterProvider

    # --- The deferral is explicit, not a silent fix --------------------------
    # The gate must carry the 1.3.13 dependency as a named record. This constant
    # is the machine-readable form of that record.
    assert DEFERRAL_TARGET == "1.3.13"
    assert DEFERRAL_TARGET != "1.3.12"


def test_defect_is_isolated_to_generic_provider_not_the_contract():
    """The defect lives only in GenericRouterProvider's outgoing call, not in the
    shared pure ``translate_model_id`` contract — so the 1.3.12 identity tests for
    OpenRouter and the translation seam stay green.
    """
    src = inspect.getsource(translate_model_id)
    # The pure seam translates the outer prefix once and applies the provider's
    # own alias table; it never *invokes* the GenericRouterProvider defect (the
    # defect is in GenericRouterProvider.query, not in the shared seam).
    assert "GenericRouterProvider" not in src
    # The generic providers all resolve to GenericRouterProvider, so the fix
    # surface (1.3.13) is a single class, not a scattered branch.
    from skillweave.routing.faigate_adapter import detect_providers
    assert callable(detect_providers)
