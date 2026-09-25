"""Authorized workspace cleanup with durable receipts (SW-155-HEALTH-002).

Covers the acceptance surface of the *cleanup* phase that sits on top of the
read-only inventory in :mod:`skillweave.repo_health.worktrees`:

* cleanup removes **only** candidates explicitly authorized by stable identity
  (``repo/run/lane``), never by a broad path or glob;
* cleanup is idempotent and resumable: a completed removal is recorded in a
  durable receipt and is not repeated by a later run, even after the process
  was interrupted between removals;
* every attempt produces a durable receipt carrying before/after state, branch
  status, recoverability, the authorization identity and the outcome;
* branch deletion is **never** performed by cleanup and remains a separate,
  disabled-by-default concern;
* facts gate removal fail-closed: unsafe or unavailable evidence refuses.

All fixtures are disposable worktrees under ``tempfile.TemporaryDirectory``.
The tests also prove a real/current worktree is never selected: every path the
remover is called with must live under the fixture root, and the live
repository's own ``git worktree list`` must be byte-identical before/after.

This file was authored first and run red against the pre-implementation module
(``ImportError`` for the cleanup API); the module then grew the narrowest
compatible API to make it green.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.repo_health.worktrees import (  # noqa: E402
    CLEANUP_ALLOWED_CLASSIFICATIONS,
    CleanupAuthorization,
    CleanupOutcome,
    Recoverability,
    WorkspaceIdentity,
    cleanup_authorized_workspaces,
    read_cleanup_receipts,
)
from skillweave.routing.workspace import (  # noqa: E402
    Lease,
    WorkspaceManifest,
    WorkspaceManifestError,
    default_worktree_path,
)

_LIVE_REPO = Path(__file__).resolve().parent.parent.parent

REPO = "repo"
NOW = "2026-09-24T00:00:00+00:00"
PAST = "2020-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# git helpers (fixtures only - cleanup never shells out)
# --------------------------------------------------------------------------- #
def _run(*args, cwd=None, check=True):
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def _git(repo, *args, check=True):
    return _run("git", *args, cwd=repo, check=check)


def _init_repo(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    _run("git", "init", "-q", "-b", "main", str(path))
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "seed.txt").write_text("init\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return _git(path, "rev-parse", "HEAD").stdout.strip()


def _collection(tmp):
    """A disposable collection holding one primary checkout."""
    collection = Path(tmp) / "collection"
    primary = collection / REPO
    head = _init_repo(primary)
    return collection, primary, head


def _add_worktree(primary, collection, run, lane, branch):
    path = default_worktree_path(str(collection), repo=REPO, run=run, lane=lane)
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(primary, "worktree", "add", "-q", "-b", branch, str(path))
    return path


def _expired_manifest(repo, head, branch, run, lane):
    return WorkspaceManifest(
        repo=repo,
        base_sha=head,
        head_sha=head,
        branch=branch,
        run=run,
        lane=lane,
        session="sess-1",
        write_scope=["src/"],
        lease=Lease(lease_until=PAST, owner="host"),
        heartbeat=PAST,
        state="active",
        retention="temporary",
    )


class _Remover:
    """A real, disposable-worktree remover; records every path it is given."""

    def __init__(self, primary):
        self.primary = str(primary)
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        if not os.path.exists(path):
            return False
        _git(self.primary, "worktree", "remove", "--force", path)
        return True


def _authorize(run, lane, authorized_by="ops@sw155"):
    return CleanupAuthorization(
        repo=REPO, run=run, lane=lane, authorized_by=authorized_by
    )


def _cleanup(collection, authorizations, remover, receipts_path=None, **kwargs):
    return cleanup_authorized_workspaces(
        str(collection),
        authorizations=authorizations,
        worktree_remover=remover,
        receipts_path=str(receipts_path) if receipts_path else None,
        **kwargs,
    )


def _live_worktrees():
    return _git(_LIVE_REPO, "worktree", "list", "--porcelain").stdout


# --------------------------------------------------------------------------- #
# 1. only explicitly authorized identities are removed; never path/glob
# --------------------------------------------------------------------------- #
def test_cleanup_removes_only_the_authorized_candidate():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        authorized = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        bystander = _add_worktree(primary, collection, "run2", "lane2", "feat-b")

        remover = _Remover(primary)
        receipts = tmp + "/receipts.jsonl"
        report = _cleanup(
            collection, [_authorize("run1", "lane1")], remover, receipts
        )

        assert [r.outcome for r in report.receipts] == [CleanupOutcome.REMOVED]
        assert not authorized.exists()
        # The unauthorized neighbor is untouched even though it is a candidate.
        assert bystander.exists()
        assert remover.calls == [str(authorized)]


def test_unauthorized_existing_worktree_is_never_selected():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        _add_worktree(primary, collection, "run2", "lane2", "feat-b")

        remover = _Remover(primary)
        report = _cleanup(collection, [_authorize("run1", "lane1")], remover)

        assert len(report.receipts) == 1
        assert report.receipts[0].identity == WorkspaceIdentity(REPO, "run1", "lane1")
        assert all("run2" not in p for p in remover.calls)


def test_glob_and_traversal_identities_are_refused_at_authorization():
    for bad in ("*", "run*", "..", "a/b", "a?b", "run[1]", ""):
        try:
            CleanupAuthorization(
                repo=REPO, run=bad, lane="lane1", authorized_by="ops"
            )
        except WorkspaceManifestError:
            continue
        raise AssertionError(f"identity component {bad!r} was accepted")


def test_identity_key_is_the_stable_composition():
    assert _authorize("run1", "lane1").identity.key == "repo/run1/lane1"
    # Every identity maps to one deterministic path, composed not globbed.
    assert WorkspaceIdentity(REPO, "run1", "lane1").path_under(
        "/tmp/coll"
    ) == str(default_worktree_path("/tmp/coll", repo=REPO, run="run1", lane="lane1"))


# --------------------------------------------------------------------------- #
# 2. idempotent + resumable after an interrupted run
# --------------------------------------------------------------------------- #
def test_cleanup_is_idempotent_and_does_not_repeat_completed_removals():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        target = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        receipts = tmp + "/receipts.jsonl"
        remover = _Remover(primary)

        first = _cleanup(collection, [_authorize("run1", "lane1")], remover, receipts)
        assert first.receipts[0].outcome is CleanupOutcome.REMOVED
        assert len(remover.calls) == 1

        second = _cleanup(collection, [_authorize("run1", "lane1")], remover, receipts)
        assert second.receipts[0].outcome is CleanupOutcome.SKIPPED_COMPLETED
        assert second.receipts[0].reason == "already_completed"
        # The completed removal is not repeated: the remover is not called again.
        assert remover.calls == [str(target)]

        # The durable ledger holds both attempts, in order.
        durable = read_cleanup_receipts(receipts)
        assert [r.outcome for r in durable] == [
            CleanupOutcome.REMOVED,
            CleanupOutcome.SKIPPED_COMPLETED,
        ]


def test_cleanup_resumes_after_an_interrupted_run():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        first_target = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        second_target = _add_worktree(primary, collection, "run2", "lane2", "feat-b")
        receipts = tmp + "/receipts.jsonl"
        remover = _Remover(primary)

        # Batch 1 completes and is durably recorded, then the process stops.
        _cleanup(collection, [_authorize("run1", "lane1")], remover, receipts)
        assert not first_target.exists()

        # Something re-materialises the already-completed identity's directory.
        first_target.mkdir(parents=True)

        # Batch 2 resumes over both identities.
        report = _cleanup(
            collection,
            [_authorize("run1", "lane1"), _authorize("run2", "lane2")],
            remover,
            receipts,
        )
        outcomes = {r.identity.key: r.outcome for r in report.receipts}
        assert outcomes["repo/run1/lane1"] is CleanupOutcome.SKIPPED_COMPLETED
        assert outcomes["repo/run2/lane2"] is CleanupOutcome.REMOVED
        # The ledger - not the directory state - suppressed the repeat.
        assert first_target.exists()
        assert not second_target.exists()

        # A torn final line (crash mid-write) does not poison the ledger.
        with open(receipts, "a", encoding="utf-8") as handle:
            handle.write('{"identity": "repo/run3/lane3", "outco')
        assert len(read_cleanup_receipts(receipts)) == 3


def test_receipts_are_written_durably_before_the_next_removal():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        receipts = tmp + "/receipts.jsonl"
        seen = {}

        class _InspectingRemover(_Remover):
            def __call__(self, path):
                # At the moment of the FIRST removal, nothing is on disk yet;
                # after it, the receipt must already be durable.
                seen["before"] = os.path.exists(receipts)
                return super().__call__(path)

        remover = _InspectingRemover(primary)
        _cleanup(
            collection,
            [_authorize("run1", "lane1"), _authorize("run9", "lane9")],
            remover,
            receipts,
        )
        assert seen["before"] is False
        # run9 never existed, so its attempt is still recorded durably.
        assert len(read_cleanup_receipts(receipts)) == 2


def test_missing_candidate_is_a_noop_not_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        remover = _Remover(primary)
        report = _cleanup(collection, [_authorize("run1", "lane1")], remover)

        assert report.receipts[0].outcome is CleanupOutcome.ALREADY_ABSENT
        assert report.receipts[0].reason == "already_absent"
        assert remover.calls == []


# --------------------------------------------------------------------------- #
# 3. the durable receipt records the full required surface
# --------------------------------------------------------------------------- #
def test_receipt_records_before_after_branch_recoverability_and_authorization():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, head = _collection(tmp)
        target = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        manifest = _expired_manifest(REPO, head, "feat-a", "run1", "lane1")
        receipts = tmp + "/receipts.jsonl"

        report = _cleanup(
            collection,
            [_authorize("run1", "lane1", authorized_by="ops-owner")],
            _Remover(primary),
            receipts,
            manifests={str(target): manifest},
        )
        receipt = report.receipts[0]

        assert receipt.authorized_by == "ops-owner"
        assert receipt.identity == WorkspaceIdentity(REPO, "run1", "lane1")
        assert receipt.path == str(target)
        assert receipt.outcome is CleanupOutcome.REMOVED

        # before/after state are explicit and distinguishable
        assert receipt.before["existence"] == "present"
        assert receipt.before["classification"] in {
            c.value for c in CLEANUP_ALLOWED_CLASSIFICATIONS
        }
        assert receipt.after["existence"] == "missing"

        # branch status + recoverability: the branch survives, so work is
        # recoverable from it.
        assert receipt.branch == "feat-a"
        assert receipt.branch_status == "preserved"
        assert receipt.branch_deleted is False
        assert receipt.recoverability is Recoverability.BRANCH_PRESERVED
        assert receipt.digest

        # the durable form round-trips the same facts
        durable = read_cleanup_receipts(receipts)[0]
        assert durable.to_dict() == receipt.to_dict()
        raw = json.loads(Path(receipts).read_text(encoding="utf-8").splitlines()[0])
        assert raw["identity"] == "repo/run1/lane1"
        assert raw["before"]["existence"] == "present"
        assert raw["after"]["existence"] == "missing"
        assert raw["branch_status"] == "preserved"
        assert raw["recoverability"] == "branch_preserved"
        assert raw["branch_deleted"] is False


# --------------------------------------------------------------------------- #
# 4. unsafe/unavailable evidence refuses; branch deletion never happens
# --------------------------------------------------------------------------- #
def test_unsafe_evidence_refuses_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, head = _collection(tmp)
        target = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        (target / "scratch.txt").write_text("uncommitted\n")
        remover = _Remover(primary)

        report = _cleanup(
            collection, [_authorize("run1", "lane1")], remover, manifests=None
        )

        assert report.receipts[0].outcome is CleanupOutcome.REFUSED
        assert target.exists()
        assert remover.calls == []


def test_healthy_worktree_is_not_removed():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, head = _collection(tmp)
        target = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        future = "2030-01-01T00:00:00+00:00"
        manifest = _expired_manifest(REPO, head, "feat-a", "run1", "lane1")
        manifest.lease = Lease(lease_until=future, owner="host")
        manifest.heartbeat = NOW

        report = _cleanup(
            collection,
            [_authorize("run1", "lane1")],
            _Remover(primary),
            manifests={str(target): manifest},
            processes={str(target): [os.getpid()]},
            now=NOW,
        )
        assert report.receipts[0].outcome is CleanupOutcome.REFUSED
        assert target.exists()


def test_cleanup_never_deletes_the_branch():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, head = _collection(tmp)
        target = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        manifest = _expired_manifest(REPO, head, "feat-a", "run1", "lane1")

        _cleanup(
            collection,
            [_authorize("run1", "lane1")],
            _Remover(primary),
            manifests={str(target): manifest},
        )

        assert not target.exists()
        # The branch is a separate, disabled-by-default concern: still present.
        assert _git(primary, "branch", "--list", "feat-a").stdout.strip()
        assert (
            _git(primary, "cat-file", "-t", head).stdout.strip() == "commit"
        )


def test_an_unregistered_directory_is_refused_not_deleted():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        stray = default_worktree_path(
            str(collection), repo=REPO, run="run1", lane="lane1"
        )
        stray.mkdir(parents=True)
        (stray / "loose.txt").write_text("not a workspace\n")

        report = _cleanup(collection, [_authorize("run1", "lane1")], _Remover(primary))
        assert report.receipts[0].outcome is CleanupOutcome.REFUSED
        assert report.receipts[0].reason == "not_a_workspace"
        assert stray.exists()


# --------------------------------------------------------------------------- #
# 5. only disposable fixture worktrees are ever selected
# --------------------------------------------------------------------------- #
def test_only_paths_under_the_fixture_root_are_touched():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        target = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        remover = _Remover(primary)

        _cleanup(collection, [_authorize("run1", "lane1")], remover)

        root = Path(tmp).resolve()
        assert remover.calls == [str(target)]
        for called in remover.calls:
            assert root in Path(called).resolve().parents


def test_a_real_current_worktree_is_never_selected():
    live_before = _live_worktrees()
    assert "worktree " in live_before

    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        remover = _Remover(primary)

        _cleanup(
            collection,
            [_authorize("run1", "lane1"), _authorize("other", "lane")],
            remover,
        )

        for called in remover.calls:
            assert str(_LIVE_REPO) not in called

    # The live repository's worktree registrations are byte-identical.
    assert _live_worktrees() == live_before


def test_current_worktree_is_refused_while_disposable_candidate_is_removed():
    """A genuinely-registered worktree the process *occupies* is refused.

    Both candidates here are clean, registered and manifest-less, so the
    inventory alone cannot tell them apart: the only thing that separates them
    is that ``run1/lane1`` is the process's current directory. The disposable
    neighbour must still be removed in the same pass, proving the refusal is
    targeted rather than a blanket stop.
    """
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _ = _collection(tmp)
        current = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        disposable = _add_worktree(primary, collection, "run2", "lane2", "feat-b")
        remover = _Remover(primary)

        previous = os.getcwd()
        os.chdir(current)
        try:
            report = _cleanup(
                collection,
                [_authorize("run1", "lane1"), _authorize("run2", "lane2")],
                remover,
            )
        finally:
            os.chdir(previous)

        outcomes = {r.identity.key: r.outcome for r in report.receipts}
        assert outcomes["repo/run1/lane1"] is CleanupOutcome.REFUSED
        assert report.receipts[0].reason == "current"
        assert outcomes["repo/run2/lane2"] is CleanupOutcome.REMOVED
        # The occupied worktree survives; only the disposable one is gone.
        assert current.exists()
        assert not disposable.exists()
        assert remover.calls == [str(disposable)]
