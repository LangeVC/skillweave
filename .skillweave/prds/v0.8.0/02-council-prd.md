# skillweave-council — PRD v0.8.0

## 1. Executive Summary

**LLM Council as SkillWeave Skill**: Multi-model deliberation engine — mehrere LLMs beantworten eine Frage unabhängig, reviewen sich anonym gegenseitig, und ein Chairman synthetisiert die finale Antwort. Mit Web-Search (real-time + Zeiträume), Faigate-Routing (Model-Availability + Guthaben-Check), strukturierter JSON-Output.

Ersetzt `last30days` in der Discovery-Phase und erweitert SkillWeave um collective AI intelligence.

## 2. Problem Statement

**Warum ein Council statt einem Modell?**
- Einzelne Modelle haben blind spots (Halluzination, Bias, veraltetes Wissen)
- Kein peer review — Fehler bleiben unentdeckt
- Kein Web-Search für aktuelle Daten in bestehenden Skills
- `last30days` ist nicht originär und nur 30-Tage-Recherche, kein Multi-Model

**Council löst das durch:**
- 3-Stage-Deliberation (Opinions → Peer Review → Synthesis)
- Multi-Provider Web-Search (DuckDuckGo, Serper, Tavily, Brave)
- Zeitraum-Suche (30d, quarter, 6mo, 1yr, any)
- Faigate als Model-Router (verfügbare Modelle + Guthaben)
- Modular: standalone einsetzbar oder als Phase-Tool

## 3. Target Users & Personas

- **Product Manager**: Wettbewerbsanalyse, Marktforschung via Council + Web-Search
- **Engineer**: Architektur-Review mit Multi-Model-Perspektive
- **Researcher**: Deep-Dive in ein Thema mit Zeitraum-Suche + Council-Synthese
- **Designer**: Design-Evaluation mit mehreren Modellen
- **Post-Release Analyst**: Feedback-Kategorisierung mit Council-Intelligenz

## 4. Solution Overview

### Core Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    USER QUERY                                │
│  topic="..." time_range="30d" mode="full" output="json"     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 0: WEB SEARCH (optional)                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │DuckDuckGo│  │  Serper  │  │  Tavily  │  │  Brave   │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │              │              │              │         │
│       └──────────────┴──────────────┴──────────────┘         │
│                           │                                  │
│               Search Context (top N results)                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: DELIBERATION                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │ Model A │  │ Model B │  │ Model C │  │ Model D │         │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘         │
│       │            │            │            │               │
│       ▼            ▼            ▼            ▼               │
│  Response A   Response B   Response C   Response D           │
│  (via Faigate routing, parallel)                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 2: PEER REVIEW                                       │
│  Responses anonymized → each model ranks all others          │
│  Rankings aggregated → consensus score per response          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 3: CHAIRMAN SYNTHESIS                                │
│  Chairman model receives:                                    │
│  - All responses + rankings + search context                 │
│  - Synthesizes final answer (markdown or structured JSON)    │
└─────────────────────────────────────────────────────────────┘
```

### Execution Modes

| Mode | Stages | Use Case |
|------|--------|----------|
| **quick** | Stage 1 only | Schneller Modellvergleich, keine Review |
| **standard** | Stages 1 + 2 | Modellvergleich mit Ranking (default) |
| **full** | All 3 | Vollständige Deliberation mit Chairman-Synthese |

### Zeitraum-Suche

| Range | Beschreibung | DuckDuckGo | Serper/Tavily |
|-------|-------------|------------|---------------|
| `30d` | Letzte 30 Tage | `timelimit='m'` | Post-hoc-Date-Filter |
| `quarter` | Letzte 3 Monate | `timelimit='m'` | Post-hoc-Date-Filter |
| `6mo` | Letzte 6 Monate | `timelimit='w'`* | Post-hoc-Date-Filter |
| `1yr` | Letztes Jahr | `timelimit='y'` | Post-hoc-Date-Filter |
| `any` | Kein Zeitlimit | Standard | Standard |

*\*DuckDuckGo hat kein 6-Monats-Limit → filter post-hoc*

## 5. Functional Requirements

### 5.1 Core Features

| ID | Feature | Priority |
|----|---------|----------|
| CNL-001 | 3-Stage Council Engine (deliberation → peer review → synthesis) | high |
| CNL-002 | Multi-Model Routing via Faigate (verfügbarkeit + Guthaben) | high |
| CNL-003 | Web Search Integration (4 Provider) | high |
| CNL-004 | Zeitraum-Suche (30d/quarter/6mo/1yr/any) | high |
| CNL-005 | Structured JSON Output (Schema-validiert) | high |
| CNL-006 | Council Profiles (default/quick/deep/expert) | medium |
| CNL-007 | SKILL.md + capability.yaml nach promptchain-Muster | high |
| CNL-008 | last30days Ersatz in phases.yaml | high |

### 5.2 User Stories

- Als PM will ich mit `/skillweave-council topic="Wettbewerbsanalyse Q2" time_range="quarter"` den Markt analysieren
- Als Engineer will ich Architektur-Vorschläge von 4 Modellen reviewen lassen
- Als Researcher will ich ein Thema mit Web-Search + Multi-Model-Synthese explorieren
- Als Standalone-User will ich den Council ohne SkillWeave-Lifecycle nutzen

## 6. Non-Functional Requirements

- **Performance**: Stage 1 parallel (asyncio.gather), max 30s pro Modell, 120s Gesamt-Timeout
- **Failability**: Failed models gracefully skipped, nicht blockierend
- **Security**: Keine API-Key-Speicherung (faigate managed Auth)
- **Output**: Markdown + Structured JSON (JSON Schema-validiert)
- **Agent-Agnostic**: Capability-based (works with any AI coding agent)

## 7. Technical Architecture

### Python Module: `src/skillweave/council/`

```
src/skillweave/council/
├── __init__.py
├── engine.py          # CouncilEngine: orchestriert 3 Stages
├── providers.py        # ModelProvider, SearchProvider abstractions
├── faigate_adapter.py  # faigate model routing + availability check
├── search.py           # WebSearch: DuckDuckGo, Serper, Tavily, Brave
├── prompts.py          # Stage 1/2/3 Prompt-Templates
├── synthesis.py        # Chairman synthesis + JSON output
└── profiles.py         # Council Profiles (default/quick/deep/expert)
```

### Key Classes

```python
@dataclass
class CouncilConfig:
    models: list[str]          # ["faigate:model-a", "faigate:model-b", ...]
    chairman: str              # "faigate:model-c"
    mode: str                  # "quick" | "standard" | "full"
    search_provider: str       # "duckduckgo" | "serper" | "tavily" | "brave"
    time_range: str            # "30d" | "quarter" | "6mo" | "1yr" | "any"
    temperature: float         # 0.3-0.7
    output_format: str         # "markdown" | "json"

