from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RetroItem:
    category: str  # "went_well" | "to_improve" | "action_item"
    description: str
    priority: Optional[str] = None  # "P1" | "P2" | "P3" — nur für action_item
    owner: Optional[str] = None

    def __post_init__(self) -> None:
        valid_categories = {"went_well", "to_improve", "action_item"}
        if self.category not in valid_categories:
            raise ValueError(f"Invalid category: {self.category}. Must be one of {valid_categories}")
        if self.category == "action_item":
            valid_priorities = {"P1", "P2", "P3"}
            if self.priority not in valid_priorities:
                raise ValueError(f"action_item requires priority in {valid_priorities}, got {self.priority}")
        else:
            if self.priority is not None:
                raise ValueError(f"priority only valid for action_item, got category={self.category}")


def create_retro_template(release_version: str) -> dict:
    today = date.today().isoformat()
    return {
        "version": release_version,
        "date": today,
        "sections": {
            "went_well": [],
            "to_improve": [],
            "action_items": [],
        },
    }


def format_retro_report(items: list[RetroItem]) -> str:
    lines = []
    lines.append("# Retrospective Report\n")

    went_well = [i for i in items if i.category == "went_well"]
    to_improve = [i for i in items if i.category == "to_improve"]
    action_items = [i for i in items if i.category == "action_item"]

    if went_well:
        lines.append("## What went well\n")
        for item in went_well:
            lines.append(f"- {item.description}")
        lines.append("")

    if to_improve:
        lines.append("## What to improve\n")
        for item in to_improve:
            lines.append(f"- {item.description}")
        lines.append("")

    if action_items:
        lines.append("## Action Items\n")
        lines.append("| Priority | Action | Owner |")
        lines.append("|----------|--------|-------|")
        sorted_actions = sorted(action_items, key=lambda x: {"P1": 0, "P2": 1, "P3": 2}[x.priority or "P3"])
        for item in sorted_actions:
            owner = item.owner or "-"
            lines.append(f"| {item.priority} | {item.description} | {owner} |")
        lines.append("")

    lines.append("---\n")
    lines.append(f"_{len(items)} items total_  \n")
    lines.append(f"_Observe-Report kann unter `/skillweave-observe command=\"report\" session=\"<id>\"` eingebettet werden._\n")

    return "\n".join(lines)
