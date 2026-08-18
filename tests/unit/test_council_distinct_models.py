"""A deliberation counts distinct answering models, not filled seats.

SW-CN-002 / dispatch 1 of 2. The premise is measured against a live Faigate:
three of four seats answer as ``deepseek-v4-flash`` (silent substitution, HTTP
200), so a "four-model" council is really two models. Swiping the answer back
into the record (SW-CN-001) now lets the engine count what actually answered
instead of how many seats were requested.

These tests prove two criteria:

1. ``min_models_required`` counts DISTINCT answering models. The four-seat
   configuration that collapses onto two models fails a minimum of three;
   against v1.3.5 (478211f) the identical run reported four and passed.

2. Stage 2 records when a ranking is self-review: a reviewer whose answering
   model also authored one of the ranked responses is marked ``self_ranked`` so
   a later reader can tell peer review from a model reranking itself.
"""

import asyncio

import pytest

from skillweave.council.engine import (
    CouncilConfig,
    CouncilDegradedError,
    CouncilEngine,
    ModelResponse,
)
from skillweave.routing.faigate_adapter import AttributedResponse


class _AttributingProvider:
    """Returns an ``AttributedResponse`` naming which model actually answered."""

    def __init__(self, answering, *, stage2_text=None, stage3_text=None):
        self.answering = dict(answering)      # requested -> answering model
        self.stage2_text = stage2_text
        self.stage3_text = stage3_text
        self.queries = []

    async def query(self, model, messages, temperature=0.5):
        self.queries.append(model)
        joined = " ".join(m.get("content", "") for m in messages)
        if "Rank these responses" in joined:
            content = self.stage2_text if self.stage2_text is not None else f"answer from {model}"
        elif "Chairman" in joined:
            content = self.stage3_text if self.stage3_text is not None else f"synthesis from {model}"
        else:
            content = f"answer from {model}"
        answering = self.answering.get(model, model)
        return AttributedResponse(content, requested_model=model, answering_model=answering)


def _run(coro):
    return asyncio.run(coro)


def test_min_models_required_counts_distinct_answering_models():
    """Four seats collapsing onto two models fail a minimum of three.

    RED PROOF (criterion 1): three seats answer as ``deepseek-v4-flash`` and one
    as ``deepseek-v4-pro``. Distinct count is two, so ``min_models_required=3``
    degrades; v1.3.5 counted requested seats and reported four.
    """
    provider = _AttributingProvider({
        "seat-a": "deepseek-v4-flash",
        "seat-b": "deepseek-v4-flash",
        "seat-c": "deepseek-v4-flash",
        "seat-d": "deepseek-v4-pro",
    })
    engine = CouncilEngine(provider)
    config = CouncilConfig(
        models=["seat-a", "seat-b", "seat-c", "seat-d"],
        chairman="seat-a",
        mode="standard",
        min_models_required=3,
    )
    with pytest.raises(CouncilDegradedError) as exc:
        _run(engine._stage1_opinions("q", config))
    assert "distinct" in str(exc.value)


def test_distinct_models_satisfy_threshold():
    """Every seat a distinct answering model passes the same minimum."""
    provider = _AttributingProvider({
        "seat-a": "model-1",
        "seat-b": "model-2",
        "seat-c": "model-3",
    })
    engine = CouncilEngine(provider)
    config = CouncilConfig(
        models=["seat-a", "seat-b", "seat-c"],
        chairman="seat-a",
        mode="standard",
        min_models_required=3,
    )
    responses = _run(engine._stage1_opinions("q", config))
    assert len(responses) == 3
    assert {r.answering_model for r in responses} == {"model-1", "model-2", "model-3"}


def test_stage1_carries_answering_model_per_seat():
    """Each ModelResponse names the model that answered, not the requested id."""
    provider = _AttributingProvider({"seat-a": "deepseek-v4-flash", "seat-b": "deepseek-v4-pro"})
    engine = CouncilEngine(provider)
    config = CouncilConfig(models=["seat-a", "seat-b"], chairman="seat-a", mode="standard")
    responses = _run(engine._stage1_opinions("q", config))
    by_id = {r.model_id: r.answering_model for r in responses}
    assert by_id["seat-a"] == "deepseek-v4-flash"
    assert by_id["seat-b"] == "deepseek-v4-pro"


_RANK_4 = "FINAL RANKING:\n1. Response A — best\n2. Response B — ok\n3. Response C — meh\n4. Response D — worst"
_RANK_2 = "FINAL RANKING:\n1. Response A — best\n2. Response B — ok"


