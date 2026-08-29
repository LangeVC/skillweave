"""Provider-specific adapter mappings (SW1311-ROUTING-RECONCILE-001).

The two mappings that shipped on ``main`` after the 1.3.11 gate —
``FAIGATE_MAP`` and ``OPENROUTER_MAP`` — previously existed only in ``src/``
and were never tested. They are now the single, provider-specific backend of
``translate_model_id``: namespace translation happens exactly once, then the
resolved provider-native alias is mapped to the concrete target the router
expects, with no second translation path and no inline ``.replace`` at a call
site.

These tests pin, per map:
1. a mapped alias resolves to its target id;
2. an unmapped alias passes through unchanged;
3. namespace translation still applies exactly once, and a foreign or doubled
   prefix still raises ``ModelNamespaceError`` before any mapping;
4. the requested model identity survives into the response and is not
   overwritten by the provider's echo (the intent of ``e9c4e53``).
"""

import asyncio

import pytest

from skillweave.routing.faigate_adapter import (
    FAIGATE_MAP,
    OPENROUTER_MAP,
    FaigateProvider,
    ModelNamespaceError,
    _extract_answer,
    translate_model_id,
)


def _run(coro):
    return asyncio.run(coro)


def test_faigate_map_translates_known_aliases():
    for alias, target in FAIGATE_MAP.items():
        assert translate_model_id(alias, "faigate") == target


def test_openrouter_map_translates_known_aliases():
    for alias, target in OPENROUTER_MAP.items():
        assert translate_model_id(alias, "openrouter") == target


def test_unmapped_alias_passes_through_unchanged():
    assert translate_model_id("no-such-alias-xyzzy", "faigate") == "no-such-alias-xyzzy"
    assert translate_model_id("no-such-alias-xyzzy", "openrouter") == "no-such-alias-xyzzy"


def test_faigate_prefix_stripped_then_mapped():
    # The outer gateway prefix is removed exactly once, then the alias is mapped.
    assert translate_model_id("faigate/sonnet") == "anthropic-sonnet"
    assert translate_model_id("faigate:sonnet") == "anthropic-sonnet"


def test_doubled_prefix_still_raises_before_mapping():
    with pytest.raises(ModelNamespaceError):
        translate_model_id("faigate/faigate/sonnet")
    with pytest.raises(ModelNamespaceError):
        translate_model_id("faigate:faigate:sonnet")


def test_foreign_prefix_still_raises_before_mapping():
    with pytest.raises(ModelNamespaceError):
        translate_model_id("openrouter/sonnet")
    with pytest.raises(ModelNamespaceError):
        translate_model_id("openrouter:sonnet")


def test_openrouter_prefix_is_foreign_and_raises():
    # ``openrouter/`` is not a valid outer namespace for the faigate adapter;
    # the openrouter map is reached only through a bare alias, not a prefix.
    with pytest.raises(ModelNamespaceError):
        translate_model_id("openrouter/sonnet", "openrouter")


def test_default_provider_is_faigate():
    assert translate_model_id("sonnet") == "anthropic-sonnet"


def test_requested_identity_survives_the_provider_echo():
    # e9c4e53's intent: the provider's echo must not overwrite the requested
    # identity. A mapped request records the alias as requested, the mapped
    # target as resolved, and the envelope's ``model`` as answering.
    envelope = {
        "model": "anthropic-sonnet",
        "choices": [{"message": {"content": "answer text"}}],
    }
    response = _extract_answer(envelope, "sonnet", "faigate")
    assert response.requested_model == "sonnet"
    assert response.answering_model == "anthropic-sonnet"
    assert response.provider == "faigate"


class _EnvelopeProvider(FaigateProvider):
    """Fake provider returning a canned envelope and capturing the sent body."""

    def __init__(self, envelope):
        super().__init__(base_url="http://example.invalid", api_key="x")
        self._envelope = envelope
        self.sent_model = None

    def _req(self, path, method="GET", body=None, timeout=None):
        self.sent_model = body.get("model") if body else None
        return self._envelope


def test_query_sends_mapped_target_but_keeps_requested_alias():
    # The body carries the mapped target; the requested identity stays the alias
    # the caller handed in, and the envelope ``model`` becomes the answering id.
    provider = _EnvelopeProvider({
        "model": "anthropic-sonnet",
        "choices": [{"message": {"content": "answer text"}}],
    })
    response = _run(provider.query("sonnet", [{"role": "user", "content": "q"}]))
    assert provider.sent_model == "anthropic-sonnet"
    assert response.requested_model == "sonnet"
    assert response.answering_model == "anthropic-sonnet"
    assert response.provider == "faigate"


def test_query_mapping_never_uses_inline_replace():
    # There is exactly one translation path; the FaigateProvider does not mutate
    # the id via a raw ``replace`` — the namespace-owned translation owns it.
    import inspect

    src = inspect.getsource(FaigateProvider.query)
    assert ".replace(" not in src
