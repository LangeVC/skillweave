from skillweave.models import PromptSequence, StepSpec
from skillweave.orchestrator import initialize_context, next_step


def test_next_step_returns_first_eligible_step():
    seq = PromptSequence(
        metadata={},
        objective="x",
        success_criteria=[],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="step-01", name="A", purpose="p", instructions="do"),
            StepSpec(id="step-02", name="B", purpose="p", instructions="do", depends_on=["step-01"]),
        ],
        final_assembly="done",
        validation_rules=[],
        failure_handling="stop",
        final_deliverable_format="md",
    )
    ctx = initialize_context("seq-1", "execute", {}, {})
    step = next_step(seq, ctx)
    assert step is not None
    assert step.id == "step-01"
