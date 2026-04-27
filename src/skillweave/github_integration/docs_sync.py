"""Auto-docs sync module.

Scans source code for docstrings, checks documentation coverage,
and generates documentation sync reports.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DocCoverageItem:
    file_path: str
    class_name: str
    function_name: str
    has_docstring: bool
    docstring_length: int = 0


@dataclass
class DocsSyncResult:
    timestamp: str = ""
    total_functions: int = 0
    documented: int = 0
    coverage_pct: float = 0.0
    items: list[DocCoverageItem] = field(default_factory=list)
    missing_docs: list[DocCoverageItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


_FUNC_RE = re.compile(
    r"^(?:async\s+)?def\s+(\w+)\s*\(",
    re.MULTILINE,
)
_CLASS_RE = re.compile(
    r"^class\s+(\w+)",
    re.MULTILINE,
)
_DOCSTRING_RE = re.compile(r'"""(.*?)"""', re.DOTALL)


class DocsSynchronizer:
    def __init__(self, repo_root: str | None = None):
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()

    def scan_python_files(self, paths: list[str] | None = None) -> DocsSyncResult:
        result = DocsSyncResult(timestamp=datetime.utcnow().isoformat() + "Z")

        source_dir = self.repo_root / "src"
        if not source_dir.exists():
            result.errors.append(f"Source directory not found: {source_dir}")
            return result

        if paths:
            py_files = [Path(p) for p in paths if Path(p).suffix == ".py"]
        else:
            py_files = list(source_dir.rglob("*.py"))

        for py_file in sorted(py_files):
            try:
                content = py_file.read_text()
                relative = str(py_file.relative_to(self.repo_root))
            except Exception:
                continue

            classes = _CLASS_RE.findall(content)
            functions = _FUNC_RE.findall(content)

            docstrings = _DOCSTRING_RE.findall(content)
            docstring_starts = set()
            for ds in docstrings:
                pos = content.index(f'"""')
                docstring_starts.add(pos)

            for cls_name in classes:
                cls_pattern = rf"class\s+{re.escape(cls_name)}\b"
                cls_match = re.search(cls_pattern, content)
                if not cls_match:
                    continue
                cls_start = cls_match.start()
                cls_body = content[cls_start:cls_start + 500]
                has_docs = bool(_DOCSTRING_RE.search(cls_body))
                ds_len = 0
                if has_docs:
                    ds_match = _DOCSTRING_RE.search(cls_body)
                    if ds_match:
                        ds_len = len(ds_match.group(1).strip())
                item = DocCoverageItem(
                    file_path=relative,
                    class_name=cls_name,
                    function_name="",
                    has_docstring=has_docs,
                    docstring_length=ds_len,
                )
                result.items.append(item)
                if not has_docs:
                    result.missing_docs.append(item)
                result.total_functions += 1
                if has_docs:
                    result.documented += 1

            for func_name in functions:
                func_pattern = rf"^(?:async\s+)?def\s+{re.escape(func_name)}\b"
                func_match = re.search(func_pattern, content, re.MULTILINE)
                if not func_match:
                    continue
                func_start = func_match.start()
                func_body = content[func_start:func_start + 500]
                has_docs = bool(_DOCSTRING_RE.search(func_body))
                ds_len = 0
                if has_docs:
                    ds_match = _DOCSTRING_RE.search(func_body)
                    if ds_match:
                        ds_len = len(ds_match.group(1).strip())
                item = DocCoverageItem(
                    file_path=relative,
                    class_name="",
                    function_name=func_name,
                    has_docstring=has_docs,
                    docstring_length=ds_len,
                )
                result.items.append(item)
                if not has_docs:
                    result.missing_docs.append(item)
                result.total_functions += 1
                if has_docs:
                    result.documented += 1

        if result.total_functions > 0:
            result.coverage_pct = round(result.documented / result.total_functions * 100, 1)

        return result

    def generate_markdown(self, result: DocsSyncResult) -> str:
        lines = [
            "# Documentation Sync Report",
            "",
            f"_Generated: {result.timestamp}_",
            "",
            "## Coverage Summary",
            "",
            f"- **Total functions/classes**: {result.total_functions}",
            f"- **Documented**: {result.documented}",
            f"- **Missing docs**: {len(result.missing_docs)}",
            f"- **Coverage**: {result.coverage_pct}%",
            "",
        ]

        if result.missing_docs:
            lines.append("## Missing Documentation")
            lines.append("")
            for item in result.missing_docs:
                if item.class_name:
                    lines.append(f"- `{item.file_path}` → class `{item.class_name}`")
                else:
                    lines.append(f"- `{item.file_path}` → `{item.function_name}()`")
            lines.append("")

        if result.errors:
            lines.append("## Errors")
            for err in result.errors:
                lines.append(f"- ⚠️ {err}")
            lines.append("")

        return "\n".join(lines)

    def generate_json(self, result: DocsSyncResult) -> str:
        return json.dumps({
            "timestamp": result.timestamp,
            "total_functions": result.total_functions,
            "documented": result.documented,
            "coverage_pct": result.coverage_pct,
            "missing_docs": [
                {"file": i.file_path, "class": i.class_name, "function": i.function_name}
                for i in result.missing_docs
            ],
            "errors": result.errors,
        }, indent=2)
