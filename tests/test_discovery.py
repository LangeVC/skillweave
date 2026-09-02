"""
Test suite for Discovery & Design Thinking features.
Covers: lens configuration, prompt library, artifacts, ideation, assumptions, iteration.

All repository resources are resolved from an explicit repository root so the
suite passes identically regardless of the caller's working directory. No product
or test path depends on Path.cwd or a relative glob rooted at the caller.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'fixtures', 'substrate-root', '.skillweave', 'lib'))

import yaml
import tempfile
from pathlib import Path

from skillweave.design_thinking import (
    DesignThinkingLens,
    resolve_discovery_asset,
)
from skillweave.persistence import SkillWeavePersistence

from ideation import IdeationSession, IdeationConfig, IdeationMode
from assumptions import AssumptionTracker, Assumption


# The repository's own .skillweave/ is git-excluded (docs/substrate-map.md,
# invariant 5), so no test may read it. Discovery assets (lenses, prompts and
# templates) now ship as packaged defaults under src/skillweave/assets/ and are
# resolved through resolve_discovery_asset(): a project root with no
# skillweave.config/ tier falls through to the packaged default. SUBSTRATE_ROOT
# (tests/fixtures/substrate-root/) no longer copies those assets; it only holds
# fixture-only files (phases.yaml, bundles.yaml, config.yaml, lib/, and the
# release policy). See tests/fixtures/substrate-root/README.md.
SUBSTRATE_ROOT = Path(__file__).resolve().parent / "fixtures" / "substrate-root"


def _lens_data():
    path = resolve_discovery_asset(SUBSTRATE_ROOT, "lenses", "design-thinking.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def _prompt_files():
    # No fixture-directory glob: the prompts are the shipped packaged defaults,
    # enumerated by name and resolved through resolve_discovery_asset().
    return sorted(
        resolve_discovery_asset(SUBSTRATE_ROOT, "prompts", name)
        for name in PACKAGED_DISCOVERY_ASSETS["prompts"]
    )


def _template_files():
    # Resolved through resolve_discovery_asset(), not a fixture-directory glob.
    return sorted(
        resolve_discovery_asset(SUBSTRATE_ROOT, "templates", name)
        for name in PACKAGED_DISCOVERY_ASSETS["templates"]
    )


# ===== Lens Configuration Tests =====

def test_lens_config_has_six_rules():
    data = _lens_data()
    rules = data['lens']['workshop_rules']
    assert len(rules) == 6
    rule_ids = [r['id'] for r in rules]
    for rid in ['empathy_first', 'quantity_before_quality', 'deferred_judgment', 'show_dont_tell', 'yes_and', 'bias_toward_action']:
        assert rid in rule_ids


def test_lens_config_has_five_principles():
    data = _lens_data()
    principles = data['lens']['ux_principles']
    assert len(principles) == 5
    pids = [p['id'] for p in principles]
    for pid in ['value_over_noise', 'scan_before_read', 'hierarchy_of_needs', 'progressive_disclosure', 'recognition_over_recall']:
        assert pid in pids


def test_lens_opt_in_by_default():
    data = _lens_data()
    assert data['lens']['enabled'] is False
    assert data['lens']['activation']['mechanism'] == 'opt-in'


def test_config_yaml_lens_section():
    path = SUBSTRATE_ROOT / ".skillweave" / "config.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert 'lens' in data
    assert 'design_thinking' in data['lens']
    assert len(data['lens']['design_thinking']['rules']) == 6
    assert len(data['lens']['design_thinking']['principles']) == 5


def test_lens_loading_via_design_thinking_module():
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        config = persistence.load_config()
        config.features['design_thinking_lens'] = True
        persistence.save_config(config)
        manifesto_dir = Path(tmpdir) / '.skillweave' / 'manifesto'
        manifesto_dir.mkdir(exist_ok=True)
        with open(manifesto_dir / 'design-rules.yaml', 'w') as f:
            yaml.dump({'enabled': True, 'rules': {'value_noise': True, 'scan_before_read': True}}, f)
        lens = DesignThinkingLens(tmpdir)
        assert lens.is_enabled() is True


# ===== Prompt Library Tests =====

def test_prompt_library_completeness():
    prompts = _prompt_files()
    assert len(prompts) >= 10
    empathy = [p for p in prompts if 'empathy-' in p.name]
    research = [p for p in prompts if 'research-' in p.name]
    framing = [p for p in prompts if 'framing-' in p.name]
    assert len(empathy) >= 3
    assert len(research) >= 3
    assert len(framing) >= 4


def test_prompt_has_io_specs():
    for p in _prompt_files():
        with open(p) as f:
            content = f.read()
        assert 'Input Requirements' in content, f'{p} missing input requirements'
        assert 'Output Format' in content, f'{p} missing output format'
        assert 'Next Action' in content or 'Instructions' in content, f'{p} missing instructions/action'


def test_prompt_inventory_registered():
    library = _prompt_files()
    assert len(library) >= 10
    path = Path(__file__).resolve().parent / 'fixtures' / 'tracking-log' / 'prompt-inventory.yaml'
    assert path.exists()
    with open(path) as f:
        data = yaml.safe_load(f)
    assert data['total_prompts'] >= 10
    assert len(data['inventory']) >= 10
    assert data['total_prompts'] == len(data['inventory'])
    # Each inventory entry points at a discovery prompt; resolve it through the
    # packaged default (the fixture no longer carries a copy) and require it to
    # exist among the shipped prompts.
    registered = {
        resolve_discovery_asset(
            SUBSTRATE_ROOT, "prompts", entry["file"].split("prompts/", 1)[1]
        ).resolve()
        for entry in data["inventory"]
    }
    assert registered.issubset({p.resolve() for p in library})


# ===== Artifact Template Tests =====

def test_all_five_templates_exist():
    expected = ['persona-card.md', 'competitor-matrix.md', 'assumption-log.yaml', 'opportunity-canvas.md', 'research-summary.md']
    for name in expected:
        path = resolve_discovery_asset(SUBSTRATE_ROOT, "templates", f"discovery/{name}")
        assert path.exists(), f'Missing template: {name}'


def test_templates_have_placeholders():
    md_templates = [t for t in _template_files() if t.name.endswith(".md")]
    assert md_templates, "no markdown templates resolved"
    for t in md_templates:
        with open(t) as f:
            content = f.read()
        assert '{{' in content, f'{t} missing placeholders'


def test_assumption_log_yaml_valid():
    path = resolve_discovery_asset(SUBSTRATE_ROOT, "templates", "discovery/assumption-log.yaml")
    with open(path) as f:
        data = yaml.safe_load(f)
    assert 'assumptions' in data
    assert len(data['assumptions']) >= 5


# ===== Ideation Module Tests =====

def test_ideation_generates_minimum_options():
    session = IdeationSession(IdeationConfig(min_options=5))
    options = session.generate('Test problem')
    assert len(options) >= 5


def test_ideation_includes_wild_option():
    session = IdeationSession()
    options = session.generate('Test problem')
    assert any(o.is_wild for o in options)


def test_ideation_separate_evaluation():
    session = IdeationSession()
    session.generate('Test problem')
    evaluated = session.evaluate()
    for o in evaluated:
        assert o.evaluation is not None
        assert 'weighted_score' in o.evaluation
    with SessionErrorCheck(session):
        pass


class SessionErrorCheck:
    def __init__(self, session):
        self.session = session
    def __enter__(self):
        pass
    def __exit__(self, *args):
        return False


def test_ideation_cannot_generate_in_evaluate_mode():
    session = IdeationSession()
    session.generate('Test')
    session.evaluate()
    import pytest as _pytest
    try:
        session.generate('test')
        assert False, 'Should raise ValueError'
    except ValueError:
        pass


def test_ideation_expand_mode():
    session = IdeationSession()
    session.generate('Test')
    first_id = session.options[0].id
    expansions = session.expand(first_id)
    assert len(expansions) == 3
    for e in expansions:
        assert e.parent_id == first_id


def test_ideation_reset():
    session = IdeationSession()
    session.generate('Test')
    assert len(session.options) > 0
    session.reset()
    assert len(session.options) == 0
    assert session.mode == IdeationMode.GENERATE


# ===== Assumption Tracking Tests =====

def _assert_no_cwd_mutation(monkeypatch, tmp_path):
    """Change to an unrelated working directory and assert assumption tracking
    writes only under its isolated temp root, never beneath the caller's cwd."""
    foreign = tmp_path / "foreign_cwd"
    foreign.mkdir()
    monkeypatch.chdir(foreign)
    state_dir = tmp_path / "extra_state"
    state_dir.mkdir()
    tracker = AssumptionTracker(str(state_dir))
    tracker.clear()
    tracker.extract_from_text('Users will adopt the platform quickly. The market will grow.')
    assert (state_dir / ".skillweave" / "tracking-log" / "assumptions.yaml").exists()
    assert not (foreign / ".skillweave").exists()


