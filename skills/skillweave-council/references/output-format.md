# Council Output Formats

## Markdown (default)

Structured markdown document containing:
1. Chairman synthesis
2. Aggregate council rankings
3. Individual model responses
4. Dissent areas (if any)
5. Search context used

## JSON

Schema-validated JSON:
- title: Concise answer title (5-200 chars)
- summary: Executive summary (20-1000 chars)
- key_insights: Array of insights (1-10 items, 10-500 chars each)
- consensus_score: 0.0-1.0 (1.0 = unanimous)
- dissent: Areas of disagreement or null
- sources: Cited sources array
