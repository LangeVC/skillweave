"""Configuration loading and environment resolution for context profiles (SW-CONTEXT-001).

Acceptance Criteria:
1. Implement context check-pointing in `src/skillweave/core/context/`.
2. Introduce profiles for token limits (e.g. 120k for no new task, 150k for checkpoint, 170k for stop).
3. Ensure the profiles are configurable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from .limits import (
    BUILTIN_PROFILES,
    DEFAULT_PROFILE,
    ProfileConfigurationError,
    TokenLimitProfile,
    get_profile_registry,
    register_profile,
)


def load_profile_from_dict(data: Mapping[str, Any], name: Optional[str] = None) -> TokenLimitProfile:
    """Construct and register a TokenLimitProfile from dictionary configuration."""
    profile = TokenLimitProfile.from_dict(data, name=name)
    register_profile(profile, override=True)
    return profile


def load_profile_from_yaml(content_or_path: Union[str, Path]) -> TokenLimitProfile:
    """Load a TokenLimitProfile from a YAML string or file path."""
    import yaml

    content: str
    p = Path(content_or_path) if isinstance(content_or_path, (str, Path)) else None
    if p and p.exists() and p.is_file():
        content = p.read_text(encoding="utf-8")
    else:
        content = str(content_or_path)

    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ProfileConfigurationError("YAML content must define a mapping/dictionary.")

    # Check if this is a wrapped profile structure (e.g. under 'context_limits' or 'limits')
    if "context_limits" in data and isinstance(data["context_limits"], dict):
        profile_data = dict(data["context_limits"])
        if "name" not in profile_data and "name" in data:
            profile_data["name"] = data["name"]
        return load_profile_from_dict(profile_data)

    if "limits" in data and ("checkpoint_limit" in data["limits"] or "no_new_task_limit" in data["limits"]):
        profile_data = dict(data["limits"])
        if "name" not in profile_data and "name" in data:
            profile_data["name"] = data["name"]
        return load_profile_from_dict(profile_data)

    return load_profile_from_dict(data)


def load_profiles_from_yaml_file(file_path: Union[str, Path]) -> Dict[str, TokenLimitProfile]:
    """Load one or multiple token limit profiles from a YAML file."""
    import yaml

    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Context profile file not found: {file_path}")

    content = p.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ProfileConfigurationError("YAML file must define a dictionary.")

    results: Dict[str, TokenLimitProfile] = {}

    # If the file defines a list or multi-profile mapping under 'profiles' or at root
    if "profiles" in data and isinstance(data["profiles"], dict):
        for name, entry in data["profiles"].items():
            if isinstance(entry, dict):
                prof = load_profile_from_dict(entry, name=name)
                results[prof.name] = prof
    elif "profiles" in data and isinstance(data["profiles"], list):
        for entry in data["profiles"]:
            if isinstance(entry, dict):
                prof = load_profile_from_dict(entry)
                results[prof.name] = prof
    elif any(k in data for k in ("no_new_task_limit", "checkpoint_limit", "stop_limit", "context_limits")):
        # Single profile file
        prof = load_profile_from_yaml(p)
        results[prof.name] = prof
    else:
        # Map of profile_name -> profile_dict
        for name, entry in data.items():
            if isinstance(entry, dict):
                prof = load_profile_from_dict(entry, name=name)
                results[prof.name] = prof

    return results


def load_profile_from_env() -> TokenLimitProfile:
    """Load and resolve context limit profile from environment variables.

    Environment variables supported:
    - ``SW_CONTEXT_PROFILE`` or ``SKILLWEAVE_CONTEXT_PROFILE``: named profile (e.g. 'conservative')
    - ``SW_TOKEN_NO_NEW_TASK_LIMIT``: custom override for no-new-task threshold
    - ``SW_TOKEN_CHECKPOINT_LIMIT``: custom override for checkpoint threshold
    - ``SW_TOKEN_STOP_LIMIT``: custom override for stop threshold
    - ``SW_TOKEN_MAX_CONTEXT_LIMIT``: custom override for max context window
    - ``SW_TOKEN_COMPACT_LIMIT``: custom override for compact threshold
    """
    profile_name = os.environ.get("SW_CONTEXT_PROFILE") or os.environ.get("SKILLWEAVE_CONTEXT_PROFILE")
    registry = get_profile_registry()

    if profile_name and registry.has_profile(profile_name):
        base_profile = registry.get(profile_name)
    else:
        base_profile = DEFAULT_PROFILE

    # Apply specific environment overrides if present
    no_new_task = os.environ.get("SW_TOKEN_NO_NEW_TASK_LIMIT") or os.environ.get("SKILLWEAVE_TOKEN_NO_NEW_TASK_LIMIT")
    checkpoint = os.environ.get("SW_TOKEN_CHECKPOINT_LIMIT") or os.environ.get("SKILLWEAVE_TOKEN_CHECKPOINT_LIMIT")
    stop = os.environ.get("SW_TOKEN_STOP_LIMIT") or os.environ.get("SKILLWEAVE_TOKEN_STOP_LIMIT")
    max_context = os.environ.get("SW_TOKEN_MAX_CONTEXT_LIMIT") or os.environ.get("SKILLWEAVE_TOKEN_MAX_CONTEXT_LIMIT")
    compact = os.environ.get("SW_TOKEN_COMPACT_LIMIT") or os.environ.get("SKILLWEAVE_TOKEN_COMPACT_LIMIT")

    if not any([no_new_task, checkpoint, stop, max_context, compact]):
        return base_profile

    data = base_profile.to_dict()
    data["name"] = f"{base_profile.name}-env-override"

    if no_new_task:
        try:
            data["no_new_task_limit"] = int(no_new_task)
        except ValueError:
            pass
    if checkpoint:
        try:
            data["checkpoint_limit"] = int(checkpoint)
        except ValueError:
            pass
    if stop:
        try:
            data["stop_limit"] = int(stop)
        except ValueError:
            pass
    if max_context:
        try:
            data["max_context_limit"] = int(max_context)
        except ValueError:
            pass
    if compact:
        try:
            data["compact_limit"] = int(compact)
        except ValueError:
            pass

    return TokenLimitProfile.from_dict(data)


def resolve_profile(
    source: Optional[Union[str, TokenLimitProfile, Mapping[str, Any], Path]] = None,
) -> TokenLimitProfile:
    """Resolve a profile from diverse inputs: string name, file path, dict, profile instance, or None (defaults)."""
    if source is None:
        return load_profile_from_env()

    if isinstance(source, TokenLimitProfile):
        return source

    if isinstance(source, Mapping):
        return TokenLimitProfile.from_dict(source)

    if isinstance(source, Path) or (isinstance(source, str) and os.path.exists(source)):
        return load_profile_from_yaml(source)

    if isinstance(source, str):
        registry = get_profile_registry()
        if registry.has_profile(source):
            return registry.get(source)
        # Check if source is inline YAML/JSON string
        if "{" in source or ":" in source:
            try:
                return load_profile_from_yaml(source)
            except Exception:
                pass
        raise ProfileConfigurationError(f"Unknown context profile '{source}'.")

    raise ProfileConfigurationError(f"Cannot resolve context profile from source of type {type(source).__name__}.")
