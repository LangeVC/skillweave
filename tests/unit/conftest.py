"""Hermetic boundary for the unit suite (SW-UNIT-HERMETIC-001).

The unit suite must pass with the network blocked and with no live provider
reachable. Two mechanisms enforce this and make the boundary *proven*, not
declared:

1. Every outbound socket attempt (``socket.create_connection`` and
   ``socket.socket.connect``) is intercepted and refused. Any test that tries
   to reach a live provider fails loudly instead of quietly timing out or,
   worse, passing against a live router that happens to be up.

2. Every provider/router/API-key environment variable that ``detect_providers``
   (``skillweave.routing.faigate_adapter``) reads is cleared for the duration
   of the suite, so auto-detection is empty and deterministic regardless of
   the host shell. Real provider proofs live in the separate live-gate suite
   (``tests/gate_b06/live_provider_proof.py``), never here.

The guard is a *measured* contract: tests that bind a live provider must mock
``detect_providers`` (or the provider itself) exactly as
``tests/unit/test_model_availability.py`` already does, otherwise the socket
refusal surfaces the dependency.
"""

import os

import pytest

# Every environment variable ``detect_providers`` consults. Cleared so the
# unit suite cannot accidentally bind a real router from the ambient shell.
_PROVIDER_ENV_VARS = (
    "FAIGATE_API_KEY",
    "FAIGATE_BASE_URL",
    "FAIGATE_HOST",
    "FAIGATE_PORT",
    "OPENROUTER_API_KEY",
    "CLAWROUTER_API_KEY",
    "CLAWROUTER_BASE_URL",
    "KILO_API_KEY",
    "KILO_BASE_URL",
    "OMNIROUTE_API_KEY",
    "OMNIROUTE_BASE_URL",
    "OMNIROUTE_PORT",
    "NINEROUTER_API_KEY",
    "NINEROUTER_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "COUNCIL_MODEL",
    "OPENAI_MODEL",
    "DEFAULT_MODEL",
    "ANTHROPIC_API_KEY",
)


class _NetworkBlocked(RuntimeError):
    """Raised when a unit test attempts an outbound connection."""


@pytest.fixture(autouse=True)
def _hermetic_unit_boundary(monkeypatch):
    """Block every outbound socket and clear provider env vars for the suite."""
    import socket

    def _blocked_create_connection(*args, **kwargs):
        addr = args[0] if args else kwargs.get("address")
        raise _NetworkBlocked(
            "unit suite attempted an outbound connection to "
            f"{addr!r}; unit tests must not reach a live provider "
            "(see tests/unit/conftest.py and tests/gate_b06/)"
        )

    def _blocked_connect(self, *args, **kwargs):
        raise _NetworkBlocked(
            "unit suite attempted a socket connect; unit tests must not reach "
            "a live provider (see tests/unit/conftest.py and tests/gate_b06/)"
        )

    monkeypatch.setattr(socket, "create_connection", _blocked_create_connection)
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)

    for var in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    # Faigate auto-detection also consults ~/.faigate and the tokens file on
    # disk; neutralise those so a host-local Faigate install cannot leak into
    # the unit suite (the unit boundary must be host-independent).
    _real_exists = os.path.exists
    _provider_files = {
        os.path.expanduser("~/.faigate"),
        os.path.expanduser("~/.config/faigate/tokens.json"),
    }

    def _exists_without_provider_files(path):
        if path in _provider_files:
            return False
        return _real_exists(path)

    monkeypatch.setattr(os.path, "exists", _exists_without_provider_files)

    yield
