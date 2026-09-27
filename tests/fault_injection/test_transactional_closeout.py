"""Transactional closeout under fault injection (SW-157-CLOSE-002).

Covers the acceptance surface of the *transactional* closeout that sits on top
of the existing workspace release policy and the cleanup ledger:

* the transaction persists plan/authority/mutation/receipt/compensation states
  and a resume never performs a duplicate removal — even when the process was
  killed *after* the removal landed on disk but *before* its outcome was
  recorded (the classic delete/record crash window);
* every deletion **and** every deliberate preservation appears in the receipt,
  including removals completed by an earlier, interrupted run;
* branch deletion remains separately disabled: it is never performed by this
  transaction and never claimed on its receipt;
* the transaction routes removal through the injected, shell-free policy seam
  and never through the provider path that deletes branches implicitly.

Faults are injected through the transaction's ``remove`` seam (a callable that
raises at a chosen point) and by abandoning the process mid-journal via direct
journal manipulation. All fixtures are disposable; the live repository is never
touched.
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

from skillweave.closeout_transaction import (  # noqa: E402
    STATUS_COMMITTED,
    STATUS_INCOMPLETE,
    CloseoutTransaction,
    ReceiptEntryKind,
    TransactionError,
    TransactionState,
    read_journal,
)
from skillweave.repo_health.worktrees import (  # noqa: E402
    CleanupAuthorization,
    WorkspaceIdentity,
)
from skillweave.routing.workspace import (  # noqa: E402
    Lease,
    WorkspaceEvidence,
    WorkspaceManifest,
    WorkspaceReleasePolicy,
    default_worktree_path,
)

_LIVE_REPO = Path(__file__).resolve().parent.parent.parent

REPO = "repo"
NOW = "2026-09-24T00:00:00+00:00"
PAST = "2020-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# git + disposable-fixture helpers (the fixtures use git; the transaction does
# not — it only ever calls the injected seam)
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
    collection = Path(tmp) / "collection"
    primary = collection / REPO
    head = _init_repo(primary)
    return collection, primary, head


def _add_worktree(primary, collection, run, lane, branch):
    path = default_worktree_path(str(collection), repo=REPO, run=run, lane=lane)
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(primary, "worktree", "add", "-q", "-b", branch, str(path))
    return path


def _clean_manifest(head, branch, run, lane):
    return WorkspaceManifest(
        repo=REPO,
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


def _authorize(run, lane, authorized_by="ops@sw157"):
    return CleanupAuthorization(
        repo=REPO, run=run, lane=lane, authorized_by=authorized_by
    )


class _FaultRemover:
    """A removal seam that records calls and can be told how to fail.

    ``fail_on`` names the 1-based call number that must raise *after* the
    removal has already landed on disk — the exact crash window between
    "mutation applied" and "outcome recorded".
    """

    def __init__(self, fail_on=None, fail_before_call=None):
        self.fail_on = fail_on
        self.fail_before_call = fail_before_call
        self.calls = []

    def __call__(self, identity):
        self.calls.append(identity.key)
        index = len(self.calls)
        if self.fail_before_call is not None and index == self.fail_before_call:
            # Crash *before* the mutation: nothing was removed.
            raise OSError("injected: crashed before removal")
        if self.fail_on is not None and index == self.fail_on:
            # Crash *after* the mutation: the removal landed, unrecorded.
            raise OSError("injected: crashed after removal")
        return True


def _policy(collection, manifests=None, *, evidence=None):
    """A policy over a disposable collection, with an injected clean-evidence
    probe. Removals still go through the transaction's own seam."""
    probe = evidence or (lambda manifest: WorkspaceEvidence(
        worktree="clean", lease="absent", process="inactive"
    ))
    return WorkspaceReleasePolicy(
        str(_collection_root(collection)),
        collection=str(_collection_root(collection)),
        evidence_probe=probe,
    )


def _collection_root(collection):
    return Path(collection)


def _transaction(collection, journal, *, manifests=None, remove=None, evidence=None):
    policy = _policy(collection, manifests, evidence=evidence)
    return CloseoutTransaction(
        policy,
        journal_path=str(journal),
        manifests=manifests,
        remove=remove,
    )


def _live_worktrees():
    return _git(_LIVE_REPO, "worktree", "list", "--porcelain").stdout


def _identity(run, lane):
    return WorkspaceIdentity(repo=REPO, run=run, lane=lane)


