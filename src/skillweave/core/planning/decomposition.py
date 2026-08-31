"""Decomposition metadata and planning structures (SW-PLAN-001).

This module defines the decomposition data model for SkillWeave:
- Structural decomposition of objectives/PRDs into discrete execution units.
- Explicit decomposition metadata including strategies, complexity, criteria coverage,
  dependency graphs, and Fibonacci effort points.
- Fail-closed validation for dependency cycles, duplicate IDs, and criterion coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Union

#: Valid Fibonacci points for practice tasks and decomposition units
FIBONACCI_POINTS = (1, 2, 3, 5, 8, 13)


class DecompositionStrategy(str, Enum):
    """Execution and decomposition strategy for a plan."""

    SEQUENTIAL = "sequential"
    PARALLEL_LANES = "parallel_lanes"
    DAG = "dag"
    WAVE = "wave"
    HIERARCHICAL = "hierarchical"
    PHASED = "phased"


class ComplexityLevel(str, Enum):
    """Complexity classification for decomposed work."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class DecompositionError(ValueError):
    """Base error for decomposition validation and planning failures."""

    def __init__(self, message: str, *, field_name: Optional[str] = None):
        super().__init__(message)
        self.field_name = field_name


class DependencyCycleError(DecompositionError):
    """Raised when a dependency cycle is detected among decomposition units."""


class CriterionCoverageError(DecompositionError):
    """Raised when required acceptance criteria are missing or invalid."""


