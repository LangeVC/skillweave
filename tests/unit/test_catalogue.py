"""Unit tests for src/skillweave/core/catalogue.py (SW-CATALOG-001).

Coverage:
- load_catalogue: parse happy-path, missing file, non-mapping error, reload.
- get_model_for_role: role resolution, ``!= ops`` constraint, cost_index
  fallback, exclude-role separation, error conditions.
- get_harness_config: happy-path, missing-harness error, copy-not-reference.
- Utilities: list_roles / list_models / list_harnesses.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import skillweave.core.catalogue as cat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "catalogue.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


@pytest.fixture
def cheapest_ops_catalogue_path(tmp_path) -> Path:
    """Catalogue where the ``ops`` model is the cheapest by ``cost_index``.

    This is the adversarial case for the ``!= ops`` separation-of-duties
    guard: if ``get_model_for_role`` falls back to the cheapest eligible
    model WITHOUT excluding the ``ops`` model, it returns the ops model,
    violating the very ban the constraint exists for.
    """
    data = {
        "schema_version": "1.0",
        "runtime": {
            "cli": "opencode run --model {model} -",
            "version": "1.5.1",
            "repo_root_source": "config/catalogue.yaml",
        },
        "harnesses": {
            "opencode": {"status": "PROVEN", "cli": "opencode run --model {model} -"},
        },
        "models": {
            "faigate/deepseek-v4-flash": {
                "display_name": "DeepSeek V4 Flash",
                "strengths": ["fast_iteration", "code_generation"],
                "error_mode": "rate_limit",
                "cost_index": 1,
                "variance": 0.4,
            },
            "faigate/deepseek-v4-pro": {
                "display_name": "DeepSeek V4 Pro",
                "strengths": ["deep_analysis", "code_review"],
                "error_mode": "empty_completion_on_budget_exhaustion",
                "cost_index": 3,
                "variance": 0.2,
            },
        },
        "role_defaults": {
            "ops": {"model": "faigate/deepseek-v4-flash"},
            "reviewer": {
                "model": "faigate/deepseek-v4-flash",
                "constraints": ["!= ops"],
            },
        },
        "contracts": [],
    }
    return _write(tmp_path, data)


@pytest.fixture
def catalogue_path(tmp_path) -> Path:
    data = {
        "schema_version": "1.0",
        "runtime": {
            "cli": "opencode run --model {model} -",
            "version": "1.5.1",
            "repo_root_source": ".skillweave/catalogue.yaml",
        },
        "harnesses": {
            "opencode": {"status": "PROVEN", "cli": "opencode run --model {model} -"},
            "claude-code": {"status": "UNPROVEN", "cli": "claude -p"},
            "antigravity": {"status": "UNPROVEN", "cli": "antigravity run"},
        },
        "models": {
            "faigate/deepseek-v4-pro": {
                "display_name": "DeepSeek V4 Pro",
                "strengths": ["deep_analysis", "code_review"],
                "error_mode": "empty_completion_on_budget_exhaustion",
                "cost_index": 3,
                "variance": 0.2,
            },
            "faigate/deepseek-v4-flash": {
                "display_name": "DeepSeek V4 Flash",
                "strengths": ["fast_iteration", "code_generation"],
                "error_mode": "rate_limit",
                "cost_index": 1,
                "variance": 0.4,
            },
        },
        "role_defaults": {
            "discovery": {"model": "faigate/deepseek-v4-pro"},
            "verification": {"model": "faigate/deepseek-v4-flash"},
            "ops": {"model": "faigate/deepseek-v4-pro"},
            "reviewer": {
                "model": "faigate/deepseek-v4-pro",
                "constraints": ["!= ops"],
            },
        },
        "contracts": ["schemas/evidence.schema.json"],
    }
    return _write(tmp_path, data)


@pytest.fixture(autouse=True)
def reset_catalogue():
    cat._catalogue = None
    cat._catalogue_path = None
    yield
    cat._catalogue = None
    cat._catalogue_path = None


# ---------------------------------------------------------------------------
# load_catalogue
# ---------------------------------------------------------------------------

class TestLoadCatalogue:
    def test_loads_valid_file(self, catalogue_path):
        data = cat.load_catalogue(catalogue_path)
        assert isinstance(data, dict)
        for section in ("runtime", "harnesses", "models", "role_defaults", "contracts"):
            assert section in data

    def test_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError, match="catalogue not found"):
            cat.load_catalogue(missing)

    def test_raises_value_error_for_non_mapping(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            cat.load_catalogue(bad)

    def test_explicit_reload_returns_equal_data(self, catalogue_path):
        d1 = cat.load_catalogue(catalogue_path)
        d2 = cat.load_catalogue(catalogue_path)
        assert d1 == d2


# ---------------------------------------------------------------------------
# get_model_for_role
# ---------------------------------------------------------------------------

class TestGetModelForRole:
    def test_discovery_resolves(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        assert cat.get_model_for_role("discovery") == "faigate/deepseek-v4-pro"

    def test_verification_resolves(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        assert cat.get_model_for_role("verification") == "faigate/deepseek-v4-flash"

    def test_ops_resolves(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        assert cat.get_model_for_role("ops") == "faigate/deepseek-v4-pro"

    def test_reviewer_not_equals_ops(self, catalogue_path):
        """reviewer's declared model == ops's model, so ``!= ops`` forces the
        cheapest eligible (flash)."""
        cat.load_catalogue(catalogue_path)
        ops_model = cat.get_model_for_role("ops")
        reviewer_model = cat.get_model_for_role("reviewer")
        assert reviewer_model != ops_model
        assert reviewer_model == "faigate/deepseek-v4-flash"

    def test_exclude_argument_forces_alternate_model(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        result = cat.get_model_for_role("discovery", exclude="ops")
        assert result == "faigate/deepseek-v4-flash"

    def test_ops_guard_rejects_cheapest_ops_model(self, cheapest_ops_catalogue_path):
        """Regression (SW-CATALOG-001 R3 F1): when the ``ops`` model is the
        cheapest, ``!= ops`` must still keep reviewer off it."""
        cat.load_catalogue(cheapest_ops_catalogue_path)
        ops_model = cat.get_model_for_role("ops")
        reviewer_model = cat.get_model_for_role("reviewer")
        assert reviewer_model != ops_model
        assert reviewer_model == "faigate/deepseek-v4-pro"

    def test_raises_key_error_for_unknown_role(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        with pytest.raises(KeyError, match="not defined in the catalogue"):
            cat.get_model_for_role("nonexistent")


# ---------------------------------------------------------------------------
# get_harness_config
# ---------------------------------------------------------------------------

class TestGetHarnessConfig:
    def test_returns_dict_for_proven_harness(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        config = cat.get_harness_config("opencode")
        assert config["status"] == "PROVEN"

    def test_returns_unproven_harness(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        assert cat.get_harness_config("antigravity")["status"] == "UNPROVEN"

    def test_returns_copy_not_reference(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        config = cat.get_harness_config("opencode")
        config["status"] = "MUTATED"
        assert cat.get_harness_config("opencode")["status"] == "PROVEN"

    def test_raises_key_error_for_unknown_harness(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        with pytest.raises(KeyError, match="not defined in the catalogue"):
            cat.get_harness_config("nonexistent")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class TestUtilities:
    def test_list_roles(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        roles = cat.list_roles()
        assert "reviewer" in roles
        assert "ops" in roles
        assert roles == sorted(roles)

    def test_list_models(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        models = cat.list_models()
        assert "faigate/deepseek-v4-pro" in models
        assert "faigate/deepseek-v4-flash" in models

    def test_list_harnesses(self, catalogue_path):
        cat.load_catalogue(catalogue_path)
        harnesses = cat.list_harnesses()
        assert "opencode" in harnesses
        assert "antigravity" in harnesses


# ---------------------------------------------------------------------------
# Integration: the tracked catalogue deliverable on disk
# ---------------------------------------------------------------------------

class TestRealCatalogueFile:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    REAL = REPO_ROOT / "src" / "skillweave" / "assets" / "catalogue.yaml"

    def test_exists(self):
        assert self.REAL.exists(), "Missing src/skillweave/assets/catalogue.yaml (tracked deliverable)"

    def test_parseable_with_all_sections(self):
        data = cat.load_catalogue(self.REAL)
        assert set(("runtime", "harnesses", "models", "role_defaults", "contracts")).issubset(data)

    def test_reviewer_never_equals_ops(self):
        cat.load_catalogue(self.REAL)
        assert cat.get_model_for_role("reviewer") != cat.get_model_for_role("ops")


# ---------------------------------------------------------------------------
# Default resolution from a clean checkout (no .skillweave operator override)
# ---------------------------------------------------------------------------

class TestDefaultResolution:
    def test_fallback_to_tracked_deliverable(self, monkeypatch, tmp_path):
        # chdir to a directory that has no .skillweave/catalogue.yaml anywhere
        # up its parent chain, so _default_path() must fall back to the
        # module-anchored packaged assets/catalogue.yaml deliverable.
        monkeypatch.chdir(tmp_path)
        default = cat._default_path()
        assert default.exists(), f"default path missing: {default}"
        assert default.name == "catalogue.yaml"
        loader = cat.load_catalogue()
        assert set(("runtime", "harnesses", "models", "role_defaults", "contracts")).issubset(loader)

    def test_load_catalogue_without_path_resolves(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        data = cat.load_catalogue()
        assert isinstance(data, dict)
        assert "role_defaults" in data

    def test_resolves_tier2_override_over_shipped_default(self, monkeypatch, tmp_path):
        # SW152-008 criterion 4: a team-tuned skillweave.config/catalogue.yaml
        # must win over the shipped config/catalogue.yaml when no path is given.
        tier2 = tmp_path / "skillweave.config"
        tier2.mkdir()
        (tier2 / "catalogue.yaml").write_text(
            yaml.dump(
                {
                    "runtime": {"repo_root_source": "skillweave.config/catalogue.yaml"},
                    "harnesses": {},
                    "models": {"faigate/tuned-model": {"cost_index": 0}},
                    "role_defaults": {"ops": {"model": "faigate/tuned-model"}},
                    "contracts": [],
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        data = cat.load_catalogue()
        assert data["runtime"]["repo_root_source"] == "skillweave.config/catalogue.yaml"
        assert cat.get_model_for_role("ops") == "faigate/tuned-model"

    def test_no_tier2_override_falls_back_to_shipped(self, monkeypatch, tmp_path):
        # A directory with neither skillweave.config/ nor any override must
        # still resolve the module-anchored shipped deliverable.
        monkeypatch.chdir(tmp_path)
        default = cat._default_path()
        assert not str(default).startswith(str(tmp_path))
        assert default.exists()
