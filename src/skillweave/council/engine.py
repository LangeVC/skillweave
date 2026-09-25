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


#: The revision of the council profile data this engine records against. It is
#: read from the shared routing adapter (single source of truth) so the engine
#: and the adapter can never drift apart on what "current" means. The value is a
#: data revision, NOT a bundle version — the release that ships this revision is
#: gate-tagged separately (see the release readiness gate, not edited here).
try:
    from skillweave.routing.faigate_adapter import COUNCIL_PROFILE_VERSION
except Exception:  # pragma: no cover - defensive only; the adapter always ships it
    COUNCIL_PROFILE_VERSION = "unknown"


def seat_label(index: int) -> str:
    """Generate dynamic seat label for a 0-based seat index.

    0 -> 'A', 8 -> 'I', 25 -> 'Z', 26 -> 'AA', 27 -> 'AB', etc.
    Negative indices return '?'.
    """
    if index < 0:
        return "?"
    label = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return label


@dataclass
class ModelResponse:
    model_id: str                                 # requested seat (provider-native)
    response: str
    elapsed_ms: float
    error: str | None = None
    answering_model: str | None = None            # the model that actually answered (from the envelope, never inferred)
    requested_model: str | None = None            # the id as handed to the provider
    resolved_model: str | None = None             # the id the adapter resolved (exposed when it differs)
    status: str = "answered"                      # answered | substituted | errored | unavailable | rate_limited
    provider: str | None = None                   # transport that produced the answer
    served_by: str | None = None                  # the underlying model that served the request
    profile_version: str = COUNCIL_PROFILE_VERSION

    @property
    def attributed(self) -> bool:
        """True when the answering model differs from the requested model."""
        return bool(self.answering_model) and bool(self.requested_model) and self.answering_model != self.requested_model


@dataclass
class Ranking:
    reviewer: str          # requested seat that did the review
    rankings: dict[str, int]  # response_label → rank (1=best)
    raw_text: str
    reviewer_answering_model: str | None = None  # the model that actually performed this review
    self_ranked: bool = False  # True when the reviewing model also authored a ranked response
    status: str = "reviewed"
    provider: str | None = None
    profile_version: str = COUNCIL_PROFILE_VERSION


@dataclass
class SynthesisResult:
    chairman_model: str
    content: str            # markdown or JSON
    format: str             # "markdown" or "json"
    elapsed_ms: float
    chairman_answering_model: str | None = None  # the model that actually wrote the synthesis
    status: str = "synthesized"
    provider: str | None = None
    profile_version: str = COUNCIL_PROFILE_VERSION

    @property
    def attributed(self) -> bool:
        """True when the answering model differs from the chairman model."""
        return bool(self.chairman_answering_model) and self.chairman_answering_model != self.chairman_model


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
    degraded: bool = False                 # True when fewer distinct models answered than seats requested
    seats_requested: int = 0               # seats the config asked for
    models_distinct: int = 0               # distinct answering models that actually responded
    consensus: bool = False                # True only when distinct answering models >= min_models_required
    profile_version: str = COUNCIL_PROFILE_VERSION

    def attribution_matrix(self) -> list[dict]:
        """The complete requested→resolved→answering matrix for Stage 1 seats."""
        return [
            {
                "requested": r.requested_model or r.model_id,
                "resolved": r.resolved_model,
                "answering": r.answering_model,
                "status": r.status,
                "provider": r.provider,
                "profile_version": r.profile_version,
            }
            for r in self.stage1
        ]


@dataclass
class CouncilConfig:
    models: list[str]          # model IDs
    chairman: str              # chairman model ID
    mode: str = "full"         # "quick" | "standard" | "full"
    temperature: float = 0.5
    output_format: str = "markdown"  # "markdown" | "json"
    timeout_per_model: float = 60.0
    total_timeout: float = 180.0
    min_models_required: int = 2


class CouncilDegradedError(Exception):
    """Raised when too few models respond for meaningful deliberation."""
    pass


