"""Trigger scanner — finds Capacium capabilities with SkillWeave triggers.

Scans installed Capacium capabilities for ``triggers`` fields matching
``source: skillweave``, and maps CloudEvents type/source/filter to
SkillWeave phase+position bindings.

Trigger mapping convention::

    triggers:
      - type: dev.skillweave.hook
        source: skillweave
        filter:
          phase: build
          position: pre
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..binding.schema import HookBinding

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredBinding:
    """A hook binding discovered from a Capacium capability trigger.

    Attributes:
        capability: The Capacium capability identifier.
        phase: Target SkillWeave phase.
        position: Target SkillWeave position (pre/post).
        trigger_type: CloudEvents type from the trigger.
        trigger_source: CloudEvents source from the trigger.
        metadata: Additional metadata from the capability manifest.
    """

    capability: str
    phase: str
    position: str
    trigger_type: str = "dev.skillweave.hook"
    trigger_source: str = "skillweave"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_hook_binding(self, priority: int = 900) -> HookBinding:
        """Convert to a HookBinding for the resolver.

        Auto-discovered bindings get low priority (high number)
        so project/user bindings override them.
        """
        return HookBinding(
            name=f"auto:{self.capability}",
            type="capacium",
            capability=self.capability,
            priority=priority,
            failureMode="warn",  # Auto-discovered default to warn, not block
            source="auto",
            phase=self.phase,
            position=self.position,
            config=self.metadata,
        )


class TriggerScanner:
    """Scans installed Capacium capabilities for SkillWeave triggers.

    Args:
        capabilities_dir: Path to the Capacium capabilities directory.
                          Default: ~/.capacium/capabilities/
        capabilities_data: Optional pre-loaded capability data (for testing).
    """

    def __init__(
        self,
        capabilities_dir: Optional[str] = None,
        capabilities_data: Optional[List[Dict[str, Any]]] = None,
    ):
        self._cap_dir = (
            Path(capabilities_dir)
            if capabilities_dir
            else Path.home() / ".capacium" / "capabilities"
        )
        self._preloaded = capabilities_data

    def scan(self) -> List[DiscoveredBinding]:
        """Scan for capabilities with SkillWeave triggers.

        Returns:
            List of discovered bindings ready for resolution.
        """
        capabilities = self._preloaded or self._load_capabilities()
        discovered: List[DiscoveredBinding] = []

        for cap_data in capabilities:
            name = cap_data.get("name", "unknown")
            triggers = cap_data.get("triggers", [])

            if not isinstance(triggers, list):
                continue

            for trigger in triggers:
                if not isinstance(trigger, dict):
                    continue

                source = trigger.get("source", "")
                if source != "skillweave":
                    continue

                filter_spec = trigger.get("filter", {})
                phase = filter_spec.get("phase", "")
                position = filter_spec.get("position", "")

                if not phase or not position:
                    logger.warning(
                        "Capability '%s' has skillweave trigger but missing "
                        "phase/position in filter",
                        name,
                    )
                    continue

                discovered.append(
                    DiscoveredBinding(
                        capability=name,
                        phase=phase,
                        position=position,
                        trigger_type=trigger.get("type", "dev.skillweave.hook"),
                        trigger_source=source,
                        metadata={
                            k: v
                            for k, v in cap_data.items()
                            if k not in ("name", "triggers")
                        },
                    )
                )

        logger.info("Discovered %d SkillWeave triggers from capabilities", len(discovered))
        return discovered

    def _load_capabilities(self) -> List[Dict[str, Any]]:
        """Load capability manifests from the filesystem."""
        if not self._cap_dir.exists():
            logger.debug("Capacium capabilities dir not found: %s", self._cap_dir)
            return []

        capabilities: List[Dict[str, Any]] = []

        for manifest_path in sorted(self._cap_dir.glob("*/manifest.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Use directory name as capability name if not in manifest
                    if "name" not in data:
                        data["name"] = manifest_path.parent.name
                    capabilities.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read capability manifest %s: %s", manifest_path, exc)

        return capabilities

    def scan_as_bindings(self) -> List[HookBinding]:
        """Convenience: scan and convert directly to HookBinding objects."""
        return [d.to_hook_binding() for d in self.scan()]
