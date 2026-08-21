"""Workspace provisioning (SW-WORKSPACE-001).

``WorkspaceProvider`` is the contract for producing an exclusive work area for
one worker, and ``GitWorktreeProvider`` is the local git-worktree adapter: a
full base SHA is materialised into an exclusive worktree on its own branch,
attested, and cleaned up deterministically.

Two facts drive the design:

1. A worker's workspace must be *exclusive* — no other run may write it. The
   adapter therefore manages the branch itself and refuses two acquisitions on
   the same branch.

2. A workspace must be *attested and deterministically cleaned up*. An
   :class:`Attestation` records the resolved full base SHA, branch, and path at
   acquire time; cleanup removes exactly what was created, and a repeated
   cleanup is a no-op rather than an error. There is never a half-torn-down
   worktree.
"""

from .provider import (
    WorkspaceProvider,
    Workspace,
    Attestation,
    WorkspaceProviderError,
    GitWorktreeProvider,
)

__all__ = [
    "WorkspaceProvider",
    "Workspace",
    "Attestation",
    "WorkspaceProviderError",
    "GitWorktreeProvider",
]