def test_assumption_extraction(tmp_path, monkeypatch):
    tracker = AssumptionTracker(str(tmp_path))
    tracker.clear()
    text = 'Users will adopt the platform quickly. The market will grow 20% YoY. The database should handle 10K users. The team can deliver in 3 months. Users will pay for this feature.'
    extracted = tracker.extract_from_text(text)
    assert len(extracted) >= 5
    _assert_no_cwd_mutation(monkeypatch, tmp_path)


def test_assumption_risk_scoring():
    a = Assumption(id='test-1', category='user', description='Test', impact=5, probability=5)
    assert a.risk_score == 25
    assert a.zone == 'high'
    a2 = Assumption(id='test-2', category='user', description='Test', impact=1, probability=1)
    assert a2.risk_score == 1
    assert a2.zone == 'low'


def test_assumption_update_and_persistence(tmp_path):
    tracker = AssumptionTracker(str(tmp_path))
    tracker.clear()
    text = 'Users will adopt the platform. The market will grow.'
    extracted = tracker.extract_from_text(text)
    first_id = extracted[0].id
    tracker.update_assumption(first_id, {'status': 'validated'})
    updated = tracker.get_by_status('validated')
    assert len(updated) >= 1
    assert updated[0].id == first_id


def test_assumption_categorization(tmp_path):
    categories = {
        'user': 'Users need this feature',
        'market': 'The market is growing',
        'technical': 'The API should scale',
    }
    for expected_cat, text in categories.items():
        tracker = AssumptionTracker(str(tmp_path))
        tracker.clear()
        extracted = tracker.extract_from_text(text)
        if extracted:
            assert extracted[0].category == expected_cat, f'{text} → expected {expected_cat}, got {extracted[0].category}'


