"""Council Profile Parser (DR-004).

Parses declarative Council profiles that define required capabilities instead of
hardcoded model IDs, while preserving full backward compatibility with legacy
model-ID-based profiles.

Acceptance Criteria:
1. Profiles define capabilities instead of IDs.
2. Parser extracts capability lists.
3. Backward compatibility (if a profile uses a hardcoded ID, it should still work).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


# ── CouncilProfile Dataclass ──────────────────────────────────────────────────

@dataclass
class CouncilProfile:
    """A parsed Council profile definition.

    Represents either a modern capability-based profile (e.g. ``capabilities=['reasoning']``)
    or a legacy model-ID-based profile (e.g. ``models=['deepseek-v4-pro']``) for backward
    compatibility.
    """

    name: str
    capabilities: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    chairman: Optional[str] = None
    chairman_capabilities: list[str] = field(default_factory=list)
    mode: str = "full"
    temperature: float = 0.5
    use: str = ""
    description: str = ""
    min_models_required: int = 2
    max_cost: Optional[float] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.description and self.use:
            self.description = self.use
        elif not self.use and self.description:
            self.use = self.description

        # Normalize capabilities
        self.capabilities = [c.strip().lower() for c in self.capabilities if c and c.strip()]
        self.chairman_capabilities = [c.strip().lower() for c in self.chairman_capabilities if c and c.strip()]

        # If chairman was given as a capability keyword and chairman_capabilities is empty, populate it
        if self.chairman and not self.chairman_capabilities:
            if _is_likely_capability(self.chairman):
                self.chairman_capabilities = [self.chairman.strip().lower()]

        # If capabilities were not explicitly specified but models contains capability names
        if not self.capabilities and self.models:
            caps_from_models = [m.strip().lower() for m in self.models if _is_likely_capability(m)]
            if caps_from_models:
                self.capabilities = caps_from_models

    @property
    def is_capability_based(self) -> bool:
        """Whether this profile is defined via capabilities rather than hardcoded IDs."""
        return bool(self.capabilities)

    def get_capabilities(self) -> list[str]:
        """Return the list of capabilities required by this profile."""
        if self.capabilities:
            return list(self.capabilities)
        # Fallback: derive capabilities from models if available
        derived: list[str] = []
        for m in self.models:
            derived.extend(extract_capabilities_from_model_id(m))
        return list(dict.fromkeys(derived))  # deduplicate preserving order

    def has_capability(self, capability: str) -> bool:
        """Check if this profile requires or possesses a specific capability."""
        cap_clean = capability.strip().lower()
        return cap_clean in [c.lower() for c in self.get_capabilities()]

    def resolve_models(
        self,
        policy_engine: Optional[Any] = None,
        adapter_cache: Optional[Dict[str, Any]] = None,
        unavailable_models: Optional[Sequence[str]] = None,
        fallback_models: Optional[Sequence[str]] = None,
    ) -> list[str]:
        """Resolve concrete model IDs for this profile.

        If a ``policy_engine`` (or ``adapter_cache``) is provided and the profile defines
        capabilities, the policy engine scores and selects matching models dynamically.

        If the profile carries hardcoded ``models`` (backward compatibility), those IDs are
        returned directly.

        Falls back gracefully to ``fallback_models`` or known defaults if dynamic resolution
        cannot find enough matches.
        """
        # Dynamic policy resolution if policy_engine or adapter_cache is available
        engine = policy_engine
        if engine is None and adapter_cache is not None:
            try:
                from skillweave.routing.policy import RoutingPolicyEngine
                engine = RoutingPolicyEngine(adapter_cache)
            except ImportError:
                engine = None

        if engine is not None and self.capabilities:
            unavail = list(unavailable_models or [])
            scored = engine.score_models(self.capabilities, max_cost=self.max_cost)
            selected = [
                m["model_id"] for m in scored
                if m["model_id"] not in unavail
            ]
            if selected:
                return selected

        # Backward compatibility: use explicit hardcoded model IDs
        if self.models:
            return [m for m in self.models if not unavailable_models or m not in unavailable_models]

        # Explicit fallback or default roster models
        if fallback_models:
            return list(fallback_models)

        # Default fallback
        return ["deepseek-v4-pro", "deepseek-v4-flash"]

    def resolve_chairman(
        self,
        policy_engine: Optional[Any] = None,
        adapter_cache: Optional[Dict[str, Any]] = None,
        unavailable_models: Optional[Sequence[str]] = None,
        resolved_models: Optional[Sequence[str]] = None,
    ) -> str:
        """Resolve the concrete chairman model ID."""
        engine = policy_engine
        if engine is None and adapter_cache is not None:
            try:
                from skillweave.routing.policy import RoutingPolicyEngine
                engine = RoutingPolicyEngine(adapter_cache)
            except ImportError:
                engine = None

        # Check chairman capabilities first
        target_caps = self.chairman_capabilities or (
            [self.chairman.strip().lower()] if (self.chairman and _is_likely_capability(self.chairman)) else []
        )

        if engine is not None and target_caps:
            best = engine.get_with_graceful_degradation(
                target_caps,
                max_cost=self.max_cost,
                unavailable_models=list(unavailable_models or []),
            )
            if best:
                return best

        # Backward compatibility: explicit chairman model ID
        if self.chairman and not _is_likely_capability(self.chairman):
            return self.chairman

        # Fallback to first resolved model or default
        if resolved_models:
            return resolved_models[0]
        if self.models:
            return self.models[0]

        return "deepseek-v4-pro"

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile to dictionary format."""
        return {
            "name": self.name,
            "capabilities": list(self.capabilities),
            "models": list(self.models),
            "chairman": self.chairman,
            "chairman_capabilities": list(self.chairman_capabilities),
            "mode": self.mode,
            "temperature": self.temperature,
            "use": self.use,
            "description": self.description,
            "min_models_required": self.min_models_required,
            "max_cost": self.max_cost,
            "raw": dict(self.raw),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], name: Optional[str] = None) -> CouncilProfile:
        """Construct a CouncilProfile from a mapping."""
        prof_name = name or str(data.get("name") or data.get("id") or "default")
        caps = _extract_list(data.get("capabilities") or data.get("required_capabilities"))
        models = _extract_list(data.get("models") or data.get("model"))
        chairman = data.get("chairman")
        if chairman is not None:
            chairman = str(chairman).strip()
        chairman_caps = _extract_list(data.get("chairman_capabilities") or data.get("chairman_capability"))

        mode = str(data.get("mode") or "full").lower().strip()
        try:
            temp = float(data.get("temperature", 0.5))
        except (ValueError, TypeError):
            temp = 0.5

        use = str(data.get("use") or data.get("description") or "").strip()
        try:
            min_models = int(data.get("min_models_required", data.get("min_models", 2)))
        except (ValueError, TypeError):
            min_models = 2

        max_cost = None
        if data.get("max_cost") is not None:
            try:
                max_cost = float(data["max_cost"])
            except (ValueError, TypeError):
                max_cost = None

        return cls(
            name=prof_name,
            capabilities=caps,
            models=models,
            chairman=chairman,
            chairman_capabilities=chairman_caps,
            mode=mode,
            temperature=temp,
            use=use,
            description=use,
            min_models_required=min_models,
            max_cost=max_cost,
            raw=dict(data),
        )


