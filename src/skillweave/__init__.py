"""SkillWeave core package."""

from .persistence import (
    SkillWeaveConfig,
    SkillWeavePersistence,
    RiskMode,
    ensure_skillweave_folder,
    get_config,
    get_persistence,
    get_mode_only,
    is_feature_enabled,
    get_mode_specific_setting,
)

from .checklist import (
    Checklist,
    ChecklistItem,
    ChecklistItemStatus,
    ChecklistParser,
    ChecklistManager,
)

from .design_thinking import (
    DesignThinkingLens,
    DesignRule,
    DesignRuleDefinition,
    DesignThinkingConfig,
)

from .mode_manager import (
    ModeManager,
    ModeBehavior,
)

from .next_level import SkillWeaveNextLevel
from .templates import Template, TemplateManager, get_template_manager
from .community_knowhow import PatternExtractor, RepoCleanupRecommender
from .capability import (
    Capability,
    AgentType,
    CapabilityRegistry,
    CapabilityRouter,
    get_capability_router,
    route_task,
)

__all__ = [
    # Persistence
    "SkillWeaveConfig",
    "SkillWeavePersistence",
    "RiskMode",
    "ensure_skillweave_folder",
    "get_config",
    "get_persistence",
    "get_mode_only",
    "is_feature_enabled",
    "get_mode_specific_setting",
    
    # Checklist
    "Checklist",
    "ChecklistItem",
    "ChecklistItemStatus",
    "ChecklistParser",
    "ChecklistManager",
    
    # Design Thinking
    "DesignThinkingLens",
    "DesignRule",
    "DesignRuleDefinition",
    "DesignThinkingConfig",
    
    # Mode Manager
    "ModeManager",
    "ModeBehavior",
    
    # Next Level Integration
    "SkillWeaveNextLevel",
    
    # Templates
    "Template",
    "TemplateManager",
    "get_template_manager",
    
    # Community Know-How
    "PatternExtractor",
    "RepoCleanupRecommender",
    
    # Capability-based Routing
    "Capability",
    "AgentType",
    "CapabilityRegistry",
    "CapabilityRouter",
    "get_capability_router",
    "route_task",
]
