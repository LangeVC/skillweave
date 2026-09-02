"""Substrate contract tests (SW152-013).

Proves the substrate contract that stops delegating durability/disclosure to
git:

1. ``direction``, ``durability`` and ``disclosure`` are declared SDK types, with
   ``ephemeral`` a first-class durability value.
2. A backing-store seam exists with a git adapter and a local-only adapter, and
   the runtime resolves an area's store from its declaration, not from a ``.git``
   directory.
3. Red proof: a substrate in a NON-git directory reports a coherent durability
   and disclosure for every area, and refuses to treat an unclassified area as
   durable.
"""

import pytest

from skillweave.persistence import (
    AreaDeclaration,
    Direction,
    Disclosure,
    Durability,
    StoreKind,
    get_area_declaration,
)
from skillweave.runtime import (
    BackingStore,
    GitBackingStore,
    LocalOnlyBackingStore,
    ResolvedArea,
    UnclassifiedAreaError,
    classify_area,
    classify_substrate,
    resolve_store,
)


def test_axes_are_declared_types():
    """Criterion 1: the three axes exist as SDK types."""
    assert hasattr(Direction, "AUTHORED") and hasattr(Direction, "GENERATED")
    assert hasattr(Durability, "DURABLE")
    assert hasattr(Durability, "RECONSTRUCTIBLE")
    assert hasattr(Durability, "EPHEMERAL")
    assert hasattr(Disclosure, "OPEN")
    assert hasattr(Disclosure, "PRIVATE")
    assert hasattr(Disclosure, "SEALED")


def test_ephemeral_is_first_class_durability():
    """Criterion 1: ``ephemeral`` is a first-class durability value, not None."""
    assert Durability.EPHEMERAL.value == "ephemeral"
    assert Durability.EPHEMERAL is not Durability.DURABLE
    assert Durability.EPHEMERAL is not Durability.RECONSTRUCTIBLE
    # It round-trips and is a member of the enum's declared values.
    assert Durability("ephemeral") is Durability.EPHEMERAL


def test_area_declaration_binds_three_axes():
    """An AreaDeclaration carries direction, durability and disclosure together."""
    decl = AreaDeclaration("research", Direction.AUTHORED, Durability.DURABLE, Disclosure.SEALED)
    assert decl.direction is Direction.AUTHORED
    assert decl.durability is Durability.DURABLE
    assert decl.disclosure is Disclosure.SEALED
    assert decl.store is StoreKind.LOCAL_ONLY


def test_ephemeral_areas_declared_ephemeral():
    """venv/, tmp/ and worktrees/ are declared ephemeral, never durable."""
    for name in ("venv", "tmp", "worktrees", "testing", "onboarding-state.yaml"):
        decl = get_area_declaration(name)
        assert decl is not None, f"{name} not declared"
        assert decl.durability is Durability.EPHEMERAL
        assert decl.disclosure is Disclosure.SEALED


def test_backing_store_interface_has_two_adapters():
    """Criterion 2: the seam exposes a git adapter and a local-only adapter."""
    assert issubclass(GitBackingStore, BackingStore)
    assert issubclass(LocalOnlyBackingStore, BackingStore)
    assert issubclass(BackingStore, object)
    # Both are reachable via the seam resolver.
    git = resolve_store(StoreKind.GIT)
    local = resolve_store(StoreKind.LOCAL_ONLY)
    assert isinstance(git, GitBackingStore)
    assert isinstance(local, LocalOnlyBackingStore)


def test_resolution_comes_from_declaration_not_git(tmp_path):
    """Criterion 2: store kind is declared on the area, never sniffed from .git.

    A non-git directory that has an area declared ``store=git`` still resolves
    to the git adapter — proving the resolver reads the declaration, not the
    filesystem.
    """
    decl = AreaDeclaration(
        "prds", Direction.AUTHORED, Durability.DURABLE, Disclosure.PRIVATE,
        store=StoreKind.GIT,
    )
    # No .git directory exists here.
    assert not (tmp_path / ".git").exists()
    store = resolve_store(decl.store)
    assert isinstance(store, GitBackingStore)


def test_git_adapter_maps_durability_to_tracked():
    """Git adapter: durable <=> tracked; untracked durable degrades to reconstructible."""
    git = GitBackingStore(visibility=Disclosure.PRIVATE, tracked={"prds"})
    tracked = AreaDeclaration("prds", Direction.AUTHORED, Durability.DURABLE, Disclosure.PRIVATE, store=StoreKind.GIT)
    untracked = AreaDeclaration("reports", Direction.GENERATED, Durability.DURABLE, Disclosure.PRIVATE, store=StoreKind.GIT)
    assert git.effective_durability(tracked) is Durability.DURABLE
    assert git.effective_durability(untracked) is Durability.RECONSTRUCTIBLE
    assert git.effective_disclosure(tracked) is Disclosure.PRIVATE
    assert git.effective_disclosure(untracked) is Disclosure.PRIVATE


def test_local_only_adapter_never_discloses():
    """Local-only adapter: durability = this machine, disclosure = sealed."""
    local = LocalOnlyBackingStore()
    decl = get_area_declaration("research")
    assert local.effective_durability(decl) is Durability.DURABLE
    assert local.effective_disclosure(decl) is Disclosure.SEALED


class TestRedProofNonGitSubstrate:
    """Criterion 3 (red proof): a non-git directory reports every area and
    refuses to treat an unclassified area as durable."""

    def test_non_git_substrate_reports_every_area(self, tmp_path):
        """A non-git directory yields a coherent durability+disclosure per area."""
        # Explicitly ensure this is NOT a git repository.
        assert not (tmp_path / ".git").exists()

        classified = classify_substrate(str(tmp_path))
        assert classified, "no areas classified in a non-git directory"

        for name, resolved in classified.items():
            assert isinstance(resolved, ResolvedArea)
            assert resolved.durability in Durability
            assert resolved.disclosure in Disclosure
            assert resolved.disclosure is Disclosure.SEALED, (
                f"{name} leaked disclosure {resolved.disclosure} under local-only"
            )

        # Ephemeral areas are never durable.
        for name in ("venv", "tmp", "worktrees"):
            assert classified[name].durability is Durability.EPHEMERAL
            assert not classified[name].is_durable()

    def test_non_git_refuses_unclassified_durable(self, tmp_path):
        """An unclassified area is refused, not silently made durable."""
        with pytest.raises(UnclassifiedAreaError):
            classify_area("undocumented_new_feature_dir")

    def test_non_git_disk_area_absent_from_registry_is_refused(self, tmp_path):
        """A directory present on disk but undeclared raises, not durable."""
        substr = tmp_path / ".skillweave"
        substr.mkdir()
        (substr / "undocumented_new_feature_dir").mkdir()

        with pytest.raises(UnclassifiedAreaError):
            classify_substrate(str(tmp_path))
