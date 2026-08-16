"""
GLE-020 frozen public API — the contract the lazy import must preserve.

This is the authoritative, frozen name list of ``skillweave``'s public API.
It is captured from ``skillweave/__init__.py::__all__`` at v1.3.0 (the point
just before GLE-020).  GLE-020 must leave every one of these reachable as
``skillweave.<Name>`` by resolving it lazily — the test asserts against this
list, not against memory.

Do not change these lists as part of implementing GLE-020.  They are the
regression contract.  Additions to the API belong in both the package and
here, explicitly, and only when intended.
"""

# Every name ``skillweave`` exported at v1.3.0.  Frozen.
FROZEN_API = (
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
    # Execution System (lazy — transitively reaches skillweave.runtime)
    "BatchPlanner",
    "BatchPlan",
    "BatchSpec",
    "RalphLoopState",
    "RalphLoopStateMachine",
    "RetryHandler",
    "RetryBudget",
    "GatePolicy",
    "BinaryGateResult",
    "ChecklistLoopEngine",
    "ExecutionMemory",
    "ExecutionIntegration",
    "EventLogger",
    "LogLevel",
    "Timer",
    "ReportGenerator",
    "SidecarManager",
    "SidecarSpec",
)

# The names that must remain reachable even when an optional subpackage
# (runtime) is physically absent: the runtime-free core.
FROZEN_CORE = tuple(
    n
    for n in FROZEN_API
    if not n.startswith(
        (
            "Batch", "Ralph", "Retry", "Gate", "Binary",
            "Event", "LogLevel", "Timer", "Report",
            "ExecutionIntegration",
        )
    )
)
