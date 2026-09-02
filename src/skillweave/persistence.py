"""
Persistent state management for SkillWeave Next Level.

This module handles the .skillweave folder structure, configuration,
and tracking logs to enable session recovery and mode-based behavior.
"""

import os
import warnings
import yaml
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class RiskMode(str, Enum):
    CONSERVATIVE = "conservative"
    MEDIUM = "medium"
    UNICORN = "unicorn"


class Direction(str, Enum):
    """Axis of substrate data origin: authored input or generated output.

    tracked/untracked collapses this axis into a single git bit. Declaring it
    directly lets a research pack's synthesis notes be *authored*, durable and
    confidential with no git to say so.
    """

    AUTHORED = "authored"
    GENERATED = "generated"


class Durability(str, Enum):
    """Axis of substrate persistence: survive a fresh workspace vs reconstructible.

    ``ephemeral`` is a first-class value, not the absence of a value: ``venv/``,
    ``tmp/`` and ``worktrees/`` are declared ephemeral so they are never durable
    and never disclosed.
    """

    DURABLE = "durable"
    RECONSTRUCTIBLE = "reconstructible"
    EPHEMERAL = "ephemeral"


class Disclosure(str, Enum):
    """Axis of substrate visibility: who may see the content.

    A git adapter maps this to repository visibility, a local-only adapter maps
    it to ``sealed`` (nothing leaves the machine).
    """

    OPEN = "open"
    PRIVATE = "private"
    SEALED = "sealed"


class StoreKind(str, Enum):
    """Backing-store choice carried on an area declaration, not inferred from ``.git``."""

    GIT = "git"
    LOCAL_ONLY = "local_only"


@dataclass(frozen=True)
class AreaDeclaration:
    """A named substrate area bound to its three independent axes plus its store.

    The three axes replace the single tracked/untracked bit. Direction says
    whether the content is authored input or generated output; durability says
    whether it must survive a fresh workspace or is reconstructible (or
    ephemeral); disclosure says who may see it. ``store`` names the backing
    store that realises durability and disclosure in a given environment.
    """

    name: str
    direction: Direction
    durability: Durability
    disclosure: Disclosure
    store: StoreKind = StoreKind.LOCAL_ONLY


#: The substrate areas known to the substrate contract. Every area the runtime
#: is asked to treat as durable must be present here; an unclassified area is
#: refused rather than silently classified as durable.
_AREA_REGISTRY: Dict[str, AreaDeclaration] = {}


def _register(
    name: str,
    direction: Direction,
    durability: Durability,
    disclosure: Disclosure,
    store: StoreKind = StoreKind.LOCAL_ONLY,
) -> AreaDeclaration:
    decl = AreaDeclaration(name, direction, durability, disclosure, store)
    _AREA_REGISTRY[name.rstrip("/")] = decl
    return decl


def register_area(
    name: str,
    direction: Direction,
    durability: Durability,
    disclosure: Disclosure,
    store: StoreKind = StoreKind.LOCAL_ONLY,
) -> AreaDeclaration:
    """Declare a substrate area against the three axes.

    The 2.0.0 Category Packs declare their own areas against this contract; the
    core substrate declares the canonical and the coaching areas here.
    """
    return _register(name, direction, durability, disclosure, store)


def get_area_declaration(name: str) -> Optional[AreaDeclaration]:
    """Return the declaration for a named area, or ``None`` if unclassified."""
    return _AREA_REGISTRY.get(name.rstrip("/"))


def known_areas() -> List[str]:
    """Return the sorted names of every declared substrate area."""
    return sorted(_AREA_REGISTRY)


