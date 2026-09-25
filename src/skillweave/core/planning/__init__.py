"""SkillWeave Core Planning & Decomposition Module (SW-PLAN-001).

Provides:
- Explicit decomposition metadata and decomposition plans.
- Dispatchability assessments and gates for decomposed units.
- Fibonacci point validation and dependency cycle detection.
- Unit eligibility and fail-closed dispatch validation.
"""

from .decomposition import (
    ComplexityLevel,
    CriterionCoverageError,
    DecompositionError,
    DecompositionMetadata,
    DecompositionPlan,
    DecompositionStrategy,
    DecompositionUnit,
    DependencyCycleError,
    FIBONACCI_POINTS,
    create_decomposition_plan,
)

from .dispatchability import (
    DispatchabilityAssessment,
    DispatchabilityError,
    DispatchabilityEvaluator,
    DispatchabilityRequirement,
    DispatchabilityStatus,
    evaluate_dispatchability,
    get_dispatchable_units,
    validate_dispatchability,
)

__all__ = [
    # Decomposition
    "ComplexityLevel",
    "CriterionCoverageError",
    "DecompositionError",
    "DecompositionMetadata",
    "DecompositionPlan",
    "DecompositionStrategy",
    "DecompositionUnit",
    "DependencyCycleError",
    "FIBONACCI_POINTS",
    "create_decomposition_plan",
    # Dispatchability
    "DispatchabilityAssessment",
    "DispatchabilityError",
    "DispatchabilityEvaluator",
    "DispatchabilityRequirement",
    "DispatchabilityStatus",
    "evaluate_dispatchability",
    "get_dispatchable_units",
    "validate_dispatchability",
]