def _lost_tail(journal):
    """Simulate a lost journal tail: the file survives, its records do not.

    This is the at-worst damage a crash between two appends can leave: a
    journal that was clearly written (it is present) whose records can no
    longer be read back.
    """
    Path(journal).write_text("", encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1. happy path: one authorized removal, receipt complete
# --------------------------------------------------------------------------- #
def test_removes_authorized_workspace_and_receipts_it():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        manifest = _clean_manifest(head, "feat-a", "run1", "lane1")
        manifests = {str(path): manifest}

        journal = Path(tmp) / "journal.jsonl"

        # The seam removes the real disposable worktree, as the policy would.
        def remove(identity):
            _git(primary, "worktree", "remove", "--force", str(path))
            return not path.exists()

        tx = _transaction(collection, journal, manifests=manifests, remove=remove)
        receipt = tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])

        assert receipt.status == STATUS_COMMITTED
        assert [e.kind for e in receipt.entries] == [ReceiptEntryKind.REMOVED]
        assert receipt.removed()[0].identity == "repo/run1/lane1"
        assert not path.exists()
        # Branch survival is recorded, never claimed as deleted.
        assert receipt.entries[0].branch_deleted is False
        assert receipt.entries[0].branch_status == "preserved"


# --------------------------------------------------------------------------- #
# 2. the durable journal records the plan and the mutation, in order
# --------------------------------------------------------------------------- #
def test_journal_persists_plan_and_mutation_states():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _head = _collection(tmp)
        # A removal is gated on physical presence, so the workspace must really
        # exist for the mutation window to open at all.
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        journal = Path(tmp) / "journal.jsonl"

        def remove(identity):
            _git(primary, "worktree", "remove", "--force", str(path))
            return not path.exists()

        tx = _transaction(collection, journal, remove=remove)

        tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])

        states = [r.state for r in read_journal(str(journal))]
        assert states == [
            TransactionState.PLANNED.value,
            TransactionState.MUTATING.value,
            TransactionState.MUTATED.value,
        ]


# --------------------------------------------------------------------------- #
# 3. the crash window: killed after removal, before the outcome was recorded
# --------------------------------------------------------------------------- #
def test_interrupted_after_mutation_is_preserved_on_resume_not_repeated():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        journal = Path(tmp) / "journal.jsonl"

        # First attempt: the removal LANDS, then the process dies before the
        # MUTATED outcome can be journalled. The seam performs the real removal
        # and then raises: the attempt is recorded INTERRUPTED, never MUTATED,
        # so the outcome is durably *unknown* — the exact crash window a kill
        # between "removed on disk" and "recorded" would leave behind.
        removals = []

        def crashing_remove(identity):
            _git(primary, "worktree", "remove", "--force", str(path))
            removals.append(identity.key)
            raise OSError("injected: killed after removal, before MUTATED")

        tx = _transaction(collection, journal, remove=crashing_remove)
        tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])

        assert removals == ["repo/run1/lane1"]
        assert not path.exists()  # the removal really happened
        assert [r.state for r in read_journal(str(journal))] == [
            TransactionState.PLANNED.value,
            TransactionState.MUTATING.value,
            TransactionState.INTERRUPTED.value,
        ]

        # Resume: the attempt is unproven, so it is preserved — and the seam is
        # never called again, so the removal cannot happen twice.
        remover = _FaultRemover()
        resume_tx = _transaction(collection, journal, remove=remover)
        receipt = resume_tx.run(
            run_id="run-2", authorizations=[_authorize("run1", "lane1")]
        )

        assert remover.calls == []  # no duplicate removal
        assert receipt.resume is True
        assert receipt.status == STATUS_INCOMPLETE
        kinds = {e.identity: e.kind for e in receipt.entries}
        assert kinds == {"repo/run1/lane1": ReceiptEntryKind.INTERRUPTED}
        assert receipt.entries[0].reason == "interrupted_unproven"


