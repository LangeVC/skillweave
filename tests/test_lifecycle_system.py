import os
import sys
import tempfile
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skillweave.phase_detection import detect_phase, detect_phase_with_detail, phase_from_config
from skillweave.workflow_recommendation import recommend
from skillweave.onboarding_cli import run_onboarding, load_onboarding_state, _save_state
from skillweave.phase_enforcement import check_phase
from skillweave.lifecycle_integration import enrich_config, get_lifecycle_context


class TestPhaseDetection:
    def test_empty_project_returns_discovery(self):
        with tempfile.TemporaryDirectory() as td:
            phase, conf = detect_phase(td)
            assert phase == "discovery"
            assert conf >= 0.8

    def test_prd_only_project(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, ".skillweave", "prds"))
            with open(os.path.join(td, ".skillweave", "prds", "test.md"), "w") as f:
                f.write("# PRD")
            phase, conf = detect_phase(td)
            assert isinstance(phase, str)
            assert 0 <= conf <= 1

    def test_code_project_returns_build(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "src"))
            os.makedirs(os.path.join(td, "tests"))
            with open(os.path.join(td, "src", "main.py"), "w") as f:
                f.write("x = 1")
            phase, conf = detect_phase(td)
            assert phase == "build"
            assert conf >= 0.9

    def test_detect_with_detail_returns_all_fields(self):
        result = detect_phase_with_detail(".")
        assert "phase" in result
        assert "confidence" in result
        assert "evidence" in result
        assert len(result["evidence"]) == 7

    def test_phase_from_config_returns_none_if_missing(self):
        with tempfile.TemporaryDirectory() as td:
            assert phase_from_config(td) is None


class TestWorkflowRecommendation:
    def test_discovery_build_app_returns_full_lifecycle(self):
        r = recommend(project_root=".", override_phase="discovery", goal="build an app")
        assert r["recommended_bundle"] == "full-lifecycle"

    def test_blueprint_ship_it_has_gap_warning(self):
        r = recommend(project_root=".", override_phase="blueprint", goal="ship it")
        assert r["recommended_bundle"] == "release-and-launch"
        assert r["gap_analysis"]["severity"] == "warning"

    def test_build_finish_feature(self):
        r = recommend(project_root=".", override_phase="build", goal="finish feature")
        assert r["recommended_bundle"] == "design-and-build"

    def test_discovery_no_goal(self):
        r = recommend(project_root=".", override_phase="discovery")
        assert r["recommended_bundle"] is not None

    def test_next_skill_mapping(self):
        checks = [
            ("discovery", "skillweave-blueprint"),
            ("blueprint", "skillweave-promptchain-generate"),
            ("design", "frontend-design"),
            ("build", "skillweave-promptchain-execute"),
            ("release", "skillweave-releasechain"),
            ("launch", "skillweave-releasechain"),
            ("post-release", "skillweave-promptchain-generate"),
        ]
        for phase, expected_skill in checks:
            r = recommend(project_root=".", override_phase=phase)
            assert r["next_action"] == expected_skill, f"{phase}: expected {expected_skill}, got {r['next_action']}"


class TestOnboardingFlow:
    def test_skip_flag(self):
        result = run_onboarding(skip=True)
        assert result.get("skipped") is True

    def test_state_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            _save_state(td, {"phase": "build", "goal": "test"})
            state = load_onboarding_state(td)
            assert state["phase"] == "build"
            assert state["goal"] == "test"

    def test_no_state_initially(self):
        with tempfile.TemporaryDirectory() as td:
            assert load_onboarding_state(td) is None


class TestPhaseEnforcement:
    def test_override_flag_bypasses_check(self):
        with tempfile.TemporaryDirectory() as td:
            result = check_phase("skillweave-releasechain", project_root=td, override=True)
            assert result["allowed"] is True
            assert result["reason"] == "override"

    def test_release_skill_on_empty_project_emits_recommendation(self):
        with tempfile.TemporaryDirectory() as td:
            result = check_phase("skillweave-releasechain", project_root=td)
            assert "recommendation" in result
            assert result["allowed"] is True

    def test_phase_violation_logged(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, ".skillweave"))
            check_phase("skillweave-releasechain", project_root=td)
            log_path = os.path.join(td, ".skillweave", "tracking-log", "phase-violations.log")
            assert os.path.exists(log_path)
            with open(log_path) as f:
                assert "PHASE_VIOLATION" in f.read()


class TestIntegration:
    def test_enrich_config_adds_lifecycle(self):
        config = enrich_config(".")
        assert config is not None
        assert "lifecycle" in config
        assert config["lifecycle"]["current_phase"] is not None

    def test_get_lifecycle_context(self):
        ctx = get_lifecycle_context(".")
        assert ctx["phase_system_configured"] is True
        assert ctx["current_phase"] is not None

    def test_no_lifecycle_when_not_configured(self):
        with tempfile.TemporaryDirectory() as td:
            ctx = get_lifecycle_context(td)
            assert ctx["phase_system_configured"] is False

    def test_config_yaml_structure_preserved(self):
        with open(".skillweave/config.yaml") as f:
            config = yaml.safe_load(f)
        assert config["mode"] == "medium"
        assert "features" in config
        assert "lifecycle" in config

    def test_backward_compatibility(self):
        from skillweave.checklist import Checklist, ChecklistParser
        from skillweave.design_thinking import DesignThinkingLens
        from skillweave.capability import CapabilityRegistry

        assert Checklist is not None
        assert ChecklistParser is not None
        assert DesignThinkingLens is not None
        assert CapabilityRegistry is not None


class TestBundleYAML:
    def test_bundles_yaml_exists(self):
        assert os.path.exists(".skillweave/bundles.yaml")

    def test_phases_yaml_exists(self):
        assert os.path.exists(".skillweave/phases.yaml")

    def test_phases_yaml_has_7_phases(self):
        with open(".skillweave/phases.yaml") as f:
            data = yaml.safe_load(f)
        assert len(data["phases"]) == 7

    def test_bundles_yaml_has_5_bundles(self):
        with open(".skillweave/bundles.yaml") as f:
            data = yaml.safe_load(f)
        assert len(data["bundles"]) == 5
