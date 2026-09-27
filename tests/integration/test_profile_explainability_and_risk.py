"""Integration tests for profile explainability and risk (SW-160-BREADTH-002).

Four acceptance criteria, each as positive and red-state fixtures:

1. Profile selection reports matched evidence, confidence and rejected
   alternatives.
   - ``select_profile`` returns a ``ProfileSelection`` carrying the winner's
     ``matched_evidence``, a ``confidence``, and every rejected candidate with
     the reason it lost.
2. Low-confidence selection asks bounded clarification questions or returns a
   typed hold.
   - A selection below ``SELECTION_CONFIDENCE_THRESHOLD`` never proceeds: it
     asks at most ``MAX_CLARIFICATION_QUESTIONS`` questions and returns a
     ``TypedHold``. An exact evidence tie is a hold too.
3. Human coupling is derived from the affected surface and reversibility, not a
   product or category label.
   - ``derive_human_coupling`` takes only surfaces; a ``research`` profile with
     reversible surfaces derives a *lower* coupling than a ``build`` profile
     with an irreversible one.
4. Every irreversible-surface fixture requires explicit human authority before
   mutation.
   - ``authorize_mutation`` refuses every irreversible surface unless a
     ``HumanApproval`` authorizes it, and the mutation side effect is never
     executed on refusal.

Hermetic: no network, no model, no subprocess. The profiles on disk are read
as data to prove the derivation is category-blind.
"""

import sys
from pathlib import Path

import pytest
import yaml

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime import (
    IRREVERSIBLE_SURFACES,
    REVERSIBILITY_BY_SURFACE,
    MAX_CLARIFICATION_QUESTIONS,
    SELECTION_CONFIDENCE_THRESHOLD,
    ClarificationQuestion,
    HumanApproval,
    ProfileCandidate,
    ProfileSelection,
    SelectionEvidence,
    TypedHold,
    assert_human_coupling_gate,
    authorize_mutation,
    derive_human_coupling,
    irreversible_surfaces_for,
    select_profile,
    surface_reversibility,
)

_REPO = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ev(signal: str, matched: bool, weight: float = 1.0, value: str = "") -> SelectionEvidence:
    return SelectionEvidence(
        signal=signal,
        value=value or signal,
        matched=matched,
        weight=weight,
    )


def _candidate(
    profile_id: str,
    category: str,
    matched: list[SelectionEvidence],
    unmatched: list[SelectionEvidence] | None = None,
    surfaces: list[str] | None = None,
) -> ProfileCandidate:
    return ProfileCandidate(
        profile_id=profile_id,
        category=category,
        change_surfaces=list(surfaces or []),
        matched=list(matched),
        unmatched=list(unmatched or []),
    )


def _profile_raw(filename: str) -> dict:
    return yaml.safe_load((_REPO / "profiles" / filename).read_text(encoding="utf-8"))


# ===================================================================
# Criterion 1: Selection reports matched evidence, confidence, rejected
# ===================================================================