@dataclass
class SkillWeaveConfig:
    """Configuration for SkillWeave project."""
    DEFAULT_FEATURES = {
        "checklist_execution": False,
        "design_thinking_lens": False,
        "community_patterns": False,
        "modular_templates": False,
        "capability_routing": False,
        "execution_system": False,
        "intelligent_detection": True,  # New in v0.5.5
        "interactive_guidance": True,   # New in v0.5.5
    }
    # Default intelligent detection configuration
    DEFAULT_INTELLIGENT_DETECTION = {
        "enabled": True,
        "sensitivity": "medium",  # conservative, medium, aggressive
        "auto_switch_threshold": 70,  # 0-100 score threshold for suggesting switch
        "learn_from_feedback": True,
        "store_patterns": False,  # Opt-in for community pattern sharing
        "user_preferences": {},  # User-specific preferences learned from behavior
    }
    # Default guidance configuration
    DEFAULT_GUIDANCE = {
        "show_parameter_hints": True,
        "confirm_before_switching": True,
        "persist_corrections": True,
    }
    SCHEMA_VERSION = 2  # Bump version for v0.5.5 new features
    schema_version: int = SCHEMA_VERSION
    mode: RiskMode = RiskMode.MEDIUM
    features: Dict[str, bool] = field(default_factory=lambda: SkillWeaveConfig.DEFAULT_FEATURES.copy())
    overrides: Dict[str, Any] = field(default_factory=dict)
    intelligent_detection: Dict[str, Any] = field(default_factory=lambda: SkillWeaveConfig.DEFAULT_INTELLIGENT_DETECTION.copy())
    guidance: Dict[str, Any] = field(default_factory=lambda: SkillWeaveConfig.DEFAULT_GUIDANCE.copy())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillWeaveConfig":
        """Create config from dictionary."""
        schema_version = data.get("schema_version", 1)
        mode = RiskMode(data.get("mode", "medium"))
        # Merge with default features to ensure all keys exist
        user_features = data.get("features", {})
        features = cls.DEFAULT_FEATURES.copy()
        features.update(user_features)
        overrides = data.get("overrides", {})
        # Intelligent detection config
        intelligent_detection = cls.DEFAULT_INTELLIGENT_DETECTION.copy()
        intelligent_detection.update(data.get("intelligent_detection", {}))
        # Guidance config
        guidance = cls.DEFAULT_GUIDANCE.copy()
        guidance.update(data.get("guidance", {}))
        return cls(
            schema_version=schema_version,
            mode=mode,
            features=features,
            overrides=overrides,
            intelligent_detection=intelligent_detection,
            guidance=guidance,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "schema_version": self.schema_version,
            "mode": self.mode.value,
            "features": self.features,
            "overrides": self.overrides,
            "intelligent_detection": self.intelligent_detection,
            "guidance": self.guidance,
        }


# --- Substrate area declarations (seeded at import; contract v1.5.2) ---
#
# Each area binds its three axes. Ephemeral areas (venv/, tmp/, worktrees/,
# testing/, onboarding-state) are declared EPHEMERAL so they are never durable
# and never disclosed. Areas the substrate-map documents as *Generated* are
# RECONSTRUCTIBLE; hand-authored config and policy are DURABLE. Disclosure is
# SEALED for everything inside the git-excluded substrate: nothing leaves the
# machine unless an explicit git-backed store overrides it.

_D = Direction
_L = Durability
_S = Disclosure

