from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepSpec:
    id: str
    name: str
    purpose: str
    instructions: str
    depends_on: list[str] = field(default_factory=list)
    expected_output: list[str] = field(default_factory=list)
    validation: list[str] = field(default_factory=list)
    completion_rule: list[str] = field(default_factory=list)


@dataclass
class PromptSequence:
    metadata: dict[str, Any]
    objective: str
    success_criteria: list[str]
    assumptions: list[str]
    usage_notes: dict[str, Any]
    inputs_required: list[str]
    outputs_required: list[str]
    sequence_steps: list[StepSpec]
    final_assembly: str
    validation_rules: list[str]
    failure_handling: str
    final_deliverable_format: str


@dataclass
class WorkflowContext:
    sequence_id: str
    mode: str
    status: str = "pending"
    current_step_id: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    step_outputs: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    usage_notes: dict[str, Any] = field(default_factory=dict)
    validation_findings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    final_output: Any = None