class TestSelectionExplainability:
    """Profile selection reports matched evidence, confidence and rejections."""

    def test_high_confidence_selection_is_explainable(self):
        """A clear winner reports its evidence, confidence and rejected rivals."""
        winner = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("artifact:code-change", True, 3.0)],
            unmatched=[_ev("artifact:source-corpus", False, 1.0)],
        )
        loser = _candidate(
            "research-synthesis.v1",
            "research",
            matched=[],
            unmatched=[_ev("artifact:code-change", False, 1.0)],
        )

        selection = select_profile([winner, loser])

        assert isinstance(selection, ProfileSelection)
        assert selection.selected is True
        assert selection.profile_id == "software-delivery.v2"
        assert selection.confidence == pytest.approx(0.75)
        assert selection.hold is None
        assert selection.clarification_questions == []

    def test_matched_evidence_is_reported(self):
        """The winning selection reports each matched signal."""
        winner = _candidate(
            "software-delivery.v2",
            "build",
            matched=[
                _ev("artifact:code-change", True, 2.0),
                _ev("request:release", True, 2.0),
            ],
        )
        selection = select_profile([winner])

        signals = {e.signal for e in selection.matched_evidence}
        assert signals == {"artifact:code-change", "request:release"}
        assert all(e.matched for e in selection.matched_evidence)
        assert selection.confidence == pytest.approx(1.0)

    def test_rejected_alternatives_are_reported_with_reasons(self):
        """Every non-winning candidate is listed with why it lost."""
        winner = _candidate(
            "software-delivery.v2", "build", matched=[_ev("artifact:code-change", True, 3.0)]
        )
        runner_up = _candidate(
            "research-synthesis.v1", "research", matched=[_ev("artifact:code-change", True, 1.0)]
        )
        no_evidence = _candidate("learn.v1", "learn", matched=[])

        selection = select_profile([winner, runner_up, no_evidence])

        rejected_ids = [c.profile_id for c in selection.rejected]
        assert rejected_ids == ["research-synthesis.v1", "learn.v1"]
        assert "software-delivery.v2" not in rejected_ids
        for candidate in selection.rejected:
            assert candidate.rejection_reason(selection.profile_id)

    def test_confidence_is_matched_share_of_total_weight(self):
        """Confidence is the matched weight over the total weight."""
        candidate = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("m1", True, 3.0)],
            unmatched=[_ev("m2", False, 1.0)],
        )
        selection = select_profile([candidate])
        # 3.0 matched of 4.0 total -> 0.75, above the 0.70 threshold.
        assert selection.confidence == pytest.approx(0.75)

    def test_to_dict_is_machine_readable(self):
        """The selection round-trips to a plain dict for reporting."""
        winner = _candidate(
            "software-delivery.v2", "build", matched=[_ev("artifact:code-change", True, 3.0)]
        )
        loser = _candidate("research-synthesis.v1", "research", matched=[])
        payload = select_profile([winner, loser]).to_dict()

        assert payload["selected"] is True
        assert payload["profile_id"] == "software-delivery.v2"
        assert isinstance(payload["matched_evidence"], list)
        assert payload["matched_evidence"][0]["signal"] == "artifact:code-change"
        assert isinstance(payload["rejected"], list)
        assert payload["rejected"][0]["profile_id"] == "research-synthesis.v1"

    def test_selection_requires_a_candidate(self):
        """Selecting from an empty registry is a caller error."""
        with pytest.raises(ValueError):
            select_profile([])


# ===================================================================
# Criterion 2: Low confidence asks bounded questions or holds
# ===================================================================