# --------------------------------------------------------------------------- #
# 3b. the other side of the window: crashed *before* the mutation
# --------------------------------------------------------------------------- #
def test_interrupted_before_mutation_is_also_preserved_not_repeated():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        journal = Path(tmp) / "journal.jsonl"

        # The seam raises before doing anything. The removal may not have
        # landed, but the transaction cannot prove that — a raised remover is
        # unproven regardless of which side of the mutation it fell on.
        remover = _FaultRemover(fail_before_call=1)

        def remove(identity):
            return remover(identity)

        tx = _transaction(collection, journal, remove=remove)
        first = tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])
        assert [e.kind for e in first.entries] == [ReceiptEntryKind.INTERRUPTED]
        assert first.entries[0].reason == "interrupted_unproven"
        assert path.exists()  # nothing was removed, and nothing is claimed
        assert [r.state for r in read_journal(str(journal))] == [
            TransactionState.PLANNED.value,
            TransactionState.MUTATING.value,
            TransactionState.INTERRUPTED.value,
        ]

        # Resume: unproven, so it is preserved — the seam is never called again
        # and the removal can never be attempted twice.
        resume_remover = _FaultRemover()
        resume_tx = _transaction(collection, journal, remove=resume_remover)
        receipt = resume_tx.run(
            run_id="run-2", authorizations=[_authorize("run1", "lane1")]
        )
        assert resume_remover.calls == []
        assert receipt.status == STATUS_INCOMPLETE
        assert [e.kind for e in receipt.entries] == [ReceiptEntryKind.INTERRUPTED]


# --------------------------------------------------------------------------- #
# 4. resume over proof: a recorded removal is never repeated
# --------------------------------------------------------------------------- #
def test_resume_over_completed_removal_never_removes_twice():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _head = _collection(tmp)
        # A real workspace: the first run removes it physically, so the MUTATED
        # record corresponds to a removal that genuinely landed.
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        journal = Path(tmp) / "journal.jsonl"

        def remove(identity):
            _git(primary, "worktree", "remove", "--force", str(path))
            return not path.exists()

        tx = _transaction(collection, journal, remove=remove)
        first = tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])
        assert [e.kind for e in first.entries] == [ReceiptEntryKind.REMOVED]

        # A second process resumes the same journal: nothing is re-removed.
        second_remover = _FaultRemover()
        resume_tx = _transaction(collection, journal, remove=second_remover)
        second = resume_tx.run(
            run_id="run-2", authorizations=[_authorize("run1", "lane1")]
        )

        assert second_remover.calls == []
        assert second.resume is True
        # The receipt still accounts for the earlier removal.
        assert [e.kind for e in second.entries] == [ReceiptEntryKind.REMOVED]
        assert second.status == STATUS_COMMITTED


# --------------------------------------------------------------------------- #
# 4b. the lost-tail window (SW-157-REMEDY-B): a mutation whose record is gone
# --------------------------------------------------------------------------- #
def test_resume_over_lost_tail_does_not_repeat_the_removal():
    """The journal was written and then lost; the removal already landed.

    An empty-but-present journal is the signature of a lost tail: the file was
    created and appended, and its records are now unreadable. Nothing in the
    journal says whether the workspace was removed, but the workspace itself is
    gone — so the removal may be exactly what took it. The transaction must not
    run the mutation again: it preserves and reports instead.
    """
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        journal = Path(tmp) / "journal.jsonl"

        # The removal landed, then the journal tail was lost before its outcome
        # could be read back.
        _git(primary, "worktree", "remove", "--force", str(path))
        assert not path.exists()
        _lost_tail(journal)

        remover = _FaultRemover()
        tx = _transaction(collection, journal, remove=remover)
        receipt = tx.run(run_id="run-2", authorizations=[_authorize("run1", "lane1")])

        assert remover.calls == []  # the removal cannot happen twice
        assert receipt.status == STATUS_INCOMPLETE
        assert [e.kind for e in receipt.entries] == [ReceiptEntryKind.INTERRUPTED]
        assert receipt.entries[0].reason == "absent_unverified"
        assert receipt.entries[0].identity == "repo/run1/lane1"

        # The doubt is durable — the checkpoint. A second resume reads the
        # PRESERVED record and never reaches the mutation window again.
        again = _FaultRemover()
        tx2 = _transaction(collection, journal, remove=again)
        receipt2 = tx2.run(
            run_id="run-3", authorizations=[_authorize("run1", "lane1")]
        )
        assert again.calls == []
        assert [e.reason for e in receipt2.entries] == ["absent_unverified"]


def test_resume_over_missing_journal_does_not_repeat_the_removal():
    """No journal at all over an already-removed workspace: same guard.

    A journal that was never created (or was deleted) reads as empty, exactly
    like a lost tail. The physical absence is the only evidence available, and
    it is enough to withhold the mutation.
    """
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        journal = Path(tmp) / "journal.jsonl"

        _git(primary, "worktree", "remove", "--force", str(path))
        assert not journal.exists()

        remover = _FaultRemover()
        tx = _transaction(collection, journal, remove=remover)
        receipt = tx.run(run_id="run-2", authorizations=[_authorize("run1", "lane1")])

        assert remover.calls == []
        assert receipt.status == STATUS_INCOMPLETE
        assert [e.kind for e in receipt.entries] == [ReceiptEntryKind.INTERRUPTED]
        assert receipt.entries[0].reason == "absent_unverified"


