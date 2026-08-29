# Council Profiles

Pre-configured model sets for different use cases.

Each id below is a **symbolic seat** — the council's declared seat *intent*
(``sonnet`` = a Claude seat, ``gpt-4o`` = an OpenAI seat, ``gemini-pro`` = a
Gemini seat, ``deepseek-v4`` = a DeepSeek seat, …). Faigate serves no such id;
each resolves exactly once at the query boundary (``resolve_council_seats``) to
a provider-native roster id that answers as itself. Faigate's live roster
self-answers only ``deepseek-v4-pro`` and ``deepseek-v4-flash``, so each
symbolic seat resolves to one of those two — ``deepseek-v4`` to
``deepseek-v4-pro``, every other seat to ``deepseek-v4-flash`` — keeping the
council at ``>=2`` distinct self-answering models. The run record attributes the
model that actually answered (read from the response envelope, never inferred
from the request).

## default
- Models: sonnet, gpt-4o, gemini-pro, deepseek-v4
- Chairman: sonnet
- Mode: standard
- Temperature: 0.5
- Use: General-purpose deliberation

## quick
- Models: gpt-4o-mini, haiku
- Chairman: gpt-4o-mini
- Mode: quick
- Temperature: 0.3
- Use: Fast comparison, budget-friendly

## deep
- Models: sonnet, gpt-4o, gemini-pro, deepseek-v4, llama-4, mistral
- Chairman: opus
- Mode: full
- Temperature: 0.5
- Use: Comprehensive analysis, diverse perspectives

## expert
- Models: opus, gpt-4o, gemini-pro, deepseek-v4
- Chairman: opus
- Mode: full
- Temperature: 0.4
- Use: High-stakes decisions, research-grade output
