from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


#: The durable area a retrospective belongs to. This is the area name the
#: persistence layer declares (GENERATED, DURABLE, SEALED) and the name the
#: planning-sync backing store carries to the org planning repository.
RETRO_AREA = "retrospectives"


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


# --------------------------------------------------------------------------- #
# Durable sync
# --------------------------------------------------------------------------- #


def sync_retrospective(
    persistence: "SkillWeavePersistence",  # noqa: F821 - duck-typed, avoids import cycle
    release_version: str,
    document: str,
) -> object:
    """Persist a retrospective document into the durable ``retrospectives`` area.

    Writes ``.skillweave/retrospectives/vX.Y.Z.md`` — the exact payload the
    planning-sync contract expects (see
    ``tests/unit/test_planning_sync.py::test_retrospectives_sync_to_planning_retrospectives``),
    then carries that area to its backing store. Durability is not assumed: the
    sync reports what it carried, so an unreachable destination surfaces rather
    than being silently accepted.

    ``persistence`` is any object exposing ``skillweave_dir`` (a
    :class:`~skillweave.persistence.SkillWeavePersistence`), and the sync is
    delegated to :func:`skillweave.runtime.resolve_runtime_store` so this module
    never hard-codes git-vs-planning-sync.
    """
    from pathlib import Path

    from skillweave.runtime import resolve_runtime_store

    root = getattr(persistence, "skillweave_dir", None)
    if root is None:
        raise ValueError(
            "sync_retrospective needs a persistence object exposing skillweave_dir"
        )
    root = Path(root)
    retro_dir = root / RETRO_AREA
    retro_dir.mkdir(parents=True, exist_ok=True)

    document_path = retro_dir / f"v{release_version}.md"
    document_path.write_text(document)

    project_root = root.parent
    store = resolve_runtime_store(str(project_root))
    sync = getattr(store, "sync", None)
    if store is None or sync is None:
        # No store configured, or one that cannot carry an area (e.g. the
        # local-only adapter): report the payload at risk rather than claiming
        # a durability that was not realised.
        return {"area": RETRO_AREA, "carried": [document_path.name], "at_risk": True}
    return sync(RETRO_AREA, str(project_root))
