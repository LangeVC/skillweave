import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .event_logger import EventLogger, LogLevel
from .timing import Timer


class ReportGenerator:
    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root).resolve()
        self.report_dir = self.project_root / ".skillweave" / "tracking-log"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        session_id: str,
        timer: Timer,
        logger: EventLogger,
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        entries = logger.get_entries()
        metrics = [e for e in entries if e.level == LogLevel.METRIC]
        errors = [e for e in entries if e.level == LogLevel.ERROR]
        warnings = [e for e in entries if e.level == LogLevel.WARNING]

        report = {
            "session_id": session_id,
            "generated_at": datetime.now().isoformat(),
            "timing": timer.summary(),
            "metrics": [e.context for e in metrics],
            "event_counts": {
                "total": len(entries),
                "info": len([e for e in entries if e.level == LogLevel.INFO]),
                "debug": len([e for e in entries if e.level == LogLevel.DEBUG]),
                "warning": len(warnings),
                "error": len(errors),
                "metric": len(metrics),
            },
            "errors": [{"message": e.message, "step_id": e.step_id, "context": e.context} for e in errors],
            "warnings": [{"message": e.message, "step_id": e.step_id} for e in warnings],
            "metadata": metadata or {},
        }

        report_path = self.report_dir / f"execution-report-{session_id}.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        md_path = self.report_dir / f"execution-report-{session_id}.md"
        self._write_markdown_report(report, md_path)

        return report

    def _write_markdown_report(self, report: dict, path: Path) -> None:
        lines = [
            f"# Execution Report: {report['session_id']}",
            f"",
            f"**Generated:** {report['generated_at']}",
            f"",
            f"## Summary",
            f"",
            f"- Total events: {report['event_counts']['total']}",
            f"- Errors: {report['event_counts']['error']}",
            f"- Warnings: {report['event_counts']['warning']}",
            f"- Metrics: {report['event_counts']['metric']}",
            f"- Total timing records: {report['timing']['total_records']}",
            f"- Total elapsed: {report['timing']['total_elapsed']:.3f}s",
            f"",
        ]

        if report["errors"]:
            lines.append(f"## Errors")
            lines.append(f"")
            for err in report["errors"]:
                lines.append(f"- **{err['message']}** (step: {err['step_id']})")
            lines.append(f"")

        if report["warnings"]:
            lines.append(f"## Warnings")
            lines.append(f"")
            for w in report["warnings"]:
                lines.append(f"- {w['message']} (step: {w['step_id']})")
            lines.append(f"")

        if report["metrics"]:
            lines.append(f"## Metrics")
            lines.append(f"")
            for m in report["metrics"]:
                name = m.get("metric_name", "unknown")
                value = m.get("metric_value", "?")
                lines.append(f"- {name}: {value}")
            lines.append(f"")

        if report.get("timing", {}).get("records"):
            lines.append(f"## Timing Records")
            lines.append(f"")
            for rec in report["timing"]["records"]:
                elapsed = rec.get("elapsed", 0)
                lines.append(f"- {rec['name']}: {elapsed:.3f}s")
            lines.append(f"")

        path.write_text("\n".join(lines))

    def generate_metrics_yaml(
        self,
        logger: EventLogger,
        path: Optional[Path] = None,
    ) -> Path:
        if path is None:
            path = self.report_dir / "metrics.yaml"

        entries = logger.get_entries()
        metrics = [
            {
                "step_id": e.step_id,
                "metric_name": e.context.get("metric_name", ""),
                "metric_value": e.context.get("metric_value", 0),
                "tags": e.context.get("tags", {}),
                "timestamp": e.timestamp,
            }
            for e in entries if e.level == LogLevel.METRIC
        ]

        import yaml
        data = {"metrics": metrics, "generated_at": datetime.now().isoformat()}

        if path.exists():
            try:
                existing = yaml.safe_load(path.read_text()) or {}
                existing_metrics = existing.get("metrics", [])
                existing_metrics.extend(metrics)
                data["metrics"] = existing_metrics
            except Exception:
                pass

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return path
