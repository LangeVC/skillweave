import hashlib
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from .scanner import InventoryItem


@dataclass
class DuplicateGroup:
    hash: str
    paths: list[str]
    size_bytes: int
    match_type: str


def _md5(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return None


def _file_signature(path: str) -> Optional[str]:
    try:
        with open(path, "r", errors="ignore") as f:
            content = f.read()
        return hashlib.md5(content.encode()).hexdigest()
    except OSError:
        return None


def _content_similar(a: str, b: str) -> float:
    try:
        with open(a, "r", errors="ignore") as fa, open(b, "r", errors="ignore") as fb:
            ca, cb = fa.read(), fb.read()
        if not ca or not cb:
            return 0.0
        return SequenceMatcher(None, ca, cb).ratio()
    except OSError:
        return 0.0


def find_duplicates(items: list[InventoryItem], fuzzy_threshold: float = 0.85) -> list[DuplicateGroup]:
    text_exts = {"py", "js", "ts", "md", "txt", "yaml", "yml", "json", "html", "css", "scss", "xml", "toml", "cfg", "ini", "sh", "bat"}
    groups: dict[str, DuplicateGroup] = {}
    seen = set()

    # 1. Exact MD5 match (all files)
    for item in items:
        h = _file_signature(item.path) if item.file_type in text_exts else _md5(item.path)
        if h is None or h in seen:
            continue
        if h in groups:
            groups[h].paths.append(item.path)
            groups[h].size_bytes += item.size_bytes
        else:
            groups[h] = DuplicateGroup(hash=h, paths=[item.path], size_bytes=item.size_bytes, match_type="exact")
        seen.add(h)

    # 2. Fuzzy match (text files only)
    text_items = [i for i in items if i.file_type in text_exts]
    fuzzy_groups: list[list[InventoryItem]] = []
    assigned = set()

    for i, a in enumerate(text_items):
        if a.path in assigned:
            continue
        cluster = [a]
        assigned.add(a.path)
        for b in text_items[i + 1:]:
            if b.path in assigned:
                continue
            if _content_similar(a.path, b.path) >= fuzzy_threshold:
                cluster.append(b)
                assigned.add(b.path)
        if len(cluster) > 1:
            fuzzy_groups.append(cluster)

    fuzz_group: dict[str, DuplicateGroup] = {}
    for cluster in fuzzy_groups:
        key = hashlib.md5("|".join(sorted(c.path for c in cluster)).encode()).hexdigest()
        if key not in fuzz_group:
            fuzz_group[key] = DuplicateGroup(
                hash=key,
                paths=[c.path for c in cluster],
                size_bytes=sum(c.size_bytes for c in cluster),
                match_type="fuzzy",
            )

    result = [g for g in groups.values() if len(g.paths) > 1]
    result.extend(fuzz_group.values())
    return result


def dedup_report(groups: list[DuplicateGroup]) -> str:
    if not groups:
        return "## Duplikate\n\nKeine Duplikate gefunden."

    lines = ["## Duplikate\n"]
    exact = [g for g in groups if g.match_type == "exact"]
    fuzzy = [g for g in groups if g.match_type == "fuzzy"]

    if exact:
        lines.append(f"### Exakte Duplikate ({len(exact)} Gruppen)\n")
        for g in sorted(exact, key=lambda x: -x.size_bytes):
            lines.append(f"- **{g.size_bytes / 1024:.1f} KB**: {g.paths[0]}")
            for p in g.paths[1:]:
                lines.append(f"  └ {p}")

    if fuzzy:
        lines.append(f"\n### Fuzzy-Duplikate ({len(fuzzy)} Gruppen)\n")
        for g in sorted(fuzzy, key=lambda x: -x.size_bytes):
            lines.append(f"- Ähnlichkeit ≥ 85% ({g.size_bytes / 1024:.1f} KB): {g.paths[0]}")
            for p in g.paths[1:]:
                lines.append(f"  └ {p}")

    return "\n".join(lines)
