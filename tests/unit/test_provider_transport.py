"""Transport-level tests for the Faigate provider adapter (SW-RT-004, dispatch 1).

Three defects, proven at the adapter boundary without a live socket:

1. The HTTP timeout comes from configuration and reaches the socket. No provider
   hardcodes a socket timeout its caller believes it can set. RED PROOF: v1.3.5
   (478211f) hardcoded ``timeout=10`` inside ``_req``, so a 3310-character
   stage-1 prompt lost every model at exactly 10.0s before the caller's
   ``asyncio.wait_for(config.timeout_per_model)`` could fire.

2. A degraded council names why, not only who. A timeout error message carries
   the word ``timeout`` and the endpoint that timed out.

3. An empty completion is a failure, not an answer. ``query()`` returns
   ``choices[0].message.content``; for a reasoning model whose budget went to
   reasoning that is the empty string. No-content raises instead of passing
   through as a valid answer.
"""

import asyncio
import socket
import urllib.error

import pytest

from skillweave.routing import faigate_adapter as adapter


def _fake_faigate(mock_req):
    """A FaigateProvider whose _req is replaced with a deterministic stub."""

    class _Stub(adapter.FaigateProvider):
        def __init__(self):
            self.base_url = "http://127.0.0.1:9/v1"
            self.api_key = None

        def _req(self, path, method="GET", body=None, timeout=None):
            return mock_req(path, method, body, timeout)

    return _Stub()


# ── Criterion 1: the timeout reaches the socket ─────────────────────

def test_no_hardcoded_socket_timeout_default():
    # The caller configures the timeout via asyncio.wait_for; the adapter must
    # not impose a shorter socket cap behind its back. Omitting the timeout must
    # yield ``None`` (block until the OS default), not a hardcoded 10.0/30.0.
    received = {}

    def req(path, method, body, timeout):
        received["timeout"] = timeout
        return {"choices": [{"message": {"content": "yes"}}]}

    p = _fake_faigate(req)
    asyncio.run(p.query("faigate:m", [{"role": "user", "content": "hi"}], 0.5))
    assert received["timeout"] is None


def test_caller_timeout_reaches_the_socket():
    # A timeout passed by the caller is forwarded verbatim to _req/urlopen.
    received = {}

    def req(path, method, body, timeout):
        received["timeout"] = timeout
        return {"choices": [{"message": {"content": "yes"}}]}

    p = _fake_faigate(req)
    asyncio.run(p.query("faigate:m", [{"role": "user", "content": "hi"}], 0.5, timeout=42.0))
    assert received["timeout"] == 42.0


def test_provider_query_accepts_timeout_keyword():
    # Every CouncilProvider.query() must expose the timeout so a caller can set it.
    for cls in (
        adapter.FaigateProvider,
        adapter.OpenRouterProvider,
        adapter.GenericRouterProvider,
        adapter.SingleModelProvider,
    ):
        import inspect

        params = inspect.signature(cls.query).parameters
        assert "timeout" in params, f"{cls.__name__}.query must accept timeout"


# ── Criterion 2: the degraded council names why ──────────────────────

def test_timeout_error_names_timeout_and_endpoint():
    # A socket timeout produces an error string containing "timeout" and the URL.
    reason = socket.timeout("timed out")
    exc = urllib.error.URLError(reason)
    msg = adapter._describe_error(exc, "http://127.0.0.1:8090/v1/chat/completions")
    assert "timeout" in msg
    assert "127.0.0.1:8090/v1/chat/completions" in msg


def test_req_reports_timeout_cause():
    # FaigateProvider._req surfaces a timeout as an error dict with the cause.
    p = adapter.FaigateProvider(base_url="http://127.0.0.1:9/v1")

    def _boom(url, timeout=None):
        raise urllib.error.URLError(socket.timeout("timed out"))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(adapter.urllib.request, "urlopen", _boom)
        result = p._req("/chat/completions", "POST", {"model": "x"}, timeout=1.0)
    assert result["error"]
    assert "timeout" in result["error"]
    assert "127.0.0.1:9/v1/chat/completions" in result["error"]


# ── Criterion 3: empty completion is a failure ───────────────────────

def test_empty_completion_raises_not_answer():
    # A choices[0].message.content == "" response is reported as a failure and
    # must not pass through as a valid answer.
    def req(path, method, body, timeout):
        return {"choices": [{"message": {"content": ""}}]}

    p = _fake_faigate(req)
    with pytest.raises(RuntimeError, match="empty"):
        asyncio.run(p.query("faigate:m", [{"role": "user", "content": "hi"}], 0.5))


def test_nonempty_completion_returns_content():
    def req(path, method, body, timeout):
        return {"choices": [{"message": {"content": "the answer"}}]}

    p = _fake_faigate(req)
    assert (
        asyncio.run(p.query("faigate:m", [{"role": "user", "content": "hi"}], 0.5))
        == "the answer"
    )
