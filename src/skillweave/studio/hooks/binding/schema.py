"""YAML binding config schema and dataclasses.

A binding config file lives at:
  - Project level: .skillweave/hooks/<phase>-<position>.yaml
  - User level:    ~/.skillweave/hooks/<phase>-<position>.yaml

Example YAML::

    version: "1"
    phase: build
    position: pre
    hooks:
      - name: lint-gate
        type: shell
        command: "./scripts/lint.sh"
        priority: 100
        failureMode: block
        condition: "phase == 'build'"
        timeout_sec: 60
        config:
          strict: true
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


SUPPORTED_VERSIONS = ("1",)
VALID_TYPES = ("python", "shell", "skill_md", "capacium")
VALID_FAILURE_MODES = ("block", "warn", "ignore", "retry")
VALID_SOURCES = ("project", "user", "auto")


class BindingValidationError(Exception):
    """Raised when a binding YAML file is malformed or invalid."""


@dataclass
class HookBinding:
    """A single hook binding entry within a config file.

    Attributes:
        name: Unique hook identifier within the binding file.
        type: Execution type — python | shell | skill_md | capacium.
        priority: Execution order (lower = earlier). Default 500.
        failureMode: What happens on failure — block | warn | ignore | retry.
        source: Origin of this binding — project | user | auto.
        condition: Optional predicate expression evaluated before execution.
        timeout_sec: Max execution time in seconds.  Default 300.
        retry_count: Number of retries when failureMode is retry. Default 1.
        config: Arbitrary per-hook configuration dict.
        # Type-specific fields:
        module: Python dotted path to HookAdapter subclass (type=python).
        command: Shell command string (type=shell).
        skill_md: Path to SKILL.md file (type=skill_md).
        capability: Capacium capability identifier (type=capacium).
    """

    name: str
    type: Literal["python", "shell", "skill_md", "capacium"]
    priority: int = 500
    failureMode: Literal["block", "warn", "ignore", "retry"] = "block"
    source: Literal["project", "user", "auto"] = "project"
    condition: Optional[str] = None
    timeout_sec: int = 300
    retry_count: int = 1
    config: Dict[str, Any] = field(default_factory=dict)

    # Type-specific fields
    module: Optional[str] = None
    command: Optional[str] = None
    skill_md: Optional[str] = None
    capability: Optional[str] = None

    # Internal: phase+position are injected by the loader
    phase: Optional[str] = None
    position: Optional[str] = None

    @property
    def dedup_key(self) -> str:
        """Key for deduplication: capability+phase+position or name+phase+position."""
        cap = self.capability or self.module or self.command or self.skill_md or self.name
        return f"{cap}:{self.phase}:{self.position}"

    def validate(self) -> None:
        """Raise BindingValidationError if this binding is invalid."""
        if not self.name:
            raise BindingValidationError("Hook binding requires a 'name' field")

        if self.type not in VALID_TYPES:
            raise BindingValidationError(
                f"Invalid hook type '{self.type}' for '{self.name}'. "
                f"Must be one of: {', '.join(VALID_TYPES)}"
            )

        if self.failureMode not in VALID_FAILURE_MODES:
            raise BindingValidationError(
                f"Invalid failureMode '{self.failureMode}' for '{self.name}'. "
                f"Must be one of: {', '.join(VALID_FAILURE_MODES)}"
            )

        # Type-specific field requirements
        if self.type == "python" and not self.module:
            raise BindingValidationError(
                f"Hook '{self.name}' has type=python but no 'module' field"
            )
        if self.type == "shell" and not self.command:
            raise BindingValidationError(
                f"Hook '{self.name}' has type=shell but no 'command' field"
            )
        if self.type == "skill_md" and not self.skill_md:
            raise BindingValidationError(
                f"Hook '{self.name}' has type=skill_md but no 'skill_md' field"
            )
        if self.type == "capacium" and not self.capability:
            raise BindingValidationError(
                f"Hook '{self.name}' has type=capacium but no 'capability' field"
            )

        if self.priority < 0:
            raise BindingValidationError(
                f"Hook '{self.name}' has negative priority {self.priority}"
            )

        if self.timeout_sec <= 0:
            raise BindingValidationError(
                f"Hook '{self.name}' has non-positive timeout_sec {self.timeout_sec}"
            )


@dataclass
class BindingConfig:
    """Parsed and validated binding config from a YAML file.

    Attributes:
        version: Schema version string.
        phase: Lifecycle phase this config targets.
        position: Pre or post position.
        hooks: List of hook bindings.
        source_path: Path the config was loaded from (for diagnostics).
    """

    version: str
    phase: str
    position: str
    hooks: List[HookBinding] = field(default_factory=list)
    source_path: str = ""

    def validate(self) -> None:
        """Validate the entire config. Raises BindingValidationError."""
        if self.version not in SUPPORTED_VERSIONS:
            raise BindingValidationError(
                f"Unsupported binding config version '{self.version}' "
                f"in {self.source_path}. Supported: {', '.join(SUPPORTED_VERSIONS)}"
            )

        from ..models import Phase, Position

        valid_phases = {p.value for p in Phase}
        if self.phase not in valid_phases:
            raise BindingValidationError(
                f"Invalid phase '{self.phase}' in {self.source_path}. "
                f"Must be one of: {', '.join(sorted(valid_phases))}"
            )

        valid_positions = {p.value for p in Position}
        if self.position not in valid_positions:
            raise BindingValidationError(
                f"Invalid position '{self.position}' in {self.source_path}. "
                f"Must be one of: {', '.join(sorted(valid_positions))}"
            )

        names_seen: set[str] = set()
        for hook in self.hooks:
            if hook.name in names_seen:
                raise BindingValidationError(
                    f"Duplicate hook name '{hook.name}' in {self.source_path}"
                )
            names_seen.add(hook.name)
            hook.validate()

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source_path: str = "") -> "BindingConfig":
        """Parse a raw dict (from YAML) into a BindingConfig.

        Raises BindingValidationError with actionable messages on invalid input.
        """
        if not isinstance(data, dict):
            raise BindingValidationError(
                f"Expected YAML mapping at top level in {source_path}, "
                f"got {type(data).__name__}"
            )

        version = str(data.get("version", ""))
        phase = str(data.get("phase", ""))
        position = str(data.get("position", ""))

        if not version:
            raise BindingValidationError(
                f"Missing required 'version' field in {source_path}"
            )
        if not phase:
            raise BindingValidationError(
                f"Missing required 'phase' field in {source_path}"
            )
        if not position:
            raise BindingValidationError(
                f"Missing required 'position' field in {source_path}"
            )

        raw_hooks = data.get("hooks", [])
        if not isinstance(raw_hooks, list):
            raise BindingValidationError(
                f"'hooks' must be a list in {source_path}, "
                f"got {type(raw_hooks).__name__}"
            )

        hooks: List[HookBinding] = []
        for i, raw in enumerate(raw_hooks):
            if not isinstance(raw, dict):
                raise BindingValidationError(
                    f"Hook entry {i} must be a mapping in {source_path}, "
                    f"got {type(raw).__name__}"
                )
            try:
                binding = HookBinding(
                    name=raw.get("name", ""),
                    type=raw.get("type", ""),
                    priority=int(raw.get("priority", 500)),
                    failureMode=raw.get("failureMode", "block"),
                    condition=raw.get("condition"),
                    timeout_sec=int(raw.get("timeout_sec", 300)),
                    retry_count=int(raw.get("retry_count", 1)),
                    config=raw.get("config", {}),
                    module=raw.get("module"),
                    command=raw.get("command"),
                    skill_md=raw.get("skill_md"),
                    capability=raw.get("capability"),
                    phase=phase,
                    position=position,
                )
                hooks.append(binding)
            except (TypeError, ValueError) as exc:
                raise BindingValidationError(
                    f"Invalid hook entry {i} in {source_path}: {exc}"
                ) from exc

        config = cls(
            version=version,
            phase=phase,
            position=position,
            hooks=hooks,
            source_path=source_path,
        )
        config.validate()
        return config
