"""Tests for release rationalization (Initiative 03).

Covers: readiness assessment, premature detection, workflow,
checklist generation, and backward compatibility.
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skillweave.release.readiness import (
    ReadinessAssessor,
    ReadinessCheck,
    CheckResult,
    ReadinessResult,
)
from skillweave.release.detection import PrematureDetector, PrematureDetectionResult
from skillweave.release.checklist import ChecklistGenerator, ChecklistItem
from skillweave.release.workflow import ReleaseWorkflow, WorkflowStep, WorkflowStepResult


# ─── Helpers ─────────────────────────────────────────────────────────────


@pytest.fixture
def temp_project():
    root = Path(tempfile.mkdtemp())
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "tests" / "test_foo.py").write_text("def test_pass(): assert True")
    (root / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.2.0] - 2026-04-27\n### Added\n- Foo\n"
    )
    yield root
    shutil.rmtree(str(root))


@pytest.fixture
def temp_project_no_tests():
    root = Path(tempfile.mkdtemp())
    (root / "src").mkdir()
    yield root
    shutil.rmtree(str(root))


# ─── Readiness Assessment Tests ──────────────────────────────────────────


class TestReadinessModel:
    def test_checks_defined(self):
        assessor = ReadinessAssessor()
        checks = assessor.get_checks()
        assert len(checks) >= 10

    def test_tier_counts(self):
        assessor = ReadinessAssessor()
        checks = assessor.get_checks()
        critical = [c for c in checks if c.tier == "critical"]
        recommended = [c for c in checks if c.tier == "recommended"]
        optional = [c for c in checks if c.tier == "optional"]
        assert len(critical) >= 4
        assert len(recommended) >= 3
        assert len(optional) >= 2

    def test_all_checks_have_remediation(self):
        assessor = ReadinessAssessor()
        for check in assessor.get_checks():
            assert check.remediation, f"{check.id} missing remediation"

    def test_check_ids_unique(self):
        assessor = ReadinessAssessor()
        ids = [c.id for c in assessor.get_checks()]
        assert len(ids) == len(set(ids))


class TestReadinessScoring:
    def test_score_computation(self):
        check_a = ReadinessCheck(id="a", name="A", tier="critical",
                                 description="", remediation="", override_allowed=True)
        check_b = ReadinessCheck(id="b", name="B", tier="recommended",
                                 description="", remediation="", override_allowed=False)
        result = ReadinessResult(timestamp="now")
        result.checks.append(CheckResult(check=check_a, passed=True))
        result.checks.append(CheckResult(check=check_b, passed=False))
        assert result.readiness_score == 0.5

    def test_blocks_release_without_override(self, temp_project):
        assessor = ReadinessAssessor(str(temp_project))
        result = assessor.assess(override=False)
        if result.critical_failed > 0:
            assert not result.can_release

    def test_override_unblocks_release(self, temp_project):
        assessor = ReadinessAssessor(str(temp_project))
        result = assessor.assess(override=True)
        assert result.can_release

    def test_gap_analysis(self, temp_project):
        assessor = ReadinessAssessor(str(temp_project))
        result = assessor.assess(override=False)
        gaps = result.gap_analysis()
        for gap in gaps:
            assert "check_id" in gap
            assert "remediation" in gap
            assert "tier" in gap

    def test_gap_analysis_includes_override(self, temp_project):
        assessor = ReadinessAssessor(str(temp_project))
        result = assessor.assess(override=True)
        gaps = result.gap_analysis()
        for gap in gaps:
            if gap["override_applied"]:
                assert gap["override_allowed"]


# ─── Premature Detection Tests ───────────────────────────────────────────


class TestPrematureDetection:
    def test_detects_premature(self, temp_project_no_tests):
        detector = PrematureDetector(str(temp_project_no_tests))
        result = detector.detect()
        assert result.is_premature
        assert result.actual_stage != "release_ready"

    def test_detection_time(self, temp_project_no_tests):
        detector = PrematureDetector(str(temp_project_no_tests))
        result = detector.detect()
        assert result.detection_time_ms < 2000

    def test_recommends_upstream_workflow(self, temp_project_no_tests):
        detector = PrematureDetector(str(temp_project_no_tests))
        result = detector.detect()
        assert result.recommended_workflow
        assert "skillweave" in result.recommended_workflow.lower()

    def test_explanation_provided(self, temp_project_no_tests):
        detector = PrematureDetector(str(temp_project_no_tests))
        result = detector.detect()
        assert result.explanation
        assert len(result.explanation) > 20

    def test_override_available(self, temp_project_no_tests):
        detector = PrematureDetector(str(temp_project_no_tests))
        result = detector.detect()
        assert result.can_override
        assert not result.override_applied

    def test_override_applied(self, temp_project_no_tests):
        detector = PrematureDetector(str(temp_project_no_tests))
        result = detector.detect(override=True)
        assert result.override_applied

    def test_detects_ready(self, tmp_path):
        root = Path(str(tmp_path))
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "tests" / "test_foo.py").write_text("def test_pass(): assert True")
        (root / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
        (root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [0.2.0] - 2026-04-27\n"
        )
        detector = PrematureDetector(str(root))
        result = detector.detect()
        assert isinstance(result.is_premature, bool)
        assert result.recommended_workflow


# ─── Checklist Generation Tests ──────────────────────────────────────────


class TestChecklistGeneration:
    def test_generates_items(self, temp_project_no_tests):
        assessor = ReadinessAssessor(str(temp_project_no_tests))
        readiness = assessor.assess()
        gen = ChecklistGenerator()
        items = gen.generate(readiness)
        assert len(items) > 0

    def test_items_actionable(self, temp_project_no_tests):
        assessor = ReadinessAssessor(str(temp_project_no_tests))
        readiness = assessor.assess()
        gen = ChecklistGenerator()
        items = gen.generate(readiness)
        for item in items:
            assert item.action, f"{item.check_id} missing action"
            assert len(item.action) > 5

    def test_checkbox_format(self, temp_project_no_tests):
        assessor = ReadinessAssessor(str(temp_project_no_tests))
        readiness = assessor.assess()
        gen = ChecklistGenerator()
        markdown = gen.generate_markdown(readiness)
        assert "- [ ]" in markdown or "- [x]" in markdown

    def test_saves_to_file(self, temp_project_no_tests):
        assessor = ReadinessAssessor(str(temp_project_no_tests))
        readiness = assessor.assess()
        gen = ChecklistGenerator(str(temp_project_no_tests))
        path = gen.save_markdown(readiness)
        assert os.path.exists(path)
        assert "release-readiness" in path
        content = Path(path).read_text()
        assert "Checklist" in content


# ─── Release Workflow Tests ──────────────────────────────────────────────


class TestReleaseWorkflow:
    def test_has_five_steps(self):
        wf = ReleaseWorkflow()
        steps = wf.get_steps()
        assert len(steps) == 5

    def test_steps_have_gates(self):
        wf = ReleaseWorkflow()
        for step in wf.get_steps():
            assert step.id
            assert step.name
            assert step.skippable

    def test_workflow_readiness_block(self, temp_project_no_tests):
        wf = ReleaseWorkflow(str(temp_project_no_tests))
        result = wf.run(override=False)
        if result.readiness and not result.readiness.can_release:
            assert not result.all_passed

    def test_workflow_with_override(self, temp_project):
        wf = ReleaseWorkflow(str(temp_project))
        result = wf.run(skip_steps=["verify-tests", "package"], override=True)
        assert len(result.steps) > 0

    def test_progress_tracked(self, temp_project):
        wf = ReleaseWorkflow(str(temp_project))
        result = wf.run(skip_steps=["verify-tests", "package", "deploy", "validate-rollout"], override=True)
        tracking_dir = Path(str(temp_project)) / ".skillweave" / "tracking-log"
        log_files = list(tracking_dir.glob("release-workflow-*.json"))
        assert len(log_files) > 0

    def test_workflow_summary(self, temp_project):
        wf = ReleaseWorkflow(str(temp_project))
        result = wf.run(skip_steps=["verify-tests", "package"], override=True)
        summary = result.summary()
        assert "passed" in summary


# ─── Backward Compatibility Tests ────────────────────────────────────────


class TestBackwardCompatibility:
    def test_promptchain_execute_skimmable(self):
        path = Path("skills/skillweave-promptchain-execute/SKILL.md")
        assert path.exists()
        content = path.read_text()
        assert "orchestration" in content.lower()

    def test_releasechain_skimmable(self):
        path = Path("skills/skillweave-releasechain/SKILL.md")
        assert path.exists()
        content = path.read_text()
        assert "releasechain" in content

    def test_release_modules_importable(self):
        from skillweave.release import readiness, detection, checklist, workflow
        assert readiness.ReadinessAssessor
        assert detection.PrematureDetector
        assert checklist.ChecklistGenerator
        assert workflow.ReleaseWorkflow

    def test_new_init_empty(self):
        from skillweave import release
        assert release.__doc__ is not None


# ─── Edge Case Tests ─────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_project(self):
        assessor = ReadinessAssessor("/nonexistent/path")
        result = assessor.assess()
        gaps = result.gap_analysis()
        assert len(gaps) > 0
        assert result.readiness_score < 0.5

    def test_empty_project_detection(self):
        detector = PrematureDetector("/nonexistent/path")
        result = detector.detect()
        assert result.is_premature
        assert result.detection_time_ms < 2000

    def test_empty_project_checklist(self):
        assessor = ReadinessAssessor("/nonexistent/path")
        readiness = assessor.assess()
        gen = ChecklistGenerator()
        items = gen.generate(readiness)
        failed = [c for c in readiness.checks if not c.passed]
        assert len(items) == len(failed)
