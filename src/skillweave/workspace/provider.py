"""Workspace provisioning: contract plus a local git-worktree adapter.

``WorkspaceProvider`` is the abstract contract. ``GitWorktreeProvider`` is the
implementation over ``git worktree``: it creates an exclusive worktree on a
dedicated branch at a full base SHA, records an attestation, and cleans up
deterministically.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class WorkspaceProviderError(Exception):
    """A workspace could not be acquired, attested, or cleaned up."""


@dataclass
class Attestation:
    """The attested facts of an acquired workspace.

    Records the resolved full base SHA, the exclusive branch, the materialised
    path, and a digest over those facts so a later reader can prove the
    workspace matches what was created — without re-running git (``assert_matches``).
    """

    base_sha: str
    branch: str
    path: str
    created_at: str
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_sha": self.base_sha,
            "branch": self.branch,
            "path": self.path,
            "created_at": self.created_at,
            "digest": self.digest,
        }


@dataclass
class Workspace:
    """An acquired exclusive workspace: the attestation plus a release handle."""

    provider: "WorkspaceProvider"
    attestation: Attestation

    @property
    def path(self) -> Path:
        return Path(self.attestation.path)

    def release(self) -> None:
        self.provider.release(self.attestation)


class WorkspaceProvider:
    """Contract for producing exclusive workspaces.

    ``acquire`` materialises a full base SHA into an exclusive workspace and
    returns a :class:`Workspace` carrying an :class:`Attestation`. ``release``
    tears it down deterministically. ``attest`` (re-)read the facts of a
    workspace without mutating it.
    """

    def acquire(
        self,
        base_sha: str,
        branch: str,
        *,
        path: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Workspace:
        raise NotImplementedError

    def release(self, attestation: Attestation) -> bool:
        raise NotImplementedError

    def attest(self, path: str, branch: str) -> Attestation:
        raise NotImplementedError


def _digest(base_sha: str, branch: str, path: str) -> str:
    payload = f"{base_sha}|{branch}|{path}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class GitWorktreeProvider(WorkspaceProvider):
    """Local git-worktree adapter over a repository checkout.

    Each ``acquire`` creates a fresh worktree from the full ``base_sha`` on an
    exclusive ``branch``. The worktree lives inside the repository, under a
    per-run directory, so cleanup is bounded and deterministic: ``release``
    removes the worktree and deletes the branch, and repeated release is an
    idempotent no-op.
    """

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()
        self._acquired: set[str] = set()

    def _git(self, *args: str, cwd: Optional[Path] = None) -> str:
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=str(cwd or self.repo_root),
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise WorkspaceProviderError("git not available") from exc
        if out.returncode != 0:
            raise WorkspaceProviderError(
                f"git {' '.join(args)} failed: {out.stderr.strip()}"
            )
        return out.stdout.strip()

    def acquire(
        self,
        base_sha: str,
        branch: str,
        *,
        path: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Workspace:
        if branch in self._acquired:
            raise WorkspaceProviderError(
                f"branch '{branch}' is already acquired by this provider"
            )

        # The full base SHA must resolve to a commit. A short/ambiguous ref is
        # refused: the workspace is materialised from a full, unambiguous pin.
        resolved = self._git("rev-parse", "--verify", f"{base_sha}^{{commit}}")
        if not resolved or len(resolved) < 40:
            raise WorkspaceProviderError(
                f"base SHA '{base_sha}' did not resolve to a full commit"
            )

        created_at = created_at or datetime.now(timezone.utc).isoformat()
        target = Path(path) if path else self._default_path(branch)

        if target.exists():
            raise WorkspaceProviderError(
                f"worktree path '{target}' already exists; refusing to overwrite"
            )

        self._git("worktree", "add", "-b", branch, str(target), resolved)

        # Verify the materialised tree is exactly the pinned full SHA.
        head = self._git("rev-parse", "HEAD", cwd=target)
        if head != resolved:
            raise WorkspaceProviderError(
                f"worktree HEAD '{head}' != pinned base '{resolved}'"
            )

        attestation = Attestation(
            base_sha=resolved,
            branch=branch,
            path=str(target),
            created_at=created_at,
            digest=_digest(resolved, branch, str(target)),
        )
        self._acquired.add(branch)
        return Workspace(provider=self, attestation=attestation)

    def _default_path(self, branch: str) -> Path:
        # Deterministic, bounded: every worktree lands under .sw-worktrees/,
        # named by the branch, so cleanup never has to guess what to remove.
        return self.repo_root / ".sw-worktrees" / branch.replace("/", "__")

    def release(self, attestation: Attestation) -> bool:
        target = Path(attestation.path)
        branch = attestation.branch

        self._acquired.discard(branch)

        # Remove the worktree (metadata + directory) deterministically. A
        # missing path is an idempotent no-op, so repeated release is safe.
        if target.exists() and (target / ".git").exists():
            self._git("worktree", "remove", "--force", str(target))
        elif target.exists():
            shutil.rmtree(target, ignore_errors=True)

        # Delete the exclusive branch we created. Failure to find it (already
        # gone) is not an error: the branch is not something another run owns.
        out = subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
        )
        return True

    def attest(self, path: str, branch: str) -> Attestation:
        target = Path(path)
        if not target.exists():
            raise WorkspaceProviderError(f"worktree '{path}' does not exist")
        head = self._git("rev-parse", "HEAD", cwd=target)
        if not head:
            raise WorkspaceProviderError("could not resolve worktree HEAD")
        created_at = datetime.now(timezone.utc).isoformat()
        return Attestation(
            base_sha=head,
            branch=branch,
            path=str(target),
            created_at=created_at,
            digest=_digest(head, branch, str(target)),
        )