# ── Capability Helpers ────────────────────────────────────────────────────────

KNOWN_CAPABILITY_KEYWORDS = frozenset({
    "reasoning",
    "reason",
    "coding",
    "coder",
    "code",
    "vision",
    "vl",
    "image",
    "tools",
    "tool",
    "fast",
    "quick",
    "general",
    "analysis",
    "expert",
    "diversity",
    "diverse",
    "research",
    "math",
    "synthesis",
    "review",
    "balanced",
    "deep",
})


def _is_likely_capability(term: str) -> bool:
    """Return True if the term is likely a capability name rather than a specific model ID."""
    clean = term.strip().lower()
    if not clean:
        return False
    if clean in KNOWN_CAPABILITY_KEYWORDS:
        return True
    if "/" in clean or ":" in clean:
        return False
    if any(m in clean for m in ["deepseek", "gpt-", "claude-", "gemini-", "llama-", "mistral-"]):
        return False
    return True


def extract_capabilities_from_model_id(model_id: str) -> list[str]:
    """Derive capability list from a model identifier using known heuristics or faigate parser."""
    try:
        from skillweave.routing.faigate_adapter import parse_model_info
        info = parse_model_info(model_id)
        if info.capabilities:
            return list(info.capabilities)
    except Exception:
        pass

    mid_low = model_id.lower()
    caps = set()
    if any(k in mid_low for k in ["reason", "r1", "o1", "o3", "pro"]):
        caps.add("reasoning")
    if any(k in mid_low for k in ["coder", "code"]):
        caps.add("coding")
    if any(k in mid_low for k in ["vision", "4o", "vl"]):
        caps.add("vision")
    if any(k in mid_low for k in ["flash", "mini", "haiku", "fast"]):
        caps.add("fast")
    if not caps:
        caps.add("general")
    return sorted(list(caps))


def _extract_list(val: Any) -> list[str]:
    """Helper to safely extract a list of strings from various types."""
    if val is None:
        return []
    if isinstance(val, list):
        items: list[str] = []
        for item in val:
            if isinstance(item, str):
                items.extend([x.strip() for x in item.split(",") if x.strip()])
            elif item is not None:
                items.append(str(item).strip())
        return items
    if isinstance(val, str):
        cleaned = val.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1]
        return [part.strip().strip("'\"") for part in cleaned.split(",") if part.strip()]
    return [str(val).strip()]


