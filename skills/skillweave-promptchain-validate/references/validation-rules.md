# Validation Rules

A valid **topic** sequence must:
- contain all required sections (the twelve-section contract; see SKILL.md)
- define at least one step
- use unique step ids
- define coherent usage notes
- define a final assembly section

A valid **build** sequence (produced by `regen-sequence.py`, consumed by
`promptchain-execute`) must:
- declare `session_boundary` (a sequence without one is refused)
- define at least one `phases:` entry with `dispatches_total` and one `session`
- give each `parallel_lanes` lane a disjoint write surface and a separate
  `worktree`/`branch`
- list every shared write surface under `mutual_exclusion` with
  `rule: at_most_one_in_flight` (a surface written by exactly one task does not
  belong here)
- define `gate_pass_requires` as binary gates before dependent phases start

Never apply the topic checklist to a build sequence, or the build checklist to
a topic sequence.
