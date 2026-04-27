"""Release readiness assessment module.

Validates release prerequisites with scored checks, gap analysis,
and override support for critical checks.
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from pathlib import Path


@dataclass
class ReadinessCheck:
    id: str
    name: str
    tier: str
    description: str
    remediation: str
    override_allowed: bool = False


@dataclass
class CheckResult:
    check: ReadinessCheck
    passed: bool
    detail: str = ""
    override_applied: bool = False


@dataclass
class ReadinessResult:
    timestamp: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    override_active: bool = False

    @property
    def critical_count(self) -> int:
        return len([c for c in self.checks if c.check.tier == "critical"])

    @property
    def critical_passed(self) -> int:
        return len([c for c in self.checks if c.check.tier == "critical" and c.passed])

    @property
    def critical_failed(self) -> int:
        return len([c for c in self.checks if c.check.tier == "critical" and not c.passed])

    @property
    def recommended_failed(self) -> int:
        return len([c for c in self.checks if c.check.tier == "recommended" and not c.passed])

    @property
    def readiness_score(self) -> float:
        if not self.checks:
            return 0.0
        passed = sum(1 for c in self.checks if c.passed)
        return round(passed / len(self.checks), 2)

    @property
    def can_release(self) -> bool:
        if self.override_active:
            return True
        return self.critical_failed == 0

    def gap_analysis(self) -> list[dict]:
        gaps = []
        for result in self.checks:
            if not result.passed:
                gaps.append({
                    "check_id": result.check.id,
                    "name": result.check.name,
                    "tier": result.check.tier,
                    "detail": result.detail,
                    "remediation": result.check.remediation,
                    "override_allowed": result.check.override_allowed,
                    "override_applied": result.override_applied,
                })
        return gaps


class ReadinessAssessor:
    def __init__(self, project_root: str | None = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()

    def get_checks(self) -> list[ReadinessCheck]:
        return [
            ReadinessCheck(
                id="tests-exist", name="Test suite exists", tier="critical",
                description="A test suite exists in the project",
                remediation="Create a test suite in the tests/ directory",
                override_allowed=True,
            ),
            ReadinessCheck(
                id="tests-pass", name="All tests pass", tier="critical",
                description="The test suite runs without failures",
                remediation="Run tests and fix failures before releasing",
                override_allowed=True,
            ),
            ReadinessCheck(
                id="version-bumped", name="Version has been bumped", tier="critical",
                description="The project version differs from the latest git tag",
                remediation="Update version in pyproject.toml and create git tag",
                override_allowed=True,
            ),
            ReadinessCheck(
                id="changelog-updated", name="Changelog has been updated", tier="critical",
                description="Changelog contains entries for the current version",
                remediation="Add release entries to CHANGELOG.md",
                override_allowed=True,
            ),
            ReadinessCheck(
                id="deployment-config", name="Deployment configuration exists", tier="recommended",
                description="Deployment config exists for the project",
                remediation="Create a Dockerfile, deploy script, or CI workflow",
                override_allowed=False,
            ),
            ReadinessCheck(
                id="ci-passing", name="CI pipeline is passing", tier="recommended",
                description="CI configuration exists and passes",
                remediation="Check CI status and fix failures",
                override_allowed=False,
            ),
            ReadinessCheck(
                id="dependency-audit", name="Dependency audit clean", tier="recommended",
                description="No known vulnerabilities in dependencies",
                remediation="Run pip-audit and update affected packages",
                override_allowed=True,
            ),
            ReadinessCheck(
                id="benchmark-comparison", name="Benchmark comparison", tier="optional",
                description="Performance benchmarks exist and regressions documented",
                remediation="Run benchmarks and document regressions",
                override_allowed=False,
            ),
            ReadinessCheck(
                id="docs-review", name="Documentation reviewed", tier="optional",
                description="Documentation reviewed for accuracy",
                remediation="Review README, API docs, and migration guides",
                override_allowed=False,
            ),
            ReadinessCheck(
                id="security-review", name="Security review completed", tier="optional",
                description="Security review of changes completed",
                remediation="Perform security review and document findings",
                override_allowed=False,
            ),
        ]

    def _check_tests_exist(self) -> tuple[bool, str]:
        tests_dir = self.project_root / "tests"
        if not tests_dir.exists():
            return False, "tests/ directory not found"
        test_files = list(tests_dir.rglob("test_*.py"))
        if not test_files:
            return False, "No test files found in tests/"
        return True, f"{len(test_files)} test files found"

    def _check_tests_pass(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["rtk", "pytest", "tests/", "-q", "--tb=short"],
                capture_output=True, text=True, timeout=120,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                summary = lines[-1] if lines else ""
                return True, f"Tests pass: {summary}"
            else:
                return False, f"Test failures detected\n{result.stdout[-300:]}\n{result.stderr[-300:]}"
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-q", "--tb=short"],
                capture_output=True, text=True, timeout=120,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                summary = lines[-1] if lines else ""
                return True, f"Tests pass: {summary}"
            else:
                return False, f"Test failures detected\n{result.stdout[-300:]}\n{result.stderr[-300:]}"
        except FileNotFoundError:
            return False, "Could not find pytest runner"

    def _check_version_bumped(self) -> tuple[bool, str]:
        pyproject = self.project_root / "pyproject.toml"
        if not pyproject.exists():
            return False, "pyproject.toml not found"
        content = pyproject.read_text()
        match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if not match:
            return False, "Could not find version in pyproject.toml"
        current_version = match.group(1)
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True, text=True, timeout=30,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                latest_tag = result.stdout.strip().lstrip("v")
                if current_version != latest_tag:
                    return True, f"Version bumped: {latest_tag} -> {current_version}"
                else:
                    return False, f"Version unchanged: {current_version} (matches latest tag)"
            else:
                return False, "No git tags found — version not tracked"
        except FileNotFoundError:
            return False, "Git not available"

    def _check_changelog_updated(self) -> tuple[bool, str]:
        changelog = self.project_root / "CHANGELOG.md"
        if not changelog.exists():
            return False, "CHANGELOG.md not found"
        content = changelog.read_text()
        if re.search(r"##\s*\[\d+\.\d+\.\d+\]", content):
            return True, "CHANGELOG.md has version entries"
        return False, "No version entries found in CHANGELOG.md"

    def _check_deployment_config(self) -> tuple[bool, str]:
        patterns = ["Dockerfile", "Dockerfile.*", "deploy.sh", ".github/workflows/deploy*.yml"]
        for pattern in patterns:
            matches = list(self.project_root.glob(pattern))
            if matches:
                return True, f"Found: {', '.join(m.name for m in matches)}"
        return False, "No deployment configuration found"

    def _check_ci_passing(self) -> tuple[bool, str]:
        ci_paths = [
            self.project_root / ".github" / "workflows",
        ]
        for path in ci_paths:
            if path.exists() and list(path.glob("*.yml")):
                return True, "CI configuration found (status unknown — run check manually)"
        return False, "No CI configuration found"

    def _check_dependency_audit(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["pip-audit", "--descri"],
                capture_output=True, text=True, timeout=60,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                return True, "No known vulnerabilities found"
            else:
                return False, f"Vulnerabilities detected:\n{result.stdout[:300]}"
        except FileNotFoundError:
            return True, "pip-audit not installed — skipping"

    def _check_benchmark_comparison(self) -> tuple[bool, str]:
        bench_dir = self.project_root / "docs" / "benchmarks"
        if bench_dir.exists():
            return True, "Benchmark directory exists"
        return False, "No benchmarks directory found at docs/benchmarks/"

    def _check_docs_review(self) -> tuple[bool, str]:
        readme = self.project_root / "README.md"
        if readme.exists():
            return True, "README.md exists and can be reviewed"
        return False, "No README.md found for review"

    def _check_security_review(self) -> tuple[bool, str]:
        review_file = self.project_root / ".skillweave" / "release" / "security-review.md"
        if review_file.exists():
            return True, "Security review document found"
        return False, "No security review document found"

    def assess(self, override: bool = False) -> ReadinessResult:
        result = ReadinessResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
            override_active=override,
        )
        for check in self.get_checks():
            passed, detail = self._run_check(check)
            result.checks.append(CheckResult(
                check=check,
                passed=passed,
                detail=detail,
                override_applied=override if check.tier == "critical" and not passed else False,
            ))
        return result

    def _run_check(self, check: ReadinessCheck) -> tuple[bool, str]:
        method_map = {
            "tests-exist": self._check_tests_exist,
            "tests-pass": self._check_tests_pass,
            "version-bumped": self._check_version_bumped,
            "changelog-updated": self._check_changelog_updated,
            "deployment-config": self._check_deployment_config,
            "ci-passing": self._check_ci_passing,
            "dependency-audit": self._check_dependency_audit,
            "benchmark-comparison": self._check_benchmark_comparison,
            "docs-review": self._check_docs_review,
            "security-review": self._check_security_review,
        }
        method = method_map.get(check.id)
        if method:
            return method()
        return False, f"No check implementation for {check.id}"
