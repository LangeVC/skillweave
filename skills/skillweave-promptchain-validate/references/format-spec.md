# Format Spec

The skillweave-promptchain-validate skill validates a sequence against one of
two supported formats, never guessing which one the author meant:

- **Topic format**: the twelve-section contract listed in SKILL.md —
  Metadata, Objective, Success Criteria, Assumptions, Usage Notes, Inputs
  Required, Outputs Required, Sequence Steps, Final Assembly, Validation
  Rules, Failure Handling, Final Deliverable Format. Consuming flow: the
  standalone prompt-chain player / copilot-inline execution.

- **Build format**: the `execution-sequences.yaml` that `regen-sequence.py`
  emits from a PRD and `promptchain-execute` dispatches. Validated against
  `phases`, `parallel_lanes`, `mutual_exclusion`, `gate_pass_requires`, and
  `session_boundary` — not the twelve-section checklist.

The sequence author should keep the structure explicit and avoid hidden
dependencies. See `references/sequence-type-detection.md` for how to pin the
format before validating.
