import os
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InventoryItem:
    path: str
    file_type: str
    size_bytes: int
    last_modified: str
    last_accessed: str


EXCLUDE_DEFAULTS = [
    ".git", "__pycache__", "node_modules", ".DS_Store",
    ".egg-info", "*.pyc", ".mypy_cache", ".pytest_cache",
    ".venv", "venv", "env", ".tox", "*.egg",
]


def _file_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if not ext:
        name = os.path.basename(path)
        if name.startswith("."):
            return "dotfile"
        if "Makefile" in name or name.endswith("makefile"):
            return "makefile"
        return "unknown"
    return ext


def _matches_any(name: str, patterns: list[str]) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(os.path.basename(name), p) for p in patterns)


def scan_inventory(root_path: str, exclude_patterns: Optional[list[str]] = None) -> list[InventoryItem]:
    if exclude_patterns is None:
        exclude_patterns = EXCLUDE_DEFAULTS
    items: list[InventoryItem] = []
    root_path = os.path.abspath(root_path)

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in exclude_patterns and not _matches_any(d, exclude_patterns)]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if _matches_any(full, exclude_patterns):
                continue
            try:
                stat = os.stat(full)
            except OSError:
                continue
            items.append(InventoryItem(
                path=full,
                file_type=_file_type(full),
                size_bytes=stat.st_size,
                last_modified=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
                last_accessed=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_atime)),
            ))
    return items


def scan_summary(items: list[InventoryItem]) -> dict:
    if not items:
        return {"total_files": 0, "total_size_mb": 0.0, "by_type": {}, "largest_files": []}

    total_bytes = sum(i.size_bytes for i in items)
    by_type: dict[str, int] = {}
    for i in items:
        by_type[i.file_type] = by_type.get(i.file_type, 0) + 1

    sorted_items = sorted(items, key=lambda x: x.size_bytes, reverse=True)
    largest = [
        {"path": i.path, "size_mb": round(i.size_bytes / (1024 * 1024), 3), "type": i.file_type}
        for i in sorted_items[:10]
    ]

    return {
        "total_files": len(items),
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "by_type": {k: v for k, v in sorted(by_type.items(), key=lambda x: -x[1])},
        "largest_files": largest,
    }
