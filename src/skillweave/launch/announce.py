import json
import os
import re
from datetime import datetime, timezone
from typing import Optional


def generate_release_notes(summary: dict, format: str = "markdown") -> str:
    changelog = _read_changelog()
    version = summary.get("version", _extract_latest_version(changelog))
    title = summary.get("title", f"Release v{version}")
    features = summary.get("features", [])
    fixes = summary.get("fixes", [])
    breaking = summary.get("breaking", [])

    if format == "json":
        notes = {
            "version": version,
            "title": title,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "changelog_section": changelog,
            "features": features,
            "fixes": fixes,
            "breaking": breaking,
        }
        return json.dumps(notes, indent=2)

    lines = [f"# {title}", "", f"**Release Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}", ""]

    if changelog:
        lines.append("## Changelog")
        lines.append("")
        lines.append(changelog)
        lines.append("")

    if features:
        lines.append("## ✨ Features")
        lines.append("")
        for f in features:
            lines.append(f"- {f}")
        lines.append("")

    if fixes:
        lines.append("## 🐛 Bug Fixes")
        lines.append("")
        for f in fixes:
            lines.append(f"- {f}")
        lines.append("")

    if breaking:
        lines.append("## ⚠️ Breaking Changes")
        lines.append("")
        for b in breaking:
            lines.append(f"- {b}")
        lines.append("")

    return "\n".join(lines)


def format_announcement(release_notes: str, channels: list = None) -> dict:
    if channels is None:
        channels = ["release"]

    result = {}
    for channel in channels:
        if channel == "release":
            result[channel] = {
                "subject": "New Release",
                "body": release_notes,
                "format": "markdown",
            }
        elif channel == "slack":
            sections = re.split(r"^## ", release_notes, flags=re.MULTILINE)
            blocks = []
            for section in sections:
                section = section.strip()
                if not section:
                    continue
                if section.startswith("# "):
                    blocks.append({"type": "header", "text": section.lstrip("# ").strip()})
                elif section.startswith("## "):
                    lines = section.split("\n")
                    blocks.append({"type": "section", "text": lines[0].lstrip("## ").strip()})
                else:
                    lines = [l for l in section.split("\n") if l.strip()]
                    if lines:
                        blocks.append({
                            "type": "section",
                            "text": "\n".join(l.strip("- ") for l in lines),
                        })
            result[channel] = {"blocks": blocks, "format": "slack_blocks"}
        elif channel == "json":
            result[channel] = {"payload": release_notes, "format": "json"}
        else:
            result[channel] = {"body": release_notes, "format": "markdown"}

    return result


def _read_changelog() -> Optional[str]:
    path = os.environ.get("CHANGELOG_PATH", "CHANGELOG.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def _extract_latest_version(changelog: Optional[str]) -> str:
    if not changelog:
        return "0.0.0"
    match = re.search(r"##\s*\[?(\d+\.\d+\.\d+)\]?", changelog)
    return match.group(1) if match else "0.0.0"
