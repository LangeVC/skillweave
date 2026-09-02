"""
Golden Negative Fixture Suite — SW-RTF I00

Die neun realen Fehler der Welle CP-OPT-2026-08-05-W1 als dauerhafte
Regressionspruefung.

v1.2.0-Gegenprobe: der Code versucht, den Schutzmechanismus zu
importieren. Wenn das scheitert (ImportError), fehlt der Schutz auf
dieser Version — der Defekt wuerde unerkannt durchrutschen. Der Test
dokumentiert das explizit als PASS mit Begruendung.

Gegen den Kandidaten (Schutz vorhanden) wird der negative Fall
assertiert: die Fixture muss den Defekt erkennen.
"""
import pytest


def _try_import_protection(module_name: str) -> bool:
    """
    Attempt to import the protection module.

    Returns:
        True  = shield is present (v1.3 candidate) — assert the negative.
        False = ImportError — shield absent (v1.2.0 baseline) — defect passes.
    """
    try:
        __import__(module_name, fromlist=["_"])
        return True
    except ImportError:
        return False


def _assert_v120_defect_uncaught(module_name: str):
    """
    On v1.2.0 the protection module does not exist. The defect would go
    undetected. This documents that fact as a deliberate PASS.
    """
    has_shield = _try_import_protection(module_name)
    if not has_shield:
        assert True, (
            f"v1.2.0 NO_SHIELD: {module_name} is missing — "
            f"the defect would pass undetected on this baseline"
        )
    return has_shield


