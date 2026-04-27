from typing import Optional

from .classifier import Classification, ClassifiedItem
from .dedup import DuplicateGroup
from .archive import ArchiveManifest


def score_to_grade(score: float) -> str:
    if score >= 0.9:
        return "A"
    if score >= 0.8:
        return "B"
    if score >= 0.7:
        return "C"
    if score >= 0.6:
        return "D"
    if score >= 0.5:
        return "E"
    return "F"


def _calculate_score(classified: list[ClassifiedItem], duplicates: list) -> float:
    if not classified:
        return 1.0

    n = len(classified)
    penalty = 0.0

    # Count by class
    counts = {c: 0 for c in Classification}
    for ci in classified:
        counts[ci.classification] = counts.get(ci.classification, 0) + 1

    # Penalty weights
    penalty += counts.get(Classification.DEPRECATED, 0) * 0.15 / n
    penalty += counts.get(Classification.LEGACY, 0) * 0.10 / n
    penalty += counts.get(Classification.NEEDS_REVIEW, 0) * 0.08 / n
    penalty += counts.get(Classification.CONSOLIDATION, 0) * 0.03 / n

    # Duplicate penalty
    dup_wasted = sum(g.size_bytes for g in duplicates) if duplicates else 0
    total_bytes = sum(ci.item.size_bytes for ci in classified) or 1
    dup_ratio = dup_wasted / total_bytes
    penalty += dup_ratio * 0.3

    score = max(0.0, min(1.0, 1.0 - penalty))
    return round(score, 2)


def _top_recommendations(classified: list[ClassifiedItem], score: float) -> list[str]:
    recs = []
    counts = {c: 0 for c in Classification}
    for ci in classified:
        counts[ci.classification] = counts.get(ci.classification, 0) + 1

    if counts.get(Classification.DEPRECATED, 0) > 0:
        recs.append(f"🧹 {counts[Classification.DEPRECATED]} deprecierte Dateien entfernen oder .gitignore ergänzen")
    if counts.get(Classification.LEGACY, 0) > 0:
        recs.append(f"📦 {counts[Classification.LEGACY]} Legacy-Dateien archivieren")
    if counts.get(Classification.NEEDS_REVIEW, 0) > 0:
        recs.append(f"🔍 {counts[Classification.NEEDS_REVIEW]} Dateien manuell prüfen")
    if counts.get(Classification.CONSOLIDATION, 0) > 0:
        recs.append(f"📋 {counts[Classification.CONSOLIDATION]} Dateien konsolidieren")

    if score < 0.6:
        recs.insert(0, "⚠️  Dringender Handlungsbedarf — Hygiene-Score kritisch")
    elif score < 0.8:
        recs.insert(0, "📈 Mittlerer Handlungsbedarf — gezielte Cleanups empfohlen")

    return recs[:5]


def generate_report(classified: list[ClassifiedItem],
                    duplicates: list,
                    archive: Optional[ArchiveManifest] = None) -> str:
    score = _calculate_score(classified, duplicates)
    grade = score_to_grade(score)
    recs = _top_recommendations(classified, score)

    counts = {c: 0 for c in Classification}
    for ci in classified:
        counts[ci.classification] = counts.get(ci.classification, 0) + 1

    lines = [
        "# Repo Health Report\n",
        f"**Hygiene Score**: {grade} ({score})\n",
        "## Klassifikation\n",
    ]
    for c in Classification:
        cnt = counts.get(c, 0)
        pct = round(cnt / len(classified) * 100, 1) if classified else 0
        lines.append(f"- **{c.value}**: {cnt} ({pct}%)")

    lines.append("\n## Empfehlungen\n")
    for r in recs:
        lines.append(f"- {r}")

    if duplicates:
        lines.append(f"\n## Duplikate\n")
        lines.append(f"- {len(duplicates)} Gruppen gefunden")
        wasted = sum(g.size_bytes for g in duplicates)
        lines.append(f"- Verschwendeter Speicher: **{wasted / 1024:.1f} KB**")

    if archive:
        lines.append(f"\n## Archiv\n")
        lines.append(f"- {len(archive.archived_paths)} Dateien archiviert am {archive.archive_date}")
        lines.append(f"- Restored: {archive.restored}")

    return "\n".join(lines)
