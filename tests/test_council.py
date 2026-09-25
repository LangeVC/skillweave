"""Tests for skillweave council: engine, synthesis, search, prompts, profiles."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock


# ── Mock Provider ──────────────────────────────────────────────────
class MockProvider:
    """Mock provider that returns deterministic responses."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.queries = []

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        self.queries.append({"model": model, "messages": messages, "temperature": temperature})
        if model in self.responses:
            return self.responses[model]
        return f"Response from {model}: I think this is a good question."

    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        return {m: True for m in models}

    async def check_credits(self, model: str) -> float:
        return 100.0


# ── Engine Tests ────────────────────────────────────────────────────
class TestCouncilEngine:
    def test_engine_import(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig, CouncilResult
        c = CouncilConfig(models=["m1", "m2"], chairman="m3")
        assert c.models == ["m1", "m2"]
        assert c.mode == "full"

    def test_council_config_full_fields(self):
        from skillweave.council.engine import CouncilConfig
        c = CouncilConfig(
            models=["a", "b", "c"],
            chairman="a",
            mode="standard",
            temperature=0.7,
            output_format="json",
            timeout_per_model=15.0,
            total_timeout=90.0,
        )
        assert c.timeout_per_model == 15.0
        assert c.total_timeout == 90.0
        assert c.output_format == "json"
        assert c.temperature == 0.7

    def test_stage1_opinions_parallel(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["model-a", "model-b", "model-c"], chairman="model-c", mode="full")
        result = asyncio.run(engine._stage1_opinions("What is AI?", config))
        assert len(result) == 3
        assert all(r.response for r in result)
        assert len(provider.queries) == 3

    def test_stage1_with_failed_model(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig, ModelResponse
        provider = MockProvider()

        async def fail_one(model, messages, temp):
            if model == "model-b":
                raise RuntimeError("Model unavailable")
            return await MockProvider().query(model, messages, temp)

        provider.query = fail_one
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["model-a", "model-b", "model-c"], chairman="model-c", mode="full")
        result = asyncio.run(engine._stage1_opinions("Test", config))
        assert len(result) >= 2  # failed model skipped

    def test_stage1_opinions_with_search_context(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2"], chairman="m1", mode="full")
        result = asyncio.run(engine._stage1_opinions("Query", config, search_ctx="Some search results"))
        assert len(result) == 2

    def test_stage2_peer_review_anonymization(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig, ModelResponse
        provider = MockProvider({
            "model-a": "FINAL RANKING:\n1. Response A — best\n2. Response B — ok",
            "model-b": "FINAL RANKING:\n1. Response B — best\n2. Response A — ok",
        })
        engine = CouncilEngine(provider)
        responses = [
            ModelResponse(model_id="model-a", response="Answer A", elapsed_ms=100),
            ModelResponse(model_id="model-b", response="Answer B", elapsed_ms=100),
        ]
        config = CouncilConfig(models=["model-a", "model-b"], chairman="model-b", mode="standard")
        result = asyncio.run(engine._stage2_review("Test", responses, config))
        assert len(result) == 2
        assert all(r.rankings for r in result)

    def test_stage2_empty_with_single_response(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig, ModelResponse
        provider = MockProvider()
        engine = CouncilEngine(provider)
        responses = [ModelResponse(model_id="m1", response="Answer A", elapsed_ms=100)]
        config = CouncilConfig(models=["m1"], chairman="m1", mode="standard")
        result = asyncio.run(engine._stage2_review("Test", responses, config))
        assert result == []

    def test_stage3_chairman_synthesis(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig, ModelResponse
        provider = MockProvider({"chairman": "## Synthesis\nThe council agrees this is important."})
        engine = CouncilEngine(provider)
        responses = [
            ModelResponse(model_id="m1", response="Answer 1", elapsed_ms=100),
            ModelResponse(model_id="m2", response="Answer 2", elapsed_ms=100),
        ]
        rankings = []
        config = CouncilConfig(models=["m1", "m2"], chairman="chairman", mode="full")
        result = asyncio.run(engine._stage3_synthesis("Test", responses, rankings, "", config))
        assert result.format == "markdown"
        assert "Synthesis" in result.content

    def test_stage3_synthesis_failure_fallback(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig, ModelResponse

        async def fail_query(model, messages, temp):
            raise RuntimeError("Chairman down")

        provider = MockProvider()
        provider.query = fail_query
        engine = CouncilEngine(provider)
        responses = [ModelResponse(model_id="m1", response="Answer 1", elapsed_ms=100)]
        rankings = []
        config = CouncilConfig(models=["m1"], chairman="chairman", mode="full")
        result = asyncio.run(engine._stage3_synthesis("Test", responses, rankings, "", config))
        assert "Synthesis failed" in result.content
        assert result.format == "markdown"

    def test_full_deliberation_mode_quick(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2"], chairman="m1", mode="quick")
        result = asyncio.run(engine.deliberate("Test question", config))
        assert len(result.stage1) == 2
        assert result.stage2 == []
        assert result.stage3 is None

    def test_full_deliberation_mode_standard(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider({
            "m1": "FINAL RANKING:\n1. Response A — good\n2. Response B — ok",
            "m2": "FINAL RANKING:\n1. Response B — great\n2. Response A — fine",
        })
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2"], chairman="m1", mode="standard")
        result = asyncio.run(engine.deliberate("Test", config))
        assert len(result.stage1) == 2
        assert len(result.stage2) == 2
        assert result.stage3 is None

    def test_full_deliberation_mode_full(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider({
            "m1": "FINAL RANKING:\n1. Response A — insightful\n2. Response B — correct",
            "m2": "FINAL RANKING:\n1. Response B — clear\n2. Response A — verbose",
            "chairman": "**Final Answer**: The council determined...",
        })
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2"], chairman="chairman", mode="full")
        result = asyncio.run(engine.deliberate("Important question", config))
        assert len(result.stage1) == 2
        assert len(result.stage2) == 2
        assert result.stage3 is not None
        assert "Final Answer" in result.stage3.content

    def test_label_mapping(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["alpha", "beta", "gamma", "delta"], chairman="alpha", mode="full")
        result = asyncio.run(engine.deliberate("Test", config))
        assert result.label_to_model == {"A": "alpha", "B": "beta", "C": "gamma", "D": "delta"}

    def test_aggregate_rankings_computation(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig, Ranking
        provider = MockProvider()
        engine = CouncilEngine(provider)
        rankings = [
            Ranking(reviewer="m1", rankings={"A": 1, "B": 2, "C": 3}, raw_text=""),
            Ranking(reviewer="m2", rankings={"A": 2, "B": 1, "C": 3}, raw_text=""),
        ]
        agg = engine._compute_aggregate_rankings(rankings)
        assert agg["A"] == 1.5
        assert agg["B"] == 1.5
        assert agg["C"] == 3.0

    def test_build_label_map(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        engine = CouncilEngine(provider)
        label_map = engine._build_label_map(["x", "y", "z"])
        assert label_map == {"A": "x", "B": "y", "C": "z"}

    def test_build_label_map_dynamic(self):
        from skillweave.council.engine import CouncilEngine
        provider = MockProvider()
        engine = CouncilEngine(provider)
        long_models = [f"m{i}" for i in range(20)]
        label_map = engine._build_label_map(long_models)
        assert len(label_map) == 20
        assert label_map["A"] == "m0"
        assert label_map["I"] == "m8"
        assert label_map["T"] == "m19"

    def test_deliberate_with_searcher(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        searcher = MagicMock()
        searcher.search = AsyncMock(return_value="Search result context for query")
        engine = CouncilEngine(provider, searcher=searcher)
        config = CouncilConfig(models=["m1", "m2"], chairman="m1", mode="quick")
        result = asyncio.run(engine.deliberate("Test with search", config))
        assert result.search_context == "Search result context for query"
        searcher.search.assert_awaited_once()

    def test_deliberate_with_searcher_timeout(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        searcher = MagicMock()
        searcher.search = AsyncMock(side_effect=asyncio.TimeoutError())
        engine = CouncilEngine(provider, searcher=searcher)
        config = CouncilConfig(models=["m1"], chairman="m1", mode="quick", min_models_required=1)
        result = asyncio.run(engine.deliberate("Test", config))
        assert result.search_context == ""

    def test_model_response_error_field(self):
        from skillweave.council.engine import ModelResponse
        r = ModelResponse(model_id="m1", response="ok", elapsed_ms=50.0, error="timeout")
        assert r.error == "timeout"
        assert r.response == "ok"


# ── Synthesis Tests ─────────────────────────────────────────────────
class TestSynthesis:
    def test_validate_valid_json(self):
        from skillweave.council.synthesis import validate_output
        valid = json.dumps({
            "title": "Test Results",
            "summary": "The council analyzed the question and reached consensus.",
            "key_insights": ["Insight number one is quite important"],
            "consensus_score": 0.85,
        })
        ok, data, err = validate_output(valid)
        assert ok, f"Failed: {err}"
        assert data["consensus_score"] == 0.85

    def test_validate_invalid_json(self):
        from skillweave.council.synthesis import validate_output
        ok, data, err = validate_output("not json at all")
        assert not ok
        assert "Invalid JSON" in err

    def test_validate_missing_field(self):
        from skillweave.council.synthesis import validate_output
        ok, data, err = validate_output('{"title": "x"}')
        assert not ok

    def test_validate_wrong_types(self):
        from skillweave.council.synthesis import validate_output
        bad = json.dumps({
            "title": 123,
            "summary": "ok summary text here",
            "key_insights": "not an array",
            "consensus_score": "high",
        })
        ok, data, err = validate_output(bad)
        assert not ok
        assert "title must be a string" in err

    def test_validate_markdown_wrapper(self):
        from skillweave.council.synthesis import validate_output
        wrapped = '```json\n{\n  "title": "Test",\n  "summary": "A very good summary text here",\n  "key_insights": ["insight"],\n  "consensus_score": 0.5\n}\n```'
        ok, data, err = validate_output(wrapped)
        assert ok, f"Failed: {err}"
        assert data["title"] == "Test"

    def test_phase_contexts_exist(self):
        from skillweave.council.synthesis import PHASE_PROMPTS, get_phase_context
        assert "discovery" in PHASE_PROMPTS
        assert "design" in PHASE_PROMPTS
        assert "code_review" in PHASE_PROMPTS
        assert "post_release" in PHASE_PROMPTS
        assert get_phase_context("discovery") != ""
        assert get_phase_context(None) == ""

    def test_json_schema_markdown(self):
        from skillweave.council.synthesis import json_schema_to_markdown
        md = json_schema_to_markdown()
        assert "title" in md
        assert "summary" in md
        assert "|" in md  # table format

    def test_format_output_schema_instructions(self):
        from skillweave.council.synthesis import format_output_schema_instructions
        instr = format_output_schema_instructions()
        assert "OUTPUT FORMAT" in instr
        assert "consensus_score" in instr


# ── Prompts Tests ───────────────────────────────────────────────────
class TestPrompts:
    def test_stage1_prompt_basic(self):
        from skillweave.council.prompts import stage1_prompt
        p = stage1_prompt("What is AI?", "A", num_models=4)
        assert "What is AI?" in p
        assert "Response A" in p or "label is A" in p
        assert "AI Council" in p

    def test_stage1_with_phase(self):
        from skillweave.council.prompts import stage1_prompt
        p = stage1_prompt("Market analysis", "B", phase="discovery")
        assert "DISCOVERY" in p

    def test_stage1_with_search_context(self):
        from skillweave.council.prompts import stage1_prompt
        p = stage1_prompt("Query", "C", search_ctx="External data here")
        assert "External data here" in p

    def test_stage2_prompt_format(self):
        from skillweave.council.prompts import stage2_prompt
        p = stage2_prompt("Test", {"A": "Answer A", "B": "Answer B"}, ["A", "B"])
        assert "FINAL RANKING:" in p
        assert "Response A" in p
        assert "Response B" in p

    def test_stage2_prompt_with_phase(self):
        from skillweave.council.prompts import stage2_prompt
        p = stage2_prompt("Test", {"A": "Design answer"}, ["A"], phase="design")
        assert "DESIGN" in p

    def test_stage3_prompt_json_output(self):
        from skillweave.council.prompts import stage3_prompt
        p = stage3_prompt("Test", "responses...", "rankings...", output_format="json")
        assert "consensus_score" in p

    def test_stage3_prompt_default_markdown(self):
        from skillweave.council.prompts import stage3_prompt
        p = stage3_prompt("Test", "responses", "rankings")
        assert "Chairman" in p
        assert "consensus_score" not in p

    def test_compare_prompt(self):
        from skillweave.council.prompts import stage1_prompt_compare
        p = stage1_prompt_compare("Test", ["A", "B", "C"])
        assert "NOT reviewing" in p
        assert "A, B, C" in p

    def test_compare_prompt_with_phase(self):
        from skillweave.council.prompts import stage1_prompt_compare
        p = stage1_prompt_compare("Test", ["X", "Y"], phase="code_review")
        assert "CODE" in p

    def test_available_phases(self):
        from skillweave.council.prompts import phase_available_phases
        phases = phase_available_phases()
        assert "discovery" in phases
        assert "design" in phases
        assert len(phases) == 4


# ── Provider Detection + Profile Tests ──────────────────────────────
class TestProviderProfiles:
    def test_profiles_exist(self):
        from skillweave.council.faigate_adapter import list_profiles
        profiles = list_profiles()
        assert "default" in profiles
        assert "quick" in profiles
        assert "deep" in profiles
        assert "expert" in profiles

    def test_get_profile(self):
        from skillweave.council.faigate_adapter import get_profile
        default = get_profile("default")
        assert "models" in default
        assert "chairman" in default
        assert "mode" in default
        assert len(default["models"]) == 2

    def test_get_profile_copy(self):
        from skillweave.council.faigate_adapter import get_profile
        a = get_profile("quick")
        b = get_profile("quick")
        a["temperature"] = 0.999
        assert b["temperature"] != 0.999  # copies, not references

    def test_get_profile_unknown_falls_back_to_default(self):
        from skillweave.council.faigate_adapter import get_profile
        profile = get_profile("nonexistent")
        assert profile == get_profile("default")

    def test_list_profiles_order_consistent(self):
        from skillweave.council.faigate_adapter import list_profiles
        a = list_profiles()
        b = list_profiles()
        assert a == b

    def test_provider_name(self):
        from skillweave.council.faigate_adapter import FaigateProvider
        p = FaigateProvider()
        assert p.provider_name() == "faigate"

    def test_credits_check_failure(self):
        from skillweave.council.faigate_adapter import FaigateProvider
        p = FaigateProvider(base_url="https://nonexistent.example.com")
        result = asyncio.run(p.check_credits("sonnet"))
        assert result == -1.0  # fail gracefully


class TestSingleModelProvider:
    def test_is_single_model(self):
        from skillweave.council.faigate_adapter import SingleModelProvider
        p = SingleModelProvider(model="gpt-4o")
        assert p.is_single_model is True
        assert p.provider_name() == "single_model"

    def test_query_uses_own_model(self):
        import os
        from skillweave.council.faigate_adapter import SingleModelProvider
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("No OPENAI_API_KEY set")
        p = SingleModelProvider(model="gpt-4o")
        result = asyncio.run(p.query("gpt-3.5", [{"role":"user","content":"hello"}]))
        assert len(result) > 0


class TestProviderDetection:
    def test_detect_providers_returns_dict(self):
        from skillweave.council.faigate_adapter import detect_providers
        providers = detect_providers()
        assert isinstance(providers, dict)

    def test_get_best_provider_fallback(self, monkeypatch):
        from skillweave.council.faigate_adapter import get_best_provider, SingleModelProvider
        # Ensure no router env vars are set
        monkeypatch.delenv("FAIGATE_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("KILO_API_KEY", raising=False)
        monkeypatch.delenv("CLAWROUTER_API_KEY", raising=False)
        monkeypatch.delenv("LLMAI_API_KEY", raising=False)
        provider = get_best_provider()
        # Note: if ~/.config/faigate/tokens.json exists locally, Faigate will be detected
        # In CI with no ~/.config/faigate directory, this falls back to SingleModel
        allowed = (SingleModelProvider, type(provider))
        assert "single_model" in provider.provider_name() or provider.provider_name() == "faigate", \
            f"Expected single_model or faigate, got {provider.provider_name()}"

    def test_list_detected_providers(self):
        from skillweave.council.faigate_adapter import list_detected_providers
        providers = list_detected_providers()
        assert isinstance(providers, dict)


# ── Search Tests ────────────────────────────────────────────────────
class TestWebSearch:
    def test_config_defaults(self):
        from skillweave.council.search import SearchConfig, WebSearch
        s = WebSearch()
        c = s._apply_defaults(SearchConfig())
        assert c.provider == "duckduckgo"
        assert c.time_range == "any"

    def test_time_range_days(self):
        from skillweave.council.search import WebSearch
        assert WebSearch.TIME_RANGE_DAYS["30d"] == 30
        assert WebSearch.TIME_RANGE_DAYS["quarter"] == 90
        assert WebSearch.TIME_RANGE_DAYS["6mo"] == 180
        assert WebSearch.TIME_RANGE_DAYS["1yr"] == 365
        assert WebSearch.TIME_RANGE_DAYS["any"] is None

    def test_rerank_scores(self):
        from skillweave.council.search import WebSearch, SearchResult
        s = WebSearch()
        results = [
            SearchResult(title="AI Market Analysis 2026", url="https://example.com/report", snippet="AI market growing fast", source="web"),
            SearchResult(title="Unrelated topic", url="https://other.com/xyz", snippet="something else entirely", source="web"),
        ]
        ranked = s._rerank(results, "AI market analysis")
        assert ranked[0].title == "AI Market Analysis 2026"

    def test_format_context(self):
        from skillweave.council.search import WebSearch, SearchResult
        s = WebSearch()
        results = [
            SearchResult(title="Test Result", url="https://example.com", snippet="A test snippet", source="web"),
        ]
        ctx = s._format_context(results, "30d")
        assert "Test Result" in ctx
        assert "example.com" in ctx
        assert "30d" in ctx

    def test_rerank_url_authority_bonus(self):
        from skillweave.council.search import WebSearch, SearchResult
        s = WebSearch()
        results = [
            SearchResult(title="Some Blog Post", url="https://blog.example.com/ai", snippet="AI is trending everywhere", source="web"),
            SearchResult(title="Some Blog Post", url="https://wikipedia.org/wiki/AI", snippet="AI is trending everywhere", source="web"),
        ]
        ranked = s._rerank(results, "AI trends")
        assert ranked[0].url == "https://wikipedia.org/wiki/AI"  # authority bonus wins tie

    def test_search_config_fields(self):
        from skillweave.council.search import SearchConfig
        c = SearchConfig(
            provider="serper",
            time_range="quarter",
            max_results=5,
            full_content_results=2,
            hybrid_search=False,
            api_key="sk-test-key",
        )
        assert c.hybrid_search is False
        assert c.api_key == "sk-test-key"
        assert c.max_results == 5

    def test_filter_by_time_range_no_date_included(self):
        from skillweave.council.search import WebSearch, SearchResult
        s = WebSearch()
        results = [SearchResult(title="No date result", url="https://example.com", snippet="text", source="web")]
        filtered = s._filter_by_time_range(results, "30d")
        assert len(filtered) == 1  # no date → included


# ── Integration Test ────────────────────────────────────────────────
class TestCouncilIntegration:
    def test_end_to_end_mock(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider({
            "m1": "FINAL RANKING:\n1. Response A — best\n2. Response B — second",
            "m2": "FINAL RANKING:\n1. Response B — excellent\n2. Response A — great",
            "chairman": "# Council Verdict\nThe council unanimously agrees: Yes.",
        })
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2"], chairman="chairman", mode="full")
        result = asyncio.run(engine.deliberate("Should we build this feature?", config))

        assert len(result.stage1) == 2
        assert len(result.stage2) == 2
        assert result.stage3 is not None
        assert "Council" in result.stage3.content
        assert result.label_to_model

    def test_quick_mode_integration(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2", "m3"], chairman="m1", mode="quick")
        result = asyncio.run(engine.deliberate("Quick question", config))
        assert len(result.stage1) == 3
        assert result.stage2 == []
        assert result.stage3 is None
        assert result.total_elapsed_ms > 0

    def test_standard_mode_integration(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider({
            "m1": "FINAL RANKING:\n1. Response A — best\n2. Response B — ok",
            "m2": "FINAL RANKING:\n1. Response B — winner\n2. Response A — good",
        })
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2"], chairman="m1", mode="standard")
        result = asyncio.run(engine.deliberate("Standard question", config))
        assert len(result.stage1) == 2
        assert len(result.stage2) == 2
        assert result.stage3 is None
        assert result.aggregate_rankings


# ── JSON Output Integration ─────────────────────────────────────────
class TestJsonOutput:
    def test_synthesis_with_validation(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        from skillweave.council.synthesis import validate_output
        provider = MockProvider({
            "m1": "FINAL RANKING:\n1. Response A — clear\n2. Response B — good",
            "m2": "FINAL RANKING:\n1. Response B — detailed\n2. Response A — concise",
            "chairman": json.dumps({
                "title": "Council Analysis Results",
                "summary": "After deliberation, the council reached consensus on the key points.",
                "key_insights": ["The primary recommendation is well-supported by evidence"],
                "consensus_score": 0.9,
                "dissent": None,
                "sources": ["Expert analysis"],
            }),
        })
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2"], chairman="chairman", mode="full", output_format="json")
        result = asyncio.run(engine.deliberate("Should we pivot?", config))
        ok, data, err = validate_output(result.stage3.content)
        assert ok, f"Validation failed: {err}"
        assert data["consensus_score"] == 0.9
        assert len(data["key_insights"]) >= 1

    def test_json_output_with_dissent(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        from skillweave.council.synthesis import validate_output
        provider = MockProvider({
            "m1": "FINAL RANKING:\n1. Response A — good\n2. Response B — also good",
            "m2": "FINAL RANKING:\n1. Response B — solid\n2. Response A — decent",
            "chairman": json.dumps({
                "title": "Split Decision",
                "summary": "The council had differing opinions on this matter.",
                "key_insights": ["Point of agreement", "Point of disagreement"],
                "consensus_score": 0.4,
                "dissent": "Models disagree on implementation strategy",
                "sources": [],
            }),
        })
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["m1", "m2"], chairman="chairman", mode="full", output_format="json")
        result = asyncio.run(engine.deliberate("Complex question?", config))
        ok, data, err = validate_output(result.stage3.content)
        assert ok, f"Validation failed: {err}"
        assert data["consensus_score"] == 0.4
        assert data["dissent"] is not None


# ── SW1311-COUNCIL-001 — namespace, attribution and degradation ──────
import sys
from pathlib import Path

_srcpath = Path(__file__).resolve().parent.parent / "src"
if str(_srcpath) not in sys.path:
    sys.path.insert(0, str(_srcpath))


class AttributedProvider:
    """Mock provider that returns AttributedResponse envelopes for attribution tests."""

    def __init__(self, answering_map=None, provider_name="faigate", error=None):
        self.answering_map = answering_map or {}
        self.provider_name_v = provider_name
        self.error = error
        self.queries = []

    async def query(self, model, messages, temperature=0.5, timeout=None):
        self.queries.append(model)
        if self.error:
            raise self.error
        answering = self.answering_map.get(model, model)
        from skillweave.routing.faigate_adapter import AttributedResponse
        return AttributedResponse(
            f"answer from {answering}",
            requested_model=model,
            answering_model=answering,
            provider=self.provider_name_v,
        )

    def provider_name(self):
        return self.provider_name_v


class _MixedProvider:
    """Provider whose first queried seat errors, and the rest answer normally."""

    def __init__(self, error_first):
        self.error_first = error_first
        self._count = 0

    async def query(self, model, messages, temperature=0.5, timeout=None):
        self._count += 1
        if self._count == 1:
            raise self.error_first
        from skillweave.routing.faigate_adapter import AttributedResponse
        return AttributedResponse(
            f"answer from {model}",
            requested_model=model,
            answering_model=model,
            provider="faigate",
        )

    def provider_name(self):
        return "faigate"


class TestNamespaceTranslation:
    def test_bare_native_id_passes_through(self):
        from skillweave.routing.faigate_adapter import translate_model_id
        assert translate_model_id("deepseek-v4-pro") == "deepseek-v4-pro"

    def test_single_prefix_stripped_once(self):
        from skillweave.routing.faigate_adapter import translate_model_id
        assert translate_model_id("faigate/deepseek-v4-pro") == "deepseek-v4-pro"

    def test_double_prefix_raises_typed(self):
        from skillweave.routing.faigate_adapter import translate_model_id, ModelNamespaceError
        with pytest.raises(ModelNamespaceError):
            translate_model_id("faigate/faigate/deepseek-v4-pro")

    def test_foreign_prefix_raises_typed(self):
        from skillweave.routing.faigate_adapter import translate_model_id, ModelNamespaceError
        with pytest.raises(ModelNamespaceError):
            translate_model_id("openrouter/x")

    def test_empty_id_raises_typed(self):
        from skillweave.routing.faigate_adapter import translate_model_id, ModelNamespaceError
        with pytest.raises(ModelNamespaceError):
            translate_model_id("")

    def test_colon_prefix_is_translated_once_not_silently_mangled(self):
        # The legacy ``faigate:`` form is translated exactly once (never a blind
        # ``replace``), and a doubled colon prefix is refused.
        from skillweave.routing.faigate_adapter import translate_model_id, ModelNamespaceError
        assert translate_model_id("faigate:deepseek-v4-pro") == "deepseek-v4-pro"
        with pytest.raises(ModelNamespaceError):
            translate_model_id("faigate:faigate:deepseek-v4-pro")

    def test_foreign_prefix_raises_typed_colon(self):
        from skillweave.routing.faigate_adapter import translate_model_id, ModelNamespaceError
        with pytest.raises(ModelNamespaceError):
            translate_model_id("openrouter:m")


class TestProfileValidation:
    def test_provider_native_profiles_validate(self):
        from skillweave.routing.faigate_adapter import ROUTER_PROFILES, validate_council_model_ids
        for name, preset in ROUTER_PROFILES.items():
            validate_council_model_ids(
                models=preset["models"], chairman=preset["chairman"], source=name
            )

    def test_prefixed_council_profile_fails_before_call(self):
        from skillweave.routing.faigate_adapter import validate_council_model_ids, ModelNamespaceError
        with pytest.raises(ModelNamespaceError):
            validate_council_model_ids(
                models=["faigate/deepseek-v4-pro", "gpt-4o"],
                chairman="claude-opus-4",
                source="unit fixture",
            )

    def test_router_profiles_are_unprefixed(self):
        from skillweave.routing.faigate_adapter import ROUTER_PROFILES
        for preset in ROUTER_PROFILES.values():
            for mid in list(preset["models"]) + [preset["chairman"]]:
                assert "/" not in mid
                assert ":" not in mid


class TestAttributionPerSeat:
    def test_matching_roster_records_answered(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = AttributedProvider(answering_map={})
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["a", "b"], chairman="c", mode="quick")
        result = asyncio.run(engine.deliberate("q", config))
        assert result.stage1[0].status == "answered"
        assert result.stage1[0].requested_model == "a"
        assert result.stage1[0].answering_model == "a"
        assert result.stage1[0].provider == "faigate"
        assert result.stage1[0].profile_version

    def test_substituted_roster_records_substituted_not_inferred(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = AttributedProvider(answering_map={"a": "X", "b": "b"})
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["a", "b"], chairman="c", mode="quick")
        result = asyncio.run(engine.deliberate("q", config))
        first = result.stage1[0]
        assert first.status == "substituted"
        assert first.requested_model == "a"
        assert first.answering_model == "X"
        assert first.answering_model != first.requested_model  # never inferred from request

    def test_collapsed_roster_is_degraded_not_consensus(self):
        # Every seat answered by one model -> distinct set collapses below minimum.
        from skillweave.council.engine import CouncilEngine, CouncilConfig, CouncilDegradedError
        provider = AttributedProvider(answering_map={"a": "X", "b": "X", "c": "X"})
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["a", "b", "c"], chairman="c", mode="quick", min_models_required=2)
        with pytest.raises(CouncilDegradedError):
            asyncio.run(engine.deliberate("q", config))

    def test_below_minimum_is_degraded_never_consensus(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = AttributedProvider(answering_map={"a": "X", "b": "X"})
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["a", "b"], chairman="b", mode="quick", min_models_required=2)
        with pytest.raises(Exception):
            # distinct = {X}; below min=2 -> degraded path (never consensus)
            asyncio.run(engine.deliberate("q", config))

    def test_attribution_matrix_complete(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = AttributedProvider(answering_map={"a": "X"})
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["a", "b"], chairman="c", mode="quick")
        result = asyncio.run(engine.deliberate("q", config))
        matrix = result.attribution_matrix()
        assert len(matrix) == 2
        keys = set(matrix[0].keys())
        assert {"requested", "resolved", "answering", "status", "provider", "profile_version"} <= keys


class TestErrorClassification:
    def test_rate_limited_seat_status(self):
        from skillweave.routing.faigate_adapter import RateLimitedError
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = AttributedProvider(error=RateLimitedError("a"))
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["a", "healthy"], chairman="a", mode="quick", min_models_required=1)
        # only "a" matches the error mapping path? No — the provider errors for
        # every seat. Produce a mixed provider: error only on the first seat.
        mixed = _MixedProvider(error_first=RateLimitedError("a"))
        engine2 = CouncilEngine(mixed)
        result = asyncio.run(engine2.deliberate("q", config))
        assert result.stage1[0].status == "rate_limited"
        assert result.stage1[1].status == "answered"

    def test_unavailable_seat_status(self):
        from skillweave.routing.faigate_adapter import UnavailableModelError
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        mixed = _MixedProvider(error_first=UnavailableModelError("a"))
        engine = CouncilEngine(mixed)
        config = CouncilConfig(models=["a", "healthy"], chairman="a", mode="quick", min_models_required=1)
        result = asyncio.run(engine.deliberate("q", config))
        assert result.stage1[0].status == "unavailable"
        assert result.stage1[1].status == "answered"

    def test_all_unreachable_raises_degredated(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig, CouncilDegradedError
        provider = AttributedProvider(error=RuntimeError("connection refused"))
        engine = CouncilEngine(provider)
        config = CouncilConfig(models=["a", "b"], chairman="a", mode="quick", min_models_required=2)
        with pytest.raises(CouncilDegradedError):
            asyncio.run(engine.deliberate("q", config))