# ── Markdown Profile Parsing ──────────────────────────────────────────────────

def parse_profile_markdown(text: str) -> dict[str, CouncilProfile]:
    """Parse Markdown content containing one or more Council profile definitions.

    Expected format:
    ## profile_name
    - Capabilities: reasoning, general
    - Chairman: reasoning
    - Mode: standard
    - Temperature: 0.5
    - Use: General-purpose deliberation

    Also parses backward-compatible legacy sections:
    ## legacy_profile
    - Models: deepseek-v4-pro, deepseek-v4-flash
    - Chairman: deepseek-v4-pro
    - Mode: full
    """
    profiles: dict[str, CouncilProfile] = {}
    if not text or not text.strip():
        return profiles

    lines = text.splitlines()
    current_name: Optional[str] = None
    current_lines: list[str] = []

    header_pattern = re.compile(r"^#{1,3}\s+([A-Za-z0-9_\-\.]+)\s*$")

    for line in lines:
        stripped = line.strip()
        match = header_pattern.match(stripped)
        if match:
            if current_name:
                prof = parse_profile_section(current_name, "\n".join(current_lines))
                profiles[prof.name] = prof
                current_lines = []
            header_title = match.group(1).strip().lower()
            if header_title not in {"council profiles", "profiles", "overview", "usage", "commands"}:
                current_name = header_title
        elif current_name is not None:
            current_lines.append(line)

    if current_name and current_lines:
        prof = parse_profile_section(current_name, "\n".join(current_lines))
        profiles[prof.name] = prof

    return profiles


def parse_profile_section(name: str, content: str) -> CouncilProfile:
    """Parse a single section's text into a CouncilProfile."""
    data: dict[str, Any] = {"name": name}
    raw_lines = content.splitlines()

    for line in raw_lines:
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^[-*+]\s+", "", s)
        s = re.sub(r"^\d+\.\s+", "", s)

        if ":" not in s:
            continue

        key, value = s.split(":", 1)
        k = key.strip().lower().replace(" ", "_").replace("-", "_")
        v = value.strip()

        if k in {"capabilities", "required_capabilities", "capability"}:
            data["capabilities"] = _extract_list(v)
        elif k in {"models", "model"}:
            data["models"] = _extract_list(v)
        elif k in {"chairman_capabilities", "chairman_capability"}:
            data["chairman_capabilities"] = _extract_list(v)
        elif k == "chairman":
            data["chairman"] = v.strip().strip("'\"")
        elif k == "mode":
            data["mode"] = v.strip().lower()
        elif k in {"temperature", "temp"}:
            try:
                data["temperature"] = float(v)
            except ValueError:
                pass
        elif k in {"use", "description"}:
            data["use"] = v
        elif k in {"min_models_required", "min_models"}:
            try:
                data["min_models_required"] = int(v)
            except ValueError:
                pass
        elif k in {"max_cost", "cost"}:
            try:
                data["max_cost"] = float(v)
            except ValueError:
                pass
        else:
            data[k] = v

    return CouncilProfile.from_dict(data, name=name)


# ── File and Generic Parsing Entrypoints ─────────────────────────────────────

