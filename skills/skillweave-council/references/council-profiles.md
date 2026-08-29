# Council Profiles

Pre-configured model sets for different use cases.

Each id below is a **provider-native Faigate roster id** — a real id from the
live ``GET /v1/models`` roster measured to answer *as itself* (its response
envelope ``model`` field echoes the requested id). Faigate's roster self-answers
only ``deepseek-v4-pro`` and ``deepseek-v4-flash``; every other id it serves
silently collapses onto ``deepseek-v4-flash``. The presets therefore name those
two ids directly, with no symbolic seat alias and no hidden substitution: what
the profile names is exactly what runs, and the ``>=2`` distinct answering-model
gate holds on the two self-answering seats. The run record attributes the model
that actually answered (read from the response envelope, never inferred from the
request).

## default
- Models: deepseek-v4-pro, deepseek-v4-flash
- Chairman: deepseek-v4-pro
- Mode: standard
- Temperature: 0.5
- Use: General-purpose deliberation

## quick
- Models: deepseek-v4-flash
- Chairman: deepseek-v4-flash
- Mode: quick
- Temperature: 0.3
- Use: Fast comparison, budget-friendly

## deep
- Models: deepseek-v4-pro, deepseek-v4-flash
- Chairman: deepseek-v4-pro
- Mode: full
- Temperature: 0.5
- Use: Comprehensive analysis, diverse perspectives

## expert
- Models: deepseek-v4-pro, deepseek-v4-flash
- Chairman: deepseek-v4-pro
- Mode: full
- Temperature: 0.4
- Use: High-stakes decisions, research-grade output