class TestLowConfidenceHandling:
    """Low-confidence selection asks bounded questions or returns a typed hold."""

    def test_below_threshold_returns_typed_hold(self):
        """A selection under the threshold does not proceed and holds."""
        weak = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("artifact:code-change", True, 0.5)],
            unmatched=[_ev("artifact:source-corpus", False, 0.5)],
        )
        selection = select_profile([weak])

        assert selection.selected is False
        assert isinstance(selection.hold, TypedHold)
        assert selection.hold.is_hold is True
        assert selection.confidence < SELECTION_CONFIDENCE_THRESHOLD
        assert "threshold" in selection.hold.hold_reason

    def test_hold_reports_confidence_and_missing_evidence(self):
        """The hold names the confidence and the evidence that is missing."""
        weak = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("artifact:code-change", True, 0.5)],
            unmatched=[_ev("artifact:source-corpus", False, 0.5)],
        )
        hold = select_profile([weak]).hold

        assert hold is not None
        assert hold.confidence == pytest.approx(0.5)
        assert "artifact:source-corpus" in hold.missing_evidence

    def test_clarification_questions_are_bounded(self):
        """No selection can ask more than the hard question ceiling."""
        # Many shared signals across tied candidates: still bounded.
        shared = [_ev(f"signal-{i}", True, 1.0) for i in range(10)]
        a = _candidate("software-delivery.v2", "build", matched=list(shared))
        b = _candidate("research-synthesis.v1", "research", matched=list(shared))

        selection = select_profile([a, b])

        assert selection.selected is False
        assert selection.clarification_questions
        assert len(selection.clarification_questions) <= MAX_CLARIFICATION_QUESTIONS
        assert len(selection.clarification_questions) == MAX_CLARIFICATION_QUESTIONS
        for q in selection.clarification_questions:
            assert isinstance(q, ClarificationQuestion)
            assert q.question_id
            assert q.prompt

    def test_exact_tie_returns_hold_with_tied_profiles(self):
        """Two candidates with identical evidence cannot be separated."""
        a = _candidate("software-delivery.v2", "build", matched=[_ev("artifact:code-change", True, 2.0)])
        b = _candidate("research-synthesis.v1", "research", matched=[_ev("artifact:code-change", True, 2.0)])

        selection = select_profile([a, b])

        assert selection.selected is False
        assert selection.hold is not None
        assert set(selection.hold.tied_profiles) == {"software-delivery.v2", "research-synthesis.v1"}
        assert "ambiguous" in selection.hold.hold_reason

    def test_clarification_options_span_the_competing_profiles(self):
        """Each question offers the competing candidates as options."""
        a = _candidate("software-delivery.v2", "build", matched=[_ev("artifact:code-change", True, 2.0)])
        b = _candidate("research-synthesis.v1", "research", matched=[_ev("artifact:code-change", True, 2.0)])

        selection = select_profile([a, b])
        options = set(selection.clarification_questions[0].options)
        assert {"software-delivery.v2", "research-synthesis.v1"} <= options

    def test_no_evidence_at_all_holds_and_asks(self):
        """A registry that matches nothing holds rather than guessing."""
        a = _candidate("software-delivery.v2", "build", matched=[])
        b = _candidate("research-synthesis.v1", "research", matched=[])

        selection = select_profile([a, b])

        assert selection.selected is False
        assert selection.hold is not None
        assert selection.hold.questions
        assert len(selection.hold.questions) <= MAX_CLARIFICATION_QUESTIONS

    def test_hold_serializes_to_dict(self):
        """The hold round-trips to a plain dict."""
        weak = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("artifact:code-change", True, 0.5)],
            unmatched=[_ev("artifact:source-corpus", False, 0.5)],
        )
        payload = select_profile([weak]).to_dict()

        assert payload["selected"] is False
        assert payload["hold"]["kind"] == "TypedHold"
        assert payload["hold"]["confidence"] == pytest.approx(0.5)

    def test_threshold_is_configurable_but_still_gated(self):
        """Raising the threshold makes a formerly-accepted run hold."""
        candidate = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("artifact:code-change", True, 3.0)],
            unmatched=[_ev("artifact:source-corpus", False, 1.0)],
        )
        assert select_profile([candidate]).selected is True
        raised = select_profile([candidate], threshold=0.9)
        assert raised.selected is False
        assert raised.hold is not None

    def test_nan_weight_cannot_bypass_the_threshold(self):
        """Non-finite weights fail closed instead of producing nan confidence."""
        nan = float("nan")
        candidate = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("artifact:code-change", True, nan)],
            unmatched=[_ev("artifact:source-corpus", False, nan)],
        )
        import math

        selection = select_profile([candidate])
        assert math.isfinite(selection.confidence)
        assert selection.confidence <= SELECTION_CONFIDENCE_THRESHOLD
        assert selection.selected is False
        assert selection.hold is not None

    def test_negative_weight_cannot_forge_confidence(self):
        """A negative weight cannot push confidence above 1.0."""
        candidate = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("artifact:code-change", True, 5.0)],
            unmatched=[_ev("artifact:source-corpus", False, -5.0)],
        )
        selection = select_profile([candidate])
        assert selection.confidence <= 1.0

    def test_infinite_weight_does_not_disable_the_threshold(self):
        """An infinite weight cannot force confidence to a non-finite value."""
        import math

        candidate = _candidate(
            "software-delivery.v2",
            "build",
            matched=[_ev("artifact:code-change", True, float("inf"))],
        )
        selection = select_profile([candidate])
        assert math.isfinite(selection.confidence)
        assert selection.confidence <= 1.0


