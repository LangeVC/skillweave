"""Tests for skillweave council: engine, synthesis, search, prompts, profiles."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock


# ── Mock FaigniteProvider ──────────────────────────────────────────
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

    def test_build_label_map_overflow(self):
        from skillweave.council.engine import CouncilEngine, CouncilConfig
        provider = MockProvider()
        engine = CouncilEngine(provider)
        long_models = [f"m{i}" for i in range(20)]
        label_map = engine._build_label_map(long_models)
        assert len(label_map) == 8  # only A-H labels
        assert "I" not in label_map

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
        config = CouncilConfig(models=["m1"], chairman="m1", mode="quick")
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
        assert len(default["models"]) == 4

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
        from skillweave.council.faigate_adapter import FaigniteProvider
        p = FaigniteProvider()
        assert p.provider_name() == "faigate"

    def test_credits_check_failure(self):
        from skillweave.council.faigate_adapter import FaigniteProvider
        p = FaigniteProvider(base_url="https://nonexistent.example.com")
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

    def test_get_best_provider_fallback(self):
        from skillweave.council.faigate_adapter import get_best_provider, SingleModelProvider
        provider = get_best_provider()
        assert isinstance(provider, SingleModelProvider)  # no ENV set → fallback

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