@dataclass
class DecompositionUnit:
    """A discrete decomposed unit of work (task/lane/step).

    Attributes:
        id: Unique identifier for this unit (e.g. 'TASK-001', 'lane-mut-1').
        name: Short human-readable title.
        role: Required agent role for execution.
        description: Detailed instructions/description.
        mutating: Whether this unit mutates repository state.
        points: Fibonacci complexity points (1, 2, 3, 5, 8, 13).
        depends_on: IDs of predecessor units that must complete first.
        acceptance_criteria: Acceptance criteria indices or IDs covered by this unit.
        write_scope: List of path/glob patterns this unit is permitted to write to.
        repo: Repository identifier/URL (required for mutating units at dispatch).
        base_sha: Full 40-hex base commit SHA (required for mutating units at dispatch).
        execution_model: Model/runtime target for execution.
        worktree: Isolated worktree directory path if applicable.
        branch: Target branch name if applicable.
        metadata: Arbitrary user/extension metadata.
    """

    id: str
    name: str
    role: str
    description: str = ""
    mutating: bool = False
    points: Optional[int] = None
    depends_on: List[str] = field(default_factory=list)
    acceptance_criteria: List[Union[int, str]] = field(default_factory=list)
    write_scope: Optional[List[str]] = None
    repo: Optional[str] = None
    base_sha: Optional[str] = None
    execution_model: Optional[str] = None
    worktree: Optional[str] = None
    branch: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate internal consistency of the unit."""
        if not self.id or not isinstance(self.id, str) or not self.id.strip():
            raise DecompositionError("Unit 'id' must be a non-empty string", field_name="id")
        if not self.name or not isinstance(self.name, str) or not self.name.strip():
            raise DecompositionError(f"Unit '{self.id}' name must be a non-empty string", field_name=f"{self.id}.name")
        if not self.role or not isinstance(self.role, str) or not self.role.strip():
            raise DecompositionError(f"Unit '{self.id}' role must be a non-empty string", field_name=f"{self.id}.role")

        if self.points is not None:
            if not isinstance(self.points, int) or isinstance(self.points, bool):
                raise DecompositionError(
                    f"Unit '{self.id}' points must be an integer, got {self.points!r}",
                    field_name=f"{self.id}.points",
                )
            if self.points not in FIBONACCI_POINTS:
                raise DecompositionError(
                    f"Unit '{self.id}' points {self.points} must be one of {list(FIBONACCI_POINTS)}",
                    field_name=f"{self.id}.points",
                )

        if self.base_sha is not None:
            if not isinstance(self.base_sha, str) or len(self.base_sha) != 40:
                raise DecompositionError(
                    f"Unit '{self.id}' base_sha must be 40 hex characters if provided, got {self.base_sha!r}",
                    field_name=f"{self.id}.base_sha",
                )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize unit to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "mutating": self.mutating,
            "points": self.points,
            "depends_on": list(self.depends_on),
            "acceptance_criteria": list(self.acceptance_criteria),
            "write_scope": list(self.write_scope) if self.write_scope is not None else None,
            "repo": self.repo,
            "base_sha": self.base_sha,
            "execution_model": self.execution_model,
            "worktree": self.worktree,
            "branch": self.branch,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecompositionUnit:
        """Construct unit from dictionary."""
        if not isinstance(data, Mapping):
            raise DecompositionError("Unit data must be a mapping")

        unit = cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "")).strip(),
            role=str(data.get("role", "")).strip(),
            description=str(data.get("description", "")),
            mutating=bool(data.get("mutating", False)),
            points=data.get("points"),
            depends_on=list(data.get("depends_on") or []),
            acceptance_criteria=list(data.get("acceptance_criteria") or []),
            write_scope=list(data.get("write_scope")) if data.get("write_scope") is not None else None,
            repo=data.get("repo"),
            base_sha=data.get("base_sha"),
            execution_model=data.get("execution_model"),
            worktree=data.get("worktree"),
            branch=data.get("branch"),
            metadata=dict(data.get("metadata") or {}),
        )
        unit.validate()
        return unit


@dataclass
class DecompositionMetadata:
    """Explicit metadata summarizing a decomposition plan (SW-PLAN-001).

    Attributes:
        source_id: Originating PRD, feature, or objective reference.
        version: Schema/plan version.
        strategy: Decomposition strategy used.
        complexity: Optional complexity classification.
        total_points: Sum of Fibonacci points for all units.
        total_units: Number of decomposed units.
        mutating_units: Number of units requiring mutating write access.
        read_only_units: Number of non-mutating units.
        max_dependency_depth: Longest dependency path in the DAG.
        criteria_coverage: Map of criterion ID -> List of unit IDs covering it.
        created_at: ISO timestamp of metadata creation.
        custom_attributes: Extension dictionary.
    """

    source_id: str
    version: str = "1.0.0"
    strategy: DecompositionStrategy = DecompositionStrategy.DAG
    complexity: Optional[ComplexityLevel] = None
    total_points: int = 0
    total_units: int = 0
    mutating_units: int = 0
    read_only_units: int = 0
    max_dependency_depth: int = 0
    criteria_coverage: Dict[str, List[str]] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    custom_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata to dictionary."""
        return {
            "source_id": self.source_id,
            "version": self.version,
            "strategy": self.strategy.value if isinstance(self.strategy, DecompositionStrategy) else str(self.strategy),
            "complexity": self.complexity.value if isinstance(self.complexity, ComplexityLevel) else (str(self.complexity) if self.complexity else None),
            "total_points": self.total_points,
            "total_units": self.total_units,
            "mutating_units": self.mutating_units,
            "read_only_units": self.read_only_units,
            "max_dependency_depth": self.max_dependency_depth,
            "criteria_coverage": {k: list(v) for k, v in self.criteria_coverage.items()},
            "created_at": self.created_at,
            "custom_attributes": dict(self.custom_attributes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecompositionMetadata:
        """Construct metadata from dictionary."""
        if not isinstance(data, Mapping):
            raise DecompositionError("Metadata data must be a mapping")

        raw_strategy = data.get("strategy", DecompositionStrategy.DAG.value)
        try:
            strategy = DecompositionStrategy(raw_strategy)
        except ValueError:
            strategy = DecompositionStrategy.DAG

        raw_complexity = data.get("complexity")
        complexity = None
        if raw_complexity:
            try:
                complexity = ComplexityLevel(raw_complexity)
            except ValueError:
                complexity = None

        return cls(
            source_id=str(data.get("source_id", "")),
            version=str(data.get("version", "1.0.0")),
            strategy=strategy,
            complexity=complexity,
            total_points=int(data.get("total_points", 0)),
            total_units=int(data.get("total_units", 0)),
            mutating_units=int(data.get("mutating_units", 0)),
            read_only_units=int(data.get("read_only_units", 0)),
            max_dependency_depth=int(data.get("max_dependency_depth", 0)),
            criteria_coverage={str(k): list(v) for k, v in (data.get("criteria_coverage") or {}).items()},
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            custom_attributes=dict(data.get("custom_attributes") or {}),
        )


@dataclass
class DecompositionPlan:
    """Complete decomposition plan containing units, phases, and rich metadata."""

    plan_id: str
    objective: str
    metadata: DecompositionMetadata
    units: List[DecompositionUnit] = field(default_factory=list)
    phases: List[Dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        """Perform full fail-closed structural validation on the plan."""
        if not self.plan_id or not isinstance(self.plan_id, str):
            raise DecompositionError("Plan 'plan_id' must be a non-empty string", field_name="plan_id")
        if not self.objective or not isinstance(self.objective, str):
            raise DecompositionError("Plan 'objective' must be a non-empty string", field_name="objective")

        seen_ids: Set[str] = set()
        for unit in self.units:
            unit.validate()
            if unit.id in seen_ids:
                raise DecompositionError(f"Duplicate unit ID detected: '{unit.id}'", field_name=f"{unit.id}.id")
            seen_ids.add(unit.id)

        # Check unknown dependencies and cycle detection
        unit_map = {u.id: u for u in self.units}
        for unit in self.units:
            for dep in unit.depends_on:
                if dep not in unit_map:
                    raise DecompositionError(
                        f"Unit '{unit.id}' depends on non-existent unit '{dep}'",
                        field_name=f"{unit.id}.depends_on",
                    )

        self._check_dependency_cycles()

    def _check_dependency_cycles(self) -> None:
        """Detect circular dependencies using DFS graph coloring."""
        unit_map = {u.id: u for u in self.units}
        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting (in stack), 2: visited

        def dfs(node_id: str, path: List[str]) -> None:
            visited[node_id] = 1
            path.append(node_id)
            for neighbor in unit_map[node_id].depends_on:
                state = visited.get(neighbor, 0)
                if state == 1:
                    cycle_path = " -> ".join(path + [neighbor])
                    raise DependencyCycleError(f"Dependency cycle detected in decomposition: {cycle_path}")
                if state == 0:
                    dfs(neighbor, path)
            path.pop()
            visited[node_id] = 2

        for unit in self.units:
            if visited.get(unit.id, 0) == 0:
                dfs(unit.id, [])

    def calculate_metadata(self) -> DecompositionMetadata:
        """Derive fresh DecompositionMetadata from the plan's units."""
        self.validate()
        total_points = sum(u.points for u in self.units if u.points is not None)
        mutating_count = sum(1 for u in self.units if u.mutating)
        read_only_count = len(self.units) - mutating_count

        # Compute max dependency depth
        unit_map = {u.id: u for u in self.units}
        depths: Dict[str, int] = {}

        def get_depth(node_id: str) -> int:
            if node_id in depths:
                return depths[node_id]
            unit = unit_map[node_id]
            if not unit.depends_on:
                depths[node_id] = 1
                return 1
            max_d = 1 + max(get_depth(d) for d in unit.depends_on)
            depths[node_id] = max_d
            return max_d

        max_depth = max((get_depth(u.id) for u in self.units), default=0)

        # Criteria coverage mapping
        coverage: Dict[str, List[str]] = {}
        for unit in self.units:
            for c in unit.acceptance_criteria:
                c_key = str(c)
                coverage.setdefault(c_key, []).append(unit.id)

        meta = DecompositionMetadata(
            source_id=self.metadata.source_id if self.metadata else self.plan_id,
            version=self.metadata.version if self.metadata else "1.0.0",
            strategy=self.metadata.strategy if self.metadata else DecompositionStrategy.DAG,
            complexity=self.metadata.complexity if self.metadata else None,
            total_points=total_points,
            total_units=len(self.units),
            mutating_units=mutating_count,
            read_only_units=read_only_count,
            max_dependency_depth=max_depth,
            criteria_coverage=coverage,
            created_at=self.metadata.created_at if self.metadata else datetime.now(timezone.utc).isoformat(),
            custom_attributes=self.metadata.custom_attributes if self.metadata else {},
        )
        self.metadata = meta
        return meta

    def get_unit(self, unit_id: str) -> Optional[DecompositionUnit]:
        """Look up a unit by ID."""
        for unit in self.units:
            if unit.id == unit_id:
                return unit
        return None

    def get_ready_units(self, completed_ids: Sequence[str]) -> List[DecompositionUnit]:
        """Return units whose dependencies have all been completed and are not yet completed."""
        completed_set = set(completed_ids)
        ready: List[DecompositionUnit] = []
        for unit in self.units:
            if unit.id in completed_set:
                continue
            if all(dep in completed_set for dep in unit.depends_on):
                ready.append(unit)
        return ready

    def get_execution_batches(self) -> List[List[DecompositionUnit]]:
        """Calculate parallel topological batches of units."""
        self.validate()
        batches: List[List[DecompositionUnit]] = []
        completed: Set[str] = set()

        while len(completed) < len(self.units):
            ready = self.get_ready_units(list(completed))
            if not ready:
                break
            batches.append(ready)
            for unit in ready:
                completed.add(unit.id)

        return batches

    def to_dict(self) -> Dict[str, Any]:
        """Serialize plan to dictionary."""
        return {
            "plan_id": self.plan_id,
            "objective": self.objective,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "units": [u.to_dict() for u in self.units],
            "phases": list(self.phases),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecompositionPlan:
        """Construct plan from dictionary."""
        if not isinstance(data, Mapping):
            raise DecompositionError("Plan data must be a mapping")

        plan_id = str(data.get("plan_id", "")).strip()
        objective = str(data.get("objective", "")).strip()

        units = [DecompositionUnit.from_dict(u) for u in (data.get("units") or [])]
        meta_dict = data.get("metadata")
        if meta_dict and isinstance(meta_dict, Mapping):
            metadata = DecompositionMetadata.from_dict(meta_dict)
        else:
            metadata = DecompositionMetadata(source_id=plan_id)

        plan = cls(
            plan_id=plan_id,
            objective=objective,
            metadata=metadata,
            units=units,
            phases=list(data.get("phases") or []),
        )
        plan.validate()
        return plan

    def to_json(self, indent: int = 2) -> str:
        """Serialize plan to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> DecompositionPlan:
        """Construct plan from JSON string."""
        return cls.from_dict(json.loads(json_str))


def create_decomposition_plan(
    plan_id: str,
    objective: str,
    units: List[DecompositionUnit],
    strategy: DecompositionStrategy = DecompositionStrategy.DAG,
    complexity: Optional[ComplexityLevel] = None,
    source_id: Optional[str] = None,
    custom_attributes: Optional[Dict[str, Any]] = None,
) -> DecompositionPlan:
    """Factory helper to construct, validate, and compute metadata for a decomposition plan."""
    meta = DecompositionMetadata(
        source_id=source_id or plan_id,
        strategy=strategy,
        complexity=complexity,
        custom_attributes=custom_attributes or {},
    )
    plan = DecompositionPlan(
        plan_id=plan_id,
        objective=objective,
        metadata=meta,
        units=units,
    )
    plan.calculate_metadata()
    return plan
