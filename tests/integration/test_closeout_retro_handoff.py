"""Closeout -> retrospective handoff integration tests (SW-157-CLOSE-003).

Step A: evidence-linked metrics, a durable retrospective sync, and a
deduplicated backlog handed to the planning lane.

Step B: prove narrative alone cannot close a finding.

The closeout lane is exercised through its real public shape —
:class:`~skillweave.closeout_service.CloseoutPreview` — but a *frozen* preview
is built here rather than running the exit door, so this integration test stays
deterministic and never mutates a workspace. The durable sync is exercised
against a real :class:`~skillweave.persistence.SkillWeavePersistence` on
``tmp_path`` plus the planning-sync backing store, so the ``retrospectives``
area really is carried to its configured destination.
"""

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from skillweave.closeout_retro import (  # noqa: E402
    STATUS_CLOSED,
    STATUS_OPEN,
    BacklogCandidate,
    CloseoutRetro,
    CloseoutRetroError,
    DuplicationKind,
    EvidenceLink,
    Finding,
    FindingDisposition,
    FindingSource,
    InMemoryRetroWriter,
    Metric,
    MetricKind,
    RetroWriter,
    verify_receipt,
)
from skillweave.closeout_service import EvidenceStatus  # noqa: E402
from skillweave.persistence import SkillWeavePersistence  # noqa: E402
from skillweave.post_release.iteration import (  # noqa: E402
    BacklogItem,
    dedupe_backlog,
    plan_iteration,
)
from skillweave.post_release.retrospective import (  # noqa: E402
    RETRO_AREA,
    RetroItem,
    create_retro_template,
    format_retro_report,
    sync_retrospective,
)
from skillweave.assessment_service import ReadOnlyViolation  # noqa: E402

SAMPLE_SHA = "96185265b489a8333af9745278916a8d5e46d5fa"


# --------------------------------------------------------------------------- #
# Frozen fixtures
# --------------------------------------------------------------------------- #


class _Row:
    """One closeout evidence row, read by attribute exactly like the real one."""

    def __init__(self, name: str, status: EvidenceStatus) -> None:
        self.name = name
        self.status = status


class _FrozenPreview:
    """A frozen stand-in with the public attribute shape of CloseoutPreview."""

    def __init__(self, *, digest: str, blockers: tuple, evidence: tuple) -> None:
        self.digest = digest
        self.blockers = blockers
        self.evidence = evidence


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _preview(*, digest: str | None = None) -> _FrozenPreview:
    return _FrozenPreview(
        digest=digest or _sha256("closeout-preview"),
        blockers=("missing security sign-off",),
        evidence=(
            _Row("tests", EvidenceStatus.PRESENT),
            _Row("coverage", EvidenceStatus.PRESENT),
            _Row("security-signoff", EvidenceStatus.MISSING),
            _Row("build", EvidenceStatus.MISMATCHED),
        ),
    )


def _retro() -> CloseoutRetro:
    return CloseoutRetro(run_id="SW-157-CLOSE-003", subject=SAMPLE_SHA, release="1.0.0")


# --------------------------------------------------------------------------- #
# Step A — evidence-linked metrics
# --------------------------------------------------------------------------- #


def test_every_metric_carries_at_least_one_evidence_link():
    """A number that cannot be traced is not a metric (Step A)."""
    retro = _retro()
    metrics = retro.metrics_from_closeout(_preview())

    assert metrics, "no metrics derived from the closeout preview"
    for metric in metrics:
        assert metric.evidence, f"{metric.kind} carries no evidence"
        for link in metric.evidence:
            assert len(link.digest) == 64, link.digest

    by_kind = {m.kind: m.value for m in metrics}
    assert by_kind[MetricKind.BLOCKER_COUNT] == 1
    assert by_kind[MetricKind.EVIDENCE_PRESENT] == 2
    assert by_kind[MetricKind.EVIDENCE_MISSING] == 1
    assert by_kind[MetricKind.EVIDENCE_MISMATCHED] == 1


