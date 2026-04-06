# Execution Model

## MVP execution flow

1. load sequence
2. validate sequence
3. initialize workflow context
4. select next step
5. execute step
6. validate step output
7. store result
8. continue until complete
9. run final assembly

## Guardrails

- if web research is required, do not mark complete without it
- if citations are required, do not mark complete without them
- if intermediate validation is required, validate before proceeding
- if blocked, follow failure handling
