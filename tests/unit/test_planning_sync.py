"""Planning-sync backing-store contract tests (SW152-014).

Proves the third backing-store adapter: a durable area in a non-git workspace
is carried to the configured org planning repository, the sync names what it
carried, and a durable area with no reachable store is reported at risk rather
than silently accepted. Red proof: a workspace with no git and no configured
planning repository refuses to call any area durable.
"""

from skillweave.persistence import (
    Disclosure,
    Durability,
    get_area_declaration,
)
from skillweave.runtime import (
    GitBackingStore,
    PlanningSyncBackingStore,
    SyncReport,
    classify_runtime,
    discover_planning_repo,
    discover_planning_root,
    resolve_runtime_store,
    runtime_has_git,
)


def test_planning_sync_store_is_a_backing_store():
    """The adapter is a third realisation of the BackingStore seam."""
    from skillweave.runtime.substrate import BackingStore

    assert issubclass(PlanningSyncBackingStore, BackingStore)


def test_sync_carries_a_durable_area_and_names_what_it_carried(tmp_path):
    """Criterion 1: a durable area in a non-git workspace syncs to the planning
    repo and the sync names what it carried."""
    # A non-git workspace carrying a durable, declared area's payload.
    assert not (tmp_path / ".git").exists()
    source = tmp_path / ".skillweave" / "prds"
    source.mkdir(parents=True)
    (source / "a.json").write_text("{}\n")
    (source / "nested").mkdir()
    (source / "nested" / "b.yaml").write_text("x: 1\n")

    # Planning repository configured and reachable (a local checkout root).
    planning_root = tmp_path / "planning-checkout"
    planning_root.mkdir()

    store = PlanningSyncBackingStore(
        repository="skillweave/skillweave-planning", planning_root=str(planning_root)
    )
    assert store.reachable

    report = store.sync("prds", str(tmp_path))
    assert isinstance(report, SyncReport)
    assert report.at_risk is False

    carried = report.names()
    assert set(carried) == {"a.json", "nested/b.yaml"}, carried

    # The payload actually landed under the planning repo's sync root.
    assert (planning_root / ".skillweave" / "planning" / "prds" / "a.json").is_file()
    assert (
        planning_root / ".skillweave" / "planning" / "prds" / "nested" / "b.yaml"
    ).is_file()


def test_durable_area_with_no_reachable_store_is_at_risk(tmp_path):
    """Criterion 2: a durable area with no reachable store is reported at risk,
    never silently accepted as durable."""
    assert not (tmp_path / ".git").exists()
    # No sync.yaml, no env var: no planning repository is configured.
    assert discover_planning_repo(str(tmp_path)) is None

    classified = classify_runtime(str(tmp_path))
    research = classified["research"]
    decl = get_area_declaration("research")
    assert decl.durability is Durability.DURABLE

    assert research.is_at_risk() is True
    assert research.is_durable() is False


def test_no_git_no_planning_refuses_any_area_durable(tmp_path):
    """Criterion 3 (red proof): no git and no planning repo -> nothing durable."""
    assert not (tmp_path / ".git").exists()
    assert discover_planning_repo(str(tmp_path)) is None

    classified = classify_runtime(str(tmp_path))
    assert classified, "no areas classified"

    durable_named = [
        name for name, r in classified.items() if name not in ("venv", "tmp", "worktrees", "testing")
        and get_area_declaration(name).durability is Durability.DURABLE
    ]
    assert durable_named, "test premise broken: expected at least one durable-declared area"

    for name in durable_named:
        assert classified[name].is_durable() is False, f"{name} called durable with no store"


def test_git_workspace_uses_git_store(tmp_path):
    """A monorepo (git present) resolves through the git adapter, not planning-sync."""
    (tmp_path / ".git").mkdir()
    assert runtime_has_git(str(tmp_path))
    store = resolve_runtime_store(str(tmp_path))
    assert isinstance(store, GitBackingStore)


def test_planning_repo_discovered_from_sync_yaml(tmp_path):
    """The configured planning repository is read from <root>/sync.yaml."""
    (tmp_path / "sync.yaml").write_text(
        "organization: skillweave\nplanning_repository: skillweave/skillweave-planning\n"
    )
    assert discover_planning_repo(str(tmp_path)) == "skillweave/skillweave-planning"


def test_ephemeral_never_carried_or_disclosed(tmp_path):
    """Ephemeral areas are never durable and never disclosed under planning-sync."""
    planning_root = tmp_path / "planning-checkout"
    planning_root.mkdir()
    store = PlanningSyncBackingStore(
        repository="skillweave/skillweave-planning", planning_root=str(planning_root)
    )
    for name in ("venv", "tmp", "worktrees"):
        decl = get_area_declaration(name)
        assert store.effective_durability(decl) is Durability.EPHEMERAL
        assert store.effective_disclosure(decl) is Disclosure.SEALED


