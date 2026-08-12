"""SkillWeave core package.

GLE-020: The core package must be importable even when optional subpackages
are absent, so a whitelabel consumer can embed less than everything (PRD 2.2,
2.3).  ``import skillweave`` must never require ``skillweave.runtime``.

Optional subpackages are declared here rather than implied: a subpackage that
is safe to be absent is listed in ``OPTIONAL_SUBPACKAGES``.  The core modules
re-exported by this package must not top-level import any of them (enforced by
``tests/integration/test_gle020_import_cycle.py``).  Names that transitively
reach an optional subpackage are resolved lazily via PEP 562 module
``__getattr__`` — the public API is unchanged, only the import moment moves
from package load to first access.
"""

# Declared optional subpackages (GLE-020).  ``runtime`` may be physically
# absent in a whitelabel / pre-v1.3 install; ``import skillweave`` must still
# succeed.  This list is the explicit, non-implicit contract.
OPTIONAL_SUBPACKAGES = ("runtime",)

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

from .execution_checklist import ChecklistLoopEngine
from .execution_memory import ExecutionMemory
from .sidecar_manager import SidecarManager, SidecarSpec

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

    # Execution System
    "BatchPlanner", "BatchPlan", "BatchSpec",
    "RalphLoopState", "RalphLoopStateMachine",
    "RetryHandler", "RetryBudget",
    "GatePolicy", "BinaryGateResult",
    "ChecklistLoopEngine",
    "ExecutionMemory",
    "ExecutionIntegration",
    "EventLogger", "LogLevel", "Timer", "ReportGenerator",
    "SidecarManager", "SidecarSpec",
]

# Names whose module graph transitively reaches an optional subpackage
# (GLE-020).  Resolved lazily via `__getattr__` below, so `import skillweave`
# does not force `skillweave.runtime`.
_LAZY_NAMES = {
    "BatchPlanner": "skillweave.execution.batch_planner",
    "BatchPlan": "skillweave.execution.batch_planner",
    "BatchSpec": "skillweave.execution.batch_planner",
    "RalphLoopState": "skillweave.execution.state_machine",
    "RalphLoopStateMachine": "skillweave.execution.state_machine",
    "RetryHandler": "skillweave.execution.retry",
    "RetryBudget": "skillweave.execution.retry",
    "GatePolicy": "skillweave.execution.gate_policy",
    "BinaryGateResult": "skillweave.execution.gate_policy",
    "ExecutionIntegration": "skillweave.execution_integration",
    "EventLogger": "skillweave.observation.event_logger",
    "LogLevel": "skillweave.observation.event_logger",
    "Timer": "skillweave.observation.timing",
    "ReportGenerator": "skillweave.observation.report_generator",
}


def __getattr__(name: str):
    """PEP 562 lazy attribute resolution.

    Keeps the public API byte-for-byte identically reachable as
    ``skillweave.<Name>`` while deferring imports that would otherwise drag
    an optional subpackage (e.g. ``skillweave.runtime``) into the package
    load.  Without this, `import skillweave` fails when an optional
    subpackage is physically absent — the exact defect GLE-020 removes.
    """
    module_name = _LAZY_NAMES.get(name)
    if module_name is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        )
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value
