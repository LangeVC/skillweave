"""
Capability-based routing enhancement for SkillWeave Next Level.

Provides basic capability registry and routing for dynamic agent detection.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from enum import Enum
import yaml


class Capability(str, Enum):
    """Capabilities that agents/skills can provide."""
    GENERATE_BLUEPRINT = "generate_blueprint"
    EXECUTE_PROMPTCHAIN = "execute_promptchain"
    GENERATE_PROMPTCHAIN = "generate_promptchain"
    VALIDATE_PROMPTCHAIN = "validate_promptchain"
    EXECUTE_RELEASECHAIN = "execute_releasechain"
    # Generic capabilities
    FILE_OPERATIONS = "file_operations"
    CODE_GENERATION = "code_generation"
    TEST_EXECUTION = "test_execution"
    DEPLOYMENT = "deployment"


class AgentType(str, Enum):
    """Types of agents that can be integrated."""
    OPENCODE = "opencode"
    CLAUDE_CODE = "claude_code"
    CURSOR = "cursor"
    VSCODE = "vscode"
    GENERIC = "generic"


class CapabilityRegistry:
    """Registry of capabilities and available agents."""
    
    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.skills_dir = self.project_root / "skills"
        self.registry: Dict[Capability, Set[AgentType]] = {}
        self._load_default_registry()
        self._scan_available_skills()
    
    def _load_default_registry(self) -> None:
        """Load default capability mapping."""
        # Default mapping of capabilities to agent types
        default_mapping = {
            Capability.GENERATE_BLUEPRINT: {AgentType.OPENCODE, AgentType.CLAUDE_CODE},
            Capability.EXECUTE_PROMPTCHAIN: {AgentType.OPENCODE, AgentType.CLAUDE_CODE},
            Capability.GENERATE_PROMPTCHAIN: {AgentType.OPENCODE, AgentType.CLAUDE_CODE},
            Capability.VALIDATE_PROMPTCHAIN: {AgentType.OPENCODE, AgentType.CLAUDE_CODE},
            Capability.EXECUTE_RELEASECHAIN: {AgentType.OPENCODE, AgentType.CLAUDE_CODE},
            Capability.FILE_OPERATIONS: {AgentType.OPENCODE, AgentType.CLAUDE_CODE, AgentType.CURSOR, AgentType.VSCODE},
            Capability.CODE_GENERATION: {AgentType.OPENCODE, AgentType.CLAUDE_CODE, AgentType.CURSOR},
            Capability.TEST_EXECUTION: {AgentType.OPENCODE, AgentType.CLAUDE_CODE},
            Capability.DEPLOYMENT: {AgentType.OPENCODE},
        }
        
        for capability, agents in default_mapping.items():
            self.registry[capability] = agents.copy()
    
    def _scan_available_skills(self) -> None:
        """Scan skills directory to detect available skills."""
        if not self.skills_dir.exists():
            return
        
        # Map skill directories to capabilities
        skill_to_capability = {
            "skillweave-blueprint": Capability.GENERATE_BLUEPRINT,
            "skillweave-promptchain-execute": Capability.EXECUTE_PROMPTCHAIN,
            "skillweave-promptchain-generate": Capability.GENERATE_PROMPTCHAIN,
            "skillweave-promptchain-validate": Capability.VALIDATE_PROMPTCHAIN,
            "skillweave-releasechain": Capability.EXECUTE_RELEASECHAIN,
        }
        
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_name = skill_dir.name
                if skill_name in skill_to_capability:
                    capability = skill_to_capability[skill_name]
                    # Mark this capability as available via skill
                    # (We assume the skill is available in the current environment)
                    # For now, we just note it's available
                    pass
    
    def register_agent(self, agent_type: AgentType, capabilities: List[Capability]) -> None:
        """Register an agent with its capabilities."""
        for capability in capabilities:
            if capability not in self.registry:
                self.registry[capability] = set()
            self.registry[capability].add(agent_type)
    
    def get_agents_for_capability(self, capability: Capability) -> List[AgentType]:
        """Get list of agents that provide a capability."""
        agents = self.registry.get(capability, set())
        return sorted(list(agents), key=lambda x: x.value)
    
    def get_capabilities_for_agent(self, agent_type: AgentType) -> List[Capability]:
        """Get capabilities provided by an agent."""
        capabilities = []
        for capability, agents in self.registry.items():
            if agent_type in agents:
                capabilities.append(capability)
        return sorted(capabilities, key=lambda x: x.value)
    
    def route_task(self, capability: Capability, preferred_agent: Optional[AgentType] = None) -> Optional[AgentType]:
        """
        Route a task to the best available agent.
        
        Args:
            capability: Required capability
            preferred_agent: Preferred agent type (if available)
            
        Returns:
            Agent type to use, or None if no agent available
        """
        available_agents = self.get_agents_for_capability(capability)
        if not available_agents:
            return None
        
        # If preferred agent is available, use it
        if preferred_agent and preferred_agent in available_agents:
            return preferred_agent
        
        # Otherwise, use the first available agent
        # (In a real implementation, we might have prioritization logic)
        return available_agents[0]
    
    def get_fallback_agent(self, capability: Capability, unavailable_agent: AgentType) -> Optional[AgentType]:
        """Get fallback agent when primary agent is unavailable."""
        available_agents = self.get_agents_for_capability(capability)
        available_agents = [a for a in available_agents if a != unavailable_agent]
        return available_agents[0] if available_agents else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert registry to dictionary."""
        result = {}
        for capability, agents in self.registry.items():
            result[capability.value] = [agent.value for agent in agents]
        return result