def test_planned_only_tail_over_absent_workspace_is_preserved():
    """A bare PLANNED record is not a licence to re-run the mutation.

    The record proves only that the plan was written; the mutation may have
    landed before its outcome was recorded. With the workspace already gone,
    the safe answer is to preserve, never to remove again.
    """
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        journal = Path(tmp) / "journal.jsonl"

        tx = _transaction(collection, journal, remove=_FaultRemover())
        tx._persist(  # noqa: SLF001 - fault injection writes the journal directly
            _identity("run1", "lane1"),
            TransactionState.PLANNED,
            "authorized",
            str(path),
            "feat-a",
        )
        _git(primary, "worktree", "remove", "--force", str(path))
        assert not path.exists()

        remover = _FaultRemover()
        resume_tx = _transaction(collection, journal, remove=remover)
        receipt = resume_tx.run(
            run_id="run-2", authorizations=[_authorize("run1", "lane1")]
        )

        assert remover.calls == []
        assert receipt.status == STATUS_INCOMPLETE
        assert [e.kind for e in receipt.entries] == [ReceiptEntryKind.INTERRUPTED]
        assert receipt.entries[0].reason == "absent_unverified"


def test_absent_workspace_with_no_record_is_never_removed():
    """Absence is never a reason to call the remover on a resume.

    On a first run over an identity whose workspace does not exist, calling the
    remover could only ever be a no-op at best and a duplicate at worst. The
    transaction withholds it and records the doubt.
    """
    with tempfile.TemporaryDirectory() as tmp:
        collection, _primary, _head = _collection(tmp)
        journal = Path(tmp) / "journal.jsonl"

        remover = _FaultRemover()
        tx = _transaction(collection, journal, remove=remover)
        receipt = tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])

        assert remover.calls == []
        assert receipt.status == STATUS_INCOMPLETE
        assert [e.kind for e in receipt.entries] == [ReceiptEntryKind.INTERRUPTED]
        assert receipt.entries[0].reason == "absent_unverified"


def test_present_workspace_is_still_removed_exactly_once():
    """The presence gate must not block a workspace that is genuinely there.

    A lost tail over a present workspace is no reason to hold: presence is the
    proof that no removal landed, so the removal proceeds exactly once.
    """
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, _head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        journal = Path(tmp) / "journal.jsonl"

        _lost_tail(journal)  # journal present but empty
        assert path.exists()  # the workspace did not go anywhere

        calls = []

        def remove(identity):
            calls.append(identity.key)
            _git(primary, "worktree", "remove", "--force", str(path))
            return not path.exists()

        tx = _transaction(collection, journal, remove=remove)
        receipt = tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])

        assert calls == ["repo/run1/lane1"]
        assert not path.exists()
        assert [e.kind for e in receipt.entries] == [ReceiptEntryKind.REMOVED]
        assert receipt.status == STATUS_COMMITTED


# --------------------------------------------------------------------------- #
# 5. deliberate preservation is recorded with the policy's exact reason
# --------------------------------------------------------------------------- #
def test_held_removal_is_recorded_as_a_preservation():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        manifest = _clean_manifest(head, "feat-a", "run1", "lane1")
        manifests = {str(path): manifest}
        journal = Path(tmp) / "journal.jsonl"

        # Dirty evidence: the policy holds, and nothing is removed.
        dirty = lambda m: WorkspaceEvidence(
            worktree="dirty", lease="absent", process="inactive"
        )
        tx = _transaction(collection, journal, manifests=manifests, evidence=dirty)
        receipt = tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])

        assert [e.kind for e in receipt.entries] == [ReceiptEntryKind.HELD]
        assert receipt.entries[0].reason == "dirty"
        assert path.exists()  # deliberately preserved
        assert receipt.preserved()[0].identity == "repo/run1/lane1"


