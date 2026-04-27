from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .feedback import FeedbackItem
from .retrospective import RetroItem


EFFORT_ORDER = {"small": 1, "medium": 2, "large": 3}
URGENCY_ORDER = {"high": 3, "medium": 2, "low": 1}


@dataclass
class BacklogItem:
    source: str  # "retro" or "feedback"
    description: str
    effort: str = "medium"  # "small" | "medium" | "large"
    urgency: str = "medium"  # "high" | "medium" | "low"
    priority_score: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.effort not in EFFORT_ORDER:
            raise ValueError(f"Invalid effort: {self.effort}")
        if self.urgency not in URGENCY_ORDER:
            raise ValueError(f"Invalid urgency: {self.urgency}")


def plan_iteration(
    feedback_items: list[FeedbackItem],
    retro_items: list[RetroItem],
) -> list[BacklogItem]:
    backlog: list[BacklogItem] = []

    for item in feedback_items:
        effort = _estimate_effort(item)
        urgency = _estimate_urgency(item)
        backlog.append(
            BacklogItem(
                source="feedback",
                description=f"[{item.category}] {item.title}: {item.description}",
                effort=effort,
                urgency=urgency,
            )
        )

    for item in retro_items:
        if item.category == "action_item":
            priority_map = {"P1": "high", "P2": "medium", "P3": "low"}
            urgency = priority_map.get(item.priority or "P3", "low")
            backlog.append(
                BacklogItem(
                    source="retro",
                    description=item.description,
                    effort="medium",
                    urgency=urgency,
                )
            )

    for bl in backlog:
        bl.priority_score = URGENCY_ORDER.get(bl.urgency, 1) / EFFORT_ORDER.get(bl.effort, 2)

    backlog.sort(key=lambda x: x.priority_score, reverse=True)
    return backlog


def _estimate_effort(item: FeedbackItem) -> str:
    text = (item.title + " " + item.description).lower()
    if any(kw in text for kw in ["large", "major", "overhaul", "epic", "complex"]):
        return "large"
    if any(kw in text for kw in ["small", "minor", "typo", "quick", "simple"]):
        return "small"
    return "medium"


def _estimate_urgency(item: FeedbackItem) -> str:
    if item.category == "bug":
        return "high"
    if item.category == "feature":
        return "medium"
    return "low"


def format_backlog(items: list[BacklogItem], fmt: str = "markdown") -> str:
    if fmt == "markdown":
        return _format_markdown(items)
    return _format_markdown(items)


def _format_markdown(items: list[BacklogItem]) -> str:
    lines = ["# Iteration Backlog\n"]
    lines.append("| # | Score | Source | Description | Effort | Urgency |")
    lines.append("|---|-------|--------|-------------|--------|---------|")

    for idx, item in enumerate(items, start=1):
        lines.append(
            f"| {idx} | {item.priority_score:.2f} | {item.source} | {item.description} | {item.effort} | {item.urgency} |"
        )
    lines.append("")

    high = sum(1 for i in items if i.urgency == "high")
    medium = sum(1 for i in items if i.urgency == "medium")
    low = sum(1 for i in items if i.urgency == "low")
    lines.append(f"_{len(items)} items: {high} high, {medium} medium, {low} low urgency_\n")

    return "\n".join(lines)