def test_stage2_records_self_ranking_when_seats_collapse():
    """A reviewer who also authored a ranked response is marked self-ranked.

    Criterion 2: three seats answer as ``deepseek-v4-flash`` and the reviewers
    all answer as the same model, so every "peer review" is that single model
    ranking its own anonymised answers. That must be visible from the record.
    """
    provider = _AttributingProvider(
        {"seat-a": "deepseek-v4-flash", "seat-b": "deepseek-v4-flash",
         "seat-c": "deepseek-v4-flash", "seat-d": "deepseek-v4-flash"},
        stage2_text=_RANK_4,
    )
    engine = CouncilEngine(provider)
    responses = [
        ModelResponse(model_id="seat-a", response="A", elapsed_ms=1, answering_model="deepseek-v4-flash"),
        ModelResponse(model_id="seat-b", response="B", elapsed_ms=1, answering_model="deepseek-v4-flash"),
        ModelResponse(model_id="seat-c", response="C", elapsed_ms=1, answering_model="deepseek-v4-flash"),
        ModelResponse(model_id="seat-d", response="D", elapsed_ms=1, answering_model="deepseek-v4-pro"),
    ]
    config = CouncilConfig(
        models=["seat-a", "seat-b", "seat-c", "seat-d"],
        chairman="seat-a",
        mode="full",
    )
    rankings = _run(engine._stage2_review("q", responses, config))
    assert len(rankings) == 4
    assert all(r.self_ranked for r in rankings)
    assert all(r.reviewer_answering_model == "deepseek-v4-flash" for r in rankings)


def test_stage2_marks_genuine_peer_review_as_not_self_ranked():
    """A reviewer answering as a model that authored nothing is not self-rank."""
    provider = _AttributingProvider(
        {"seat-a": "deepseek-v4-pro", "seat-b": "deepseek-v4-pro"},
        stage2_text=_RANK_2,
    )
    engine = CouncilEngine(provider)
    responses = [
        ModelResponse(model_id="seat-a", response="A", elapsed_ms=1, answering_model="deepseek-v4-flash"),
        ModelResponse(model_id="seat-b", response="B", elapsed_ms=1, answering_model="deepseek-v4-flash"),
    ]
    config = CouncilConfig(models=["seat-a", "seat-b"], chairman="seat-a", mode="full")
    rankings = _run(engine._stage2_review("q", responses, config))
    assert len(rankings) == 2
    assert all(not r.self_ranked for r in rankings)
    assert all(r.reviewer_answering_model == "deepseek-v4-pro" for r in rankings)


def test_stage3_records_chairman_answering_model():
    """The chairman's own substitution is recorded (criterion 3).

    The synthesis is the output most likely to be quoted later, so it must carry
    which model actually wrote it. Requesting ``anthropic-claude`` that answers
    as ``deepseek-v4-flash`` must record the latter as the author.
    """
    provider = _AttributingProvider(
        {"anthropic-claude": "deepseek-v4-flash"},
        stage3_text="The council reached consensus.",
    )
    engine = CouncilEngine(provider)
    responses = [
        ModelResponse(model_id="seat-a", response="A", elapsed_ms=1),
    ]
    config = CouncilConfig(models=["seat-a"], chairman="anthropic-claude", mode="full")
    synthesis = _run(engine._stage3_synthesis("q", responses, [], "", config))
    assert synthesis.chairman_model == "anthropic-claude"
    assert synthesis.chairman_answering_model == "deepseek-v4-flash"
    assert synthesis.chairman_model != synthesis.chairman_answering_model


def test_stage3_chairman_answering_matches_requested_when_not_substituted():
    """When the chairman answers as itself, both ids agree."""
    provider = _AttributingProvider({}, stage3_text="consensus answer")
    engine = CouncilEngine(provider)
    responses = [ModelResponse(model_id="seat-a", response="A", elapsed_ms=1)]
    config = CouncilConfig(models=["seat-a"], chairman="chairman", mode="full")
    synthesis = _run(engine._stage3_synthesis("q", responses, [], "", config))
    assert synthesis.chairman_model == "chairman"
    assert synthesis.chairman_answering_model == "chairman"


def test_collapsed_council_marks_result_degraded():
    """A collapsed council says so in its result (criterion 4).

    RED PROOF: four seats that all answer as one model produce a completed
    result whose ``degraded`` flag is set and whose two counts — seats requested
    and models distinct — are both named. No log line, no exception: the info is
    on the ``CouncilResult`` a downstream consumer reads.
    """
    provider = _AttributingProvider(
        {"seat-a": "deepseek-v4-flash", "seat-b": "deepseek-v4-flash",
         "seat-c": "deepseek-v4-flash", "seat-d": "deepseek-v4-flash"},
        stage2_text=_RANK_4,
        stage3_text="synthesis",
    )
    engine = CouncilEngine(provider)
    config = CouncilConfig(
        models=["seat-a", "seat-b", "seat-c", "seat-d"],
        chairman="seat-a",
        mode="full",
        min_models_required=1,
    )
    result = _run(engine.deliberate("q", config))
    assert result.degraded is True
    assert result.seats_requested == 4
    assert result.models_distinct == 1


def test_uncollapsed_council_is_not_degraded():
    """Distinct answering models leave the result marked not degraded."""
    provider = _AttributingProvider(
        {"seat-a": "model-1", "seat-b": "model-2"},
        stage3_text="synthesis",
    )
    engine = CouncilEngine(provider)
    config = CouncilConfig(models=["seat-a", "seat-b"], chairman="seat-a", mode="standard")
    result = _run(engine.deliberate("q", config))
    assert result.degraded is False
    assert result.seats_requested == 2
    assert result.models_distinct == 2
