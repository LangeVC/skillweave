"""Auto-changelog generation module.

Parses conventional commit messages and generates structured
changelog entries grouped by type.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


COMMIT_TYPES = {
    "feat": "Features",
    "feature": "Features",
    "fix": "Bug Fixes",
    "bugfix": "Bug Fixes",
    "docs": "Documentation",
    "doc": "Documentation",
    "style": "Styling",
    "refactor": "Refactoring",
    "perf": "Performance",
    "performance": "Performance",
    "test": "Tests",
    "testing": "Tests",
    "build": "Build System",
    "ci": "Continuous Integration",
    "chore": "Chores",
    "revert": "Reverts",
    "improvement": "Improvements",
    "improv": "Improvements",
}


@dataclass
class CommitEntry:
    sha: str
    type: str
    scope: Optional[str]
    description: str
    breaking: bool = False
    category: str = "Other"


@dataclass
class ChangelogSection:
    category: str
    entries: list[CommitEntry] = field(default_factory=list)


@dataclass
class ChangelogResult:
    timestamp: str = ""
    version: str = ""
    sections: list[ChangelogSection] = field(default_factory=list)
    total_commits: int = 0
    has_breaking_changes: bool = False
    errors: list[str] = field(default_factory=list)


_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>\w+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?\s*:\s*(?P<description>.+)",
    re.IGNORECASE,
)


class ChangelogGenerator:
    def __init__(self, repo_root: str | None = None):
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()

    def parse_commit(self, message: str, sha: str = "") -> Optional[CommitEntry]:
        match = _CONVENTIONAL_RE.match(message.strip())
        if not match:
            return None
        raw_type = match.group("type").lower()
        scope = match.group("scope") or None
        description = match.group("description").strip()
        breaking = match.group("breaking") == "!"
        category = COMMIT_TYPES.get(raw_type, raw_type.capitalize())
        return CommitEntry(
            sha=sha[:7] if sha else "",
            type=raw_type,
            scope=scope,
            description=description,
            breaking=breaking,
            category=category,
        )

    def parse_commits(self, messages: list[tuple[str, str]]) -> list[CommitEntry]:
        entries = []
        for sha, message in messages:
            entry = self.parse_commit(message, sha)
            if entry:
                entries.append(entry)
        return entries

    def generate(self, entries: list[CommitEntry], version: str = "") -> ChangelogResult:
        result = ChangelogResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
            version=version,
            total_commits=len(entries),
        )

        sections_map: dict[str, list[CommitEntry]] = {}
        for entry in entries:
            if entry.breaking:
                result.has_breaking_changes = True
            if entry.category == "Other" and entry.type in COMMIT_TYPES:
                entry.category = COMMIT_TYPES[entry.type]
            sections_map.setdefault(entry.category, []).append(entry)

        ordered_categories = [
            "Breaking Changes",
            "Features",
            "Improvements",
            "Bug Fixes",
            "Documentation",
            "Performance",
            "Refactoring",
            "Styling",
            "Tests",
            "Build System",
            "Continuous Integration",
            "Chores",
            "Reverts",
        ]

        for cat in ordered_categories:
            if cat in sections_map:
                result.sections.append(ChangelogSection(
                    category=cat, entries=sections_map[cat]
                ))
        for cat, entries in sections_map.items():
            if cat not in ordered_categories:
                result.sections.append(ChangelogSection(
                    category=cat, entries=entries
                ))

        return result

    def generate_markdown(self, result: ChangelogResult) -> str:
        lines = ["# Changelog", ""]
        if result.version:
            lines.append(f"## [{result.version}] - {datetime.utcnow().strftime('%Y-%m-%d')}")
            lines.append("")

        if result.has_breaking_changes:
            lines.append("### Breaking Changes")
            for section in result.sections:
                for entry in section.entries:
                    if entry.breaking:
                        scope = f"**{entry.scope}**: " if entry.scope else ""
                        lines.append(f"- {scope}{entry.description}")
            lines.append("")

        for section in result.sections:
            non_breaking = [e for e in section.entries if not e.breaking]
            if not non_breaking:
                continue
            lines.append(f"### {section.category}")
            for entry in non_breaking:
                scope = f"**{entry.scope}**: " if entry.scope else ""
                lines.append(f"- {scope}{entry.description}")
            lines.append("")

        return "\n".join(lines)

    def generate_json(self, result: ChangelogResult) -> str:
        return json.dumps({
            "version": result.version,
            "timestamp": result.timestamp,
            "total_commits": result.total_commits,
            "has_breaking_changes": result.has_breaking_changes,
            "sections": [
                {
                    "category": s.category,
                    "entries": [
                        {
                            "sha": e.sha,
                            "type": e.type,
                            "scope": e.scope,
                            "description": e.description,
                            "breaking": e.breaking,
                        }
                        for e in s.entries
                    ],
                }
                for s in result.sections
            ],
        }, indent=2)
