"""Workflow inventory module.

Scans .github/workflows/ for YAML workflow definitions,
extracts metadata, triggers, job names, and produces a structured inventory.
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WorkflowInfo:
    filename: str
    name: str
    triggers: list[str]
    jobs: list[dict]
    permissions: dict | None = None
    path: str = ""


@dataclass
class InventoryResult:
    timestamp: str = ""
    total_workflows: int = 0
    workflows: list[WorkflowInfo] = field(default_factory=list)
    trigger_summary: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class WorkflowInventory:
    def __init__(self, repo_root: str | None = None):
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self.workflows_dir = self.repo_root / ".github" / "workflows"

    def inventory(self) -> InventoryResult:
        result = InventoryResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

        if not self.workflows_dir.exists():
            result.errors.append(f"Workflows directory not found: {self.workflows_dir}")
            return result

        yaml_files = sorted(self.workflows_dir.glob("*.yml")) + sorted(self.workflows_dir.glob("*.yaml"))

        for yf in yaml_files:
            try:
                info = self._parse_workflow(yf)
                result.workflows.append(info)
                for trigger in info.triggers:
                    result.trigger_summary[trigger] = result.trigger_summary.get(trigger, 0) + 1
            except Exception as e:
                result.errors.append(f"Failed to parse {yf.name}: {e}")

        result.total_workflows = len(result.workflows)
        return result

    def _parse_workflow(self, path: Path) -> WorkflowInfo:
        import yaml
        content = path.read_text()
        data = yaml.safe_load(content) or {}

        name = data.get("name", path.stem)
        raw_on = data.get("on") or data.get(True) or data.get(False) or {}
        if isinstance(raw_on, dict):
            trigger_keys = [k for k in raw_on.keys() if isinstance(k, str) and not k.startswith("_")]
        elif isinstance(raw_on, str):
            trigger_keys = [raw_on]
        elif isinstance(raw_on, list):
            trigger_keys = raw_on
        else:
            trigger_keys = ["unknown"]
        triggers = trigger_keys
        jobs_list = []
        for job_id, job_data in (data.get("jobs", {}) or {}).items():
            if isinstance(job_data, dict):
                jobs_list.append({
                    "id": job_id,
                    "name": job_data.get("name", job_id),
                    "runs_on": job_data.get("runs-on", "ubuntu-latest"),
                    "needs": job_data.get("needs", []),
                })
            else:
                jobs_list.append({"id": job_id, "name": job_id})

        permissions = data.get("permissions")
        return WorkflowInfo(
            filename=path.name,
            name=name,
            triggers=triggers,
            jobs=jobs_list,
            permissions=permissions,
            path=str(path.relative_to(self.repo_root)) if path.is_relative_to(self.repo_root) else str(path),
        )

    def generate_markdown(self, result: InventoryResult) -> str:
        lines = [
            "# Workflow Inventory",
            "",
            f"_Generated: {result.timestamp}_",
            f"_Total workflows: {result.total_workflows}_",
            "",
        ]

        if result.trigger_summary:
            lines.append("## Trigger Summary")
            for trigger, count in sorted(result.trigger_summary.items()):
                lines.append(f"- `{trigger}`: {count} workflow(s)")
            lines.append("")

        lines.append("## Workflows")
        for wf in result.workflows:
            lines.append(f"### {wf.name} (`{wf.filename}`)")
            lines.append(f"- **Triggers**: {', '.join(wf.triggers)}")
            lines.append(f"- **Jobs**: {len(wf.jobs)}")
            for job in wf.jobs:
                lines.append(f"  - `{job['id']}` — {job.get('name', job['id'])}")
            lines.append("")

        if result.errors:
            lines.append("## Errors")
            for err in result.errors:
                lines.append(f"- ⚠️ {err}")
            lines.append("")

        return "\n".join(lines)

    def generate_json(self, result: InventoryResult) -> str:
        return json.dumps({
            "timestamp": result.timestamp,
            "total_workflows": result.total_workflows,
            "trigger_summary": result.trigger_summary,
            "workflows": [
                {
                    "filename": wf.filename,
                    "name": wf.name,
                    "triggers": wf.triggers,
                    "job_count": len(wf.jobs),
                    "jobs": wf.jobs,
                }
                for wf in result.workflows
            ],
            "errors": result.errors,
        }, indent=2)
