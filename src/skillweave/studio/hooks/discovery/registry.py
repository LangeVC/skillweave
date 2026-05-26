"""Dismissal registry — tracks which auto-discovered bindings the user dismissed.

Dismissed triggers are stored in a JSON file at
``<project_root>/.skillweave/hooks/.dismissed.json``
so they don't reappear until the capability is updated.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Set

from .scanner import DiscoveredBinding

logger = logging.getLogger(__name__)

DISMISSED_FILENAME = ".dismissed.json"


class DismissalRegistry:
    """Tracks dismissed auto-discovered bindings.

    Args:
        project_root: Project root directory.
    """

    def __init__(self, project_root: str = "."):
        self._project_root = Path(project_root)
        self._file_path = (
            self._project_root / ".skillweave" / "hooks" / DISMISSED_FILENAME
        )
        self._dismissed: Set[str] = set()
        self._load()

    def _dismiss_key(self, binding: DiscoveredBinding) -> str:
        """Create a unique key for a discovered binding."""
        return f"{binding.capability}:{binding.phase}:{binding.position}"

    def _load(self) -> None:
        """Load dismissed keys from disk."""
        if not self._file_path.exists():
            self._dismissed = set()
            return

        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
            self._dismissed = set(data.get("dismissed", []))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load dismissal registry: %s", exc)
            self._dismissed = set()

    def _save(self) -> None:
        """Persist dismissed keys to disk."""
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"dismissed": sorted(self._dismissed)}
        self._file_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )

    def is_dismissed(self, binding: DiscoveredBinding) -> bool:
        """Check if a binding has been dismissed."""
        return self._dismiss_key(binding) in self._dismissed

    def dismiss(self, binding: DiscoveredBinding) -> None:
        """Dismiss a binding so it doesn't reappear."""
        key = self._dismiss_key(binding)
        self._dismissed.add(key)
        self._save()
        logger.info("Dismissed auto-discovered binding: %s", key)

    def undismiss(self, binding: DiscoveredBinding) -> None:
        """Re-enable a previously dismissed binding."""
        key = self._dismiss_key(binding)
        self._dismissed.discard(key)
        self._save()
        logger.info("Re-enabled auto-discovered binding: %s", key)

    def filter_dismissed(
        self, bindings: List[DiscoveredBinding]
    ) -> List[DiscoveredBinding]:
        """Filter out dismissed bindings from a list.

        Returns:
            Only bindings that have NOT been dismissed.
        """
        return [b for b in bindings if not self.is_dismissed(b)]

    def clear(self) -> None:
        """Clear all dismissals."""
        self._dismissed.clear()
        self._save()

    @property
    def dismissed_count(self) -> int:
        return len(self._dismissed)