# ===================================================================
# Criterion 3: Coupling from surface + reversibility, not category
# ===================================================================


class TestSurfaceDerivedCoupling:
    """Human coupling derives from surface reversibility, never the label."""

    def test_reversible_surfaces_derive_supervised(self):
        """An all-reversible surface set needs only supervised coupling."""
        assert derive_human_coupling(["code", "configuration", "infrastructure", "documents"]) == "supervised"
        assert derive_human_coupling(["documents", "knowledge", "data"]) == "supervised"

    def test_irreversible_surface_derives_approval_required(self):
        """Any irreversible surface raises the requirement."""
        assert derive_human_coupling(["code", "legal"]) == "approval_required"
        assert derive_human_coupling(["public_channel"]) == "approval_required"
        assert derive_human_coupling(["documents", "finance"]) == "approval_required"

    def test_category_label_cannot_lower_the_requirement(self):
        """A 'research' surface set can demand more than a 'build' one.

        This is the inverse of the category intuition: research surfaces that
        are reversible derive *supervised*, while a build surface set that
        includes an irreversible surface derives *approval_required*. The
        derivation has no category argument to consult.
        """
        research_like = derive_human_coupling(["documents", "knowledge", "data"])
        build_like = derive_human_coupling(["code", "legal"])
        assert research_like == "supervised"
        assert build_like == "approval_required"
        assert research_like != build_like

    def test_derive_takes_no_category_argument(self):
        """The signature proves the derivation is category-blind."""
        import inspect

        params = inspect.signature(derive_human_coupling).parameters
        assert list(params) == ["change_surfaces"]

    def test_derivation_satisfies_the_coupling_gate(self):
        """Whatever coupling is derived passes the irreversible-surface gate."""
        for surfaces in (
            ["code", "configuration"],
            ["documents", "knowledge", "data", "external_system"],
            ["legal", "finance"],
            ["organization", "human", "public_channel"],
        ):
            derived = derive_human_coupling(surfaces)
            assert assert_human_coupling_gate(derived, surfaces) == []

    def test_unknown_surface_fails_closed(self):
        """An unrecognised surface is treated as irreversible."""
        assert surface_reversibility("quantum_ledger") == "irreversible"
        assert derive_human_coupling(["quantum_ledger"]) == "approval_required"

    def test_every_irreversible_surface_is_marked_irreversible(self):
        """The declared irreversible surfaces all map to irreversible."""
        for surface in IRREVERSIBLE_SURFACES:
            assert surface_reversibility(surface) == "irreversible"
            assert REVERSIBILITY_BY_SURFACE[surface] == "irreversible"

    def test_irreversible_surfaces_for_filters_surface_set(self):
        """Only irreversible surfaces survive the filter."""
        assert irreversible_surfaces_for(["code", "legal", "documents"]) == ["legal"]
        assert irreversible_surfaces_for(["code", "configuration"]) == []

    def test_software_delivery_profile_coupling_matches_derivation(self):
        """The build profile's declared coupling equals what its surfaces imply."""
        raw = _profile_raw("software-delivery.v2.yaml")
        surfaces = raw["changeSurfaces"]
        assert derive_human_coupling(surfaces) == raw["humanCoupling"]

    def test_research_profile_surfaces_still_gate_correctly(self):
        """The research profile's surfaces satisfy whatever coupling is derived."""
        raw = _profile_raw("research-synthesis.v1.yaml")
        surfaces = raw["changeSurfaces"]
        derived = derive_human_coupling(surfaces)
        assert assert_human_coupling_gate(derived, surfaces) == []


# ===================================================================
# Criterion 4: Irreversible fixtures require human authority
# ===================================================================