def test_metric_without_evidence_is_refused():
    """The service refuses, at the seam, a metric nothing licenses."""
    retro = _retro()
    with pytest.raises(CloseoutRetroError, match="no evidence"):
        retro.record_metric(MetricKind.FINDING_COUNT, "SW-157", 3, [])

    with pytest.raises(CloseoutRetroError, match="no evidence"):
        Metric(
            kind=MetricKind.FINDING_COUNT,
            subject="SW-157",
            value=3,
            evidence=(),
        )


def test_metrics_link_back_to_the_closeout_digest_they_came_from():
    """The link addresses the preview, so a metric is checkable upstream."""
    retro = _retro()
    metrics = retro.metrics_from_closeout(_preview())
    preview_digest = _preview().digest

    for metric in metrics:
        assert preview_digest in metric.digests, metric.as_dict()
        assert metric.evidence[0].source == "closeout"


def test_preview_without_a_verifiable_digest_yields_no_metrics():
    """An unverifiable preview is refused rather than silently trusted."""
    retro = _retro()
    for bogus in ("", "not-a-digest", None, SAMPLE_SHA):
        with pytest.raises(CloseoutRetroError, match="no verifiable"):
            retro.metrics_from_closeout(_FrozenPreview(digest=bogus, blockers=(), evidence=()))


# --------------------------------------------------------------------------- #
# Step A — deduplicated backlog candidates
# --------------------------------------------------------------------------- #


def test_backlog_candidates_fold_exact_and_near_duplicates():
    """Same work, different words, is one candidate — and says what it merged."""
    retro = _retro()
    candidates = [
        BacklogCandidate(source="feedback", description="Fix login crash", urgency="high"),
        BacklogCandidate(source="feedback", description="fix  login   crash", urgency="high"),
        BacklogCandidate(source="retro", description="Fix login crashes", urgency="high"),
        BacklogCandidate(source="retro", description="Document the release runbook", urgency="low"),
    ]
    result = retro.backlog_candidates(candidates)

    unique = [c for c in result if not c.duplicate_of]
    dropped = [c for c in result if c.duplicate_of]
    assert len(unique) == 2, [c.as_dict() for c in result]
    assert len(dropped) == 2

    kinds = {c.duplication for c in dropped}
    assert DuplicationKind.EXACT.value in kinds
    assert DuplicationKind.FUZZY.value in kinds
    for c in dropped:
        assert c.duplicate_of in {u.key for u in unique}


def test_backlog_candidates_dedupe_against_an_existing_plan():
    """A fresh batch is deduplicated against an already-planned backlog."""
    retro = _retro()
    existing = [BacklogCandidate(source="retro", description="Fix login crash")]
    fresh = [BacklogCandidate(source="retro", description="Fix login crash")]

    result = retro.backlog_candidates(fresh, existing=existing)
    assert len(result) == 1
    assert result[0].duplicate_of == existing[0].key


def test_open_finding_becomes_a_candidate_but_a_closed_one_does_not():
    """Closing a finding means the next iteration does not re-raise it."""
    retro = _retro()
    preview = _preview()
    retro.metrics_from_closeout(preview)
    link = EvidenceLink(source="closeout", digest=preview.digest, kind="preview")

    retro.open_finding(Finding("f-open", FindingSource.RETRO, "flaky integration test"))
    retro.open_finding(Finding("f-closed", FindingSource.TELEMETRY, "restart storm"))
    retro.close_finding("f-closed", [link], narrative="fixed by restart guard")

    candidates = retro.candidates_from_findings()
    described = " ".join(c.description for c in candidates)
    assert "f-open" in described
    assert "f-closed" not in described