register_area("archive", _D.GENERATED, _L.DURABLE, _S.SEALED)
register_area("bundles.yaml", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("checklists", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("cleanup", _D.GENERATED, _L.RECONSTRUCTIBLE, _S.SEALED)
register_area("config.yaml", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("design", _D.GENERATED, _L.DURABLE, _S.SEALED)
register_area("discovery", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("handover", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("hooks", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("lenses", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("lib", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("licenses", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("lifecycle", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("manifesto", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("memory", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("onboarding-state.yaml", _D.GENERATED, _L.EPHEMERAL, _S.SEALED)
register_area("phases.yaml", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("planning", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("prds", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("prompts", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("release", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("reports", _D.GENERATED, _L.RECONSTRUCTIBLE, _S.SEALED)
register_area("rework", _D.GENERATED, _L.RECONSTRUCTIBLE, _S.SEALED)
register_area("sequences", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("specs", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("templates", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("tracking-log", _D.GENERATED, _L.DURABLE, _S.SEALED)
# Ephemeral areas invented by the coaching substrate: never durable, never disclosed.
register_area("venv", _D.GENERATED, _L.EPHEMERAL, _S.SEALED)
register_area("tmp", _D.GENERATED, _L.EPHEMERAL, _S.SEALED)
register_area("worktrees", _D.GENERATED, _L.EPHEMERAL, _S.SEALED)
register_area("testing", _D.GENERATED, _L.EPHEMERAL, _S.SEALED)
# Coaching substrate's own areas (not part of the 26 canonical SWE areas).
register_area("evidence", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("research", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("reviews", _D.AUTHORED, _L.DURABLE, _S.SEALED)
register_area("execution-artifacts", _D.GENERATED, _L.RECONSTRUCTIBLE, _S.SEALED)


class SkillWeavePersistence:
    """Manages the .skillweave folder and persistent state."""

    FOLDER_NAME = ".skillweave"
    # Tier-2 durable input directory. Lives in the CONSUMER's repo root, is
    # meant to be tracked and hand-edited, and carries no leading dot for that
    # reason. Named ``skillweave.config`` (not ``skillweave`` or ``config``) to
    # avoid colliding with the ``skillweave`` Python package in a consuming
    # project and with a ``config/`` directory already owned there (Django,
    # Rails, Kubernetes, Ansible, …). See SW152-008.
    CONFIG_TIER_DIR = "skillweave.config"
    SUBDIRS = ["handover", "specs", "tracking-log", "manifesto"]
    CONFIG_FILE = "config.yaml"
    # Anchored so a nested fixture root is not swallowed; the whole substrate is
    # git-excluded. skillweave.config/ is never added to .gitignore.
    GITIGNORE_ENTRY = "/.skillweave/"

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize persistence manager.
        
        Args:
            project_root: Root directory of the project. If None, uses current
                         working directory.
        """
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.skillweave_dir = self.project_root / self.FOLDER_NAME
        self.config_tier_dir = self.project_root / self.CONFIG_TIER_DIR
        self.config = None

    def ensure_folder_structure(self) -> None:
        """
        Create .skillweave folder with subdirectories if they don't exist.
        Also ensures .gitignore includes tracking-log exclusion.
        """
        # Create main folder
        self.skillweave_dir.mkdir(exist_ok=True, parents=True)
        
        # Create subdirectories
        for subdir in self.SUBDIRS:
            (self.skillweave_dir / subdir).mkdir(exist_ok=True)
        
        # Create default config if missing
        self._migrate_legacy_config()
        config_path = self._config_path()
        if not config_path.exists():
            self._create_default_config(config_path)
        
        # Update .gitignore if needed
        self._ensure_gitignore()

        # Seed the durable tier-2 config directory from packaged defaults.
        self._seed_config_tier()
        
        # Create README files in subdirectories
        self._create_readme_files()

    def _seed_config_tier(self) -> None:
        """Seed ``skillweave.config/`` from packaged defaults, never overwrite.

        The tier-2 directory holds the team's tuned inputs. A file that is
        absent is copied from its shipped tier-1 deliverable so a human has a
        starting point; one that already exists is left byte-identical, so a
        newer shipped default cannot clobber a tuning.
        """
        self.config_tier_dir.mkdir(exist_ok=True, parents=True)

        packaged = self._packaged_catalogue()
        target = self.config_tier_dir / "catalogue.yaml"
        if packaged is not None and packaged.exists() and not target.exists():
            target.write_bytes(packaged.read_bytes())

    def _packaged_catalogue(self) -> Optional[Path]:
        """Locate the shipped tier-1 catalogue deliverable, if present."""
        return (
            Path(__file__).resolve().parents[1]
            / "skillweave"
            / "assets"
            / "catalogue.yaml"
        )

    def _create_default_config(self, config_path: Path) -> None:
        """Create default configuration file."""
        default_config = SkillWeaveConfig()
        self.save_config(default_config)

    def _ensure_gitignore(self) -> None:
        """Ensure .gitignore excludes the substrate, but not skillweave.config/.

        The exclusion is anchored (``/.skillweave/``) so it only ignores THIS
        project's substrate and leaves any nested fixture root tracked. The
        tier-2 ``skillweave.config/`` directory is a durable input tier and is
        deliberately never added here.
        """
        gitignore_path = self.project_root / ".gitignore"
        if not gitignore_path.exists():
            return
        
        content = gitignore_path.read_text()
        lines = content.splitlines()
        
        # Check if our entry exists
        entry = self.GITIGNORE_ENTRY
        if entry not in lines:
            lines.append("")
            lines.append("# SkillWeave substrate (auto-generated)")
            lines.append(entry)
            gitignore_path.write_text("\n".join(lines))

    def _create_readme_files(self) -> None:
        """Create README.md files in subdirectories explaining their purpose."""
        readme_content = {
            "handover": "# Handover Documents\n\nDocuments for handing over work between agents or to humans.",
            "specs": "# Specifications\n\nProject specifications, PRDs, architecture documents.",
            "tracking-log": "# Tracking Logs\n\nAuto-generated progress logs. Excluded from git.",
            "manifesto": "# Project Manifesto\n\nProject-specific rules, mode settings, design principles.",
        }
        
        for subdir, content in readme_content.items():
            readme_path = self.skillweave_dir / subdir / "README.md"
            if not readme_path.exists():
                readme_path.write_text(content)

    def load_config(self) -> SkillWeaveConfig:
        """Load configuration from skillweave.config/config.yaml.

        Migrates a legacy .skillweave/config.yaml on first read, preferring the
        durable tier when both are present (see the SW152-010 contract).
        """
        self._migrate_legacy_config()

        config_path = self._config_path()
        if not config_path.exists():
            self.ensure_folder_structure()

        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}

        self.config = SkillWeaveConfig.from_dict(data)
        return self.config

    def save_config(self, config: SkillWeaveConfig) -> None:
        """Save configuration to skillweave.config/config.yaml."""
        # Ensure the durable config tier exists
        self.config_tier_dir.mkdir(exist_ok=True, parents=True)
        config_path = self._config_path()
        with open(config_path, 'w') as f:
            yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)
        self.config = config

    def _config_path(self) -> Path:
        """Resolve the durable tier-2 config path (skillweave.config/config.yaml)."""
        return self.config_tier_dir / self.CONFIG_FILE

    def _legacy_config_path(self) -> Path:
        """Resolve the legacy substrate config path (.skillweave/config.yaml)."""
        return self.skillweave_dir / self.CONFIG_FILE

    def _migrate_legacy_config(self) -> None:
        """Migrate a legacy .skillweave/config.yaml into the durable tier, once.

        Rules (SW152-010):

        * If only the legacy file exists, copy its values into
          skillweave.config/config.yaml and leave the legacy file in place
          (never delete anything in a consumer's repository).
        * If both exist, prefer skillweave.config/ and emit a single notice;
          the legacy file is left untouched and is never merged silently.
        """
        durable = self._config_path()
        legacy = self._legacy_config_path()

        if durable.exists() and legacy.exists():
            self._notify_dual_config_once()
            return

        if not durable.exists() and legacy.exists():
            # Copy the legacy values verbatim into the durable tier so a fresh
            # clone passes through the durable tier, not through defaults.
            durable.parent.mkdir(exist_ok=True, parents=True)
            durable.write_bytes(legacy.read_bytes())

    def _notify_dual_config_once(self) -> None:
        """Emit the dual-config notice at most once per process per project."""
        key = str(self.project_root)
        if key in _MIGRATION_NOTIFIED:
            return
        _MIGRATION_NOTIFIED.add(key)
        warnings.warn(
            f"Both {self._legacy_config_path()} and {self._config_path()} are "
            "present; using the durable skillweave.config/config.yaml.",
            stacklevel=2,
        )

    def get_tracking_log_path(self, session_id: str) -> Path:
        """Get path for a tracking log file."""
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{timestamp}-{session_id}.json"
        return self.skillweave_dir / "tracking-log" / filename

    def save_tracking_log(self, session_id: str, data: Dict[str, Any]) -> Path:
        """
        Save tracking log data.
        
        Returns:
            Path to the saved log file.
        """
        log_path = self.get_tracking_log_path(session_id)
        # Ensure tracking-log directory exists
        log_path.parent.mkdir(exist_ok=True, parents=True)
        with open(log_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return log_path

    def load_tracking_log(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load tracking log data."""
        log_path = self.get_tracking_log_path(session_id)
        if not log_path.exists():
            return None
        with open(log_path, 'r') as f:
            return json.load(f)

    def list_tracking_logs(self) -> List[Dict[str, str]]:
        """List all tracking logs with metadata."""
        log_dir = self.skillweave_dir / "tracking-log"
        logs = []
        if not log_dir.exists():
            return logs
        for log_file in log_dir.glob("*.json"):
            try:
                with open(log_file, 'r') as f:
                    data = json.load(f)
                    logs.append({
                        "file": log_file.name,
                        "session_id": data.get("session_id", "unknown"),
                        "timestamp": data.get("timestamp", "unknown"),
                        "size": log_file.stat().st_size,
                    })
            except:
                continue
        return logs


# No global instance to avoid cross-project contamination

# Tracks which project roots have already emitted the one-time "both config
# files present" notice. Keyed by resolved project root so the notice fires at
# most once per process per project, satisfying the "says so once" contract.
_MIGRATION_NOTIFIED: set = set()


def get_persistence(project_root: Optional[str] = None) -> SkillWeavePersistence:
    """
    Get persistence instance for project root.
    
    Args:
        project_root: Root directory of the project.
    
    Returns:
        SkillWeavePersistence instance.
    """
    # Always create new instance to avoid cross-project contamination
    return SkillWeavePersistence(project_root)


def ensure_skillweave_folder(project_root: Optional[str] = None) -> SkillWeavePersistence:
    """
    Ensure .skillweave folder exists and return persistence instance.
    
    This is the main entry point for skills to initialize the folder structure.
    """
    persistence = get_persistence(project_root)
    persistence.ensure_folder_structure()
    return persistence


def get_config(project_root: Optional[str] = None) -> SkillWeaveConfig:
    """Load and return configuration."""
    # Create new instance each time to avoid caching issues
    persistence = SkillWeavePersistence(project_root)
    return persistence.load_config()


# Token-optimized helper functions
def get_mode_only(project_root: Optional[str] = None) -> str:
    """
    Get only the mode string.
    
    Returns:
        "conservative", "medium", or "unicorn"
    """
    config = get_config(project_root)
    return config.mode.value


def is_feature_enabled(feature_name: str, project_root: Optional[str] = None) -> bool:
    """
    Check if a specific feature is enabled.
    
    Args:
        feature_name: Name of feature (e.g., "checklist_execution")
    
    Returns:
        True if feature is enabled, False otherwise
    """
    config = get_config(project_root)
    return config.features.get(feature_name, False)


def get_mode_specific_setting(setting_path: str, default: Any = None, project_root: Optional[str] = None) -> Any:
    """
    Get a mode-specific override setting.
    
    Args:
        setting_path: Dot notation path (e.g., "conservative.max_parallel_tasks")
        default: Default value if setting not found
    
    Returns:
        Setting value or default
    """
    config = get_config(project_root)
    mode = config.mode.value
    
    # Split path and navigate
    parts = setting_path.split('.')
    current = config.overrides
    
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    
    return current


def get_global_config() -> SkillWeaveConfig:
    """Load global configuration from ~/.skillweave/config.yaml.

    The global (user-home) config is a per-user setting, not a repo input tier;
    it intentionally keeps its legacy path and is unaffected by the project
    config migration in SW152-010.
    """
    global_persistence = SkillWeavePersistence(str(Path.home()))
    legacy = global_persistence._legacy_config_path()
    if legacy.exists():
        with open(legacy, 'r') as f:
            data = yaml.safe_load(f) or {}
        return SkillWeaveConfig.from_dict(data)
    return global_persistence.load_config()


def get_merged_config(project_root: Optional[str] = None) -> SkillWeaveConfig:
    """
    Get merged configuration with project config overriding global config.
    
    Project configuration takes precedence over global configuration.
    If neither exists, returns default configuration.
    """
    # Load global config
    try:
        global_config = get_global_config()
    except Exception:
        global_config = SkillWeaveConfig()
    
    # Load project config
    try:
        project_config = get_config(project_root)
    except Exception:
        project_config = SkillWeaveConfig()
    
    # Merge: project config overrides global config
    merged = SkillWeaveConfig()
    
    # Mode: project overrides global
    merged.mode = project_config.mode if project_config.mode != SkillWeaveConfig().mode else global_config.mode
    
    # Features: project overrides global
    merged_features = global_config.features.copy()
    merged_features.update(project_config.features)
    merged.features = merged_features
    
    # Overrides: project overrides global (deep merge might be needed but simple override for now)
    merged_overrides = global_config.overrides.copy()
    merged_overrides.update(project_config.overrides)
    merged.overrides = merged_overrides
    
    # Schema version: use project's if available, else global's
    merged.schema_version = project_config.schema_version if project_config.schema_version != SkillWeaveConfig().schema_version else global_config.schema_version
    
    return merged