class TestIrreversibleMutationAuthority:
    """Every irreversible-surface fixture needs explicit authority to mutate."""

    def test_reversible_surface_needs_no_approval(self):
        """A reversible surface mutates without human authority."""
        result = authorize_mutation("ops", "code", mutation="write source")
        assert result["authorized"] is True
        assert result["irreversibility"] == "reversible"
        assert result["approval"] is None

    def test_irreversible_surface_refused_without_approval(self):
        """No approval means the mutation is refused."""
        result = authorize_mutation("ops", "legal", mutation="file a claim")
        assert result["authorized"] is False
        assert result["irreversibility"] == "irreversible"
        assert "human authority" in result["reason"]
        assert "no approval" in result["reason"]

    def test_rejected_decision_is_not_authority(self):
        """A rejected approval does not authorize the mutation."""
        approval = HumanApproval(
            actor="reviewer",
            timestamp="2026-01-01T00:00:00+00:00",
            scope="release",
            policy_digest="sha256:deadbeef",
            decision="rejected",
        )
        result = authorize_mutation("ops", "public_channel", approval, scope="release")
        assert result["authorized"] is False
        assert "'rejected'" in result["reason"]

    def test_approved_human_approval_authorizes(self):
        """An approved HumanApproval authorizes an irreversible mutation."""
        approval = HumanApproval(
            actor="release_authority",
            timestamp="2026-01-01T00:00:00+00:00",
            scope="release",
            policy_digest="sha256:deadbeef",
            decision="approved",
        )
        result = authorize_mutation("ops", "public_channel", approval, scope="release")
        assert result["authorized"] is True
        assert result["approval"] is not None
        assert result["approval"]["decision"] == "approved"
        assert "irreversible" in result["reason"]

    def test_scope_mismatch_is_refused(self):
        """Approval for one scope does not cover another."""
        approval = HumanApproval(
            actor="release_authority",
            timestamp="2026-01-01T00:00:00+00:00",
            scope="staging",
            policy_digest="sha256:deadbeef",
            decision="approved",
        )
        result = authorize_mutation("ops", "finance", approval, scope="production")
        assert result["authorized"] is False
        assert "does not cover" in result["reason"]

    def test_every_irreversible_fixture_requires_authority(self):
        """Every irreversible surface refuses mutation without human authority."""
        assert len(IRREVERSIBLE_SURFACES) == 5
        for surface in sorted(IRREVERSIBLE_SURFACES):
            result = authorize_mutation("ops", surface, mutation=f"mutate {surface}")
            assert result["authorized"] is False, f"{surface} must require authority"
            assert result["irreversibility"] == "irreversible"

    def test_no_mutation_runs_before_authority(self):
        """The mutation side effect never runs when authority is missing."""
        applied: list[str] = []

        def mutate(surface: str) -> None:
            applied.append(surface)

        for surface in sorted(IRREVERSIBLE_SURFACES):
            decision = authorize_mutation("ops", surface)
            if decision["authorized"]:
                mutate(surface)

        assert applied == [], "no irreversible surface may mutate without authority"

        approval = HumanApproval(
            actor="release_authority",
            timestamp="2026-01-01T00:00:00+00:00",
            scope="",
            policy_digest="sha256:deadbeef",
            decision="approved",
        )
        decision = authorize_mutation("ops", "human", approval)
        if decision["authorized"]:
            mutate("human")
        assert applied == ["human"]

    def test_actor_and_surface_are_required(self):
        """An empty actor or surface is a caller error, not a permission."""
        with pytest.raises(ValueError):
            authorize_mutation("", "legal")
        with pytest.raises(ValueError):
            authorize_mutation("ops", "")

    def test_approval_as_mapping_is_accepted(self):
        """Human authority may be presented as a plain mapping."""
        result = authorize_mutation(
            "ops",
            "finance",
            {"decision": "approved", "scope": "budget"},
            scope="budget",
        )
        assert result["authorized"] is True

    def test_result_serializes_to_dict(self):
        """The authorization decision is machine-readable."""
        result = authorize_mutation("ops", "organization")
        assert result["authorized"] is False
        assert result["surface"] == "organization"
        assert result["actor"] == "ops"
        assert result["mutation"] == "mutate"
        assert isinstance(result["reason"], str)