def test_iteration_plan_iteration_deduplicates_the_backlog():
    """plan_iteration (the planning lane's own entry point) folds duplicates."""
    from skillweave.post_release.feedback import FeedbackItem

    def feedback_item(title: str, description: str) -> FeedbackItem:
        return FeedbackItem(
            source="https://example.invalid/issues/1",
            title=title,
            category="bug",
            description=description,
            author="reporter",
            date="2026-01-01",
        )

    feedback = [
        feedback_item("Login", "App crashes on login"),
        feedback_item("Login", "App crashes on login"),
    ]
    retro_items = [
        RetroItem(category="action_item", description="App crashes on login", priority="P1")
    ]
    backlog = plan_iteration(feedback, retro_items)

    descriptions = [b.description for b in backlog]
    assert len(descriptions) == len(set(descriptions)), descriptions
    assert len(backlog) < 3, backlog

    # The low-level seam folds near-duplicates too, leaving the first standing.
    items = [
        BacklogItem(source="feedback", description="Document the release runbook"),
        BacklogItem(source="retro", description="Document the release runbook."),
    ]
    kept = dedupe_backlog(items)
    assert len(kept) == 1
    assert kept[0].description == "Document the release runbook"


# --------------------------------------------------------------------------- #
# Step A — durable retrospective sync
# --------------------------------------------------------------------------- #


def test_sync_retrospective_writes_the_document_the_planning_contract_carries(tmp_path):
    """A retrospective lands at .skillweave/retrospectives/vX.Y.Z.md."""
    persistence = SkillWeavePersistence(str(tmp_path))
    document = "# Retrospective 1.0.0\n\n## What went well\n- shipped on time\n"

    report = sync_retrospective(persistence, "1.0.0", document)

    written = Path(persistence.skillweave_dir) / RETRO_AREA / "v1.0.0.md"
    assert written.is_file()
    assert written.read_text() == document

    # Durability is reported, not assumed: the result names the area and its
    # at-risk state whichever adapter carried it.
    area = getattr(report, "area", None)
    if area is None and isinstance(report, dict):
        area = report.get("area")
    assert area == RETRO_AREA
    assert hasattr(report, "at_risk") or "at_risk" in report


def test_sync_retrospective_carries_the_area_to_the_planning_repo(tmp_path, monkeypatch):
    """The durable payload is carried to the configured planning repository."""
    # A non-git workspace so the planning-sync adapter is the one that resolves.
    persistence = SkillWeavePersistence(str(tmp_path))
    assert not (tmp_path / ".git").exists()

    planning_root = tmp_path / "planning-checkout"
    planning_root.mkdir()
    monkeypatch.setenv("SKILLWEAVE_PLANNING_REPOSITORY", "skillweave/skillweave-planning")
    monkeypatch.setenv("SKILLWEAVE_PLANNING_ROOT", str(planning_root))

    document = "# Retrospective 1.0.0\n\n## What went well\n- shipped on time\n"
    report = sync_retrospective(persistence, "1.0.0", document)

    assert report.at_risk is False
    assert list(report.names()) == ["v1.0.0.md"]
    carried = (
        planning_root / ".skillweave" / "planning" / RETRO_AREA / "v1.0.0.md"
    )
    assert carried.is_file()
    assert carried.read_text() == document


def test_sync_retrospective_refuses_a_persistence_without_a_root():
    with pytest.raises(ValueError, match="skillweave_dir"):
        sync_retrospective(object(), "1.0.0", "x")


