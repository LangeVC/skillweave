"""Tests for the workspace provider (SW-WORKSPACE-001).

Proves the local git-worktree adapter against a real, local (network-free)
repository:

* an exclusive worktree/branch is materialised from a full base SHA;
* the materialised tree is attested (HEAD == the full pin, digest recorded);
* a duplicate acquisition on the same branch is refused;
* release is deterministic and idempotent (repeat release is a no-op, the
  worktree and branch are gone).

Self-contained sys.path handling and a hermetic temp repo, following the
convention of the module's sibling tests.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.workspace import (  # noqa: E402
    Attestation,
    GitWorktreeProvider,
    Workspace,
    WorkspaceProviderError,
)


def _make_repo() -> tuple[str, str]:
    """Create a throwaway git repo with two commits; return (root, full_sha)."""
    root = tempfile.mkdtemp(prefix="sw-ws-")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=root, check=True
    )
    (Path(root) / "file.txt").write_text("one")
    subprocess.run(["git", "add", "file.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=root, check=True)
    (Path(root) / "file.txt").write_text("two")
    subprocess.run(["git", "commit", "-q", "-am", "c2"], cwd=root, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    return root, sha


def test_acquire_materialises_exclusive_worktree_from_full_sha():
    root, sha = _make_repo()
    provider = GitWorktreeProvider(root)
    ws = provider.acquire(sha, "ops/SW-WS-test")

    assert isinstance(ws, Workspace)
    assert isinstance(ws.attestation, Attestation)
    # Attested facts: full base SHA resolved, branch, path, digest recorded.
    assert ws.attestation.base_sha == sha
    assert ws.attestation.branch == "ops/SW-WS-test"
    assert ws.attestation.digest
    assert ws.path.exists()
    assert ws.path.is_dir()
    # The worktree is at the exact pinned commit and carries the repo content.
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(ws.path),
        capture_output=True, text=True,
    ).stdout.strip()
    assert head == sha
    assert (ws.path / "file.txt").read_text() == "two"

    ws.release()


def test_duplicate_acquisition_on_same_branch_is_refused():
    root, sha = _make_repo()
    provider = GitWorktreeProvider(root)
    ws = provider.acquire(sha, "ops/SW-WS-dup")
    try:
        provider.acquire(sha, "ops/SW-WS-dup")
    except WorkspaceProviderError:
        pass
    else:
        raise AssertionError("duplicate branch acquisition did not raise")
    ws.release()


def test_release_is_deterministic_and_idempotent():
    root, sha = _make_repo()
    provider = GitWorktreeProvider(root)
    ws = provider.acquire(sha, "ops/SW-WS-rel")
    path = ws.attestation.path
    branch = ws.attestation.branch

    assert provider.release(ws.attestation) is True
    assert not Path(path).exists()
    # The exclusive branch is gone.
    branches = subprocess.run(
        ["git", "branch", "--list", branch], cwd=root,
        capture_output=True, text=True,
    ).stdout
    assert branch not in branches

    # Repeated release is a no-op, not an error.
    assert provider.release(ws.attestation) is True


def test_garbage_base_sha_is_refused():
    root, _ = _make_repo()
    provider = GitWorktreeProvider(root)
    try:
        provider.acquire("0000000000000000000000000000000000000000", "ops/SW-WS-bad")
    except WorkspaceProviderError:
        pass
    else:
        raise AssertionError("garbage base SHA was accepted")


def _run_all() -> int:
    tests = [
        test_acquire_materialises_exclusive_worktree_from_full_sha,
        test_duplicate_acquisition_on_same_branch_is_refused,
        test_release_is_deterministic_and_idempotent,
        test_garbage_base_sha_is_refused,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
