import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from .checklist import Checklist, ChecklistItem, ChecklistItemStatus, ChecklistParser


class ChecklistLoopEngine:
    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root).resolve()
        self.checklists_dir = self.project_root / ".skillweave" / "checklists"
        self.checklists_dir.mkdir(parents=True, exist_ok=True)

    def parse_nested_markdown(self, markdown: str, source_label: str = "") -> dict:
        items: list[dict] = []
        stack = [items]
        lines = markdown.strip().split("\n")

        for line in lines:
            stripped = line.rstrip()
            if not stripped.strip():
                continue
            indent = len(stripped) - len(stripped.lstrip())
            level = indent // 2

            checkbox_match = re.match(
                r'^(\s*[-*+]\s+)(\[( |x|X)\]\s+)?(.+)$', stripped
            )
            if not checkbox_match:
                continue

            checkbox_content = checkbox_match.group(4).strip()
            checked = checkbox_match.group(3) is not None and checkbox_match.group(3).strip() in ("x", "X")

            item = {
                "text": checkbox_content,
                "checked": checked,
                "children": [],
                "status": "checked" if checked else "unchecked",
            }

            text_lower = checkbox_content.lower()
            is_blocker = any(kw in text_lower for kw in ["blocker", "blocking", "blocked", "cannot proceed"])
            if is_blocker:
                item["is_blocker"] = True

            while len(stack) <= level:
                stack.append(stack[-1][-1]["children"])

            while len(stack) > level + 1:
                stack.pop()

            stack[-1].append(item)

        return {"items": items, "source": source_label}

    def flatten_items(self, nested: dict, depth: int = 0) -> list[dict]:
        result: list[dict] = []
        for item in nested.get("items", []):
            entry = {**item, "depth": depth}
            result.append(entry)
            if item.get("children"):
                result.extend(self.flatten_items({"items": item["children"]}, depth + 1))
        return result

    def find_next_unchecked(self, nested: dict) -> Optional[dict]:
        for item in nested.get("items", []):
            if not item.get("checked", False):
                if item.get("is_blocker"):
                    return {**item, "blocker": True}
                children = item.get("children", [])
                if children:
                    child_result = self.find_next_unchecked({"items": children})
                    if child_result:
                        return child_result
                return item
            children = item.get("children", [])
            if children:
                child_result = self.find_next_unchecked({"items": children})
                if child_result:
                    return child_result
        return None

    def find_next_unchecked_sibling_first(self, nested: dict) -> Optional[dict]:
        for item in nested.get("items", []):
            if not item.get("checked", False):
                if item.get("is_blocker"):
                    return {**item, "blocker": True}
                children = item.get("children", [])
                if not children:
                    return item
                if children:
                    child_result = self.find_next_unchecked({"items": children})
                    if child_result:
                        return child_result
                    return item
            children = item.get("children", [])
            if children:
                child_result = self.find_next_unchecked({"items": children})
                if child_result:
                    return child_result
        return None

    def check_for_blocker(self, nested: dict) -> Optional[dict]:
        for item in nested.get("items", []):
            if not item.get("checked", False) and item.get("is_blocker"):
                return item
            children = item.get("children", [])
            if children:
                child_result = self.check_for_blocker({"items": children})
                if child_result:
                    return child_result
        return None

    def _parse_checkbox_groups(self, line: str):
        m = re.match(r'^(\s*[-*+]\s+)(\[( |x|X)\]\s+)?(.+)$', line)
        if not m:
            m = re.match(r'^(\s*[-*+]\s+)(\[( |x|X)\])$', line)
        if not m:
            m = re.match(r'^(\s*[-*+]\s+)(.+)$', line)
        return m

    def _is_unchecked(self, m) -> bool:
        if m.lastindex is None:
            return False
        if m.lastindex < 3:
            return True
        return m.group(3) == " "

    def mark_complete(self, markdown: str, target_text: str) -> str:
        lines = markdown.split("\n")
        result: list[str] = []
        for line in lines:
            m = self._parse_checkbox_groups(line)
            if m and m.lastindex >= 2:
                text = (m.group(m.lastindex) or "").strip()
                prefix = m.group(1)
                if text == target_text and self._is_unchecked(m):
                    result.append(f"{prefix}[x] {text}")
                else:
                    result.append(line)
            else:
                result.append(line)
        return "\n".join(result)

    def mark_failed(self, markdown: str, target_text: str, reason: str) -> str:
        lines = markdown.split("\n")
        result: list[str] = []
        for line in lines:
            m = self._parse_checkbox_groups(line)
            if m and m.lastindex >= 2:
                text = (m.group(m.lastindex) or "").strip()
                prefix = m.group(1)
                if text == target_text:
                    result.append(f"{prefix}[~] {text}  # FAILED: {reason}")
                else:
                    result.append(line)
            else:
                result.append(line)
        return "\n".join(result)

    def read_nested_checklist(self, filename: str = "") -> tuple[str, dict]:
        path = self.checklists_dir / filename if filename else self._find_latest_checklist()
        if not path or not path.exists():
            return "", {"items": []}
        content = path.read_text()
        nested = self.parse_nested_markdown(content, source_label=path.name)
        return content, nested

    def save_checklist_markdown(self, content: str, filename: str = "") -> Path:
        path = self.checklists_dir / filename if filename else self._find_latest_checklist()
        if not path:
            path = self.checklists_dir / "execution-checklist.md"
        path.write_text(content)
        return path

    def get_session_file(self) -> Path:
        session_path = self.project_root / ".skillweave" / "tracking-log" / "checklist-session.json"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        return session_path

    def save_session(self, session: dict) -> None:
        path = self.get_session_file()
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except (json.JSONDecodeError, Exception):
                existing = {}
        existing.update(session)
        path.write_text(json.dumps(existing, indent=2))

    def load_session(self) -> dict:
        path = self.get_session_file()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, Exception):
            return {}

    def _find_latest_checklist(self) -> Optional[Path]:
        files = sorted(self.checklists_dir.glob("*.md"))
        return files[-1] if files else None

    def execute_loop(
        self,
        executor_fn: Callable[[str, dict], bool],
        filename: str = "",
        context: Optional[dict] = None,
    ) -> dict:
        content, nested = self.read_nested_checklist(filename)
        if not content:
            return {"status": "error", "error": "No checklist found"}

        session = self.load_session()
        session.setdefault("completed_items", [])
        session.setdefault("retries", {})
        session.setdefault("started_at", datetime.now().isoformat())

        loop_count = 0
        max_loops = 50
        results: list[dict] = []

        while loop_count < max_loops:
            loop_count += 1
            blocker = self.check_for_blocker(nested)
            if blocker:
                return {
                    "status": "blocked",
                    "blocker": blocker["text"],
                    "completed": len(results),
                    "results": results,
                }

            next_item = self.find_next_unchecked(nested)
            if not next_item:
                break

            item_text = next_item["text"]
            if item_text in session["completed_items"]:
                content = self.mark_complete(content, item_text)
                self.save_checklist_markdown(content)
                continue

            session["current_item"] = item_text
            self.save_session(session)

            try:
                success = executor_fn(item_text, next_item)
            except Exception as e:
                success = False
                next_item["error"] = str(e)

            if success:
                content = self.mark_complete(content, item_text)
                session["completed_items"].append(item_text)
                results.append({"item": item_text, "status": "passed", "depth": next_item.get("depth", 0)})
            else:
                reason = next_item.get("error", "execution returned False")
                content = self.mark_failed(content, item_text, reason)
                results.append({"item": item_text, "status": "failed", "error": reason, "depth": next_item.get("depth", 0)})

                retry_key = f"retry_{item_text}"
                session.setdefault(retry_key, 0)
                session[retry_key] += 1
                if session[retry_key] >= 3:
                    return {
                        "status": "max_retries_exceeded",
                        "item": item_text,
                        "results": results,
                    }

            self.save_checklist_markdown(content)
            content, nested = self.read_nested_checklist()

        session["completed_at"] = datetime.now().isoformat()
        session["loop_count"] = loop_count
        self.save_session(session)

        all_done = self.find_next_unchecked(nested) is None
        return {
            "status": "complete" if all_done else "partial",
            "completed": len([r for r in results if r["status"] == "passed"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "results": results,
        }
