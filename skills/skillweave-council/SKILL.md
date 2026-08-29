---
name: skillweave-council
description: "Multi-Model LLM Council — Deliberation, Peer Review, and Chairman Synthesis with Web Search and Faigate Routing"
argument-hint: topic="[topic]" time_range="[30d|quarter|6mo|1yr|any]" mode="[quick|standard|full]" profile="[default|quick|deep|expert]" output="[markdown|json]" phase="[discovery|design|code_review|post_release]"
---

# /skillweave-council

**Collective AI Intelligence** — Instead of asking one LLM, convene a council of AI models that deliberate, peer-review, and synthesize the best answer.

## Overview

skillweave-council is a standalone SkillWeave skill that implements the LLM Council pattern:

1. **Stage 1 — Deliberation**: Multiple models answer independently in parallel (via Faigate routing)
2. **Stage 2 — Peer Review**: Models anonymously rank each other's responses
3. **Stage 3 — Chairman Synthesis**: A chairman model synthesizes the final answer

Optional Stage 0: Web Search (DuckDuckGo, Serper, Tavily, Brave) grounds responses in real-time data with configurable time ranges.

## Usage

```
/skillweave-council topic="Wettbewerbsanalyse Q2 2026" time_range="quarter" mode="full"

/skillweave-council topic="Evaluate this architecture decision..." mode="full" output="json" phase="code_review"

/skillweave-council command="search" topic="latest AI trends" time_range="30d"

/skillweave-council command="profiles"

/skillweave-council command="compare" topic="..." profile="quick"
```

## Commands

| Command | Description | Stages |
|---------|-------------|--------|
| `deliberate` | Full council deliberation (default) | 0→1→2→3 |
| `compare` | Side-by-side model comparison | 0→1 |
| `search` | Web search only (no models) | 0 |
| `profiles` | List available council profiles | — |

## Parameters

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `topic` | string | required | Question or topic for the council |
| `time_range` | 30d, quarter, 6mo, 1yr, any | any | Web search time window |
| `mode` | quick, standard, full | full | Execution depth |
| `profile` | default, quick, deep, expert | default | Pre-configured model set |
| `output` | markdown, json | markdown | Output format |
| `phase` | discovery, design, code_review, post_release | — | SkillWeave lifecycle phase context |

## Council Profiles

| Profile | Models | Mode | Use Case |
|---------|--------|------|----------|
| **default** | 4 models (balanced) | standard | General-purpose deliberation |
| **quick** | 2 models (fastest) | quick | Rapid comparison, low latency |
| **deep** | 6 models (diverse) | full | Comprehensive analysis |
| **expert** | 4 models (top-tier) | full | High-stakes decisions, research |

## Execution Modes

| Mode | Stages | Description |
|------|--------|-------------|
| **quick** | Stage 1 only | Models answer independently, no review |
| **standard** | Stages 1 + 2 | Models answer + peer review with rankings |
| **full** | All 3 stages | Deliberation + peer review + chairman synthesis |

## Web Search Providers

| Provider | Type | Key Required |
|----------|------|-------------|
| DuckDuckGo | Free web+news | No |
| Serper | Google results | Yes (SERPER_API_KEY) |
| Tavily | LLM-optimized | Yes (TAVILY_API_KEY) |
| Brave | Privacy-focused | Yes (BRAVE_API_KEY) |

## Phase Integration

skillweave-council integrates with the SkillWeave 7-phase lifecycle:

| Phase | Council Focus | Typical Use |
|-------|---------------|-------------|
| **discovery** | Market research, competitive analysis | Replaces last30days |
| **design** | Design evaluation, UX critique | Optional design review |
| **code_review** | Architecture review, code quality | Build-phase quality gate |
| **post_release** | Feedback analysis, pattern detection | Release retrospective |

## Output Format

### Markdown (default)
A structured markdown document with the chairman's synthesis, council rankings, and individual model responses.

### JSON
Structured output with schema validation:
```json
{
  "title": "Concise answer title",
  "summary": "Executive summary",
  "key_insights": ["Insight 1", "Insight 2"],
  "consensus_score": 0.85,
  "dissent": "Minor disagreement on timeline",
  "sources": ["Source A", "Source B"]
}
```

## Faigate Integration

skillweave-council uses Faigate for model routing:
- Automatic availability check before queries
- Credit balance verification
- Failed models gracefully excluded (no council abort)
- Multi-provider routing through a single API

No API key management needed — Faigate handles authentication internally.

### Symbolic seats and provider-native resolution

Council profile data (`references/council-profiles.md` and the shared
`ROUTER_PROFILES` in `skillweave.routing.faigate_adapter`) declares **symbolic
seats** — the council's seat *intents* (a DeepSeek seat, a Claude seat, …).
These resolve to **provider-native** roster ids exactly once at the query
boundary via `resolve_council_seats`; Faigate's live roster self-answers only
`deepseek-v4-pro` and `deepseek-v4-flash`, so every symbolic seat resolves to
one of those two to hold the `>=2` distinct answering-model gate. The `faigate/`
gateway prefix never appears in Council profile data; it belongs to the dispatch
layer's gateway qualification only, and is translated exactly once at the
adapter boundary. A `faigate/` (or any other outer) prefix in a Council profile
is refused **before** any provider call, with the offending id named.

### Who answered

Every seat records, independently: the **requested** model, the **resolved**
model (when the adapter exposes one), the **answering** model (read from the
response envelope, never inferred from the request), the provider, the
attribution **status** (`answered` | `substituted` | `unavailable` |
`rate_limited` | `errored`), and the profile revision. Fewer than
`min_models_required` distinct answering models is a **degraded** run and is
never reported as consensus.

### Faigate endpoint

The council talks to Faigate at exactly one address, resolved in this order:

1. `FAIGATE_BASE_URL` env var (full URL, e.g. `http://127.0.0.1:8090/v1`)
2. `FAIGATE_HOST` + `FAIGATE_PORT` env vars
3. Default: `http://127.0.0.1:8090/v1`

The default is the address the brew-installed Faigate actually listens on
(`127.0.0.1`, port `8090`). Do not guess a different port — `8080` is a
foreign service (Docker), not Faigate.

## Sandbox Preflight

The council validates:
1. Faigate endpoint reachable at the address resolved above
2. At least 2 models available (for peer review)
3. Chairman model available (for full mode)
4. Web search provider configured (if time_range specified)
5. JSON schema valid (if output=json)

When the preflight fails, the message MUST name the address (and port) it
checked, not just report "not reachable". An unreachability report without
the address is not a diagnosis — it points the operator at nothing. For
example: `Faigate not reachable at http://127.0.0.1:8090/v1 (connection refused)`.

## Testing

| Test | Description |
|------|-------------|
| Stage 1 parallel execution | All models respond within timeout |
| Stage 1 graceful failure | 1 model fails, others succeed |
| Stage 2 anonymization | Responses anonymized as A/B/C |
| Stage 2 ranking parse | FINAL RANKING: format parsed correctly |
| Stage 3 markdown synthesis | Chairman produces valid markdown |
| Stage 3 JSON output | Valid JSON with schema compliance |
| Faigate availability mock | Check returns model statuses |
| Web search DuckDuckGo | Real search returns results |
| Time-range filter | 30d/quarter/6mo/1yr filtering |
| Council profile selection | All 4 profiles load correctly |
| Phase context injection | Discovery/design prompts modify output |
| Standalone mode | No phase context = generic prompt |