class CapabilityRouter:
    """High-level router for capability-based task assignment."""
    
    def __init__(self, project_root: Optional[str] = None):
        self.registry = CapabilityRegistry(project_root)
        self.detected_agents = self._detect_available_agents()
    
    def _detect_available_agents(self) -> Set[AgentType]:
        """
        Detect available agents in the current environment.
        
        This is a prototype implementation. In a real environment,
        this would scan installed tools, check environment variables, etc.
        """
        available = set()
        
        # Simple detection based on common environment indicators
        env_vars = os.environ
        
        # Check for opencode (SkillWeave's primary environment)
        if "RTK" in env_vars or "OPENCODE" in env_vars:
            available.add(AgentType.OPENCODE)
        
        # Assume Claude Code is available (since we're likely running in it)
        available.add(AgentType.CLAUDE_CODE)
        
        # Check for Cursor (would have specific env vars)
        if "CURSOR" in env_vars:
            available.add(AgentType.CURSOR)
        
        # VS Code detection
        if "VSCODE_PID" in env_vars or "VSCODE_IPC_HOOK" in env_vars:
            available.add(AgentType.VSCODE)
        
        # Always include generic as fallback
        available.add(AgentType.GENERIC)
        
        return available
    
    def route(self, capability: Capability, preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Route a task to an available agent.
        
        Args:
            capability: Required capability
            preferences: Routing preferences (e.g., {"preferred_agent": "claude_code"})
            
        Returns:
            Routing decision with agent and fallback options
        """
        preferred_agent = None
        if preferences and "preferred_agent" in preferences:
            try:
                preferred_agent = AgentType(preferences["preferred_agent"])
            except ValueError:
                pass
        
        # Get available agents for this capability
        all_agents = self.registry.get_agents_for_capability(capability)
        available_agents = [agent for agent in all_agents if agent in self.detected_agents]
        
        # If no agents available for capability, try generic
        if not available_agents:
            available_agents = [AgentType.GENERIC]
        
        # Select agent
        selected_agent = None
        if preferred_agent and preferred_agent in available_agents:
            selected_agent = preferred_agent
        else:
            selected_agent = available_agents[0] if available_agents else AgentType.GENERIC
        
        # Determine fallback
        fallback_agent = None
        if len(available_agents) > 1:
            fallback_agent = available_agents[1]
        else:
            fallback_agent = self.registry.get_fallback_agent(capability, selected_agent)
        
        return {
            "capability": capability.value,
            "selected_agent": selected_agent.value,
            "available_agents": [agent.value for agent in available_agents],
            "fallback_agent": fallback_agent.value if fallback_agent else None,
            "routing_reason": f"Selected {selected_agent.value} based on availability and preferences"
        }


def get_capability_router(project_root: Optional[str] = None) -> CapabilityRouter:
    """Get capability router for project root."""
    return CapabilityRouter(project_root)


def route_task(capability: str, project_root: Optional[str] = None, preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function to route a task."""
    router = get_capability_router(project_root)
    try:
        capability_enum = Capability(capability)
    except ValueError:
        # If capability not in enum, treat as custom capability
        # For prototype, route to generic agent
        return {
            "capability": capability,
            "selected_agent": AgentType.GENERIC.value,
            "available_agents": [AgentType.GENERIC.value],
            "fallback_agent": None,
            "routing_reason": f"Custom capability routed to generic agent"
        }
    
    return router.route(capability_enum, preferences)