def test_sync_reaches_store_via_configured_path(tmp_path, monkeypatch):
    """Criterion 1 end to end: a durable area syncs when the planning repository
    and its local checkout are configured only via environment, with no explicit
    planning_root handed to any call."""
    assert not (tmp_path / ".git").exists()

    source = tmp_path / ".skillweave" / "prds"
    source.mkdir(parents=True)
    (source / "a.json").write_text("{}\n")

    planning_root = tmp_path / "planning-checkout"
    planning_root.mkdir()

    # Configure the destination purely through the environment + sync.yaml:
    # no explicit planning_root is passed to resolve_runtime_store/classify_runtime.
    monkeypatch.setenv("SKILLWEAVE_PLANNING_REPOSITORY", "skillweave/skillweave-planning")
    monkeypatch.setenv("SKILLWEAVE_PLANNING_ROOT", str(planning_root))

    store = resolve_runtime_store(str(tmp_path))
    assert isinstance(store, PlanningSyncBackingStore)
    assert store.reachable is True

    classified = classify_runtime(str(tmp_path))
    assert classified["prds"].is_at_risk() is False
    assert classified["prds"].is_durable() is True

    report = store.sync("prds", str(tmp_path))
    assert report.at_risk is False
    assert set(report.names()) == {"a.json"}, report.names()
    assert (planning_root / ".skillweave" / "planning" / "prds" / "a.json").is_file()


def test_planning_root_discovered_from_sync_yaml(tmp_path):
    """The local planning checkout is read from <root>/sync.yaml (planning_root)."""
    planning_root = tmp_path / "planning-checkout"
    planning_root.mkdir()
    (tmp_path / "sync.yaml").write_text(
        "organization: skillweave\n"
        "planning_repository: skillweave/skillweave-planning\n"
        f"planning_root: {planning_root}\n"
    )
    assert discover_planning_root(str(tmp_path)) == str(planning_root.resolve())


def test_planning_root_absent_is_unreachable(tmp_path, monkeypatch):
    """A configured destination path that does not exist is not waved through."""
    monkeypatch.setenv("SKILLWEAVE_PLANNING_ROOT", str(tmp_path / "does-not-exist"))
    assert discover_planning_root() is None


def test_unreachable_destination_sync_reports_at_risk_no_crash(tmp_path, monkeypatch):
    """Criterion 2 (b): a configured planning repository whose destination root
    is absent on disk reports the durable area at risk through the sync/carry
    path without crashing, rather than silently accepting it."""
    assert not (tmp_path / ".git").exists()

    # Payload exists so a successful sync would carry it.
    source = tmp_path / ".skillweave" / "prds"
    source.mkdir(parents=True)
    (source / "a.json").write_text("{}\n")

    # Configure a planning repository + a planning_root that does NOT exist.
    (tmp_path / "sync.yaml").write_text(
        "organization: skillweave\n"
        "planning_repository: skillweave/skillweave-planning\n"
        f"planning_root: {tmp_path / 'does-not-exist'}\n"
    )

    store = resolve_runtime_store(str(tmp_path))
    assert isinstance(store, PlanningSyncBackingStore)
    assert store.reachable is False

    classified = classify_runtime(str(tmp_path))
    assert classified["prds"].is_at_risk() is True
    assert classified["prds"].is_durable() is False

    report = store.sync("prds", str(tmp_path))
    assert report.at_risk is True
    assert report.reason, "at-risk report must carry a non-empty reason"


def test_unreachable_destination_sync_reports_at_risk_via_env(tmp_path, monkeypatch):
    """Same as above, but configured purely via environment variables."""
    assert not (tmp_path / ".git").exists()

    source = tmp_path / ".skillweave" / "prds"
    source.mkdir(parents=True)
    (source / "a.json").write_text("{}\n")

    monkeypatch.setenv("SKILLWEAVE_PLANNING_REPOSITORY", "skillweave/skillweave-planning")
    monkeypatch.setenv("SKILLWEAVE_PLANNING_ROOT", str(tmp_path / "does-not-exist"))

    store = resolve_runtime_store(str(tmp_path))
    assert isinstance(store, PlanningSyncBackingStore)
    assert store.reachable is False

    classified = classify_runtime(str(tmp_path))
    assert classified["prds"].is_at_risk() is True

    report = store.sync("prds", str(tmp_path))
    assert report.at_risk is True
    assert report.reason, "at-risk report must carry a non-empty reason"

