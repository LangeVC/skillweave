"""CouncilEngine — 3-stage LLM deliberation orchestrator.

Stage 1: All models answer independently in parallel (asyncio.gather)
Stage 2: Anonymized peer review — each model ranks all responses  
Stage 3: Chairman synthesizes final answer from all data
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelResponse:
    model_id: str
    response: str
    elapsed_ms: float
    error: str | None = None


@dataclass
class Ranking:
    reviewer: str          # model that did the review
    rankings: dict[str, int]  # response_label → rank (1=best)
    raw_text: str


@dataclass
class SynthesisResult:
    chairman_model: str
    content: str            # markdown or JSON
    format: str             # "markdown" or "json"
    elapsed_ms: float


@dataclass 
class CouncilResult:
    query: str
    stage1: list[ModelResponse] = field(default_factory=list)
    stage2: list[Ranking] = field(default_factory=list)
    stage3: SynthesisResult | None = None
    search_context: str = ""
    aggregate_rankings: dict[str, float] = field(default_factory=dict)  # label → avg rank
    label_to_model: dict[str, str] = field(default_factory=dict)  # label → model_id
    total_elapsed_ms: float = 0.0


@dataclass
class CouncilConfig:
    models: list[str]          # model IDs
    chairman: str              # chairman model ID
    mode: str = "full"         # "quick" | "standard" | "full"
    temperature: float = 0.5
    output_format: str = "markdown"  # "markdown" | "json"
    timeout_per_model: float = 30.0
    total_timeout: float = 120.0


class CouncilEngine:
    """Orchestrates the 3-stage LLM Council deliberation."""

    def __init__(self, provider, searcher=None):
        """
        Args:
            provider: ModelProvider implementation (e.g. FaigniteProvider)
            searcher: Optional WebSearch instance for Stage 0
        """
        self.provider = provider
        self.searcher = searcher

    async def deliberate(self, query: str, config: CouncilConfig) -> CouncilResult:
        """Run full council deliberation. Mode controls which stages execute."""
        start = time.monotonic()
        result = CouncilResult(query=query)

        # Stage 0: Web Search (optional)
        if self.searcher:
            try:
                result.search_context = await asyncio.wait_for(
                    self.searcher.search(query),
                    timeout=15.0
                )
            except Exception:
                result.search_context = ""

        # Stage 1: First Opinions (all models in parallel)
        if config.mode in ("quick", "standard", "full"):
            result.stage1 = await self._stage1_opinions(query, config, result.search_context)
            result.label_to_model = self._build_label_map(config.models)

        # Stage 2: Peer Review (anonymized)
        if config.mode in ("standard", "full") and len(result.stage1) >= 2:
            result.stage2 = await self._stage2_review(query, result.stage1, config, result.search_context)
            result.aggregate_rankings = self._compute_aggregate_rankings(result.stage2)

        # Stage 3: Chairman Synthesis
        if config.mode == "full" and result.stage1:
            result.stage3 = await self._stage3_synthesis(
                query, result.stage1, result.stage2, result.search_context, config
            )

        result.total_elapsed_ms = (time.monotonic() - start) * 1000
        return result

    async def _stage1_opinions(self, query: str, config: CouncilConfig, search_ctx: str = "") -> list[ModelResponse]:
        """Run all models in parallel via asyncio.gather. Failed models gracefully skipped."""
        LABELS = "ABCDEFGH"
        
        async def query_one(model_id: str) -> ModelResponse:
            t0 = time.monotonic()
            try:
                label = LABELS[config.models.index(model_id)] if model_id in config.models else "?"
                prompt = _stage1_prompt(query, label, search_ctx, len(config.models))
                messages = [{"role": "user", "content": prompt}]
                response = await asyncio.wait_for(
                    self.provider.query(model_id, messages, config.temperature),
                    timeout=config.timeout_per_model
                )
                return ModelResponse(
                    model_id=model_id,
                    response=response,
                    elapsed_ms=(time.monotonic() - t0) * 1000
                )
            except Exception as e:
                return ModelResponse(
                    model_id=model_id,
                    response="",
                    elapsed_ms=(time.monotonic() - t0) * 1000,
                    error=str(e)
                )

        tasks = [query_one(m) for m in config.models]
        responses = await asyncio.gather(*tasks, return_exceptions=False)
        return [r for r in responses if not r.error or r.response]  # keep partial successes

    async def _stage2_review(self, query: str, responses: list[ModelResponse], config: CouncilConfig, search_ctx: str = "") -> list[Ranking]:
        """Each model reviews all responses (anonymized)."""
        LABELS = "ABCDEFGH"
        anonymized = {}
        label_map = {}
        labels_used = []
        for i, r in enumerate(responses):
            if r.response and not r.error:
                label = LABELS[i]
                anonymized[label] = r.response
                label_map[label] = r.model_id
                labels_used.append(label)

        if len(labels_used) < 2:
            return []

        async def review_one(model_id: str) -> Ranking:
            t0 = time.monotonic()
            try:
                prompt = _stage2_prompt(query, anonymized, labels_used, search_ctx)
                messages = [{"role": "user", "content": prompt}]
                raw = await asyncio.wait_for(
                    self.provider.query(model_id, messages, 0.3),
                    timeout=config.timeout_per_model
                )
                rankings = _parse_rankings(raw, labels_used)
                return Ranking(reviewer=model_id, rankings=rankings, raw_text=raw)
            except Exception as e:
                return Ranking(reviewer=model_id, rankings={}, raw_text=f"ERROR: {e}")

        tasks = [review_one(m) for m in config.models]
        rankings = await asyncio.gather(*tasks)
        return [r for r in rankings if r.rankings]

    async def _stage3_synthesis(self, query: str, stage1: list[ModelResponse], stage2: list[Ranking], search_ctx: str, config: CouncilConfig) -> SynthesisResult:
        """Chairman synthesizes final answer."""
        t0 = time.monotonic()
        
        # Build context: all responses + rankings + search
        responses_text = ""
        LABELS = "ABCDEFGH"
        for i, r in enumerate(stage1):
            if r.response and not r.error:
                responses_text += f"\n### Response {LABELS[i]} (from model {LABELS[i]})\n{r.response}\n"

        rankings_text = ""
        for rank in stage2:
            rankings_text += f"\nReviewer rankings: {json.dumps(rank.rankings)}"

        prompt = _stage3_prompt(query, responses_text, rankings_text, search_ctx, config.output_format)
        messages = [{"role": "user", "content": prompt}]
        
        try:
            content = await asyncio.wait_for(
                self.provider.query(config.chairman, messages, 0.4),
                timeout=config.timeout_per_model * 2
            )
            return SynthesisResult(
                chairman_model=config.chairman,
                content=content,
                format=config.output_format,
                elapsed_ms=(time.monotonic() - t0) * 1000
            )
        except Exception as e:
            return SynthesisResult(
                chairman_model=config.chairman,
                content=f"Synthesis failed: {e}",
                format="markdown",
                elapsed_ms=(time.monotonic() - t0) * 1000
            )

    def _build_label_map(self, models: list[str]) -> dict[str, str]:
        LABELS = "ABCDEFGH"
        return {LABELS[i]: m for i, m in enumerate(models) if i < len(LABELS)}

    def _compute_aggregate_rankings(self, rankings: list[Ranking]) -> dict[str, float]:
        """Average rank across all peer evaluations. Lower = better."""
        totals = {}
        counts = {}
        for r in rankings:
            for label, rank in r.rankings.items():
                totals[label] = totals.get(label, 0) + rank
                counts[label] = counts.get(label, 0) + 1
        return {label: totals[label] / counts[label] for label in totals}


def _stage1_prompt(query: str, label: str, search_ctx: str, num_models: int) -> str:
    """Prompt for Stage 1: independent deliberation."""
    ctx = f"\n\nSEARCH CONTEXT (use this to ground your answer):\n{search_ctx}" if search_ctx else ""
    return f"""You are a member of an AI Council of {num_models} models deliberating on a question. Your response label is {label}.

