"""
Tests for capability-based routing enhancement.
"""

import os
from unittest.mock import patch
from src.skillweave.capability import (
    Capability,
    AgentType,
    CapabilityRegistry,
    CapabilityRouter,
    route_task,
)


def test_capability_enum():
    """Test capability enum values."""
    assert Capability.GENERATE_BLUEPRINT == "generate_blueprint"
    assert Capability.EXECUTE_PROMPTCHAIN == "execute_promptchain"
    assert len(list(Capability)) >= 5


def test_agent_type_enum():
    """Test agent type enum values."""
    assert AgentType.OPENCODE == "opencode"
    assert AgentType.CLAUDE_CODE == "claude_code"
    assert len(list(AgentType)) >= 3


def test_capability_registry_defaults():
    """Test default capability mappings."""
    registry = CapabilityRegistry()
    
    # Check that default capabilities are registered
    assert Capability.GENERATE_BLUEPRINT in registry.registry
    assert Capability.EXECUTE_PROMPTCHAIN in registry.registry
    assert Capability.EXECUTE_RELEASECHAIN in registry.registry
    
    # Check that opencode and claude_code are registered for basic capabilities
    agents = registry.get_agents_for_capability(Capability.GENERATE_BLUEPRINT)
    assert AgentType.OPENCODE in agents
    assert AgentType.CLAUDE_CODE in agents


def test_register_agent():
    """Test registering new agent capabilities."""
    registry = CapabilityRegistry()
    
    # Register a new agent
    registry.register_agent(AgentType.VSCODE, [Capability.CODE_GENERATION])
    
    agents = registry.get_agents_for_capability(Capability.CODE_GENERATION)
    assert AgentType.VSCODE in agents


def test_get_capabilities_for_agent():
    """Test getting capabilities for a specific agent."""
    registry = CapabilityRegistry()
    
    capabilities = registry.get_capabilities_for_agent(AgentType.OPENCODE)
    assert Capability.GENERATE_BLUEPRINT in capabilities
    assert Capability.EXECUTE_PROMPTCHAIN in capabilities


def test_route_task():
    """Test task routing with preferred agent."""
    registry = CapabilityRegistry()
    
    # Route with preferred agent available
    agent = registry.route_task(Capability.GENERATE_BLUEPRINT, preferred_agent=AgentType.OPENCODE)
    assert agent == AgentType.OPENCODE
    
    # Route with preferred agent not available (use default)
    agent = registry.route_task(Capability.GENERATE_BLUEPRINT, preferred_agent=AgentType.CURSOR)
    assert agent in [AgentType.OPENCODE, AgentType.CLAUDE_CODE]


def test_get_fallback_agent():
    """Test fallback agent selection."""
    registry = CapabilityRegistry()
    
    fallback = registry.get_fallback_agent(Capability.GENERATE_BLUEPRINT, AgentType.OPENCODE)
    assert fallback == AgentType.CLAUDE_CODE or fallback is None


@patch.dict(os.environ, {"RTK": "true"})
def test_capability_router_detection():
    """Test agent detection in router."""
    router = CapabilityRouter()
    
    # With RTK env var, opencode should be detected
    assert AgentType.OPENCODE in router.detected_agents
    # Claude Code should always be detected in our test environment
    assert AgentType.CLAUDE_CODE in router.detected_agents


def test_capability_router_route():
    """Test router routing decision."""
    router = CapabilityRouter()
    
    # Mock detection to control available agents
    router.detected_agents = {AgentType.OPENCODE, AgentType.CLAUDE_CODE}
    
    result = router.route(Capability.GENERATE_BLUEPRINT)
    
    assert "selected_agent" in result
    assert "available_agents" in result
    assert "fallback_agent" in result
    assert result["capability"] == "generate_blueprint"
    assert result["selected_agent"] in ["opencode", "claude_code"]


def test_route_task_function():
    """Test convenience route_task function."""
    with patch.dict(os.environ, {"RTK": "true"}):
        result = route_task("generate_blueprint")
        
        assert "selected_agent" in result
        assert result["capability"] == "generate_blueprint"
        assert result["selected_agent"] in ["opencode", "claude_code", "generic"]


def test_route_task_custom_capability():
    """Test routing for custom capability."""
    result = route_task("custom_capability")
    
    assert result["capability"] == "custom_capability"
    assert result["selected_agent"] == "generic"


def test_registry_to_dict():
    """Test registry serialization to dictionary."""
    registry = CapabilityRegistry()
    data = registry.to_dict()
    
    assert isinstance(data, dict)
    assert "generate_blueprint" in data
    assert isinstance(data["generate_blueprint"], list)
    assert "opencode" in data["generate_blueprint"] or "claude_code" in data["generate_blueprint"]