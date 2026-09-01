"""Core rework-brief logic for SkillWeave.

Reads the gate log for a failed lane and produces a structured Markdown rework
brief that a controller can hand to the correcting agent without any manual
editing.

Gate log discovery order
------------------------
1. ``.skillweave/tracking-log/<lane_id>/status.yaml``  (YAML tracking log)
2. ``.skillweave/tracking-log/<lane_id>/gate_*.json``  (JSON gate receipts, newest first)
3. ``.skillweave/tracking-log/<lane_id>/*.json``        (any JSON files, newest first)
4. Release-gate data file ``release-gate-data.json`` at project root (fallback)

Output
------
Brief written to ``.skillweave/rework/<lane_id>-<timestamp>.md``.
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    import yaml as _yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------

class ReworkError(RuntimeError):
    """Raised when a rework brief cannot be produced."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class GateLogEntry:
    """A single gate-check entry extracted from a gate log.

    Attributes
    ----------
    check_id:
        Machine-readable identifier (e.g. ``"capacium-manifests"``).
    name:
        Human-readable name of the check.
    passed:
        ``True`` when the check passed, ``False`` when it failed.
    detail:
        Free-text explanation emitted by the gate runner.
    required:
        Whether this check is blocking.  Non-required failures are surfaced
        but do not block release.
    """

    check_id: str
    name: str
    passed: bool
    detail: str = ""
    required: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GateLogEntry":
        """Construct from a gate-check dictionary (JSON/YAML representation)."""
        return cls(
            check_id=str(data.get("id", data.get("check_id", "unknown"))),
            name=str(data.get("name", "")),
            passed=bool(data.get("passed", False)),
            detail=str(data.get("detail", data.get("message", ""))),
            required=bool(data.get("required", True)),
        )


@dataclass
class ReworkBrief:
    """Structured rework brief produced from a failed gate log.

    Attributes
    ----------
    lane_id:
        The lane identifier (e.g. ``"SW-CLI-REWORK-001"``).
    task_ids:
        Task IDs extracted from the gate log (may be empty if not present).
    failing_criteria:
        Entries from the gate log that did not pass.
    gate_log_path:
        Absolute path to the gate log file that was read.
    generated_at:
        UTC timestamp of when the brief was generated.
    """

    lane_id: str
    task_ids: List[str] = field(default_factory=list)
    failing_criteria: List[GateLogEntry] = field(default_factory=list)
    gate_log_path: Optional[Path] = None
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


# ---------------------------------------------------------------------------
# Gate log reader
# ---------------------------------------------------------------------------

