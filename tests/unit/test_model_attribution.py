"""Model attribution: the answering model survives the transport.

SW-CN-001 / dispatch 1 of 1. The premise is measured against a live Faigate:
a router silently substitutes a different model (HTTP 200, well-formed answer,
no error field) and the ONLY place the truth surfaced was the ``model`` field of
the response envelope — which ``query()`` used to throw away.

These tests prove the adapter now reads that field and carries it per seat,
without changing the ``str`` contract the council engine depends on (engine.py
is out of scope here and must not be modified).
"""

import asyncio

import pytest

from skillweave.routing.faigate_adapter import (
    AttributedResponse,
    FaigateProvider,
    OpenRouterProvider,
    _extract_answer,
)


def _run(coro):
    return asyncio.run(coro)


class _EnvelopeProvider(FaigateProvider):
    """Fake provider that returns a canned chat-completions envelope."""

    def __init__(self, envelope):
        super().__init__(base_url="http://example.invalid", api_key="x")
        self._envelope = envelope

    def _req(self, path, method="GET", body=None):
        return self._envelope


def test_answering_model_read_from_envelope():
    """Requesting sonnet records deepseek-v4-flash when the envelope says so.

    RED PROOF (criterion 1): against v1.3.5 this recorded ``sonnet`` because
    ``query()`` returned only ``choices[0].message.content`` and discarded
    ``model``. Now it records the answering model from the envelope.
    """
    envelope = {
        "model": "deepseek-v4-flash",
        "choices": [{"message": {"content": "answer text"}}],
    }
    provider = _EnvelopeProvider(envelope)
    response = _run(provider.query("sonnet", [{"role": "user", "content": "q"}]))

    assert isinstance(response, str)
    assert response == "answer text"
    assert response.requested_model == "sonnet"
    assert response.answering_model == "deepseek-v4-flash"


def test_requested_and_answering_both_named():
    """When they differ, both ids are surfaced — the record is not collapsed."""
    response = AttributedResponse(
        "body", requested_model="gemini-pro", answering_model="gpt-4o"
    )
    assert response.requested_model == "gemini-pro"
    assert response.answering_model == "gpt-4o"
    assert response.requested_model != response.answering_model


def test_fallback_when_envelope_omits_model():
    """An envelope without a ``model`` field falls back to the requested id.

    The provider never fabricates a model; it keeps the requested one rather
    than crashing, so the run record stays cheap and truthful about the
    transport it actually saw.
    """
    response = _extract_answer(
        {"choices": [{"message": {"content": "hi"}}]}, requested_model="sonnet"
    )
    assert response.answering_model == "sonnet"
    assert response == "hi"


def test_stays_a_plain_string_for_engine():
    """The return value behaves as a str so engine.py needs no change."""
    response = AttributedResponse("text", requested_model="a", answering_model="b")
    assert response == "text"
    assert f"got {response}" == "got text"
    assert bool(response) is True
    assert response[:2] == "te"


@pytest.mark.parametrize(
    "provider_factory",
    [lambda: OpenRouterProvider(base_url="http://example.invalid", api_key="k")],
)
def test_openrouter_query_reads_envelope_model(provider_factory):
    """OpenRouter's query path hits the same envelope reader."""
    provider = provider_factory()
    provider._req = lambda path, body=None, method="POST": {
        "model": "actual-model",
        "choices": [{"message": {"content": "content"}}],
    }
    response = _run(provider.query("requested", [{"role": "user", "content": "q"}]))
    assert response.answering_model == "actual-model"
    assert response.requested_model == "requested"
