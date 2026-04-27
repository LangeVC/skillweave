from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "bug": ["bug", "crash", "error", "broken", "fix", "regression", "fails", "exception"],
    "feature": ["feature", "feat", "request", "would like", "please add", "support for", "implement"],
    "improvement": ["improve", "enhancement", "refactor", "cleanup", "optimize", "better", "performance"],
    "question": ["question", "how to", "why", "what is", "help", "clarify", "documentation"],
}


@dataclass
class FeedbackItem:
    source: str  # GitHub issue URL or comment
    title: str
    category: str  # bug | feature | improvement | question
    description: str
    author: str
    date: str


def _classify_item(title: str, description: str, labels: list[str]) -> str:
    label_lower = [l.lower() for l in labels]
    if "bug" in label_lower:
        return "bug"
    if "feature" in label_lower or "enhancement" in label_lower:
        return "feature"
    if "improvement" in label_lower:
        return "improvement"
    if "question" in label_lower:
        return "question"

    text = (title + " " + description).lower()
    best_score = 0
    best_category = "question"

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category


def collect_feedback(repo: str, since_tag: Optional[str] = None) -> list[FeedbackItem]:
    items: list[FeedbackItem] = []
    if not repo:
        return items
    return items


def categorize_feedback(items: list[FeedbackItem]) -> dict[str, list[FeedbackItem]]:
    result: dict[str, list[FeedbackItem]] = {
        "bugs": [],
        "features": [],
        "improvements": [],
        "questions": [],
    }
    for item in items:
        if item.category == "bug":
            result["bugs"].append(item)
        elif item.category == "feature":
            result["features"].append(item)
        elif item.category == "improvement":
            result["improvements"].append(item)
        else:
            result["questions"].append(item)
    return result
