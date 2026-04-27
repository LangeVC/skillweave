"""Auto-PR description generation module.

Generates structured PR descriptions from commit messages
grouped by conventional commit type, with diff summary.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .changelog import ChangelogGenerator, COMMIT_TYPES


@dataclass
class PRSection:
    heading: str
    items: list[str] = field(default_factory=list)


@dataclass
class PRDescriptionResult:
    timestamp: str = ""
    title: str = ""
    sections: list[PRSection] = field(default_factory=list)
    commit_count: int = 0
    files_changed: int = 0
    has_breaking_changes: bool = False
    errors: list[str] = field(default_factory=list)


class PRDescriptionGenerator:
    def __init__(self, repo_root: str | None = None):
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self._changelog = ChangelogGenerator(repo_root)

    def generate_from_commits(
        self,
        messages: list[tuple[str, str]],
        branch_name: str = "",
        files_changed: int = 0,
    ) -> PRDescriptionResult:
        entries = self._changelog.parse_commits(messages)
        commits_by_type: dict[str, list[str]] = {}
        breaking_items: list[str] = []

        for entry in entries:
            prefix = f"**{entry.scope}**: " if entry.scope else ""
            item = f"{prefix}{entry.description} ({entry.sha})"

            if entry.breaking:
                breaking_items.append(item)
            else:
                commits_by_type.setdefault(entry.category, []).append(item)

        sections: list[PRSection] = []
        total_commits = len(entries)

        section_order = ["Breaking Changes", "Features", "Improvements",
                         "Bug Fixes", "Refactoring", "Documentation",
                         "Performance", "Tests", "Chores"]

        if breaking_items:
            sections.append(PRSection(heading="Breaking Changes", items=breaking_items))

        for cat in section_order:
            if cat == "Breaking Changes":
                continue
            if cat in commits_by_type:
                sections.append(PRSection(heading=cat, items=commits_by_type[cat]))

        for cat, items in commits_by_type.items():
            if cat not in section_order:
                sections.append(PRSection(heading=cat, items=items))

        title = self._generate_title(entries, branch_name)

        return PRDescriptionResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
            title=title,
            sections=sections,
            commit_count=total_commits,
            files_changed=files_changed,
            has_breaking_changes=len(breaking_items) > 0,
        )

    def _generate_title(self, entries: list, branch_name: str) -> str:
        if branch_name:
            cleaned = branch_name.replace("-", " ").replace("_", " ").replace("/", ": ")
            words = cleaned.split()
            if words:
                return " ".join(w.capitalize() for w in words)

        for entry in entries:
            if entry.type in ("feat", "feature"):
                return f"feat: {entry.description[:80]}"
            if entry.type == "fix":
                return f"fix: {entry.description[:80]}"

        if entries:
            return f"{entries[0].type}: {entries[0].description[:80]}"
        return "Pull Request"

    def generate_markdown(self, result: PRDescriptionResult) -> str:
        lines = [
            f"## Summary",
            f"",
            f"- **{result.commit_count}** commits across **{result.files_changed}** files"
            if result.files_changed > 0 else f"- **{result.commit_count}** commits",
            f"",
        ]

        if result.has_breaking_changes:
            lines.append("> ⚠️ This PR contains breaking changes.")
            lines.append("")

        for section in result.sections:
            lines.append(f"### {section.heading}")
            for item in section.items:
                lines.append(f"- {item}")
            lines.append("")

        lines.append("### Checklist")
        lines.append("- [ ] Changes follow coding conventions")
        lines.append("- [ ] Tests added/updated")
        lines.append("- [ ] Documentation updated")
        lines.append("- [ ] CHANGELOG entry added")
        lines.append("")
        lines.append("---")
        lines.append("_Auto-generated PR description by SkillWeave_")

        return "\n".join(lines)

    def generate_json(self, result: PRDescriptionResult) -> str:
        return json.dumps({
            "title": result.title,
            "timestamp": result.timestamp,
            "commit_count": result.commit_count,
            "files_changed": result.files_changed,
            "has_breaking_changes": result.has_breaking_changes,
            "sections": [
                {"heading": s.heading, "items": s.items}
                for s in result.sections
            ],
            "errors": result.errors,
        }, indent=2)