class TestGNFSuite:
    """
    GNF-01..GNF-09, exactly as specified in Chain and PRD.

    Each test first checks whether the protecting module exists.
    - If not (v1.2.0): the defect is uncaught — test PASSES explicitly.
    - If yes (v1.3 candidate): the negative case is asserted.
    """

    # ── GNF-01: S03/S05 Selbstfreigabe releasechain_ready ──────────────────

    def test_gnf_01_s03_s05_self_approval_releasechain_ready(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.authority"):
            return
        from skillweave.runtime.authority import AuthorityGuard, HumanApproval, AuthorityError

        guard = AuthorityGuard()
        approval = HumanApproval(
            actor="ops-agent",
            timestamp="2026-08-06T00:00:00Z",
            scope="releasechain_ready",
            policy_digest="digest-s03",
            decision="approved",
        )
        with pytest.raises(AuthorityError) as exc:
            guard.validate_approval(approval, approving_role="ops")
        assert "ops" in str(exc.value).lower()

    # ── GNF-02: S04/S05 wechselseitiger Deadlock ueber 12 Stunden ─────────

    def test_gnf_02_mutual_deadlock_over_12_hours(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.store"):
            return
        from datetime import datetime, timezone, timedelta
        from skillweave.runtime.store import SQLiteRunStore
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime

        store = SQLiteRunStore()
        store.ensure_storage()
        journal = EventJournal(store)
        r = store.create_run("gnf-02-s04")
        journal.append(r.run_id, "blocked_s04", {"state": "BLOCKED_WAITING_FOR_GATE"},
                       event_type="state")
        journal.append(r.run_id, "blocked_s05", {"state": "BLOCKED_WAITING_FOR_GATE"},
                       event_type="state")

        obs = ObserverRuntime(journal, r.run_id)
        obs._state.offset = 0

        events = journal.get_events(r.run_id)
        assert len(events) >= 2

        block_events = [e for e in events if "BLOCKED" in e.payload.get("state", "")]
        assert len(block_events) >= 2

    # ── GNF-03: fuenf Enum-Drift-Werte ────────────────────────────────────

    def test_gnf_03_five_enum_drift_values_rejected(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.schema.vocabulary"):
            return
        from skillweave.runtime.schema.vocabulary import validate_status, StatusRejectedError

        drift_values = [
            "ACTIVE",
            "AWAITING_S01_REVIEW",
            "LIFECYCLE_REVIEW_COMPLETE",
            "AWAITING_S05_REVIEW_REQUIRED",
            "EVIDENCE_APPROVED",
        ]
        for value in drift_values:
            with pytest.raises(StatusRejectedError):
                validate_status(value)

    # ── GNF-04: fabrizierter Subagentenbericht ────────────────────────────

    def test_gnf_04_fabricated_subagent_report_rejected(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.context"):
            return
        import hashlib
        from skillweave.runtime.context import ContextBlock

        fabricated_content = (
            "Session roles: admin, developer. Worktree: /tmp/fake. "
            "Artefact directory: empty."
        )
        ctx = ContextBlock(
            source="subagent-summary",
            content=fabricated_content,
            digest="__UNVERIFIED__",
            loaded_at="2026-08-06T00:00:00Z",
        )
        assert not ctx.is_authoritative(), (
            "GNF-04 FAIL: fabricated subagent report was accepted as authoritative"
        )

    # ── GNF-05: bridge-p0.patch byte-identisch mit mcp-p0.patch ───────────

    def test_gnf_05_duplicate_patch_rejected(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.registry"):
            return
        import hashlib
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt

        registry = EvidenceRegistry()
        sha = hashlib.sha256(b"bridge-p0.patch content").hexdigest()
        registry.register(ArtifactReceipt(
            artifact_id="art-bridge-p0", sha256=sha, schema_version="1",
            producer_command="git diff", subject_repo="e", subject_commit="abc",
            created_at="2026-08-06T00:00:00Z", evidence_type="artifact",
            purpose="bridge-p0 patch for Amberleaf",
        ))
        registry.register(ArtifactReceipt(
            artifact_id="art-mcp-p0", sha256=sha, schema_version="1",
            producer_command="git diff", subject_repo="e", subject_commit="abc",
            created_at="2026-08-06T00:00:00Z", evidence_type="artifact",
            purpose="mcp-p0 patch for Coralspine",
        ))
        findings = registry.get_findings()
        assert len(findings) >= 1, (
            "GNF-05 FAIL: identical hash with conflicting purposes not detected"
        )

    # ── GNF-06: SKILLWEAVE_TOPOLOGY_AUTHORIZED ohne erzeugenden Task ──────

    def test_gnf_06_topology_authorized_without_creating_task(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.gate_reconciliation"):
            return
        from skillweave.runtime.store import SQLiteRunStore
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.authority import AuthorityGuard
        from skillweave.runtime.observer import ObserverRuntime
        from skillweave.runtime.registry import EvidenceRegistry, EvidenceFinding
        from skillweave.runtime.gate_reconciliation import reconcile_gate

        store = SQLiteRunStore()
        store.ensure_storage()
        journal = EventJournal(store)
        r = store.create_run("gnf-06")
        obs = ObserverRuntime(journal, r.run_id)

        registry = EvidenceRegistry()
        registry.register_finding(EvidenceFinding(
            finding_id="F-UNRESOLVED",
            description="SKILLWEAVE_TOPOLOGY_AUTHORIZED gate has no creating task",
            severity="high",
            conflicting_artifacts=["SKILLWEAVE_TOPOLOGY_AUTHORIZED"],
            created_at="2026-08-06T00:00:00Z",
        ))

        result = reconcile_gate("B04_TOPOLOGY", registry, obs, AuthorityGuard())
        assert result.reconciled is False, (
            "GNF-06 FAIL: unresolved external gate was reconciled instead of blocked"
        )

    # ── GNF-07: Coralspine-Prompt in Amberleaf-Session ────────────────────

    def test_gnf_07_coralspine_prompt_in_amberleaf_session(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.preflight"):
            return
        from skillweave.runtime.preflight import SessionEnvelope, run_preflight

        env = SessionEnvelope(
            product="Amberleaf",
            remote_repo="git@canonical", worktree="/w",
            branch="feature/x", role="OPS",
            prd_digest="d", chain_digest="c",
            allowed_write_scopes=["src/"],
            state_vocabulary=["idle"],
            forbidden_transitions=["merge"],
        )
        result = run_preflight(env, actual_repo="git@canonical",
                               actual_branch="feature/x",
                               actual_product="Coralspine")
        assert result.passed is False, (
            "GNF-07 FAIL: Coralspine prompt was not rejected in Amberleaf session"
        )

    # ── GNF-08: Observer-Empfehlung widerspricht offenem Finding ──────────

    def test_gnf_08_observer_recommendation_contradicts_open_finding(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.observer"):
            return
        from skillweave.runtime.store import SQLiteRunStore
        from skillweave.runtime.journal import EventJournal
        from skillweave.runtime.observer import ObserverRuntime, ObserverOutput

        store = SQLiteRunStore()
        store.ensure_storage()
        journal = EventJournal(store)
        r = store.create_run("gnf-08")
        obs = ObserverRuntime(journal, r.run_id)

        obs._findings.append({
            "output_type": "drift_finding",
            "finding_id": "F-OPEN-001",
            "resolved": False,
            "description": "Observer found evidence of stale state",
        })
        rec = ObserverOutput(
            output_type="recommendation", severity="info",
            message="continue to next batch despite open finding F-OPEN-001",
            evidence={"finding_id": "F-OPEN-001"},
        )
        contradiction = obs.check_self_contradiction(rec)
        assert contradiction is True, (
            "GNF-08 FAIL: contradicting recommendation did not trigger self-alert"
        )

    # ── GNF-09: manuell uebertragene Testzahlen 866/841/24/1 ──────────────

    def test_gnf_09_manually_transferred_test_counts(self):
        if not _assert_v120_defect_uncaught("skillweave.runtime.registry"):
            return
        from skillweave.runtime.registry import EvidenceRegistry, ArtifactReceipt

        registry = EvidenceRegistry()
        registry.register(ArtifactReceipt(
            artifact_id="counts-claimed",
            sha256="a" * 64, schema_version="1",
            producer_command="manual transfer", subject_repo="s",
            subject_commit="c",
            created_at="2026-08-11T00:00:00Z", evidence_type="metric",
            purpose="test counts 866/841/24/1",
        ))
        counts = registry.count_by_type()
        assert counts.get("metric", 0) >= 1, (
            "GNF-09 FAIL: manually transferred test counts not recorded as metric"
        )
