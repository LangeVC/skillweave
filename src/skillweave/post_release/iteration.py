from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from .feedback import FeedbackItem
from .retrospective import RetroItem


EFFORT_ORDER = {"small": 1, "medium": 2, "large": 3}
URGENCY_ORDER = {"high": 3, "medium": 2, "low": 1}

#: Near-duplicate threshold, matching the repo-health file dedup default.
DEFAULT_FUZZY_THRESHOLD = 0.85


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

    backlog = dedupe_backlog(backlog)
    backlog.sort(key=lambda x: x.priority_score, reverse=True)
    return backlog


def dedupe_backlog(
    items: list[BacklogItem],
    existing: Optional[list[BacklogItem]] = None,
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
) -> list[BacklogItem]:
    """Drop backlog candidates already present, exactly or near-exactly.

    The first occurrence of a description wins; later ones are dropped.
    ``existing`` seeds the seen-set so a fresh batch is deduplicated against
    an already-planned backlog rather than only against itself. Exact matches
    are keyed by a normalised MD5 of the description (mirroring
    ``repo_health.dedup``); remaining near-matches are found with
    :class:`difflib.SequenceMatcher` at ``fuzzy_threshold`` (default 0.85, the
    repo-health file-dedup default).
    """
    seen: list[BacklogItem] = list(existing or [])
    exact_seen: dict[str, BacklogItem] = {_exact_key(i.description): i for i in seen}

    kept: list[BacklogItem] = []
    for item in items:
        key = _exact_key(item.description)
        if key in exact_seen:
            continue
        if _find_near_duplicate(seen + kept, item.description, fuzzy_threshold) is not None:
            continue
        exact_seen[key] = item
        kept.append(item)
    return kept


def _exact_key(description: str) -> str:
    normalised = " ".join(description.lower().split())
    return hashlib.md5(normalised.encode("utf-8")).hexdigest()


def _find_near_duplicate(
    pool: list[BacklogItem],
    description: str,
    threshold: float,
) -> Optional[BacklogItem]:
    target = " ".join(description.lower().split())
    if not target:
        return None
    for candidate in pool:
        other = " ".join(candidate.description.lower().split())
        if not other:
            continue
        if SequenceMatcher(None, target, other).ratio() >= threshold:
            return candidate
    return None


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
