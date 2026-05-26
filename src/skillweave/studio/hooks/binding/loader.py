"""Binding loader — reads YAML config files from project and user directories.

Resolution sources (in precedence order):
  1. Project-level:  <project_root>/.skillweave/hooks/<phase>-<position>.yaml
  2. User-level:     ~/.skillweave/hooks/<phase>-<position>.yaml
  3. Auto-discovered: injected by the discovery module (not loaded from disk)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .schema import BindingConfig, BindingValidationError

logger = logging.getLogger(__name__)


class BindingLoader:
    """Loads binding configs from the filesystem.

    Args:
        project_root: Absolute path to the project root.
        user_dir: Override for the user-level hooks directory
                  (default: ~/.skillweave/hooks/).
    """

    def __init__(
        self,
        project_root: str = ".",
        user_dir: Optional[str] = None,
    ):
        self._project_root = Path(project_root)
        self._user_dir = Path(user_dir) if user_dir else Path.home() / ".skillweave" / "hooks"

    @property
    def project_hooks_dir(self) -> Path:
        return self._project_root / ".skillweave" / "hooks"

    @property
    def user_hooks_dir(self) -> Path:
        return self._user_dir

    def load_file(self, path: Path, source: str = "project") -> BindingConfig:
        """Load and validate a single YAML binding file.

        Args:
            path: Path to the YAML file.
            source: Origin tag for hooks in this file (project | user).

        Returns:
            Validated BindingConfig.

        Raises:
            BindingValidationError: On invalid YAML or schema violations.
            FileNotFoundError: If the file doesn't exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"Binding config not found: {path}")

        raw_text = path.read_text(encoding="utf-8")

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise BindingValidationError(
                f"Invalid YAML in {path}: {exc}"
            ) from exc

        if data is None:
            raise BindingValidationError(f"Empty YAML file: {path}")

        config = BindingConfig.from_dict(data, source_path=str(path))

        # Tag each hook with its source
        for hook in config.hooks:
            hook.source = source  # type: ignore[assignment]

        return config

    def load_for_phase(
        self,
        phase: str,
        position: str,
    ) -> Dict[str, List[BindingConfig]]:
        """Load binding configs for a specific phase+position from both sources.

        Returns:
            Dict with keys 'project', 'user', each containing a list of
            BindingConfig objects found for that source.
        """
        filename = f"{phase}-{position}.yaml"
        result: Dict[str, List[BindingConfig]] = {"project": [], "user": []}

        # Project-level
        project_path = self.project_hooks_dir / filename
        if project_path.exists():
            try:
                config = self.load_file(project_path, source="project")
                result["project"].append(config)
            except (BindingValidationError, FileNotFoundError) as exc:
                logger.warning("Skipping invalid project binding %s: %s", project_path, exc)

        # User-level
        user_path = self.user_hooks_dir / filename
        if user_path.exists():
            try:
                config = self.load_file(user_path, source="user")
                result["user"].append(config)
            except (BindingValidationError, FileNotFoundError) as exc:
                logger.warning("Skipping invalid user binding %s: %s", user_path, exc)

        return result

    def load_all(self) -> List[BindingConfig]:
        """Load all binding configs from both project and user directories.

        Scans for all YAML files matching the <phase>-<position>.yaml pattern.

        Returns:
            List of all valid BindingConfig objects found.
        """
        from ..models import Phase, Position

        configs: List[BindingConfig] = []

        for phase in Phase:
            for position in Position:
                by_source = self.load_for_phase(phase.value, position.value)
                configs.extend(by_source["project"])
                configs.extend(by_source["user"])

        return configs
