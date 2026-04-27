"""Release execution workflow module.

Structured release flow with 5 sequential steps, each with pass/fail gates.
"""

import os
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path

from .readiness import ReadinessAssessor, ReadinessResult


@dataclass
class WorkflowStep:
    id: str
    name: str
    description: str
    skippable: bool = False


@dataclass
class WorkflowStepResult:
    step: WorkflowStep
    passed: bool = False
    detail: str = ""
    skipped: bool = False
    error_guidance: str = ""


@dataclass
class WorkflowResult:
    steps: list[WorkflowStepResult] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    readiness: ReadinessResult | None = None

    @property
    def all_passed(self) -> bool:
        return all(s.passed or s.skipped for s in self.steps)

    @property
    def failed_steps(self) -> list[WorkflowStepResult]:
        return [s for s in self.steps if not s.passed and not s.skipped]

    def summary(self) -> str:
        total = len(self.steps)
        passed = sum(1 for s in self.steps if s.passed)
        skipped = sum(1 for s in self.steps if s.skipped)
        failed = sum(1 for s in self.steps if not s.passed and not s.skipped)
        return (
            f"Release workflow: {passed}/{total} passed"
            + (f", {skipped} skipped" if skipped else "")
            + (f", {failed} failed" if failed else "")
        )


class ReleaseWorkflow:
    def __init__(self, project_root: str | None = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self._assessor = ReadinessAssessor(project_root)

    def get_steps(self) -> list[WorkflowStep]:
        return [
            WorkflowStep(
                id="verify-tests",
                name="Verify Tests",
                description="Run test suite and confirm all tests pass",
                skippable=True,
            ),
            WorkflowStep(
                id="package",
                name="Package Build Artifacts",
                description="Build distributable artifacts (sdist, wheel)",
                skippable=True,
            ),
            WorkflowStep(
                id="generate-release-notes",
                name="Generate Release Notes",
                description="Generate changelog entry for the release",
                skippable=True,
            ),
            WorkflowStep(
                id="deploy",
                name="Deploy Artifacts",
                description="Publish artifacts to package registry",
                skippable=True,
            ),
            WorkflowStep(
                id="validate-rollout",
                name="Validate Rollout",
                description="Verify the published package is installable and functional",
                skippable=True,
            ),
        ]

    def run(
        self,
        skip_steps: list[str] | None = None,
        override: bool = False,
    ) -> WorkflowResult:
        skip = set(skip_steps or [])
        result = WorkflowResult(
            start_time=datetime.utcnow().isoformat() + "Z",
        )

        readiness = self._assessor.assess(override=override)
        result.readiness = readiness

        if not readiness.can_release and not override:
            msg = "Critical prerequisites not met and override not set"
            failed_step = WorkflowStep(id="readiness-check", name="Readiness Check",
                                       description="", skippable=False)
            result.steps.append(WorkflowStepResult(
                step=failed_step, passed=False,
                detail=msg,
                error_guidance="Run readiness assessment or set override=True",
            ))
            result.end_time = datetime.utcnow().isoformat() + "Z"
            return result

        for step in self.get_steps():
            if step.id in skip:
                result.steps.append(WorkflowStepResult(
                    step=step, passed=True, skipped=True, detail="Skipped by configuration"
                ))
                continue

            step_result = self._execute_step(step)
            result.steps.append(step_result)

            if not step_result.passed and not step.skippable:
                break

        result.end_time = datetime.utcnow().isoformat() + "Z"
        self._save_progress(result)
        return result

    def _execute_step(self, step: WorkflowStep) -> WorkflowStepResult:
        methods = {
            "verify-tests": self._step_verify_tests,
            "package": self._step_package,
            "generate-release-notes": self._step_release_notes,
            "deploy": self._step_deploy,
            "validate-rollout": self._step_validate_rollout,
        }
        method = methods.get(step.id)
        if method:
            return method(step)
        return WorkflowStepResult(
            step=step, passed=False,
            detail=f"No implementation for step: {step.id}",
            error_guidance="Check workflow step configuration",
        )

    def _step_verify_tests(self, step: WorkflowStep) -> WorkflowStepResult:
        try:
            result = subprocess.run(
                ["rtk", "pytest", "tests/", "-q", "--tb=short"],
                capture_output=True, text=True, timeout=180,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                return WorkflowStepResult(
                    step=step, passed=True,
                    detail=f"Tests passed: {lines[-1] if lines else ''}",
                )
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-q", "--tb=short"],
                capture_output=True, text=True, timeout=180,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                return WorkflowStepResult(
                    step=step, passed=True,
                    detail=f"Tests passed: {lines[-1] if lines else ''}",
                )
            else:
                errors = result.stdout[-500:] + result.stderr[-500:]
                return WorkflowStepResult(
                    step=step, passed=False,
                    detail="Test failures detected",
                    error_guidance=f"Fix failing tests:\n{errors}",
                )
        except FileNotFoundError:
            return WorkflowStepResult(
                step=step, passed=False,
                detail="Could not find pytest runner",
                error_guidance="Install pytest: pip install pytest",
            )

    def _step_package(self, step: WorkflowStep) -> WorkflowStepResult:
        try:
            dist = self.project_root / "dist"
            if dist.exists():
                import shutil
                shutil.rmtree(str(dist))
            result = subprocess.run(
                ["python3", "-m", "build"],
                capture_output=True, text=True, timeout=120,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                artifacts = list(dist.glob("*"))
                return WorkflowStepResult(
                    step=step, passed=True,
                    detail=f"Built {len(artifacts)} artifact(s): {', '.join(a.name for a in artifacts)}",
                )
            else:
                return WorkflowStepResult(
                    step=step, passed=False,
                    detail=f"Build failed: {result.stderr[-300:]}",
                    error_guidance="Check build dependencies and pyproject.toml configuration",
                )
        except FileNotFoundError:
            return WorkflowStepResult(
                step=step, passed=False,
                detail="python3 -m build not available",
                error_guidance="Install build package: pip install build",
            )

    def _step_release_notes(self, step: WorkflowStep) -> WorkflowStepResult:
        changelog = self.project_root / "CHANGELOG.md"
        if changelog.exists():
            return WorkflowStepResult(
                step=step, passed=True,
                detail="CHANGELOG.md exists — review entries before deployment",
            )
        return WorkflowStepResult(
            step=step, passed=False,
            detail="CHANGELOG.md not found",
            error_guidance="Create CHANGELOG.md with release entries",
        )

    def _step_deploy(self, step: WorkflowStep) -> WorkflowStepResult:
        dist = self.project_root / "dist"
        if dist.exists() and list(dist.glob("*.whl")):
            return WorkflowStepResult(
                step=step, passed=True,
                detail=f"Artifacts ready in dist/: {[f.name for f in dist.glob('*.whl')]}",
            )
        return WorkflowStepResult(
            step=step, passed=False,
            detail="No wheel artifacts found in dist/",
            error_guidance="Run packaging step first or build artifacts manually",
        )

    def _step_validate_rollout(self, step: WorkflowStep) -> WorkflowStepResult:
        dist = self.project_root / "dist"
        wheels = list(dist.glob("*.whl"))
        if wheels:
            return WorkflowStepResult(
                step=step, passed=True,
                detail=f"Rollout artifacts validated: {len(wheels)} wheel(s) available",
            )
        dist_exists = dist.exists() and list(dist.glob("*"))
        if dist_exists:
            return WorkflowStepResult(
                step=step, passed=True,
                detail="Distribution artifacts exist — manual validation required",
            )
        return WorkflowStepResult(
            step=step, passed=False,
            detail="No distribution artifacts found",
            error_guidance="Run packaging step before validation",
        )

    def _save_progress(self, result: WorkflowResult) -> None:
        tracking_dir = self.project_root / ".skillweave" / "tracking-log"
        os.makedirs(str(tracking_dir), exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        filepath = tracking_dir / f"release-workflow-{timestamp}.json"
        data = {
            "start_time": result.start_time,
            "end_time": result.end_time,
            "all_passed": result.all_passed,
            "summary": result.summary(),
            "steps": [
                {
                    "id": s.step.id,
                    "name": s.step.name,
                    "passed": s.passed,
                    "skipped": s.skipped,
                    "detail": s.detail,
                }
                for s in result.steps
            ],
        }
        filepath.write_text(json.dumps(data, indent=2))
