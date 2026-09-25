"""Dispatchability assessment and gates for planning (SW-PLAN-001).

This module evaluates whether a decomposed unit or lane meets all prerequisite
contract requirements to be dispatched safely:
- State checks (already completed, running, blocked by dependencies).
- Mutating contract validation (non-empty repo, full 40-hex base SHA, execution model).
- Role and capability requirements.
- Fail-closed validation for planning dispatch gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from .decomposition import DecompositionPlan, DecompositionUnit


class DispatchabilityStatus(str, Enum):
    """Evaluation status for unit dispatchability."""

    READY = "ready"
    BLOCKED = "blocked"
    INELIGIBLE = "ineligible"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FAILED = "failed"


class DispatchabilityError(ValueError):
    """Raised when a unit fails required dispatchability checks."""

    def __init__(self, message: str, *, unit_id: Optional[str] = None, reasons: Optional[List[str]] = None):
        super().__init__(message)
        self.unit_id = unit_id
        self.reasons = reasons or []


@dataclass
class DispatchabilityRequirement:
    """Pre-dispatch validation contract requirements."""

    require_repo_for_mutating: bool = True
    require_full_base_sha_for_mutating: bool = True
    require_execution_model_for_mutating: bool = True
    require_role: bool = True
    require_criteria_for_mutating: bool = False
    required_capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "require_repo_for_mutating": self.require_repo_for_mutating,
            "require_full_base_sha_for_mutating": self.require_full_base_sha_for_mutating,
            "require_execution_model_for_mutating": self.require_execution_model_for_mutating,
            "require_role": self.require_role,
            "require_criteria_for_mutating": self.require_criteria_for_mutating,
            "required_capabilities": list(self.required_capabilities),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DispatchabilityRequirement:
        return cls(
            require_repo_for_mutating=bool(data.get("require_repo_for_mutating", True)),
            require_full_base_sha_for_mutating=bool(data.get("require_full_base_sha_for_mutating", True)),
            require_execution_model_for_mutating=bool(data.get("require_execution_model_for_mutating", True)),
            require_role=bool(data.get("require_role", True)),
            require_criteria_for_mutating=bool(data.get("require_criteria_for_mutating", False)),
            required_capabilities=list(data.get("required_capabilities") or []),
        )


@dataclass
class DispatchabilityAssessment:
    """The result of evaluating a unit's dispatchability."""

    unit_id: str
    is_dispatchable: bool
    status: DispatchabilityStatus
    reasons: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    missing_requirements: List[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "is_dispatchable": self.is_dispatchable,
            "status": self.status.value if isinstance(self.status, DispatchabilityStatus) else str(self.status),
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "missing_requirements": list(self.missing_requirements),
            "evaluated_at": self.evaluated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DispatchabilityAssessment:
        raw_status = data.get("status", DispatchabilityStatus.INELIGIBLE.value)
        try:
            status = DispatchabilityStatus(raw_status)
        except ValueError:
            status = DispatchabilityStatus.INELIGIBLE

        return cls(
            unit_id=str(data.get("unit_id", "")),
            is_dispatchable=bool(data.get("is_dispatchable", False)),
            status=status,
            reasons=list(data.get("reasons") or []),
            blockers=list(data.get("blockers") or []),
            missing_requirements=list(data.get("missing_requirements") or []),
            evaluated_at=str(data.get("evaluated_at") or datetime.now(timezone.utc).isoformat()),
            metadata=dict(data.get("metadata") or {}),
        )


def _is_full_sha(value: Any) -> bool:
    """Verify if a string is a 40-character hexadecimal git SHA."""
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


class DispatchabilityEvaluator:
    """Evaluates units against execution status and dispatchability requirements."""

    def __init__(self, requirements: Optional[DispatchabilityRequirement] = None):
        self.requirements = requirements or DispatchabilityRequirement()

    def assess_unit(
        self,
        unit: DecompositionUnit,
        completed_unit_ids: Sequence[str] = (),
        running_unit_ids: Sequence[str] = (),
        failed_unit_ids: Sequence[str] = (),
    ) -> DispatchabilityAssessment:
        """Evaluate a single unit for dispatchability."""
        completed_set: Set[str] = set(completed_unit_ids)
        running_set: Set[str] = set(running_unit_ids)
        failed_set: Set[str] = set(failed_unit_ids)

        reasons: List[str] = []
        blockers: List[str] = []
        missing: List[str] = []

        # 1. State checks
        if unit.id in completed_set:
            return DispatchabilityAssessment(
                unit_id=unit.id,
                is_dispatchable=False,
                status=DispatchabilityStatus.COMPLETED,
                reasons=[f"Unit '{unit.id}' is already completed."],
            )

        if unit.id in running_set:
            return DispatchabilityAssessment(
                unit_id=unit.id,
                is_dispatchable=False,
                status=DispatchabilityStatus.DISPATCHED,
                reasons=[f"Unit '{unit.id}' is currently dispatched and running."],
            )

        if unit.id in failed_set:
            return DispatchabilityAssessment(
                unit_id=unit.id,
                is_dispatchable=False,
                status=DispatchabilityStatus.FAILED,
                reasons=[f"Unit '{unit.id}' previously failed."],
            )

        # 2. Dependency blocker checks
        unmet_deps = [dep for dep in unit.depends_on if dep not in completed_set]
        if unmet_deps:
            blockers.extend(unmet_deps)
            reasons.append(f"Unit '{unit.id}' has unresolved dependencies: {', '.join(unmet_deps)}")

        # 3. Requirement checks
        if self.requirements.require_role and not unit.role:
            missing.append("role")
            reasons.append(f"Unit '{unit.id}' missing required role.")

        if unit.mutating:
            if self.requirements.require_repo_for_mutating and not unit.repo:
                missing.append("repo")
                reasons.append(f"Mutating unit '{unit.id}' missing required 'repo'.")

            if self.requirements.require_full_base_sha_for_mutating:
                if not unit.base_sha or not _is_full_sha(unit.base_sha):
                    missing.append("base_sha")
                    reasons.append(f"Mutating unit '{unit.id}' missing valid 40-hex 'base_sha'.")

            if self.requirements.require_execution_model_for_mutating and not unit.execution_model:
                missing.append("execution_model")
                reasons.append(f"Mutating unit '{unit.id}' missing required 'execution_model'.")

            if self.requirements.require_criteria_for_mutating and not unit.acceptance_criteria:
                missing.append("acceptance_criteria")
                reasons.append(f"Mutating unit '{unit.id}' missing required 'acceptance_criteria'.")

        # Determine final status
        if missing:
            return DispatchabilityAssessment(
                unit_id=unit.id,
                is_dispatchable=False,
                status=DispatchabilityStatus.INELIGIBLE,
                reasons=reasons,
                blockers=blockers,
                missing_requirements=missing,
            )

        if blockers:
            return DispatchabilityAssessment(
                unit_id=unit.id,
                is_dispatchable=False,
                status=DispatchabilityStatus.BLOCKED,
                reasons=reasons,
                blockers=blockers,
            )

        return DispatchabilityAssessment(
            unit_id=unit.id,
            is_dispatchable=True,
            status=DispatchabilityStatus.READY,
            reasons=["All prerequisites and contract requirements met for dispatch."],
        )

    def assess_plan(
        self,
        plan: DecompositionPlan,
        completed_unit_ids: Sequence[str] = (),
        running_unit_ids: Sequence[str] = (),
        failed_unit_ids: Sequence[str] = (),
    ) -> Dict[str, DispatchabilityAssessment]:
        """Evaluate all units in a decomposition plan."""
        return {
            unit.id: self.assess_unit(
                unit,
                completed_unit_ids=completed_unit_ids,
                running_unit_ids=running_unit_ids,
                failed_unit_ids=failed_unit_ids,
            )
            for unit in plan.units
        }


def evaluate_dispatchability(
    unit: DecompositionUnit,
    completed_ids: Sequence[str] = (),
    running_ids: Sequence[str] = (),
    failed_ids: Sequence[str] = (),
    requirements: Optional[DispatchabilityRequirement] = None,
) -> DispatchabilityAssessment:
    """Convenience helper to assess dispatchability for a single unit."""
    evaluator = DispatchabilityEvaluator(requirements)
    return evaluator.assess_unit(
        unit,
        completed_unit_ids=completed_ids,
        running_unit_ids=running_ids,
        failed_unit_ids=failed_ids,
    )


def validate_dispatchability(
    unit: DecompositionUnit,
    completed_ids: Sequence[str] = (),
    running_ids: Sequence[str] = (),
    failed_ids: Sequence[str] = (),
    requirements: Optional[DispatchabilityRequirement] = None,
) -> DispatchabilityAssessment:
    """Validate that a unit is ready for dispatch; raises DispatchabilityError if not."""
    assessment = evaluate_dispatchability(
        unit,
        completed_ids=completed_ids,
        running_ids=running_ids,
        failed_ids=failed_ids,
        requirements=requirements,
    )
    if not assessment.is_dispatchable:
        err_reasons = "; ".join(assessment.reasons)
        raise DispatchabilityError(
            f"Unit '{unit.id}' is not dispatchable (status={assessment.status.value}): {err_reasons}",
            unit_id=unit.id,
            reasons=assessment.reasons,
        )
    return assessment


def get_dispatchable_units(
    plan: DecompositionPlan,
    completed_ids: Sequence[str] = (),
    running_ids: Sequence[str] = (),
    failed_ids: Sequence[str] = (),
    requirements: Optional[DispatchabilityRequirement] = None,
) -> List[DecompositionUnit]:
    """Filter and return only the units in the plan that are currently READY for dispatch."""
    evaluator = DispatchabilityEvaluator(requirements)
    assessments = evaluator.assess_plan(
        plan,
        completed_unit_ids=completed_ids,
        running_unit_ids=running_ids,
        failed_unit_ids=failed_ids,
    )
    return [u for u in plan.units if assessments[u.id].is_dispatchable]