class CouncilEngine:
    async def deliberate(query: str, config: CouncilConfig) -> CouncilResult
    async def stage1_opinions() -> list[ModelResponse]     # parallel
    async def stage2_review() -> list[Ranking]             # anonymized
    async def stage3_synthesis() -> SynthesisResult        # chairman
```

### Faigate Adapter

```python
class faigateProvider:
    async def check_availability(models: list[str]) -> dict[str, bool]
    async def check_credits(model: str) -> float
    async def query(model: str, messages: list, temperature: float) -> str
    def get_available_models() -> list[str]
    def best_fit(profile: str) -> list[str]  # nach Council-Profil
```

### Skill Structure

```
skills/skillweave-council/
├── SKILL.md                    # YAML frontmatter + usage + commands
├── capability.yaml             # kind=skill, capabilities list
└── references/
    ├── council-profiles.md     # Profile definitions
    ├── search-providers.md     # Web-Search Provider Guide
    └── output-format.md        # JSON Schema + Markdown format
```

## 8. Scope & Constraints

### In Scope
- Core Council Engine (3 stages, parallel execution)
- faigate Adapter (model routing, availability, credits)
- Web Search (DuckDuckGo default + 3 optional)
- Zeitraum-Suche (alle 5 ranges)
- Structured JSON Output (schema-validated)
- Council Profiles (4 Profile)
- SKILL.md + capability.yaml
- phases.yaml Update (last30days → council)
- Modular standalone Nutzung

### Out of Scope
- Web UI (React frontend)
- API Key Management (faigate macht das)
- Ollama/Local Models (nur via faigate)
- Conversation History (kein Chat-Interface)
- Rate Limiting UI (faigate managed Raten)

## 9. Timeline & Milestones

| Milestone | Tasks | Aufwand |
|-----------|-------|---------|
| M1: Engine Core | CNL-001, CNL-002 | 3h |
| M2: Web Search | CNL-003, CNL-004 | 3h |
| M3: Output + Profiles | CNL-005, CNL-006 | 2h |
| M4: Skill + Lifecycle | CNL-007, CNL-008 | 2h |
| M5: Tests | 15+ tests | 2h |
| **Total** | | **~12h** |

## 10. Assumptions

- faigate hat einen REST-Endpunkt für Model-Abfragen (availability, credits, query)
- DuckDuckGo `ddgs` Python-Library ist installierbar
- Serper/Tavily/Brave API-Keys können via .skillweave/config.yaml konfiguriert werden
- 3 Council-Modelle + 1 Chairman sind über Faigate verfügbar
- Kein Node.js/Frontend nötig (reiner CLI-Skill)
