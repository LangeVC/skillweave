import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


MEMORY_CATEGORIES = ["rules", "decisions", "conventions", "architecture", "open-issues"]


class ExecutionMemory:
    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root).resolve()
        self.memory_dir = self.project_root / ".skillweave" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._seed_categories()

    def _seed_categories(self) -> None:
        for cat in MEMORY_CATEGORIES:
            path = self.memory_dir / f"{cat}.yaml"
            if not path.exists():
                with open(path, "w") as f:
                    yaml.dump({"category": cat, "entries": []}, f, default_flow_style=False)

    def _category_path(self, category: str) -> Path:
        return self.memory_dir / f"{category}.yaml"

    def write_entry(
        self,
        category: str,
        content: str,
        source: str = "",
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        if category not in MEMORY_CATEGORIES:
            raise ValueError(f"Unknown category '{category}'. Valid: {MEMORY_CATEGORIES}")

        entry = {
            "timestamp": datetime.now().isoformat(),
            "content": content,
            "source": source,
            "tags": tags or [],
            "metadata": metadata or {},
        }

        path = self._category_path(category)
        data = self._read_category(category)
        data["entries"].append(entry)
        self._write_category(category, data)
        return entry

    def read_all(self) -> dict[str, list[dict]]:
        result = {}
        for cat in MEMORY_CATEGORIES:
            data = self._read_category(cat)
            result[cat] = data.get("entries", [])
        return result

    def read_category(self, category: str) -> list[dict]:
        if category not in MEMORY_CATEGORIES:
            return []
        data = self._read_category(category)
        return data.get("entries", [])

    def search(self, query: str, category: Optional[str] = None) -> list[dict]:
        results = []
        cats = [category] if category else MEMORY_CATEGORIES
        query_lower = query.lower()
        for cat in cats:
            entries = self.read_category(cat)
            for entry in entries:
                content = entry.get("content", "").lower()
                tags = " ".join(entry.get("tags", [])).lower()
                if query_lower in content or query_lower in tags:
                    results.append({**entry, "category": cat})
        return results

    def search_by_tag(self, tag: str, category: Optional[str] = None) -> list[dict]:
        results = []
        cats = [category] if category else MEMORY_CATEGORIES
        for cat in cats:
            entries = self.read_category(cat)
            for entry in entries:
                if tag in entry.get("tags", []):
                    results.append({**entry, "category": cat})
        return results

    def count_entries(self) -> dict[str, int]:
        counts = {}
        for cat in MEMORY_CATEGORIES:
            entries = self.read_category(cat)
            counts[cat] = len(entries)
        return counts

    def summary(self) -> dict[str, Any]:
        counts = self.count_entries()
        total = sum(counts.values())
        return {"total_entries": total, "category_counts": counts, "categories": MEMORY_CATEGORIES}

    def _read_category(self, category: str) -> dict[str, Any]:
        path = self._category_path(category)
        try:
            with open(path) as f:
                return yaml.safe_load(f) or {"category": category, "entries": []}
        except (FileNotFoundError, yaml.YAMLError):
            return {"category": category, "entries": []}

    def _write_category(self, category: str, data: dict) -> None:
        path = self._category_path(category)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
