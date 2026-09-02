"""Backing-store seam for the substrate contract.

The substrate previously delegated its durability/disclosure decision to git:
the presence of a ``.git`` directory and the tracked/untracked bit were treated
as the whole answer. That collapses three independent properties — direction,
durability, disclosure — into one bit, and is wrong the moment the workspace is
not a git repository (the measured majority case), or an area is ephemeral.

This module introduces a :class:`BackingStore` seam with two adapters:

* :class:`GitBackingStore` — durability is git-tracked-ness and disclosure is
  repository visibility.
* :class:`LocalOnlyBackingStore` — durability is "this machine" and disclosure
  is "nothing leaves".

The runtime resolves an area's store from its :class:`AreaDeclaration` (the
``store`` axis), not from the presence of a ``.git`` directory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from skillweave.persistence import (
    AreaDeclaration,
    Direction,
    Disclosure,
    Durability,
    StoreKind,
    get_area_declaration,
    known_areas,
)


class UnclassifiedAreaError(ValueError):
    """Raised when the runtime is asked to treat an area as durable but the area
    has no declaration. An unclassified area is refused rather than silently
    classified as durable."""

    def __init__(self, area_name: str):
        self.area_name = area_name
        super().__init__(
            f"area '{area_name}' has no substrate declaration; "
            "refusing to treat it as durable"
        )


@dataclass(frozen=True)
class ResolvedArea:
    """The effective axes for one area as realised by a backing store."""

    name: str
    direction: Direction
    durability: Durability
    disclosure: Disclosure
    store: StoreKind

    def is_durable(self) -> bool:
        return self.durability is Durability.DURABLE


class BackingStore(ABC):
    """A backing store realises durability and disclosure for a declared area."""

    kind: StoreKind

    @abstractmethod
    def resolve(self, area: AreaDeclaration) -> ResolvedArea:
        """Resolve a declared area to its effective axes under this store."""
        ...

    @abstractmethod
    def effective_durability(self, area: AreaDeclaration) -> Durability:
        """Return the durability this store grants the declared area."""
        ...

    @abstractmethod
    def effective_disclosure(self, area: AreaDeclaration) -> Disclosure:
        """Return the disclosure this store grants the declared area."""
        ...


class GitBackingStore(BackingStore):
    """Durability = git-tracked, disclosure = repository visibility.

    A tracked area is durable; an untracked area is reconstructible at best.
    Disclosure follows the repository's visibility (open vs private). An area
    declared EPHEMERAL stays ephemeral regardless of git status: ``venv/``,
    ``tmp/`` and ``worktrees/`` are never durable or disclosed even in a repo.
    """

    kind = StoreKind.GIT

    def __init__(
        self, visibility: Disclosure = Disclosure.PRIVATE, tracked: Optional[set] = None
    ) -> None:
        self._visibility = visibility
        self._tracked: set = tracked or set()

    def effective_durability(self, area: AreaDeclaration) -> Durability:
        if area.durability is Durability.EPHEMERAL:
            return Durability.EPHEMERAL
        if area.durability is Durability.DURABLE and area.name in self._tracked:
            return Durability.DURABLE
        if area.durability is Durability.RECONSTRUCTIBLE:
            return Durability.RECONSTRUCTIBLE
        return Durability.RECONSTRUCTIBLE

    def effective_disclosure(self, area: AreaDeclaration) -> Disclosure:
        if area.durability is Durability.EPHEMERAL:
            return Disclosure.SEALED
        return self._visibility

    def resolve(self, area: AreaDeclaration) -> ResolvedArea:
        return ResolvedArea(
            name=area.name,
            direction=area.direction,
            durability=self.effective_durability(area),
            disclosure=self.effective_disclosure(area),
            store=self.kind,
        )


class LocalOnlyBackingStore(BackingStore):
    """Durability = this machine, disclosure = nothing leaves.

    The local-only adapter is the generic case: it does not need git and treats
    the declared durability as the answer, with disclosure always SEALED.
    Ephemeral areas stay ephemeral.
    """

    kind = StoreKind.LOCAL_ONLY

    def effective_durability(self, area: AreaDeclaration) -> Durability:
        return area.durability

    def effective_disclosure(self, area: AreaDeclaration) -> Disclosure:
        if area.durability is Durability.EPHEMERAL:
            return Disclosure.SEALED
        return Disclosure.SEALED

    def resolve(self, area: AreaDeclaration) -> ResolvedArea:
        return ResolvedArea(
            name=area.name,
            direction=area.direction,
            durability=area.durability,
            disclosure=Disclosure.SEALED,
            store=self.kind,
        )


_STORE_FACTORIES = {
    StoreKind.GIT: GitBackingStore,
    StoreKind.LOCAL_ONLY: LocalOnlyBackingStore,
}


def resolve_store(
    store_kind: StoreKind,
    visibility: Disclosure = Disclosure.PRIVATE,
    tracked: Optional[set] = None,
) -> BackingStore:
    """Resolve a backing store from its *declared* kind, not from ``.git``.

    This is the inversion the contract requires: the caller names a store kind
    (via the area's declaration) and gets the adapter, instead of probing the
    filesystem for a ``.git`` directory.
    """
    factory = _STORE_FACTORIES[store_kind]
    if store_kind is StoreKind.GIT:
        return factory(visibility=visibility, tracked=tracked)
    return factory()


def classify_area(area_name: str, store: Optional[BackingStore] = None) -> ResolvedArea:
    """Classify a single named area against its declaration and a store.

    Unclassified areas that would be durable are refused with
    :class:`UnclassifiedAreaError`; unclassified ephemeral names are never
    promoted to durable.
    """
    decl = get_area_declaration(area_name)
    if decl is None:
        raise UnclassifiedAreaError(area_name)
    store = store or resolve_store(decl.store)
    return store.resolve(decl)


def classify_substrate(
    project_root: Optional[str] = None,
    areas: Optional[List[str]] = None,
    store: Optional[BackingStore] = None,
) -> Dict[str, ResolvedArea]:
    """Classify every area of a substrate, refusing unclassified-durable names.

    In a non-git directory the local-only store is used by default (nothing
    leaves, durability is "this machine"). Every declared area reports a
    coherent durability and disclosure; an area present on disk but absent from
    the declaration raises :class:`UnclassifiedAreaError` instead of being
    silently treated as durable.
    """
    names = areas if areas is not None else known_areas()
    if project_root is not None:
        root = Path(project_root)
        substr = root / ".skillweave"
        if substr.is_dir():
            on_disk = sorted(
                p.name for p in substr.iterdir() if not p.name.startswith(".")
            )
            names = list(dict.fromkeys([*names, *on_disk]))
    store = store or LocalOnlyBackingStore()

    result: Dict[str, ResolvedArea] = {}
    for name in names:
        decl = get_area_declaration(name)
        if decl is None:
            raise UnclassifiedAreaError(name)
        result[name] = store.resolve(decl)
    return result


__all__ = [
    "BackingStore",
    "GitBackingStore",
    "LocalOnlyBackingStore",
    "ResolvedArea",
    "UnclassifiedAreaError",
    "resolve_store",
    "classify_area",
    "classify_substrate",
]
