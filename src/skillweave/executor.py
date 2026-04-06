from .models import WorkflowContext, StepSpec


def execute_step(step: StepSpec, context: WorkflowContext) -> dict:
    context.current_step_id = step.id
    # Placeholder execution. In a real runtime, this would call the model/tools.
    result = {
        "step_id": step.id,
        "step_name": step.name,
        "status": "completed",
        "output": f"Executed step: {step.name}",
    }
    context.step_outputs[step.id] = result
    context.completed_steps.append(step.id)
    return result
