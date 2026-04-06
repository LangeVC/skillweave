from .models import WorkflowContext, PromptSequence


def initialize_context(sequence_id: str, mode: str, inputs: dict, usage_notes: dict) -> WorkflowContext:
    return WorkflowContext(
        sequence_id=sequence_id,
        mode=mode,
        status="running",
        inputs=inputs,
        usage_notes=usage_notes,
    )


def next_step(sequence: PromptSequence, context: WorkflowContext):
    completed = set(context.completed_steps)
    for step in sequence.sequence_steps:
        deps = set(step.depends_on)
        if step.id not in completed and deps.issubset(completed):
            return step
    return None