class CouncilEngine:
    """Orchestrates the 3-stage LLM Council deliberation."""

    def __init__(self, provider, searcher=None, routing_engine=None):
        """
        Args:
            provider: ModelProvider implementation (e.g. FaigateProvider)
            searcher: Optional WebSearch instance for Stage 0
            routing_engine: Optional RoutingPolicyEngine for fallback model replacements
        """
        self.provider = provider
        self.searcher = searcher
        self.routing_engine = routing_engine

    async def deliberate(self, query: str, config: CouncilConfig) -> CouncilResult:
        """Run full council deliberation. Mode controls which stages execute.

        Enforces total_timeout across all stages. Returns partial results on timeout.
        Raises CouncilDegradedError if fewer than min_models_required respond in Stage 1.
        """
        start = time.monotonic()
        result = CouncilResult(query=query)

        try:
            result = await asyncio.wait_for(
                self._deliberate_inner(query, config, result),
                timeout=config.total_timeout
            )
        except asyncio.TimeoutError:
            result.total_elapsed_ms = (time.monotonic() - start) * 1000
            if not result.stage3:
                result.stage3 = SynthesisResult(
                    chairman_model=config.chairman,
                    content="[Council timed out — returning partial results from completed stages]",
                    format="markdown",
                    elapsed_ms=0
                )

        result.total_elapsed_ms = (time.monotonic() - start) * 1000
        return result

    async def _deliberate_inner(self, query: str, config: CouncilConfig, result: CouncilResult) -> CouncilResult:
        """Inner deliberation logic, wrapped by total timeout."""
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
            result.seats_requested = len(config.models)
            answered = [r for r in result.stage1 if r.response and not r.error]
            result.models_distinct = len({r.served_by or r.answering_model or r.model_id for r in answered})
            result.degraded = result.models_distinct < result.seats_requested
            # Below the minimum distinct answering-model contract the run is
            # DEGRADED — it is never reported as consensus.
            result.consensus = result.models_distinct >= config.min_models_required

        # Stage 2: Peer Review (anonymized, structured JSON)
        if config.mode in ("standard", "full") and len(result.stage1) >= 2:
            result.stage2 = await self._stage2_review(query, result.stage1, config, result.search_context)
            result.aggregate_rankings = self._compute_aggregate_rankings(result.stage2)

        # Stage 3: Chairman Synthesis
        if config.mode == "full" and result.stage1:
            result.stage3 = await self._stage3_synthesis(
                query, result.stage1, result.stage2, result.search_context, config
            )

        return result

    async def _stage1_opinions(self, query: str, config: CouncilConfig, search_ctx: str = "") -> list[ModelResponse]:
        """Run all models in parallel via asyncio.gather. Failed models gracefully skipped."""
        async def query_one(model_id: str) -> ModelResponse:
            t0 = time.monotonic()
            try:
                seat_idx = config.models.index(model_id) if model_id in config.models else -1
                label = seat_label(seat_idx)
                prompt = _stage1_prompt(query, label, search_ctx, len(config.models))
                messages = [{"role": "user", "content": prompt}]
                response = await asyncio.wait_for(
                    self.provider.query(model_id, messages, config.temperature),
                    timeout=config.timeout_per_model
                )
                answering_model = getattr(response, "answering_model", None)
                served_by = getattr(response, "served_by", None)
                provider = getattr(response, "provider", None)
                # requested_model is what was handed to the provider; resolved_model
                # is what the adapter resolved (same unless the adapter exposed a
                # distinct resolution). answering_model is read from the envelope
                # only — never copied from the request (criterion 4).
                requested = getattr(response, "requested_model", None) or model_id
                status = "substituted" if answering_model and answering_model != requested else "answered"
                return ModelResponse(
                    model_id=model_id,
                    response=response,
                    elapsed_ms=(time.monotonic() - t0) * 1000,
                    answering_model=answering_model,
                    requested_model=requested,
                    resolved_model=requested,
                    status=status,
                    provider=provider,
                    served_by=served_by,
                )
            except Exception as e:
                return ModelResponse(
                    model_id=model_id,
                    response="",
                    elapsed_ms=(time.monotonic() - t0) * 1000,
                    error=str(e),
                    requested_model=model_id,
                    status=_classify_error(e),
                )

        tasks = [query_one(m) for m in config.models]
        responses = await asyncio.gather(*tasks, return_exceptions=False)
        successful = [r for r in responses if r.response and not r.error]
        
        seen_identities = set()
        for r in successful:
            identity = r.served_by or r.answering_model or r.model_id
            if identity not in seen_identities:
                seen_identities.add(identity)
            else:
                r.status = "duplicate"
                r.error = f"Duplicate voice detected: {identity}"
                r.response = ""

        successful = [r for r in responses if r.response and not r.error]
        distinct_models = {r.served_by or r.answering_model or r.model_id for r in successful}
        if len(distinct_models) < config.min_models_required:
            failed_models = [r.model_id for r in responses if r.error]
            raise CouncilDegradedError(
                f"Only {len(distinct_models)} distinct models responded "
                f"(minimum: {config.min_models_required}, seats requested: {len(config.models)}). "
                f"Distinct: {sorted(m for m in distinct_models if m)}. Failed: {failed_models}"
            )
        # Return every seat — answered and failed — so the run record keeps the
        # complete requested→resolved→answering matrix, including the seats that
        # errored/rate-limited/unavailable. Downstream stages filter on
        # ``response and not error``; nothing is silently dropped from evidence.
        return responses

    async def _stage2_review(self, query: str, responses: list[ModelResponse], config: CouncilConfig, search_ctx: str = "") -> list[Ranking]:
        """Each model reviews all responses (anonymized)."""
        anonymized = {}
        label_map = {}
        answering_map = {}
        labels_used = []
        for i, r in enumerate(responses):
            if r.response and not r.error:
                label = seat_label(i)
                anonymized[label] = r.response
                label_map[label] = r.model_id
                answering_map[label] = r.answering_model or r.model_id
                labels_used.append(label)

        if len(labels_used) < 2:
            return []

        authored_by = set(answering_map.values())

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
                reviewer_answering_model = getattr(raw, "answering_model", None) or model_id
                provider = getattr(raw, "provider", None)
                self_ranked = reviewer_answering_model in authored_by
                return Ranking(
                    reviewer=model_id,
                    rankings=rankings,
                    raw_text=raw,
                    reviewer_answering_model=reviewer_answering_model,
                    self_ranked=self_ranked,
                    status="reviewed",
                    provider=provider,
                )
            except Exception as e:
                return Ranking(reviewer=model_id, rankings={}, raw_text=f"ERROR: {e}", status=_classify_error(e))

        tasks = [review_one(m) for m in config.models]
        rankings = await asyncio.gather(*tasks)
        return [r for r in rankings if r.rankings]

    async def _stage3_synthesis(self, query: str, stage1: list[ModelResponse], stage2: list[Ranking], search_ctx: str, config: CouncilConfig) -> SynthesisResult:
        """Chairman synthesizes final answer."""
        t0 = time.monotonic()
        
        # Build context: all responses + rankings + search
        responses_text = ""
        for i, r in enumerate(stage1):
            if r.response and not r.error:
                lbl = seat_label(i)
                responses_text += f"\n### Response {lbl} (from model {lbl})\n{r.response}\n"

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
            chairman_answering_model = getattr(content, "answering_model", None)
            provider = getattr(content, "provider", None)
            status = "substituted" if chairman_answering_model and chairman_answering_model != config.chairman else "synthesized"
            return SynthesisResult(
                chairman_model=config.chairman,
                content=content,
                format=config.output_format,
                elapsed_ms=(time.monotonic() - t0) * 1000,
                chairman_answering_model=chairman_answering_model,
                status=status,
                provider=provider,
            )
        except Exception as e:
            return SynthesisResult(
                chairman_model=config.chairman,
                content=f"Synthesis failed: {e}",
                format="markdown",
                elapsed_ms=(time.monotonic() - t0) * 1000,
                status=_classify_error(e),
            )

    def _build_label_map(self, models: list[str]) -> dict[str, str]:
        return {seat_label(i): m for i, m in enumerate(models)}

    def _compute_aggregate_rankings(self, rankings: list[Ranking]) -> dict[str, float]:
        """Average rank across all peer evaluations. Lower = better."""
        totals = {}
        counts = {}
        for r in rankings:
            for label, rank in r.rankings.items():
                totals[label] = totals.get(label, 0) + rank
                counts[label] = counts.get(label, 0) + 1
        return {label: totals[label] / counts[label] for label in totals}