# --------------------------------------------------------------------------- #
# 6. branch deletion is separately disabled — never performed, never claimed
# --------------------------------------------------------------------------- #
def test_branch_is_never_deleted_or_claimed_deleted():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, head = _collection(tmp)
        path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        manifest = _clean_manifest(head, "feat-a", "run1", "lane1")
        manifests = {str(path): manifest}
        journal = Path(tmp) / "journal.jsonl"

        # A branch_deleter that would record any deletion attempt.
        deletions = []

        def branch_deleter(branch):
            deletions.append(branch)
            return True

        policy = WorkspaceReleasePolicy(
            str(collection),
            collection=str(collection),
            evidence_probe=lambda m: WorkspaceEvidence(
                worktree="clean", lease="absent", process="inactive"
            ),
            branch_deleter=branch_deleter,
        )
        tx = CloseoutTransaction(
            policy, journal_path=str(journal), manifests=manifests,
            remove=_FaultRemover(),
        )
        receipt = tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])

        assert deletions == []  # the transaction never routes to delete_branch
        assert all(e.branch_deleted is False for e in receipt.entries)
        assert all(e.branch_status == "preserved" for e in receipt.entries)
        # The branch genuinely still exists in the fixture repo.
        branches = _git(primary, "branch", "--list", "feat-a").stdout
        assert "feat-a" in branches

        # The receipt structurally refuses any claim of a deleted branch.
        try:
            ReceiptEntry = type(receipt.entries[0])
            ReceiptEntry(
                kind=ReceiptEntryKind.REMOVED,
                identity="repo/run1/lane1",
                path=str(path),
                branch="feat-a",
                reason="removed",
                branch_deleted=True,
            )
        except TransactionError:
            pass
        else:
            raise AssertionError("receipt accepted a deleted-branch claim")


# --------------------------------------------------------------------------- #
# 7. the receipt is deterministic and complete for a mixed batch
# --------------------------------------------------------------------------- #
def test_receipt_covers_every_deletion_and_preservation_deterministically():
    with tempfile.TemporaryDirectory() as tmp:
        collection, primary, head = _collection(tmp)
        run1_path = _add_worktree(primary, collection, "run1", "lane1", "feat-a")
        run2_path = _add_worktree(primary, collection, "run2", "lane2", "feat-b")
        # run1 will be removed; run2's evidence is unknown, so it is held.
        manifests = {
            str(run1_path): _clean_manifest(head, "feat-a", "run1", "lane1"),
            str(run2_path): _clean_manifest(head, "feat-b", "run2", "lane2"),
        }

        journal = Path(tmp) / "journal.jsonl"

        def evidence(manifest):
            if manifest.run == "run2":
                return WorkspaceEvidence()  # all unknown -> hold
            return WorkspaceEvidence(worktree="clean", lease="absent", process="inactive")

        # The removal seam removes the real disposable worktree for run1 only.
        def remove(identity):
            if identity.run != "run1":
                return False
            _git(primary, "worktree", "remove", "--force", str(run1_path))
            return not run1_path.exists()

        tx = _transaction(collection, journal, manifests=manifests, remove=remove)
        receipt = tx.run(
            run_id="run-1",
            authorizations=[_authorize("run1", "lane1"), _authorize("run2", "lane2")],
        )

        kinds = {e.identity: e.kind for e in receipt.entries}
        assert kinds == {
            "repo/run1/lane1": ReceiptEntryKind.REMOVED,
            "repo/run2/lane2": ReceiptEntryKind.HELD,
        }
        # Deterministic: the account rebuilt from the same journal is identical
        # entry for entry. Only ``resume`` differs — the first pass began from
        # an empty journal, the second resumed one — and it is digested, so it
        # is asserted explicitly rather than folded into a digest comparison.
        tx2 = _transaction(collection, journal, manifests=manifests, evidence=evidence)
        receipt2 = tx2.run(
            run_id="run-1",
            authorizations=[_authorize("run1", "lane1"), _authorize("run2", "lane2")],
        )
        assert [e.to_dict() for e in receipt2.entries] == [
            e.to_dict() for e in receipt.entries
        ]
        assert receipt.resume is False and receipt2.resume is True
        # Same entries, same journal digest: the account is byte-stable.
        assert receipt2.journal_digest == receipt.journal_digest


# --------------------------------------------------------------------------- #
# 8. the live repository is never touched
# --------------------------------------------------------------------------- #
def test_live_repository_worktrees_are_untouched():
    before = _live_worktrees()
    with tempfile.TemporaryDirectory() as tmp:
        collection, _primary, _head = _collection(tmp)
        journal = Path(tmp) / "journal.jsonl"
        tx = _transaction(collection, journal, remove=_FaultRemover())
        tx.run(run_id="run-1", authorizations=[_authorize("run1", "lane1")])
    assert _live_worktrees() == before
