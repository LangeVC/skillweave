"""Workspace release policy (SW-155 / SW-155-WORKSPACE-002).

Covers the acceptance surface of the fail-closed release lifecycle:

* lease release, worktree removal and branch deletion are three independent
  operations and are never chained implicitly;
* removal is held when the worktree is dirty or unreachable, when a lease is
  still active, when a process/session is still active, or when any fact is
  unknown/unavailable (fail-closed);
* branch deletion is a separate, explicitly authorized action and is disabled
  by default;
* every attempt returns a deterministic receipt, including HOLD and no-op
  outcomes, and repeated lease-release/removal attempts are idempotent;
* no real machine worktree is ever touched: facts arrive through an injected
  evidence probe and mutations through injected callables. The tests use
  throwaway temporary repositories only.

Self-contained sys.path handling, following the convention of the workspace
module's sibling tests.

This file was authored first and run red against the pre-implementation module
(``ImportError`` for the release API); the module then grew the narrowest
compatible API to make it green.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.routing.workspace import (  # noqa: E402
    BranchDeletionAuthorization,
    WorkspaceEvidence,
    WorkspaceManifest,
    WorkspaceReleaseError,
    WorkspaceReleasePolicy,
    worktree_path,
)

BASE_SHA = "1" * 40
HEAD_SHA = "2" * 40
ISO_TS = "2026-09-24T00:00:00+00:00"
REPO = "skillweave"
RUN = "sw155"
LANE = "workspace-release-big-pickle"


# --- Fixtures / fakes ------------------------------------------------------


def _manifest(branch: str = "ops/SW-155-workspace-release-big-pickle") -> WorkspaceManifest:
    return WorkspaceManifest.from_dict(
        {
            "repo": REPO,
            "base_sha": BASE_SHA,
            "head_sha": HEAD_SHA,
            "branch": branch,
            "run": RUN,
            "lane": LANE,
            "session": "session-001",
            "write_scope": ["src/skillweave/routing/"],
            "lease": {"lease_until": ISO_TS, "owner": "ops"},
            "heartbeat": ISO_TS,
            "state": "active",
            "retention": "project_lifetime",
        }
    )


def _probe(worktree="clean", lease="released", process="inactive"):
    def probe(_manifest):
        return WorkspaceEvidence(worktree=worktree, lease=lease, process=process)

    return probe


class _Recorder:
    """Records injected mutation calls; never touches a real workspace."""

    def __init__(self, result: bool = True):
        self.calls = []
        self.result = result

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


def _policy(root, *, probe=None, remover=None, deleter=None, releaser=None):
    return WorkspaceReleasePolicy(
        str(root),
        evidence_probe=probe if probe is not None else _probe(),
        worktree_remover=remover if remover is not None else _Recorder(),
        branch_deleter=deleter if deleter is not None else _Recorder(),
        lease_releaser=releaser if releaser is not None else _Recorder(),
    )


def _make_repo() -> str:
    """Create a throwaway git repo with one commit; return its root path.

    The checkout lives in its own unique directory, so each test's derived
    collection (and therefore worktree path) is unique too.
    """
    tmp = tempfile.mkdtemp(prefix="sw-ws-release-")
    root = str(Path(tmp) / "repo")
    Path(root).mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    (Path(root) / "file.txt").write_text("one")
    subprocess.run(["git", "add", "file.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=root, check=True)
    return root


def _branches(root: str, branch: str) -> str:
    return subprocess.run(
        ["git", "branch", "--list", branch],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _target(root: str) -> Path:
    return worktree_path(root, repo=REPO, run=RUN, lane=LANE)


# --- Lease release is its own operation -----------------------------------


def test_release_lease_releases_only_the_lease():
    root = _make_repo()
    manifest = _manifest()
    remover, deleter, releaser = _Recorder(), _Recorder(), _Recorder()

    receipt = _policy(
        root,
        probe=_probe(lease="active"),
        remover=remover,
        deleter=deleter,
        releaser=releaser,
    ).release_lease(manifest)

    assert receipt.action == "release_lease"
    assert receipt.outcome == "ok"
    assert receipt.reason == "lease_released"
    assert receipt.branch == manifest.branch
    assert len(releaser.calls) == 1
    # Releasing the lease touches neither the worktree nor the branch.
    assert remover.calls == []
    assert deleter.calls == []


def test_release_lease_is_idempotent_and_deterministic():
    root = _make_repo()
    manifest = _manifest()
    state = {"lease": "active"}

    def probe(_manifest):
        return WorkspaceEvidence(
            worktree="clean", lease=state["lease"], process="inactive"
        )

    def releaser(_manifest):
        state["lease"] = "released"
        return True

    policy = _policy(root, probe=probe, releaser=releaser)
    first = policy.release_lease(manifest)
    second = policy.release_lease(manifest)
    third = policy.release_lease(manifest)

    assert first.outcome == "ok" and first.reason == "lease_released"
    assert second.outcome == "noop" and second.reason == "lease_absent"
    # Repeated attempts in the same state are byte-identical.
    assert third.to_json() == second.to_json()
    assert third.digest == second.digest


def test_release_lease_holds_when_the_lease_fact_is_unknown():
    root = _make_repo()
    releaser = _Recorder()
    receipt = _policy(
        root, probe=_probe(lease="unknown"), releaser=releaser
    ).release_lease(_manifest())

    assert receipt.outcome == "hold"
    assert receipt.reason == "unknown"
    assert releaser.calls == []


# --- Worktree removal is gated, fail-closed -------------------------------


def test_clean_worktree_removal_is_allowed_and_never_deletes_the_branch():
    root = _make_repo()
    branch = "ops/SW-155-keep"
    manifest = _manifest(branch)
    subprocess.run(["git", "branch", branch], cwd=root, check=True)
    remover, deleter = _Recorder(), _Recorder()

    receipt = _policy(
        root, probe=_probe(), remover=remover, deleter=deleter
    ).remove_worktree(manifest)

    assert receipt.action == "remove_worktree"
    assert receipt.outcome == "ok"
    assert receipt.reason == "worktree_removed"
    assert len(remover.calls) == 1
    # Branch deletion is a separate action and stays disabled: not attempted.
    assert deleter.calls == []
    assert branch in _branches(root, branch)


def test_removal_is_held_when_the_worktree_is_dirty():
    root = _make_repo()
    remover = _Recorder()
    receipt = _policy(
        root, probe=_probe(worktree="dirty"), remover=remover
    ).remove_worktree(_manifest())

    assert receipt.outcome == "hold"
    assert receipt.reason == "dirty"
    assert remover.calls == []


def test_removal_is_held_when_the_worktree_is_unreachable():
    root = _make_repo()
    remover = _Recorder()
    receipt = _policy(
        root, probe=_probe(worktree="unreachable"), remover=remover
    ).remove_worktree(_manifest())

    assert receipt.outcome == "hold"
    assert receipt.reason == "unreachable"
    assert remover.calls == []


def test_removal_is_held_when_a_lease_is_still_active():
    root = _make_repo()
    remover = _Recorder()
    receipt = _policy(
        root, probe=_probe(lease="active"), remover=remover
    ).remove_worktree(_manifest())

    assert receipt.outcome == "hold"
    assert receipt.reason == "active_lease"
    assert remover.calls == []


def test_removal_is_held_when_a_process_is_still_active():
    root = _make_repo()
    remover = _Recorder()
    receipt = _policy(
        root, probe=_probe(process="active"), remover=remover
    ).remove_worktree(_manifest())

    assert receipt.outcome == "hold"
    assert receipt.reason == "active_process"
    assert remover.calls == []


def test_removal_is_held_when_evidence_is_unavailable_or_unknown():
    root = _make_repo()
    remover = _Recorder()
    manifest = _manifest()

    def raising_probe(_manifest):
        raise RuntimeError("no evidence source")

    receipt = _policy(root, probe=raising_probe, remover=remover).remove_worktree(
        manifest
    )
    assert receipt.outcome == "hold"
    assert receipt.reason == "unknown"
    assert remover.calls == []

    # An unproven dimension is coerced to unknown, never guessed: this holds
    # removal even though every other fact says it is safe.
    receipt = _policy(
        root, probe=_probe(worktree="banana"), remover=remover
    ).remove_worktree(manifest)
    assert receipt.outcome == "hold"
    assert receipt.reason == "unknown"
    assert remover.calls == []

    # A probe handing back an unusable object is equally fail-closed.
    receipt = _policy(
        root, probe=lambda _manifest: object(), remover=remover
    ).remove_worktree(manifest)
    assert receipt.outcome == "hold"
    assert receipt.reason == "unknown"
    assert remover.calls == []


def test_removing_an_absent_worktree_is_a_noop():
    root = _make_repo()
    remover = _Recorder()
    receipt = _policy(
        root, probe=_probe(worktree="absent"), remover=remover
    ).remove_worktree(_manifest())

    assert receipt.outcome == "noop"
    assert receipt.reason == "worktree_absent"
    assert remover.calls == []


def test_removal_is_idempotent():
    root = _make_repo()
    manifest = _manifest()
    state = {"worktree": "clean"}

    def probe(_manifest):
        return WorkspaceEvidence(
            worktree=state["worktree"], lease="released", process="inactive"
        )

    def remover(_path):
        state["worktree"] = "absent"
        return True

    policy = _policy(root, probe=probe, remover=remover)
    first = policy.remove_worktree(manifest)
    second = policy.remove_worktree(manifest)
    third = policy.remove_worktree(manifest)

    assert first.outcome == "ok" and first.reason == "worktree_removed"
    assert second.outcome == "noop" and second.reason == "worktree_absent"
    assert third.to_json() == second.to_json()


# --- Branch deletion is separate, explicit and disabled by default --------


def test_branch_deletion_is_disabled_by_default():
    root = _make_repo()
    branch = "ops/SW-155-disabled"
    manifest = _manifest(branch)
    subprocess.run(["git", "branch", branch], cwd=root, check=True)
    deleter = _Recorder()

    receipt = _policy(root, deleter=deleter).delete_branch(manifest)

    assert receipt.action == "delete_branch"
    assert receipt.outcome == "noop"
    assert receipt.reason == "branch_deletion_disabled"
    assert deleter.calls == []
    assert branch in _branches(root, branch)


def test_branch_deletion_requires_matching_explicit_authorization():
    root = _make_repo()
    branch = "ops/SW-155-authorized"
    manifest = _manifest(branch)
    subprocess.run(["git", "branch", branch], cwd=root, check=True)

    def deleter(name):
        subprocess.run(
            ["git", "branch", "-D", name], cwd=root, check=True, capture_output=True
        )
        return True

    policy = _policy(root, deleter=deleter)

    # Authorization naming a different branch is refused: no retargeting.
    wrong = BranchDeletionAuthorization(branch="ops/SW-155-other", authorized_by="ops")
    receipt = policy.delete_branch(manifest, authorization=wrong)
    assert receipt.outcome == "hold"
    assert receipt.reason == "branch_authorization_mismatch"
    assert branch in _branches(root, branch)

    # A matching authorization deletes exactly the named branch.
    right = BranchDeletionAuthorization(branch=branch, authorized_by="ops")
    receipt = policy.delete_branch(manifest, authorization=right)
    assert receipt.outcome == "ok"
    assert receipt.reason == "branch_deleted"
    assert branch not in _branches(root, branch)


# --- Full sequence: separation and determinism ----------------------------


def test_branch_deletion_is_never_attempted_when_removal_is_held():
    root = _make_repo()
    branch = "ops/SW-155-held"
    manifest = _manifest(branch)
    remover, deleter = _Recorder(), _Recorder()
    authorization = BranchDeletionAuthorization(branch=branch, authorized_by="ops")

    receipts = _policy(
        root, probe=_probe(worktree="dirty"), remover=remover, deleter=deleter
    ).release_workspace(manifest, branch_authorization=authorization)

    assert [r.action for r in receipts] == [
        "release_lease",
        "remove_worktree",
        "delete_branch",
    ]
    assert receipts[1].outcome == "hold" and receipts[1].reason == "dirty"
    assert receipts[2].outcome == "hold"
    assert receipts[2].reason == "removal_blocked"
    # Removal held => neither mutation was ever attempted, even authorized.
    assert remover.calls == []
    assert deleter.calls == []


def test_release_workspace_runs_the_three_steps_when_clean_and_authorized():
    root = _make_repo()
    branch = "ops/SW-155-clean"
    manifest = _manifest(branch)
    state = {"worktree": "clean", "lease": "active"}

    def probe(_manifest):
        return WorkspaceEvidence(
            worktree=state["worktree"], lease=state["lease"], process="inactive"
        )

    def releaser(_manifest):
        state["lease"] = "released"
        return True

    def remover(_path):
        state["worktree"] = "absent"
        return True

    deleter = _Recorder()
    authorization = BranchDeletionAuthorization(branch=branch, authorized_by="ops")
    receipts = _policy(
        root, probe=probe, remover=remover, deleter=deleter, releaser=releaser
    ).release_workspace(manifest, branch_authorization=authorization)

    assert [r.outcome for r in receipts] == ["ok", "ok", "ok"]
    assert deleter.calls == [(branch,)]


def test_receipts_are_deterministic_for_ok_hold_and_noop():
    root = _make_repo()
    manifest = _manifest()

    def once(probe):
        return _policy(root, probe=probe).remove_worktree(manifest)

    ok = [once(_probe()), once(_probe())]
    hold = [once(_probe(worktree="dirty")), once(_probe(worktree="dirty"))]
    noop = [once(_probe(worktree="absent")), once(_probe(worktree="absent"))]

    for first, second in (ok, hold, noop):
        assert first.outcome == second.outcome
        assert first.to_json() == second.to_json()
        assert first.digest == second.digest
    assert (
        ok[0].outcome == "ok"
        and hold[0].outcome == "hold"
        and noop[0].outcome == "noop"
    )


# --- Safety: nothing real is ever touched ---------------------------------


def test_policy_delegates_mutation_and_leaves_the_real_path_untouched():
    root = _make_repo()
    manifest = _manifest()
    target = _target(root)
    target.mkdir(parents=True)
    remover = _Recorder()

    receipt = _policy(root, probe=_probe(), remover=remover).remove_worktree(manifest)

    assert receipt.outcome == "ok"
    assert remover.calls == [(target,)]
    # The policy itself never deletes anything: only the injected remover acts.
    assert target.exists()


def test_default_policy_is_fail_closed_and_mutates_nothing():
    root = _make_repo()
    manifest = _manifest()
    target = _target(root)

    policy = WorkspaceReleasePolicy(root)  # no injected evidence or mutators
    existed_before = target.exists()

    removal = policy.remove_worktree(manifest)
    assert removal.outcome == "hold" and removal.reason == "unknown"

    lease = policy.release_lease(manifest)
    assert lease.outcome == "hold" and lease.reason == "unknown"

    # Branch deletion still defaults to disabled even with no other evidence.
    branch = policy.delete_branch(manifest)
    assert branch.outcome == "noop" and branch.reason == "branch_deletion_disabled"

    # The default policy is inert: it neither creates nor removes the path.
    assert target.exists() == existed_before


def test_a_non_manifest_input_is_refused_fail_closed():
    root = _make_repo()
    policy = _policy(root)
    try:
        policy.remove_worktree({"not": "a manifest"})
    except WorkspaceReleaseError:
        pass
    else:
        raise AssertionError("non-manifest input was accepted")


def _run_all() -> int:
    tests = [
        v
        for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
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