class GateLogReader:
    """Finds and parses the gate log for a given lane.

    Parameters
    ----------
    project_root:
        Root of the SkillWeave project.  Defaults to the current working
        directory.
    """

    _TRACKING_ROOT = ".skillweave/tracking-log"
    _RELEASE_GATE_FILENAME = "release-gate-data.json"

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = Path(project_root or Path.cwd()).resolve()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def read(self, lane_id: str) -> ReworkBrief:
        """Load the gate log for *lane_id* and return a :class:`ReworkBrief`.

        Raises
        ------
        ReworkError
            When no gate log can be found for the given lane.
        """
        log_path, raw = self._find_and_load(lane_id)
        entries, task_ids = self._parse(raw, lane_id)
        failing = [e for e in entries if not e.passed]
        return ReworkBrief(
            lane_id=lane_id,
            task_ids=task_ids,
            failing_criteria=failing,
            gate_log_path=log_path,
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _find_and_load(self, lane_id: str) -> tuple[Path, Any]:
        """Return ``(path, parsed_data)`` for the best gate log found."""
        candidates = list(self._candidate_paths(lane_id))
        for path in candidates:
            try:
                data = self._load_file(path)
                if data is not None:
                    return path, data
            except Exception:
                continue
        raise ReworkError(
            f"No gate log found for lane '{lane_id}'. "
            f"Searched: {[str(p) for p in candidates]}"
        )

    def _candidate_paths(self, lane_id: str) -> Sequence[Path]:
        """Yield candidate gate-log paths in priority order."""
        lane_dir = self.project_root / self._TRACKING_ROOT / lane_id

        # 1. Standard status YAML
        yield lane_dir / "status.yaml"

        # 2. JSON gate receipts (newest first)
        if lane_dir.is_dir():
            gate_jsons = sorted(
                lane_dir.glob("gate_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            yield from gate_jsons

            # 3. Any JSON in the lane directory
            all_jsons = sorted(
                [p for p in lane_dir.glob("*.json") if p not in gate_jsons],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            yield from all_jsons

        # 4. Project-root release-gate fallback
        yield self.project_root / self._RELEASE_GATE_FILENAME

    def _load_file(self, path: Path) -> Optional[Any]:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            if not _YAML_AVAILABLE:  # pragma: no cover
                raise ReworkError(
                    "PyYAML is required to read YAML gate logs. "
                    "Install it with: pip install PyYAML"
                )
            return _yaml.safe_load(text)
        # JSON (or anything else — try JSON)
        return json.loads(text)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse(
        self, raw: Any, lane_id: str
    ) -> tuple[List[GateLogEntry], List[str]]:
        """Normalise *raw* into a list of entries and task IDs."""
        if isinstance(raw, dict):
            return self._parse_dict(raw, lane_id)
        if isinstance(raw, list):
            # Bare list of check objects
            entries = [GateLogEntry.from_dict(item) for item in raw if isinstance(item, dict)]
            return entries, []
        return [], []

    def _parse_dict(
        self, data: dict, lane_id: str
    ) -> tuple[List[GateLogEntry], List[str]]:
        """Handle the two common dict shapes: release-gate JSON and status YAML."""
        task_ids: List[str] = []
        entries: List[GateLogEntry] = []

        # --- release-gate-data.json shape ---
        if "checks" in data and isinstance(data["checks"], list):
            entries = [
                GateLogEntry.from_dict(c)
                for c in data["checks"]
                if isinstance(c, dict)
            ]
            return entries, task_ids

        # --- status.yaml shape ---
        # Task IDs can be in completed_tasks or deliverables
        if "completed_tasks" in data and isinstance(data["completed_tasks"], list):
            task_ids = [str(t) for t in data["completed_tasks"]]

        # Extract failing criteria from known YAML fields
        entries.extend(self._yaml_entries_from_status(data))

        return entries, task_ids

    def _yaml_entries_from_status(self, data: dict) -> List[GateLogEntry]:
        """Convert known status.yaml fields into synthetic gate-check entries."""
        entries: List[GateLogEntry] = []
        state = str(data.get("state", ""))
        status_detail = str(data.get("status_detail", ""))

        # An overall FAILED / ERROR state is itself a failing criterion
        failed_states = {"FAILED", "ERROR", "BLOCKED", "REJECTED", "STOPPED"}
        if any(s in state.upper() for s in failed_states):
            entries.append(GateLogEntry(
                check_id="overall-state",
                name="Overall lane state",
                passed=False,
                detail=f"State: {state}. {status_detail}".strip(". "),
                required=True,
            ))

        # Synthesize entries from reproducible_test_count
        rtc = data.get("reproducible_test_count", {})
        if isinstance(rtc, dict):
            for key, val in rtc.items():
                if isinstance(val, dict):
                    failed = val.get("failed", 0)
                    if int(failed) > 0:
                        entries.append(GateLogEntry(
                            check_id=f"test-suite-{key}",
                            name=f"Test suite: {key}",
                            passed=False,
                            detail=f"{val.get('passed', 0)} passed, {failed} failed",
                            required=True,
                        ))

        # Discovery baseline failures
        disc = data.get("discovery_baseline", {})
        if isinstance(disc, dict):
            for env, info in disc.items():
                if isinstance(info, dict):
                    failed_tests = info.get("failed_tests", [])
                    if failed_tests:
                        entries.append(GateLogEntry(
                            check_id=f"discovery-{env}",
                            name=f"Discovery baseline ({env})",
                            passed=False,
                            detail="Failed: " + ", ".join(str(t) for t in failed_tests),
                            required=False,
                        ))

        return entries


# ---------------------------------------------------------------------------
# Brief writer
# ---------------------------------------------------------------------------

_NEXT_STEPS_TEMPLATE = [
    "Review each failing criterion listed above and identify the root cause.",
    "Update the relevant source files, tests, or configuration to address each failure.",
    "Re-run the gate checks locally (`skillweave run ...`) to verify the fix.",
    "Commit the corrections with a message referencing the lane ID and criterion IDs.",
    "Submit for re-review once all required criteria pass.",
]

_VERDICT_TEMPLATE = """\
## VERDICT

> **Instructions for the reviewer**: After correcting the items above, fill in
> this section and return the brief to the controller.

| Field          | Value |
|----------------|-------|
| Reviewer       | _<name / model-id>_ |
| Review date    | _<YYYY-MM-DD>_ |
| Outcome        | ☐ PASS  ☐ FAIL  ☐ PARTIAL |
| Notes          | _<free text>_ |

### Criteria sign-off

<!-- For each failing criterion above, mark ✅ (fixed), ❌ (still failing),
     or ⏭️ (deferred with justification). -->
"""


class ReworkBriefWriter:
    """Writes a Markdown rework brief for a failed lane.

    Parameters
    ----------
    project_root:
        Root of the SkillWeave project.  Defaults to the current working
        directory.
    output_dir:
        Directory to write briefs into.  Defaults to
        ``<project_root>/.skillweave/rework/``.
    """

    _DEFAULT_OUTPUT_SUBDIR = ".skillweave/rework"

    def __init__(
        self,
        project_root: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.output_dir = (
            Path(output_dir).resolve()
            if output_dir
            else self.project_root / self._DEFAULT_OUTPUT_SUBDIR
        )
        self._reader = GateLogReader(self.project_root)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def write(self, lane_id: str) -> Path:
        """Generate and persist a rework brief for *lane_id*.

        Returns
        -------
        Path
            Absolute path to the written Markdown file.

        Raises
        ------
        ReworkError
            When no gate log can be found for the lane.
        """
        brief = self._reader.read(lane_id)
        return self._persist(brief)

    def write_brief(self, brief: ReworkBrief) -> Path:
        """Persist a pre-built :class:`ReworkBrief` object.

        This is the low-level variant useful for testing without touching the
        filesystem twice.
        """
        return self._persist(brief)

    # ------------------------------------------------------------------
    # Markdown rendering
    # ------------------------------------------------------------------

    def render(self, brief: ReworkBrief) -> str:
        """Return the full Markdown text for *brief*."""
        ts_iso = brief.generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_human = brief.generated_at.strftime("%Y-%m-%d %H:%M UTC")
        log_ref = (
            str(brief.gate_log_path.relative_to(self.project_root))
            if brief.gate_log_path
            else "—"
        )

        lines: List[str] = [
            f"# Rework Brief — {brief.lane_id}",
            "",
            f"**Generated:** {ts_human}  ",
            f"**Gate log:** `{log_ref}`",
            "",
            "---",
            "",
            "## Lane Information",
            "",
            f"| Field    | Value |",
            f"|----------|-------|",
            f"| Lane ID  | `{brief.lane_id}` |",
        ]

        if brief.task_ids:
            task_list = ", ".join(f"`{t}`" for t in brief.task_ids)
            lines.append(f"| Task IDs | {task_list} |")
        else:
            lines.append("| Task IDs | _none recorded in gate log_ |")

        lines += [
            "",
            "---",
            "",
            "## Failing Criteria",
            "",
        ]

        if not brief.failing_criteria:
            lines.append(
                "> ⚠️  No explicit failing criteria were extracted from the gate log.  "
                "The log may use an unrecognised format.  Review the log manually."
            )
        else:
            blocking = [e for e in brief.failing_criteria if e.required]
            advisory = [e for e in brief.failing_criteria if not e.required]

            if blocking:
                lines += [
                    "### 🔴 Blocking failures (must be fixed)",
                    "",
                ]
                for entry in blocking:
                    lines += self._render_criterion(entry)

            if advisory:
                lines += [
                    "### 🟡 Advisory failures (non-blocking)",
                    "",
                ]
                for entry in advisory:
                    lines += self._render_criterion(entry)

        lines += [
            "",
            "---",
            "",
            "## Suggested Next Steps",
            "",
        ]
        for i, step in enumerate(_NEXT_STEPS_TEMPLATE, start=1):
            lines.append(f"{i}. {step}")

        lines += [
            "",
            "---",
            "",
            _VERDICT_TEMPLATE.rstrip(),
            "",
            "---",
            "",
            f"<!-- Rework brief auto-generated by `skillweave rework` at {ts_iso} -->",
        ]

        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_criterion(entry: GateLogEntry) -> List[str]:
        lines = [
            f"#### `{entry.check_id}` — {entry.name}",
            "",
        ]
        if entry.detail:
            # Wrap long detail lines for readability
            wrapped = textwrap.fill(entry.detail, width=100)
            lines += [
                "**Detail:**",
                "",
                f"> {wrapped.replace(chr(10), chr(10) + '> ')}",
                "",
            ]
        return lines

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, brief: ReworkBrief) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ts = brief.generated_at.strftime("%Y%m%dT%H%M%SZ")
        # Sanitise lane_id so it is safe for filenames
        safe_lane = re.sub(r"[^\w\-]", "_", brief.lane_id)
        filename = f"{safe_lane}-{ts}.md"
        out_path = self.output_dir / filename
        out_path.write_text(self.render(brief), encoding="utf-8")
        return out_path