# ===== Iteration Framework Tests =====

def test_iteration_log_exists():
    path = Path(__file__).resolve().parent / 'fixtures' / 'tracking-log' / 'iterations.yaml'
    assert path.exists()
    with open(path) as f:
        data = yaml.safe_load(f)
    assert 'iterations' in data
    assert isinstance(data['iterations'], list)
    assert len(data['iterations']) >= 1
    for entry in data['iterations']:
        for field in ('id', 'artifact', 'changes', 'evidence'):
            assert field in entry


def test_feedback_synthesis_template_exists():
    path = resolve_discovery_asset(SUBSTRATE_ROOT, "templates", "discovery/feedback-synthesis.md")
    with open(path) as f:
        content = f.read()
    assert '{{' in content


def test_revision_prompt_requires_evidence():
    path = resolve_discovery_asset(SUBSTRATE_ROOT, "prompts", "discovery/iteration-revision.md")
    with open(path) as f:
        content = f.read()
    assert 'Evidence' in content or 'evidence' in content


# ===== Hermetic Resource Resolution Tests =====

# The full discovery surface the product ships as tier-1 packaged defaults
# (src/skillweave/assets/). Enumerated explicitly so the red proof below fails
# if any asset stops shipping, rather than silently passing because the
# packaged tree under test happened to be empty.
PACKAGED_DISCOVERY_ASSETS = {
    "lenses": ["design-thinking.yaml"],
    "prompts": [
        "discovery/empathy-pain-points.md",
        "discovery/empathy-persona-dev.md",
        "discovery/empathy-user-context.md",
        "discovery/framing-assumption-prioritization.md",
        "discovery/framing-assumption-surfacing.md",
        "discovery/framing-opportunity.md",
        "discovery/framing-problem-statement.md",
        "discovery/iteration-revision.md",
        "discovery/research-competitor-analysis.md",
        "discovery/research-landscape-map.md",
        "discovery/research-opportunity-assessment.md",
    ],
    "templates": [
        "discovery/assumption-log.yaml",
        "discovery/competitor-matrix.md",
        "discovery/feedback-synthesis.md",
        "discovery/opportunity-canvas.md",
        "discovery/persona-card.md",
        "discovery/research-summary.md",
    ],
}