def parse_profile_file(file_path: Union[str, Path]) -> dict[str, CouncilProfile]:
    """Parse a profile file (Markdown or YAML)."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Council profile file not found: {file_path}")

    content = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                return parse_profile_dict(data)  # type: ignore
        except Exception:
            pass

    return parse_profile_markdown(content)


def parse_profile_dict(
    data: Mapping[str, Any],
    name: Optional[str] = None,
) -> Union[CouncilProfile, dict[str, CouncilProfile]]:
    """Parse a dictionary into a CouncilProfile or dictionary of CouncilProfiles."""
    if "capabilities" in data or "models" in data or "mode" in data:
        return CouncilProfile.from_dict(data, name=name)

    result: dict[str, CouncilProfile] = {}
    for prof_name, prof_data in data.items():
        if isinstance(prof_data, Mapping):
            result[prof_name] = CouncilProfile.from_dict(prof_data, name=prof_name)
        elif isinstance(prof_data, CouncilProfile):
            result[prof_name] = prof_data
    return result


def parse_profile(
    source: Union[str, Path, Mapping[str, Any], CouncilProfile]
) -> Union[CouncilProfile, dict[str, CouncilProfile]]:
    """Universal parser accepting Markdown string, file path, dict, or CouncilProfile."""
    if isinstance(source, CouncilProfile):
        return source

    if isinstance(source, Mapping):
        return parse_profile_dict(source)

    if isinstance(source, Path):
        return parse_profile_file(source)

    if isinstance(source, str):
        if os.path.exists(source):
            return parse_profile_file(source)
        if "##" in source or "-" in source or ":" in source:
            return parse_profile_markdown(source)

        profiles = load_council_profiles()
        if source in profiles:
            return profiles[source]

    raise ValueError(f"Unable to parse council profile from source: {source!r}")


# ── Capability Extraction ─────────────────────────────────────────────────────

def extract_capabilities(source: Union[CouncilProfile, Mapping[str, Any], str, Sequence[str]]) -> list[str]:
    """Extract capability lists from any profile representation (Acceptance Criterion 2).

    Accepts:
    - CouncilProfile: returns its required capabilities.
    - Mapping/dict: extracts capabilities or required_capabilities.
    - Markdown string: parses profile(s) and returns combined capabilities.
    - Model ID / String: extracts derived capabilities.
    """
    if isinstance(source, CouncilProfile):
        return source.get_capabilities()

    if isinstance(source, Mapping):
        if "capabilities" in source or "required_capabilities" in source:
            return _extract_list(source.get("capabilities") or source.get("required_capabilities"))
        if "models" in source:
            models = _extract_list(source.get("models"))
            caps = []
            for m in models:
                caps.extend(extract_capabilities_from_model_id(m))
            return list(dict.fromkeys(caps))
        return []

    if isinstance(source, (list, tuple, set)):
        items: list[str] = []
        for elem in source:
            if isinstance(elem, str):
                items.extend(_extract_list(elem))
        return list(dict.fromkeys(items))

    if isinstance(source, str):
        if os.path.exists(source):
            profs = parse_profile_file(source)
            all_caps: list[str] = []
            for p in profs.values():
                all_caps.extend(p.get_capabilities())
            return list(dict.fromkeys(all_caps))

        if "##" in source:
            profs = parse_profile_markdown(source)
            all_caps = []
            for p in profs.values():
                all_caps.extend(p.get_capabilities())
            return list(dict.fromkeys(all_caps))

        if _is_likely_capability(source):
            return [source.strip().lower()]

        return extract_capabilities_from_model_id(source)

    return []


# ── Profile Loading & Defaults ────────────────────────────────────────────────

def find_profiles_file() -> Optional[Path]:
    """Locate the default council-profiles.md file in standard repository locations."""
    candidates = [
        Path.cwd() / "skills" / "skillweave-council" / "references" / "council-profiles.md",
        Path(__file__).resolve().parent.parent.parent.parent / "skills" / "skillweave-council" / "references" / "council-profiles.md",
        Path.cwd() / "references" / "council-profiles.md",
        Path(__file__).resolve().parent.parent.parent.parent / "references" / "council-profiles.md",
    ]
    for cand in candidates:
        if cand.exists() and cand.is_file():
            return cand
    return None


def load_council_profiles(path: Optional[Union[str, Path]] = None) -> dict[str, CouncilProfile]:
    """Load default Council profiles from file or built-in capability definitions."""
    target_path = Path(path) if path else find_profiles_file()
    if target_path and target_path.exists():
        return parse_profile_file(target_path)

    # Built-in fallback capability profiles
    return {
        "default": CouncilProfile(
            name="default",
            capabilities=["reasoning", "general"],
            chairman="reasoning",
            mode="standard",
            temperature=0.5,
            use="General-purpose deliberation",
        ),
        "quick": CouncilProfile(
            name="quick",
            capabilities=["fast", "general"],
            chairman="fast",
            mode="quick",
            temperature=0.3,
            use="Fast comparison, budget-friendly",
        ),
        "deep": CouncilProfile(
            name="deep",
            capabilities=["reasoning", "analysis", "diversity"],
            chairman="reasoning",
            mode="full",
            temperature=0.5,
            use="Comprehensive analysis, diverse perspectives",
        ),
        "expert": CouncilProfile(
            name="expert",
            capabilities=["reasoning", "expert", "analysis"],
            chairman="reasoning",
            mode="full",
            temperature=0.4,
            use="High-stakes decisions, research-grade output",
        ),
    }


def get_profile(name: str, profiles: Optional[dict[str, CouncilProfile]] = None) -> CouncilProfile:
    """Retrieve a specific Council profile by name, falling back to 'default'."""
    profs = profiles or load_council_profiles()
    clean_name = name.strip().lower() if name else "default"
    if clean_name in profs:
        return profs[clean_name]
    if "default" in profs:
        return profs["default"]
    return CouncilProfile(
        name="default",
        capabilities=["reasoning", "general"],
        chairman="reasoning",
        mode="standard",
        temperature=0.5,
    )


__all__ = [
    "CouncilProfile",
    "extract_capabilities",
    "extract_capabilities_from_model_id",
    "find_profiles_file",
    "get_profile",
    "load_council_profiles",
    "parse_profile",
    "parse_profile_dict",
    "parse_profile_file",
    "parse_profile_markdown",
    "parse_profile_section",
]
