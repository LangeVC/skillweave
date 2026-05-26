"""Binding resolver — merges, deduplicates, and sorts hook bindings.

Resolution strategy:
  1. Collect bindings from all sources (project, user, auto-discovered).
  2. Project bindings override user bindings for the same dedup_key.
  3. User bindings override auto-discovered bindings.
  4. Within the same source level, sort by priority (ascending).
  5. Deduplication key: capability+phase+position (see HookBinding.dedup_key).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .schema import HookBinding, BindingConfig
from .loader import BindingLoader

logger = logging.getLogger(__name__)

# Source precedence: lower index = higher precedence
SOURCE_PRECEDENCE: Dict[str, int] = {
    "project": 0,
    "user": 1,
    "auto": 2,
}


class BindingResolver:
    """Resolves the effective set of hooks for a given phase+position.

    Merges bindings from project, user, and auto-discovered sources,
    deduplicates by capability+phase+position, and sorts by priority.

    Args:
        loader: BindingLoader instance for filesystem access.
    """

    def __init__(self, loader: BindingLoader):
        self._loader = loader

    def resolve(
        self,
        phase: str,
        position: str,
        auto_bindings: Optional[List[HookBinding]] = None,
    ) -> List[HookBinding]:
        """Resolve the effective hook bindings for a phase+position.

        Args:
            phase: Lifecycle phase (e.g. "build").
            position: Hook position ("pre" or "post").
            auto_bindings: Optional list of auto-discovered bindings to merge.

        Returns:
            Sorted, deduplicated list of HookBinding objects ready for execution.
        """
        # Collect all bindings from disk
        by_source = self._loader.load_for_phase(phase, position)

        all_bindings: List[HookBinding] = []

        # Project-level (highest precedence)
        for config in by_source.get("project", []):
            all_bindings.extend(config.hooks)

        # User-level
        for config in by_source.get("user", []):
            all_bindings.extend(config.hooks)

        # Auto-discovered (lowest precedence)
        if auto_bindings:
            for binding in auto_bindings:
                binding.source = "auto"
                binding.phase = phase
                binding.position = position
                all_bindings.append(binding)

        # Deduplicate: keep highest-precedence source for each dedup_key
        resolved = self._deduplicate(all_bindings)

        # Sort by priority (ascending — lower number runs first)
        resolved.sort(key=lambda h: h.priority)

        logger.debug(
            "Resolved %d hooks for %s_%s (from %d candidates)",
            len(resolved),
            position,
            phase,
            len(all_bindings),
        )

        return resolved

    def resolve_all(
        self,
        auto_bindings: Optional[List[HookBinding]] = None,
    ) -> Dict[str, List[HookBinding]]:
        """Resolve hooks for all phase+position combinations.

        Returns:
            Dict keyed by "{position}_{phase}" with resolved hook lists.
        """
        from ..models import Phase, Position

        result: Dict[str, List[HookBinding]] = {}

        for phase in Phase:
            for pos in Position:
                key = f"{pos.value}_{phase.value}"
                # Filter auto_bindings for this phase+position
                filtered_auto = None
                if auto_bindings:
                    filtered_auto = [
                        b for b in auto_bindings
                        if b.phase == phase.value and b.position == pos.value
                    ]
                hooks = self.resolve(phase.value, pos.value, filtered_auto)
                if hooks:
                    result[key] = hooks

        return result

    @staticmethod
    def _deduplicate(bindings: List[HookBinding]) -> List[HookBinding]:
        """Deduplicate bindings by dedup_key, keeping highest-precedence source.

        When two bindings have the same dedup_key, the one with higher
        source precedence (project > user > auto) wins.
        """
        seen: Dict[str, HookBinding] = {}

        for binding in bindings:
            key = binding.dedup_key
            if key in seen:
                existing = seen[key]
                existing_prec = SOURCE_PRECEDENCE.get(existing.source, 99)
                new_prec = SOURCE_PRECEDENCE.get(binding.source, 99)

                if new_prec < existing_prec:
                    # New binding has higher precedence
                    logger.debug(
                        "Overriding %s binding '%s' with %s binding",
                        existing.source,
                        key,
                        binding.source,
                    )
                    seen[key] = binding
                # else: keep existing (higher or equal precedence)
            else:
                seen[key] = binding

        return list(seen.values())
