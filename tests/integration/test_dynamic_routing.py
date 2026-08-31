import pytest
import asyncio
from unittest.mock import patch

from skillweave.routing.faigate_adapter import (
    FaigateProvider,
    AttributedResponse
)
from skillweave.routing.policy import RoutingPolicyEngine

from tests.mocks.faigate_server import run_server


@pytest.fixture(scope="module")
def mock_server():
    server, thread = run_server(port=0)
    port = server.server_port
    yield port
    server.shutdown()


@pytest.mark.asyncio
async def test_anti_masking_logic(mock_server):
    """Prove that Anti-Masking logic works (deduplication of silent fallbacks)."""
    provider = FaigateProvider(base_url=f"http://127.0.0.1:{mock_server}/v1", api_key="test")
    
    # Simulate a substitution scenario: request gpt-4o, served by deepseek-v4-flash
    requested_model = "gpt-4o"
    result = await provider.query(requested_model, [{"role": "user", "content": "hi"}])
    
    # result should be AttributedResponse and have is_substituted set to True
    assert isinstance(result, AttributedResponse)
    assert result.is_substituted is True
    assert result.requested_model == "gpt-4o"
    assert result.answering_model == "gpt-4o" # As per our mock
    assert result.served_by == "deepseek-v4-flash" # Mock sets this in headers

    # Test when requested matches served
    result2 = await provider.query("deepseek-v4-flash", [{"role": "user", "content": "hi"}])
    assert isinstance(result2, AttributedResponse)
    assert result2.is_substituted is False
    assert result2.requested_model == "deepseek-v4-flash"
    assert result2.answering_model == "deepseek-v4-flash"
    assert result2.served_by == "deepseek-v4-flash"


def test_capabilities_routing_policy_engine():
    """Prove that the capabilities routing policy engine correctly finds replacements when primary fails or is masked."""
    # Mock capability cache
    adapter_cache = {
        "gpt-4o": {"capabilities": ["vision", "reasoning"], "cost": 0.05},
        "deepseek-v4-pro": {"capabilities": ["reasoning", "coding"], "cost": 0.03},
        "deepseek-v4-flash": {"capabilities": ["reasoning", "coding"], "cost": 0.01},
        "claude-3.5-sonnet": {"capabilities": ["vision", "reasoning", "coding"], "cost": 0.04},
    }
    
    engine = RoutingPolicyEngine(adapter_cache)
    
    # Requested capabilities: reasoning and coding
    caps = ["reasoning", "coding"]
    
    # Best match should be deepseek-v4-flash (lowest cost)
    best_match = engine.get_best_match(caps)
    assert best_match == "deepseek-v4-flash"
    
    # What if deepseek-v4-flash fails or is masked?
    unavailable = ["deepseek-v4-flash"]
    replacement = engine.get_with_graceful_degradation(caps, unavailable_models=unavailable)
    
    # Next lowest cost with reasoning and coding is deepseek-v4-pro
    assert replacement == "deepseek-v4-pro"
    
    # If deepseek-v4-pro is also unavailable
    unavailable.append("deepseek-v4-pro")
    replacement2 = engine.get_with_graceful_degradation(caps, unavailable_models=unavailable)
    
    # Next is claude-3.5-sonnet
    assert replacement2 == "claude-3.5-sonnet"
    
    # What if all are unavailable?
    unavailable.append("claude-3.5-sonnet")
    replacement3 = engine.get_with_graceful_degradation(caps, unavailable_models=unavailable)
    
    assert replacement3 is None
