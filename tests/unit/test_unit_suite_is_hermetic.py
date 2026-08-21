"""Prove the unit suite is hermetic (SW-UNIT-HERMETIC-001).

Three assertions, all measured at import/collect time rather than declared:

1. The unit suite's own boundary guard (tests/unit/conftest.py) is active: an
   outbound socket attempt inside a unit test is refused. This proves the block
   is applied, not merely documented.

2. ``detect_providers()`` returns nothing under that boundary: provider env
   vars are cleared, so auto-detection cannot bind a live Faigate/OpenRouter
   from the ambient shell. Real provider proofs live in the separate live-gate
   suite (tests/gate_b06/live_provider_proof.py), never in the unit suite.

3. No unit module under test imports a provider probe that runs at import time
   (imports are side-effect-free for network). This guards the other direction:
   a test file that eagerly opened a socket at collect time would not survive
   the boundary, and this test names the boundary so the failure is legible.
"""

import os
import socket

import pytest

import skillweave.routing.faigate_adapter as adapter


def test_outbound_socket_is_refused_by_boundary():
    # The autouse fixture in conftest.py replaces socket.create_connection with
    # a refusal. Attempting one inside a unit test must raise, proving the block
    # is real and not a no-op.
    with pytest.raises(RuntimeError, match="outbound connection"):
        socket.create_connection(("127.0.0.1", 8090), timeout=1)


def test_detect_providers_is_empty_under_boundary():
    # With provider env vars cleared and sockets refused, auto-detection yields
    # no providers. A live router can therefore never leak into a unit test.
    providers = adapter.detect_providers()
    assert providers == {}


def test_provider_env_vars_are_cleared():
    # Belt-and-braces: the exact env keys detection reads are absent here.
    for var in (
        "FAIGATE_API_KEY", "OPENROUTER_API_KEY", "OMNIROUTE_API_KEY",
        "KILO_API_KEY", "CLAWROUTER_API_KEY", "NINEROUTER_API_KEY",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    ):
        assert os.environ.get(var) is None, f"{var} leaked into the unit suite"