def test_sync_retrospective_writes_durably_via_fsync_and_atomic_replace(tmp_path, monkeypatch):
    """The durable write is fsync-ed to a temp file and atomically renamed.

    A bare ``write_text`` leaves a torn file on crash and is not provably on
    disk. This pins the durable shape: contents go to a sibling temp file, are
    ``fsync``-ed, and are ``os.replace``-d into place — never truncating the
    destination in the open.
    """
    import os

    from skillweave.post_release import retrospective as mod

    real_replace = os.replace
    fsynced_fds: list[int] = []
    real_fsync = os.fsync
    replaced: list[tuple[str, str]] = []

    def spy_fsync(fd: int) -> None:
        fsynced_fds.append(fd)
        return real_fsync(fd)

    def spy_replace(src, dst) -> None:
        replaced.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(mod.os, "fsync", spy_fsync)
    monkeypatch.setattr(mod.os, "replace", spy_replace)

    persistence = SkillWeavePersistence(str(tmp_path))
    document = "# Retrospective 9.9.9\n\n- durable\n"
    sync_retrospective(persistence, "9.9.9", document)

    written = Path(persistence.skillweave_dir) / RETRO_AREA / "v9.9.9.md"
    assert written.is_file()
    assert written.read_text() == document

    # Contents were flushed to disk before the rename, and the rename was atomic.
    assert fsynced_fds, "the document was not fsync-ed before being made visible"
    assert len(replaced) == 1
    src, dst = replaced[0]
    assert dst == str(written)
    assert Path(src).parent == written.parent, "temp file is not a same-dir sibling"
    assert Path(src).suffix == ".tmp"

    # No temp residue is left behind on success.
    leftovers = [p.name for p in written.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == [], leftovers


def test_atomic_write_leaves_no_partial_document_when_the_write_fails(tmp_path):
    """A failed write never exposes a torn document and cleans up its temp file."""
    from skillweave.post_release.retrospective import atomic_write_text

    target = tmp_path / "retrospectives" / "v1.0.0.md"
    atomic_write_text(target, "complete")
    assert target.read_text() == "complete"

    class _Boom(Exception):
        pass

    class _ExplodingDocument(str):
        def encode(self, *args, **kwargs):  # noqa: D401 - sabotage the payload
            raise _Boom("disk full mid-write")

    with pytest.raises(_Boom):
        atomic_write_text(target, _ExplodingDocument("partial"))

    # The previous complete document is intact — no torn state became visible.
    assert target.read_text() == "complete"
    leftovers = [p.name for p in target.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == [], leftovers


def test_handoff_seals_receipt_writes_document_and_syncs_the_durable_area():
    """The whole Step A handoff, through an explicit writer."""
    retro = _retro()
    preview = _preview()
    retro.metrics_from_closeout(preview)
    link = EvidenceLink(source="closeout", digest=preview.digest)

    retro.open_finding(Finding("f-1", FindingSource.CLOSEOUT, "security sign-off missing"))
    retro.close_finding("f-1", [link], narrative="sign-off obtained post-freeze")

    writer = InMemoryRetroWriter()
    candidates = retro.backlog_candidates(
        [BacklogCandidate(source="retro", description="automate sign-off capture")]
    )
    receipt = retro.handoff(candidates=candidates, writer=writer)

    # A sealed, verifiable receipt.
    assert verify_receipt(receipt) is True
    assert receipt.digest == hashlib.sha256(
        __import__("json").dumps(
            receipt.payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

    # The document is bound to the receipt, and both were persisted.
    assert hashlib.sha256(receipt.document.encode("utf-8")).hexdigest() == receipt.document_digest
    assert writer.receipts["SW-157-CLOSE-003"].digest == receipt.digest
    assert "v1.0.0.md" in writer.documents

    # The durable area was carried to its backing store.
    assert writer.synced == [RETRO_AREA]


def test_tampered_receipt_fails_verification():
    """A receipt whose content moved no longer verifies (digest-sealed)."""
    retro = _retro()
    retro.metrics_from_closeout(_preview())
    receipt = retro.handoff(writer=InMemoryRetroWriter())
    assert verify_receipt(receipt) is True

    from dataclasses import replace

    tampered = replace(receipt, status=STATUS_CLOSED)
    assert verify_receipt(tampered) is False


def test_handoff_needs_an_explicit_writer():
    """There is no implicit global writer to persist through."""
    retro = _retro()
    retro.open_finding(Finding("f-1", FindingSource.RETRO, "no writer"))
    with pytest.raises(CloseoutRetroError, match="RetroWriter"):
        retro.handoff()


def test_read_only_authority_cannot_back_a_writer():
    """A read-only authority is refused at the writing seam."""

    class _Authority:
        read_only = True

    with pytest.raises(ReadOnlyViolation):
        RetroWriter("memory://", authority=_Authority())


# --------------------------------------------------------------------------- #
# Step B — narrative alone cannot close a finding
# --------------------------------------------------------------------------- #


def test_a_finding_opens_unresolved():
    retro = _retro()
    finding = retro.open_finding(
        Finding("f-1", FindingSource.CLOSEOUT, "evidence row missing")
    )
    assert finding in retro.open_findings
    assert retro.disposition("f-1").status == STATUS_OPEN
    assert retro.disposition("f-1").is_closed is False


def test_persuasive_narrative_alone_cannot_close_a_finding():
    """Step B: a confident story is not a resolution."""
    retro = _retro()
    retro.metrics_from_closeout(_preview())
    retro.open_finding(Finding("f-1", FindingSource.CLOSEOUT, "evidence row missing"))

    with pytest.raises(CloseoutRetroError, match="narrative alone"):
        retro.close_finding("f-1", [], narrative="confirmed fine by the release captain")

    # Still open — the narrative changed nothing.
    assert retro.disposition("f-1").status == STATUS_OPEN
    assert retro.disposition("f-1").is_closed is False
    assert [f.finding_id for f in retro.open_findings] == ["f-1"]


def test_closed_without_evidence_is_unrepresentable():
    """The shape 'closed, no evidence' cannot be constructed at all."""
    with pytest.raises(CloseoutRetroError, match="narrative alone"):
        FindingDisposition(finding_id="f-1", status=STATUS_CLOSED, narrative="it's fine")


def test_evidence_licenses_closure():
    """The positive pole: recorded evidence closes the finding."""
    retro = _retro()
    preview = _preview()
    retro.metrics_from_closeout(preview)
    retro.open_finding(Finding("f-1", FindingSource.CLOSEOUT, "evidence row missing"))
    link = EvidenceLink(source="closeout", digest=preview.digest)

    disposition = retro.close_finding("f-1", [link], narrative="re-ran sign-off")
    assert disposition.is_closed is True
    assert disposition.digests == (preview.digest,)
    assert retro.open_findings == ()


def test_closure_on_a_fabricated_digest_is_refused():
    """A plausible-looking citation this run never produced is not evidence."""
    retro = _retro()
    retro.metrics_from_closeout(_preview())
    retro.open_finding(Finding("f-1", FindingSource.CLOSEOUT, "evidence row missing"))

    fabricated = EvidenceLink(source="closeout", digest=_sha256("made-up"))
    with pytest.raises(CloseoutRetroError, match="unrecorded evidence"):
        retro.close_finding("f-1", [fabricated], narrative="trust the digest")

    assert retro.disposition("f-1").status == STATUS_OPEN


def test_a_non_canonical_digest_is_not_a_link():
    """An evidence link with a non-sha256 digest cannot be constructed."""
    for bogus in ("abc", SAMPLE_SHA, "", _sha256("x").upper()):
        with pytest.raises(CloseoutRetroError):
            EvidenceLink(source="closeout", digest=bogus)


def test_status_rolls_up_open_until_every_finding_is_resolved():
    """A retrospective with one open finding is OPEN, not CLOSED."""
    retro = _retro()
    preview = _preview()
    retro.metrics_from_closeout(preview)
    link = EvidenceLink(source="closeout", digest=preview.digest)
    retro.open_finding(Finding("f-1", FindingSource.CLOSEOUT, "a"))
    retro.open_finding(Finding("f-2", FindingSource.TELEMETRY, "b"))

    open_receipt = retro.handoff(writer=InMemoryRetroWriter())
    assert open_receipt.status == STATUS_OPEN

    retro.close_finding("f-1", [link])
    retro.close_finding("f-2", [link])
    closed_receipt = retro.handoff(writer=InMemoryRetroWriter())
    assert closed_receipt.status == STATUS_CLOSED


# --------------------------------------------------------------------------- #
# Step A — the existing post_release surface stays coherent
# --------------------------------------------------------------------------- #


def test_retro_document_renders_through_the_post_release_formatter():
    """The handoff document and the existing retro report share one lane."""
    retro = _retro()
    retro.metrics_from_closeout(_preview())
    receipt = retro.handoff(writer=InMemoryRetroWriter())

    report = format_retro_report(
        [
            RetroItem(category="went_well", description="closeout gate held"),
            RetroItem(category="action_item", description="capture sign-off", priority="P2"),
        ]
    )
    assert "# Retrospective" in receipt.document
    assert "## Action Items" in report
    assert create_retro_template("1.0.0")["sections"]["action_items"] == []
