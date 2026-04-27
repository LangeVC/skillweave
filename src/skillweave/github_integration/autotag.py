"""Auto-tag and auto-release module.

Detects version changes in pyproject.toml, compares against
existing git tags, and generates candidate tags for release.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TagCandidate:
    version: str
    tag: str
    source: str
    is_new: bool = False
    previous_tag: Optional[str] = None


@dataclass
class AutoTagResult:
    timestamp: str = ""
    current_version: str = ""
    latest_tag: Optional[str] = None
    candidates: list[TagCandidate] = field(default_factory=list)
    should_release: bool = False
    errors: list[str] = field(default_factory=list)


class AutoTagger:
    def __init__(self, repo_root: str | None = None):
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()

    def _read_version_from_pyproject(self) -> Optional[str]:
        pyproject = self.repo_root / "pyproject.toml"
        if not pyproject.exists():
            return None
        content = pyproject.read_text()
        match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if match:
            return match.group(1)
        return None

    def _read_version_from_init(self) -> Optional[str]:
        init = self.repo_root / "src" / "skillweave" / "__init__.py"
        if not init.exists():
            return None
        content = init.read_text()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
        return None

    def get_current_version(self) -> Optional[str]:
        return self._read_version_from_pyproject() or self._read_version_from_init()

    def _simulate_git_tags(self, versions: list[str]) -> list[str]:
        return [f"v{v}" for v in versions]

    def analyze(self, existing_tags: list[str] | None = None) -> AutoTagResult:
        result = AutoTagResult(timestamp=datetime.utcnow().isoformat() + "Z")

        current = self.get_current_version()
        if not current:
            result.errors.append("Could not determine current version")
            return result
        result.current_version = current

        if existing_tags:
            clean_tags = [t.lstrip("v") for t in existing_tags if t.startswith("v")]
            clean_tags.sort(key=lambda v: tuple(int(x) for x in v.split(".")))
            if clean_tags:
                result.latest_tag = clean_tags[-1]

        candidate = TagCandidate(
            version=current,
            tag=f"v{current}",
            source="pyproject.toml",
            is_new=result.latest_tag != current,
            previous_tag=f"v{result.latest_tag}" if result.latest_tag else None,
        )
        result.candidates.append(candidate)
        result.should_release = candidate.is_new
        return result

    def generate_tag_commands(self, result: AutoTagResult) -> list[str]:
        commands = []
        for candidate in result.candidates:
            if candidate.is_new:
                commands.append(f"git tag -a {candidate.tag} -m \"Release {candidate.tag}\"")
        if not commands:
            commands.append("# No new tags to create")
        return commands

    def generate_json(self, result: AutoTagResult) -> str:
        return json.dumps({
            "timestamp": result.timestamp,
            "current_version": result.current_version,
            "latest_tag": result.latest_tag,
            "should_release": result.should_release,
            "candidates": [
                {"version": c.version, "tag": c.tag, "is_new": c.is_new}
                for c in result.candidates
            ],
            "errors": result.errors,
        }, indent=2)
