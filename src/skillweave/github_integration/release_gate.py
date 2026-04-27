"""Release readiness gate module.

Integrates with Initiative 03's readiness assessment to provide
a GitHub Actions-compatible release gate. Checks version bump,
changelog, tests, required files, and WIP markers.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class GateCheck:
    id: str
    name: str
    passed: bool
    detail: str = ""
    required: bool = True


@dataclass
class ReleaseGateResult:
    timestamp: str = ""
    checks: list[GateCheck] = field(default_factory=list)
    all_required_passed: bool = False
    can_release: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def required_failed(self) -> list[GateCheck]:
        return [c for c in self.checks if not c.passed and c.required]


_WIP_PATTERNS = [
    r"\bWIP\b",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bHACK\b",
    r"\bdraft\b",
    r"\bwork in progress\b",
    r"\bnot\s*ready\b",
]


class ReleaseReadinessGate:
    def __init__(self, repo_root: str | None = None):
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()

    def check_version_bump(self, current_version: str, latest_tag: Optional[str] = None) -> GateCheck:
        if not latest_tag:
            return GateCheck(
                id="version-bump",
                name="Version bumped",
                passed=True,
                detail=f"Current version: {current_version} (no previous tag found)",
                required=True,
            )

        current = current_version.lstrip("v")
        latest = latest_tag.lstrip("v")

        if current != latest:
            return GateCheck(
                id="version-bump",
                name="Version bumped",
                passed=True,
                detail=f"Version changed: {latest} → {current}",
                required=True,
            )

        return GateCheck(
            id="version-bump",
            name="Version bumped",
            passed=False,
            detail=f"Version unchanged: {current} (matches latest tag v{latest})",
            required=True,
        )

    def check_changelog(self, version: str) -> GateCheck:
        changelog = self.repo_root / "CHANGELOG.md"
        if not changelog.exists():
            return GateCheck(
                id="changelog-exists",
                name="CHANGELOG.md exists",
                passed=False,
                detail="CHANGELOG.md not found",
                required=True,
            )

        content = changelog.read_text()
        clean_ver = version.lstrip("v")
        escaped = re.escape(clean_ver)
        pattern = rf"##\s*(?:\[)?{escaped}(?:\])?"
        if re.search(pattern, content):
            return GateCheck(
                id="changelog-updated",
                name="CHANGELOG has version entry",
                passed=True,
                detail=f"Entry found for version {clean_ver}",
                required=True,
            )

        if re.search(r"##\s*\[\d+\.\d+\.\d+\]", content):
            return GateCheck(
                id="changelog-updated",
                name="CHANGELOG has version entry",
                passed=False,
                detail=f"No entry found for version {clean_ver} (other entries exist)",
                required=True,
            )

        return GateCheck(
            id="changelog-updated",
            name="CHANGELOG has version entry",
            passed=False,
            detail="No version entries found in CHANGELOG.md",
            required=True,
        )

    def check_tests(self) -> GateCheck:
        tests_dir = self.repo_root / "tests"
        if not tests_dir.exists():
            return GateCheck(
                id="tests-exist",
                name="Test suite exists",
                passed=False,
                detail="tests/ directory not found",
                required=True,
            )

        test_files = list(tests_dir.rglob("test_*.py"))
        if not test_files:
            return GateCheck(
                id="tests-exist",
                name="Test suite exists",
                passed=False,
                detail="No test_*.py files found in tests/",
                required=True,
            )

        return GateCheck(
            id="tests-exist",
            name="Test suite exists",
            passed=True,
            detail=f"{len(test_files)} test files found",
            required=True,
        )

    def check_required_files(self, required_files: list[str] | None = None) -> list[GateCheck]:
        checks = []
        files = required_files or [
            "README.md",
            "pyproject.toml",
            "CHANGELOG.md",
            "LICENSE",
        ]
        for filename in files:
            fpath = self.repo_root / filename
            exists = fpath.exists()
            checks.append(GateCheck(
                id=f"file-{filename.lower().replace('.', '-')}",
                name=f"Required file: {filename}",
                passed=exists,
                detail=f"{'Found' if exists else 'Not found'}: {filename}",
                required=True,
            ))
        return checks

    def check_wip_markers(self, paths: list[str] | None = None) -> GateCheck:
        wip_found = []

        if paths:
            search_paths = [self.repo_root / p for p in paths]
        else:
            search_paths = [self.repo_root / path for path in
                            ["src", "README.md", "CHANGELOG.md", "AGENTS.md"]
                            if (self.repo_root / path).exists()]

        combined_pattern = "|".join(_WIP_PATTERNS)

        for sp in search_paths:
            if sp.is_file():
                files_to_check = [sp]
            elif sp.is_dir():
                files_to_check = list(sp.rglob("*.py")) + list(sp.rglob("*.md"))
            else:
                continue

            for f in files_to_check:
                try:
                    content = f.read_text()
                    for match in re.finditer(combined_pattern, content, re.IGNORECASE):
                        for line_no, line in enumerate(content.split("\n"), 1):
                            if match.group() in line:
                                wip_found.append(f"{f.relative_to(self.repo_root)}:{line_no}")
                                break
                except Exception:
                    continue

        if wip_found:
            return GateCheck(
                id="no-wip-markers",
                name="No WIP/draft markers",
                passed=False,
                detail=f"Found {len(wip_found)} WIP marker(s): {', '.join(wip_found[:10])}",
                required=False,
            )

        return GateCheck(
            id="no-wip-markers",
            name="No WIP/draft markers",
            passed=True,
            detail="No WIP markers detected",
            required=False,
        )

    def check_pyproject_toml(self) -> GateCheck:
        pyproject = self.repo_root / "pyproject.toml"
        if not pyproject.exists():
            return GateCheck(
                id="pyproject-exists",
                name="pyproject.toml exists",
                passed=False,
                detail="pyproject.toml not found",
                required=True,
            )
        return GateCheck(
            id="pyproject-exists",
            name="pyproject.toml exists",
            passed=True,
            detail="pyproject.toml found",
            required=True,
        )

    def evaluate(
        self,
        current_version: str,
        latest_tag: Optional[str] = None,
        required_files: list[str] | None = None,
        wip_scan_paths: list[str] | None = None,
    ) -> ReleaseGateResult:
        result = ReleaseGateResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

        result.checks.append(self.check_version_bump(current_version, latest_tag))
        result.checks.append(self.check_changelog(current_version))
        result.checks.append(self.check_tests())
        result.checks.append(self.check_pyproject_toml())
        result.checks.extend(self.check_required_files(required_files))
        result.checks.append(self.check_wip_markers(wip_scan_paths))

        result.all_required_passed = len(result.required_failed) == 0
        result.can_release = result.all_required_passed
        return result

    def generate_markdown(self, result: ReleaseGateResult) -> str:
        lines = [
            "# Release Readiness Gate Report",
            "",
            f"_Generated: {result.timestamp}_",
            f"_Can release: {'**YES**' if result.can_release else '**NO**'}_",
            f"_Passed: {result.passed_count}/{len(result.checks)}_",
            "",
            "## Check Results",
            "",
        ]

        for check in result.checks:
            status = "✅" if check.passed else "❌"
            required = " (required)" if check.required else ""
            lines.append(f"- {status} **{check.name}**{required}")
            lines.append(f"  - {check.detail}")
            lines.append("")

        failed = result.required_failed
        if failed:
            lines.append("## Failed Required Checks")
            for check in failed:
                lines.append(f"- ❌ **{check.name}**: {check.detail}")
            lines.append("")

        lines.append("---")
        lines.append("_Auto-generated by SkillWeave Release Readiness Gate_")
        return "\n".join(lines)

    def generate_json(self, result: ReleaseGateResult) -> str:
        return json.dumps({
            "timestamp": result.timestamp,
            "can_release": result.can_release,
            "all_required_passed": result.all_required_passed,
            "passed_count": result.passed_count,
            "total_checks": len(result.checks),
            "checks": [
                {
                    "id": c.id,
                    "name": c.name,
                    "passed": c.passed,
                    "detail": c.detail,
                    "required": c.required,
                }
                for c in result.checks
            ],
            "errors": result.errors,
        }, indent=2)


def run_cli():
    """CLI entry for GitHub Actions: reads env vars, runs gate, writes outputs."""
    version = os.environ.get("RELEASE_VERSION", "unknown")
    latest_tag = os.environ.get("RELEASE_LATEST_TAG") or None
    gate = ReleaseReadinessGate()
    result = gate.evaluate(
        current_version=version,
        latest_tag=latest_tag,
        wip_scan_paths=["src", "README.md", "CHANGELOG.md"],
    )

    markdown = gate.generate_markdown(result)
    with open("release-gate-report.md", "w") as f:
        f.write(markdown)

    json_out = gate.generate_json(result)
    with open("release-gate-data.json", "w") as f:
        f.write(json_out)

    data = json.loads(json_out)
    print(f"can_release={'true' if result.can_release else 'false'}")
    print(f"passed_count={data['passed_count']}")
    print(f"total_checks={data['total_checks']}")

    for check in result.checks:
        if not check.passed:
            level = "error" if check.required else "warning"
            print(f"::{level} title=ReleaseGate::{check.name}: {check.detail}")


import os