def _empty_project(tmp_path):
    """A fresh project root whose skillweave.config/ is absent (empty inputs tier)."""
    root = tmp_path / "empty-project"
    root.mkdir()
    return root


def test_missing_discovery_asset_fails_explicitly(tmp_path):
    from skillweave.design_thinking import DiscoveryAssetNotFound
    missing = tmp_path / "pkgroot"
    missing.mkdir()
    project_expected = (missing / "skillweave.config" / "lenses" / "no-such-asset.yaml").resolve()
    packaged_expected = (
        Path(__file__).resolve().parent.parent
        / "src" / "skillweave" / "assets" / "lenses" / "no-such-asset.yaml"
    ).resolve()
    try:
        resolve_discovery_asset(missing, "lenses", "no-such-asset.yaml")
        assert False, "expected DiscoveryAssetNotFound"
    except DiscoveryAssetNotFound as exc:
        assert exc.project_path == project_expected
        assert exc.packaged_path == packaged_expected
        assert str(project_expected) in str(exc)
        assert str(packaged_expected) in str(exc)


def test_discovery_assets_resolve_from_repo_root_not_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    lens = resolve_discovery_asset(_empty_project(tmp_path), "lenses", "design-thinking.yaml")
    packaged = (
        Path(__file__).resolve().parent.parent
        / "src" / "skillweave" / "assets" / "lenses" / "design-thinking.yaml"
    ).resolve()
    assert lens == packaged
    assert lens.exists()


# ===== Resolver Chain Tests (SW152-009) =====


def test_package_only_asset_resolves(tmp_path):
    root = _empty_project(tmp_path)
    path = resolve_discovery_asset(root, "lenses", "design-thinking.yaml")
    packaged = (
        Path(__file__).resolve().parent.parent
        / "src" / "skillweave" / "assets" / "lenses" / "design-thinking.yaml"
    ).resolve()
    assert path == packaged
    assert path.exists()


def test_project_input_wins_over_packaged_default(tmp_path):
    root = _empty_project(tmp_path)
    tier = root / "skillweave.config" / "lenses"
    tier.mkdir(parents=True)
    (tier / "design-thinking.yaml").write_text("tuned: true\n")
    path = resolve_discovery_asset(root, "lenses", "design-thinking.yaml")
    assert path == (tier / "design-thinking.yaml").resolve()
    assert "tuned: true" in path.read_text()


def test_empty_config_tier_resolves_every_packaged_asset(tmp_path):
    root = _empty_project(tmp_path)
    for kind, names in PACKAGED_DISCOVERY_ASSETS.items():
        for name in names:
            path = resolve_discovery_asset(root, kind, name)
            assert path.exists(), f"packaged default missing: {kind}/{name}"
            assert path.is_absolute()
            assert "skillweave.config" not in path.parts
