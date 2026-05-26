"""Core dataclasses for the hook system."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


class Phase(str, Enum):
    """SkillWeave lifecycle phases where hooks can bind."""

    DISCOVERY = "discovery"
    BLUEPRINT = "blueprint"
    BUILD = "build"
    TEST = "test"
    RELEASE = "release"
    LAUNCH = "launch"
    OBSERVE = "observe"


class Position(str, Enum):
    """Hook position relative to a phase gate."""

    PRE = "pre"
    POST = "post"


HookStatus = Literal["pass", "fail", "skip"]


@dataclass(frozen=True)
class PhaseContext:
    """Immutable context passed to every hook execution.

    Attributes:
        phase: Current lifecycle phase.
        position: Pre or post gate.
        gate_decision: Upstream gate result (None if first hook).
        project_root: Absolute path to the project root.
        config: Resolved SkillWeave config dict.
        hook_config: Per-hook configuration from the binding YAML.
    """

    phase: Phase
    position: Position
    gate_decision: Optional[bool] = None
    project_root: str = "."
    config: Dict[str, Any] = field(default_factory=dict)
    hook_config: Dict[str, Any] = field(default_factory=dict)

    # -- Serialization --------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase.value
        d["position"] = self.position.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhaseContext":
        return cls(
            phase=Phase(data["phase"]),
            position=Position(data["position"]),
            gate_decision=data.get("gate_decision"),
            project_root=data.get("project_root", "."),
            config=data.get("config", {}),
            hook_config=data.get("hook_config", {}),
        )

    # -- Env export for shell hooks ------------------------------------

    def as_env(self) -> Dict[str, str]:
        """Return context as flat env-var dict for subprocess hooks."""
        return {
            "SKILLWEAVE_PHASE": self.phase.value,
            "SKILLWEAVE_POSITION": self.position.value,
            "SKILLWEAVE_GATE_DECISION": str(self.gate_decision) if self.gate_decision is not None else "",
            "SKILLWEAVE_PROJECT_ROOT": self.project_root,
        }


@dataclass
class HookResult:
    """Result returned by a hook execution.

    Attributes:
        status: pass / fail / skip.
        message: Human-readable explanation.
        artifacts: Paths or URIs produced by the hook.
        gate_override: If set, overrides the phase gate decision.
    """

    status: HookStatus
    message: str = ""
    artifacts: List[str] = field(default_factory=list)
    gate_override: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.status not in ("pass", "fail", "skip"):
            raise ValueError(f"Invalid HookStatus: {self.status!r}. Must be pass/fail/skip.")
        if self.gate_override is not None and not isinstance(self.gate_override, bool):
            raise TypeError(f"gate_override must be bool or None, got {type(self.gate_override).__name__}")

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    @property
    def failed(self) -> bool:
        return self.status == "fail"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "artifacts": self.artifacts,
            "gate_override": self.gate_override,
        }
