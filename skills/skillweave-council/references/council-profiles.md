# Council Profiles

Pre-configured model sets for different use cases.

Each id below is a **Faidate roster id** — the exact `id` field Faidate serves
from `GET /v1/models`. The council never invents its own aliases, so a cast
that names a real roster id answers truthfully and the run record can attribute
which model actually answered (read from the response envelope, never inferred
from the request).

## default
- Models: deepseek-v4-pro, deepseek-v4-flash, gemini-flash, kilo-sonnet
- Chairman: deepseek-v4-pro
- Mode: standard
- Temperature: 0.5
- Use: General-purpose deliberation

## quick
- Models: deepseek-v4-flash, gemini-flash-lite
- Chairman: deepseek-v4-flash
- Mode: quick
- Temperature: 0.3
- Use: Fast comparison, budget-friendly

## deep
- Models: deepseek-v4-pro, deepseek-v4-flash, gemini-flash, gemini-flash-lite, kilo-sonnet, kilo-opus
- Chairman: kilo-opus
- Mode: full
- Temperature: 0.5
- Use: Comprehensive analysis, diverse perspectives

## expert
- Models: kilo-opus, kilo-sonnet, deepseek-v4-pro, gemini-flash
- Chairman: kilo-opus
- Mode: full
- Temperature: 0.4
- Use: High-stakes decisions, research-grade output
