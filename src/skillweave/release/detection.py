"""Premature invocation detection and redirect module.

Detects when release is invoked without prerequisites,
identifies actual stage, explains gap, and recommends upstream workflow.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from .readiness import ReadinessAssessor, ReadinessResult, CheckResult


@dataclass
class PrematureDetectionResult:
    is_premature: bool = False
    actual_stage: str = ""
    missing_checks: list[dict] = field(default_factory=list)
    recommended_workflow: str = ""
    explanation: str = ""
    detection_time_ms: float = 0.0
    readiness_summary: str = ""
    can_override: bool = False
    override_applied: bool = False


class PrematureDetector:
    def __init__(self, project_root: str | None = None):
        self.project_root = project_root
        self._assessor = ReadinessAssessor(project_root)

    def _determine_stage(self, result: ReadinessResult) -> str:
        critical_failed = [c for c in result.checks if c.check.tier == "critical" and not c.passed]
        if not critical_failed:
            return "release_ready"
        failed_ids = {c.check.id for c in critical_failed}
        if "tests-exist" in failed_ids or "tests-pass" in failed_ids:
            return "build"
        if "changelog-updated" in failed_ids:
            return "prerelease_setup"
        if "version-bumped" in failed_ids:
            return "versioning"
        return "mixed_prerelease"

    def _get_recommended_workflow(self, stage: str) -> str:
        mapping = {
            "build": "skillweave-promptchain-execute (build phase)",
            "prerelease_setup": "skillweave-releasechain (changelog + prerelease preparation)",
            "versioning": "skillweave-releasechain (version bump + tagging)",
            "mixed_prerelease": "skillweave-releasechain (run readiness checklist first)",
            "release_ready": "skillweave-releasechain (proceed with release workflow)",
        }
        return mapping.get(stage, "skillweave-releasechain")

    def _fast_assess(self, override: bool = False) -> ReadinessResult:
        checks = self._assessor.get_checks()
        result = ReadinessResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
            override_active=override,
        )
        for check in checks:
            if check.id in ("tests-pass", "dependency-audit"):
                passed, detail = (True, "Skipped (fast detection — run full assessment for details)")
            else:
                passed, detail = self._assessor._run_check(check)
            result.checks.append(CheckResult(
                check=check,
                passed=passed,
                detail=detail,
                override_applied=override if check.tier == "critical" and not passed else False,
            ))
        return result

    def detect(
        self,
        override: bool = False,
        generate_checklist: bool = False,
    ) -> PrematureDetectionResult:
        start = time.perf_counter()
        result = self._fast_assess(override=override)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

        stage = self._determine_stage(result)
        is_premature = stage != "release_ready"
        workflow = self._get_recommended_workflow(stage)

        gaps = result.gap_analysis()
        missing_checks = [
            {"id": g["check_id"], "name": g["name"], "tier": g["tier"], "detail": g["detail"]}
            for g in gaps
        ]

        if is_premature:
            explanation = (
                f"Release invoked prematurely: detected stage is '{stage}'.\n"
                f"Missing {len(missing_checks)} prerequisite(s): "
                + ", ".join(g["name"] for g in missing_checks[:5])
                + (f" (+{len(missing_checks)-5} more)" if len(missing_checks) > 5 else "")
                + f"\nRecommended: switch to {workflow}"
            )
        else:
            explanation = "All prerequisites met — ready for release."

        return PrematureDetectionResult(
            is_premature=is_premature,
            actual_stage=stage,
            missing_checks=missing_checks,
            recommended_workflow=workflow,
            explanation=explanation,
            detection_time_ms=elapsed_ms,
            readiness_summary=f"Score: {result.readiness_score}, "
            f"Critical: {result.critical_passed}/{result.critical_count}",
            can_override=True,
            override_applied=override and is_premature,
        )
