# Council Profiles

Pre-configured capability profiles for different use cases.

Council profiles define required model capabilities instead of hardcoded model IDs. The dynamic routing engine matches these capability requirements against active models in the provider registry (e.g. reasoning, coding, vision, general deliberation).

## default
- Capabilities: reasoning, general
- Chairman: reasoning
- Mode: standard
- Temperature: 0.5
- Use: General-purpose deliberation

## quick
- Capabilities: fast, general
- Chairman: fast
- Mode: quick
- Temperature: 0.3
- Use: Fast comparison, budget-friendly

## deep
- Capabilities: reasoning, analysis, diversity
- Chairman: reasoning
- Mode: full
- Temperature: 0.5
- Use: Comprehensive analysis, diverse perspectives

## expert
- Capabilities: reasoning, expert, analysis
- Chairman: reasoning
- Mode: full
- Temperature: 0.4
- Use: High-stakes decisions, research-grade output
