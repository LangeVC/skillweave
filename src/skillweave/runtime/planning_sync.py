"""Planning-sync backing store: durability without a repository of one's own.

For a multi-repo org the central planning repository is the right default
precisely because it decouples durability from whichever repo happened to be
the working directory. ``skillweave/skillweave-planning`` already implements
the rule as an explicit allowlist in ``.gitignore``: ignore everything under
``.skillweave/``, then re-include the planning payload by name.

What was missing is not the *place* but the *path* to it: a workspace with no
git repository of its own had eight substrates whose durable areas had no
reachable store. This module adds the ``PlanningSyncBackingStore`` adapter —
a third realisation of the :class:`~skillweave.runtime.substrate.BackingStore`
seam — so an area declared durable in a non-git workspace can be carried to
the configured org planning repository, with the operator able to see what was
and what was not synced.

The adapter coexists with git-in-repo rather than replacing it: a monorepo
still resolves its areas through :class:`GitBackingStore`. The *declaration*
lives on the area (see :class:`AreaDeclaration` in
:mod:`skillweave.persistence`, the ``store`` axis and the ``durability`` axis);
this module only decides, at runtime, *which* store realises that declaration
for a given workspace — git-in-repo when a repository is present, planning-sync
when a planning repository is configured, and "at risk" when neither exists.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from skillweave.persistence import (
    AreaDeclaration,
    Disclosure,
    Durability,
    StoreKind,
    get_area_declaration,
    known_areas,
)
from skillweave.runtime.substrate import (
    BackingStore,
    GitBackingStore,
    LocalOnlyBackingStore,
    ResolvedArea,
    UnclassifiedAreaError,
)

#: Environment variable that names the org planning repository explicitly.
#: Discovery also reads ``sync.yaml`` (see :func:`discover_planning_repo`).
PLANNING_REPO_ENV = "SKILLWEAVE_PLANNING_REPOSITORY"

#: Environment variable that names the *local checkout* of the planning
#: repository — the reachable destination directory a sync writes into. This is
#: how a configured repository name becomes a usable destination.
PLANNING_ROOT_ENV = "SKILLWEAVE_PLANNING_ROOT"

#: The sync manifest key that declares the planning repository. This mirrors
#: ``skillweave/skillweave-planning/sync.yaml``, which carries
#: ``planning_repository: skillweave/skillweave-planning``.
PLANNING_REPO_KEY = "planning_repository"

#: The sync manifest key that declares the local checkout of the planning
#: repository. When absent, discovery falls back to the environment variable.
#: ``sync.yaml`` shipped today carries ``planning_repository`` but no
#: destination key, so the environment variable is the primary producer.
PLANNING_ROOT_KEY = "planning_root"

#: Default sync root inside the planning repository checkout. The planning
#: repo's own ``.gitignore`` re-includes ``.skillweave/planning/`` by name,
#: which is where a sync writes.
DEFAULT_TICKET_ROOT = ".skillweave/planning"


@dataclass(frozen=True)
class SyncReport:
    """What one planning-sync carried for one area, and whether it is at risk.

    ``carried`` is the list of files the sync copied into the planning
    repository, relative to the sync destination. A sync that carried nothing
    still names an empty list rather than claiming silently.
    """

    area: str
    carried: Tuple[str, ...] = ()
    destination: str = ""
    at_risk: bool = False
    reason: str = ""

    def names(self) -> List[str]:
        return list(self.carried)


def discover_planning_repo(project_root: Optional[str] = None) -> Optional[str]:
    """Return the configured org planning repository, or None when unconfigured.

    Resolution order (explicit wins, absence is significant and never padded by
    a default):

    1. ``SKILLWEAVE_PLANNING_REPOSITORY`` in the environment.
    2. the ``planning_repository`` key of ``<project_root>/sync.yaml``.

    A workspace with neither is *unreachable* — the whole point: a durable area
    with no reachable store must be reported at risk, not silently accepted.
    """
    env = os.environ.get(PLANNING_REPO_ENV)
    if env:
        return env.strip() or None

    if project_root is not None:
        sync_yaml = Path(project_root) / "sync.yaml"
        if sync_yaml.is_file():
            import yaml

            try:
                data = yaml.safe_load(sync_yaml.read_text()) or {}
            except Exception:
                data = {}
            repo = data.get(PLANNING_REPO_KEY)
            if isinstance(repo, str) and repo.strip():
                return repo.strip()

    return None


def discover_planning_root(project_root: Optional[str] = None) -> Optional[str]:
    """Return the local planning-repository checkout directory, or None.

    This is what turns a *configured repository name* into a *reachable
    destination*: the sync can copy payload only into a directory that exists
    on this machine. Resolution order (explicit wins, absence is significant):

    1. ``SKILLWEAVE_PLANNING_ROOT`` in the environment.
    2. the ``planning_root`` key of ``<project_root>/sync.yaml`` (also accepts
       the historical ``planning_checkout`` spelling).

    Only a directory that actually exists on disk is returned; a configured
    path that is absent is treated as unreachable (the caller reports the area
    at risk), never waved through.
    """
    env = os.environ.get(PLANNING_ROOT_ENV)
    candidate = env.strip() if (env and env.strip()) else None

    if candidate is None and project_root is not None:
        sync_yaml = Path(project_root) / "sync.yaml"
        if sync_yaml.is_file():
            import yaml

            try:
                data = yaml.safe_load(sync_yaml.read_text()) or {}
            except Exception:
                data = {}
            value = data.get(PLANNING_ROOT_KEY) or data.get("planning_checkout")
            if isinstance(value, str) and value.strip():
                candidate = value.strip()

    if not candidate:
        return None

    candidate_path = Path(candidate)
    if not candidate_path.is_dir():
        return None

    return str(candidate_path.resolve())


def runtime_has_git(project_root: Optional[str] = None) -> bool:
    """Whether the workspace is (or is inside) a git repository.

    Only the *explicit* project root is probed (its ``.git`` entry), so a
    non-git fixture is never rescued by an ambient parent repository.
    """
    if project_root is None:
        return False
    git_marker = Path(project_root) / ".git"
    return git_marker.exists()


class PlanningSyncBackingStore(BackingStore):
    """Durable areas in a non-git workspace are carried to the org planning repo.

    Durability is "will be preserved by landing in the planning repository";
    disclosure is ``PRIVATE`` once carried (the planning repo is org-private) and
    ``SEALED`` for ephemeral areas, which are never carried.

    The store is **reachable** only when a repository is configured *and* a
    planning-root destination exists. Without a destination the store reports
    the area at risk rather than pretending durability.
    """

    kind = StoreKind.GIT

    def __init__(
        self,
        repository: str,
        planning_root: Optional[str] = None,
        ticket_root: str = DEFAULT_TICKET_ROOT,
    ) -> None:
        self._repository = repository
        self._planning_root = Path(planning_root) if planning_root else None
        self._ticket_root = ticket_root

    @property
    def repository(self) -> str:
        return self._repository

    @property
    def reachable(self) -> bool:
        return self._planning_root is not None and self._planning_root.is_dir()

    def effective_durability(self, area: AreaDeclaration) -> Durability:
        return area.durability

    def effective_disclosure(self, area: AreaDeclaration) -> Disclosure:
        if area.durability is Durability.EPHEMERAL:
            return Disclosure.SEALED
        return Disclosure.PRIVATE

    def resolve(self, area: AreaDeclaration) -> ResolvedArea:
        at_risk = area.durability is Durability.DURABLE and not self.reachable
        return ResolvedArea(
            name=area.name,
            direction=area.direction,
            durability=self.effective_durability(area),
            disclosure=self.effective_disclosure(area),
            store=self.kind,
            at_risk=at_risk,
        )

    def destination(self, area_name: str) -> Path:
        """The sync destination directory for an area inside the planning root."""
        return self._planning_root / self._ticket_root / area_name

    def sync(self, area_name: str, project_root: str) -> SyncReport:
        """Carry a durable area's payload into the planning repository.

        Copies every file under ``<project_root>/.skillweave/<area_name>/`` into
        ``<planning_root>/.skillweave/planning/<area_name>/`` and returns a
        :class:`SyncReport` that *names* what it carried. An unreachable store
        (no planning root) returns an empty, at-risk report instead of claiming
        a sync that did not happen.
        """
        decl = get_area_declaration(area_name)
        if decl is None:
            raise UnclassifiedAreaError(area_name)

        source = Path(project_root) / ".skillweave" / area_name
        if not self.reachable:
            return SyncReport(
                area=area_name,
                destination=str(self.destination(area_name)),
                at_risk=decl.durability is Durability.DURABLE,
                reason=(
                    f"planning repository {self._repository!r} is configured "
                    "but no reachable destination root exists"
                ),
            )

        dest = self.destination(area_name)
        dest.mkdir(parents=True, exist_ok=True)

        carried: List[str] = []
        if source.is_dir():
            for file in sorted(source.rglob("*")):
                if not file.is_file():
                    continue
                rel = file.relative_to(source)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)
                carried.append(rel.as_posix())

        return SyncReport(
            area=area_name,
            carried=tuple(carried),
            destination=str(dest),
            at_risk=False,
            reason="",
        )


def resolve_runtime_store(
    project_root: Optional[str] = None,
    planning_repo: Optional[str] = None,
    planning_root: Optional[str] = None,
) -> BackingStore:
    """Resolve the backing store a workspace's durable areas are realised by.

    - a git repository present -> :class:`GitBackingStore` (the monorepo case);
    - else a configured planning repository -> :class:`PlanningSyncBackingStore`;
    - else -> :class:`LocalOnlyBackingStore` (durable areas will be reported at
      risk by :func:`classify_runtime`, never silently accepted).

    ``planning_repo`` and ``planning_root`` may be supplied explicitly (used by
    the operator and by tests); when omitted they are discovered from the
    environment and ``sync.yaml``. ``planning_root`` is resolved through
    :func:`discover_planning_root` so a configured repository alone yields a
    reachable destination instead of a bare, unreachable name.
    """
    if runtime_has_git(project_root):
        return GitBackingStore()

    repo = planning_repo if planning_repo is not None else discover_planning_repo(project_root)
    if repo:
        root = planning_root if planning_root is not None else discover_planning_root(project_root)
        return PlanningSyncBackingStore(repository=repo, planning_root=root)

    return LocalOnlyBackingStore()


def classify_runtime(
    project_root: Optional[str] = None,
    areas: Optional[List[str]] = None,
    planning_repo: Optional[str] = None,
    planning_root: Optional[str] = None,
) -> Dict[str, ResolvedArea]:
    """Classify every declared area for a workspace, refusing unclassified names.

    Durable areas whose durability has **no reachable store** — a workspace with
    no git repository and no configured planning repository — are reported
    ``at_risk`` (``is_durable()`` is False) rather than silently accepted. This
    is the runtime counterpart of :func:`classify_substrate` that adds the
    planning-sync store choice and the at-risk report.
    """
    has_git = runtime_has_git(project_root)
    repo = planning_repo if planning_repo is not None else discover_planning_repo(project_root)
    reachable = has_git or bool(repo)

    store = resolve_runtime_store(
        project_root=project_root,
        planning_repo=planning_repo,
        planning_root=planning_root,
    )

    names = areas if areas is not None else known_areas()
    result: Dict[str, ResolvedArea] = {}
    for name in names:
        decl = get_area_declaration(name)
        if decl is None:
            raise UnclassifiedAreaError(name)
        resolved = store.resolve(decl)
        if decl.durability is Durability.DURABLE and not reachable:
            resolved = ResolvedArea(
                name=resolved.name,
                direction=resolved.direction,
                durability=resolved.durability,
                disclosure=resolved.disclosure,
                store=resolved.store,
                at_risk=True,
            )
        result[name] = resolved
    return result


__all__ = [
    "PlanningSyncBackingStore",
    "SyncReport",
    "discover_planning_repo",
    "discover_planning_root",
    "runtime_has_git",
    "resolve_runtime_store",
    "classify_runtime",
    "PLANNING_REPO_ENV",
    "PLANNING_ROOT_ENV",
    "PLANNING_REPO_KEY",
    "PLANNING_ROOT_KEY",
]