def _classify_error(exc: Exception) -> str:
    """Map a raised exception to a truthful per-seat status (criterion 5).

    These statuses are distinct so a run record can tell a rate limit from an
    unavailable model from a generic failure. The classification looks only at
    the typed exceptions raised at the adapter boundary; it never infers an
    answer.
    """
    from skillweave.routing.faigate_adapter import (  # local import avoids a cycle
        ModelNamespaceError,
        RateLimitedError,
        UnavailableModelError,
    )
    if isinstance(exc, RateLimitedError):
        return "rate_limited"
    if isinstance(exc, UnavailableModelError):
        return "unavailable"
    if isinstance(exc, ModelNamespaceError):
        return "namespace_error"
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    return "errored"


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

Output ONLY valid JSON (no markdown, no surrounding text):

{{"rankings": [{{"label": "X", "rank": 1, "score": 0.0-1.0, "reason": "one sentence"}}], "best": "X", "consensus_note": "one sentence on agreement level"}}

FALLBACK: If you cannot produce JSON, use this format:
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
    """Parse rankings from JSON (preferred) or FINAL RANKING fallback format."""
    rankings = {}
    labels_upper = {lbl.upper(): lbl for lbl in labels}

    # Try JSON first (structured format)
    try:
        text = raw_text.strip()
        if text.startswith("{"):
            data = json.loads(text)
            if "rankings" in data:
                for entry in data["rankings"]:
                    raw_label = str(entry.get("label", ""))
                    rank = entry.get("rank", 0)
                    matched = labels_upper.get(raw_label.upper())
                    if matched and isinstance(rank, int):
                        rankings[matched] = rank
                if rankings:
                    return rankings
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # Fallback: parse FINAL RANKING text format
    pattern = r'(\d+)\.\s*Response\s*([A-Za-z0-9]+)'
    matches = re.findall(pattern, raw_text, re.IGNORECASE)
    for rank_str, raw_label in matches:
        matched = labels_upper.get(raw_label.upper())
        if matched:
            try:
                rankings[matched] = int(rank_str)
            except ValueError:
                pass
    return rankings