QUESTION: {query}
{ctx}

Provide your best answer. Be thorough, cite sources where possible, and acknowledge uncertainty. 
You will be peer-reviewed by other council members."""


def _stage2_prompt(query: str, anonymized: dict[str, str], labels: list[str], search_ctx: str) -> str:
    """Prompt for Stage 2: anonymous peer review."""
    responses_block = ""
    for label in labels:
        responses_block += f"\n--- Response {label} ---\n{anonymized[label]}\n"

    ctx = f"\n\nSEARCH CONTEXT:\n{search_ctx}" if search_ctx else ""
    label_list = ", ".join(labels)
    
    return f"""You are reviewing responses from other council members to the question:

QUESTION: {query}
{ctx}

Below are the anonymized responses (labeled {label_list}):

{responses_block}

Rank these responses from best (1) to worst ({len(labels)}) based on:
1. Accuracy — factual correctness, alignment with search context
2. Insight — depth, originality, useful perspectives
3. Completeness — addresses all aspects of the question

Output EXACTLY in this format (nothing else):

FINAL RANKING:
1. Response [LETTER] — [one sentence why]
2. Response [LETTER] — [one sentence why]
..."""


def _stage3_prompt(query: str, responses_text: str, rankings_text: str, search_ctx: str, output_format: str) -> str:
    """Prompt for Stage 3: chairman synthesis."""
    ctx = f"\n\nSEARCH CONTEXT:\n{search_ctx}" if search_ctx else ""
    format_instr = ""
    if output_format == "json":
        format_instr = """
OUTPUT FORMAT: Return ONLY valid JSON (no markdown code blocks, no surrounding text):
{
  "title": "concise title summarizing the answer",
  "summary": "2-3 sentence executive summary",
  "key_insights": ["insight 1", "insight 2", "..."],
  "consensus_score": 0.0-1.0,
  "dissent": "areas of disagreement or null if none",
  "sources": ["source description 1", "..."]
}"""

    return f"""You are the Chairman of an AI Council. Your job is to synthesize the collective wisdom of the council into a clear, authoritative final answer.

QUESTION: {query}
{ctx}

COUNCIL RESPONSES:
{responses_text}

PEER REVIEW RANKINGS:
{rankings_text}

Synthesize the best insights from all responses. Where models agree, present the consensus. 
Where they disagree, acknowledge the dissent and present the strongest argument.
Be balanced, fair, and cite which models made which points.{format_instr}"""


def _parse_rankings(raw_text: str, labels: list[str]) -> dict[str, int]:
    """Parse FINAL RANKING: blocks into {label: rank} dict."""
    rankings = {}
    pattern = r'(\d+)\.\s*Response\s*([A-H])'
    matches = re.findall(pattern, raw_text, re.IGNORECASE)
    for rank_str, label in matches:
        if label in labels:
            rankings[label] = int(rank_str)
    return rankings
