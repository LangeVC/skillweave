"""Council prompt templates with SkillWeave phase integration.

Provides prompts for all 3 council stages with optional phase-context injection.
Phase context tailors the council's focus: discovery (market research),
design (UX evaluation), code_review (architecture review), post_release (feedback analysis).
"""

from skillweave.council.synthesis import get_phase_context, format_output_schema_instructions


def stage1_prompt(query: str, label: str, search_ctx: str = "", num_models: int = 4, phase: str | None = None) -> str:
    """Prompt for Stage 1: independent deliberation with optional phase context."""
    phase_ctx = get_phase_context(phase)
    phase_section = f"\n\nPHASE CONTEXT:\n{phase_ctx}" if phase_ctx else ""
    ctx = f"\n\nSEARCH CONTEXT (use this to ground your answer):\n{search_ctx}" if search_ctx else ""
    return f"""You are a member of an AI Council of {num_models} models deliberating on a question. Your response label is {label}.
{phase_section}
QUESTION: {query}
{ctx}

Provide your best answer. Be thorough, cite sources where possible, and acknowledge uncertainty. 
You will be peer-reviewed by other council members."""


def stage2_prompt(query: str, anonymized: dict[str, str], labels: list[str], search_ctx: str = "", phase: str | None = None) -> str:
    """Prompt for Stage 2: anonymous peer review."""
    responses_block = ""
    for label in labels:
        responses_block += f"\n--- Response {label} ---\n{anonymized[label]}\n"

    phase_ctx = get_phase_context(phase)
    phase_section = f"\n\nPHASE CONTEXT:\n{phase_ctx}" if phase_ctx else ""
    ctx = f"\n\nSEARCH CONTEXT:\n{search_ctx}" if search_ctx else ""
    label_list = ", ".join(labels)

    return f"""You are reviewing responses from other council members to the question:
{phase_section}

QUESTION: {query}
{ctx}

Below are the anonymized responses (labeled {label_list}):

{responses_block}

Rank these responses from best (1) to worst ({len(labels)}) based on:
1. Accuracy — factual correctness, alignment with search context
2. Insight — depth, originality, useful perspectives
3. Completeness — addresses all aspects of the question

Output EXACTLY in this format (nothing else):

FINAL RANKING:
1. Response [LETTER] — [one sentence why]
2. Response [LETTER] — [one sentence why]
..."""


def stage3_prompt(query: str, responses_text: str, rankings_text: str, search_ctx: str = "", output_format: str = "markdown", phase: str | None = None) -> str:
    """Prompt for Stage 3: chairman synthesis."""
    phase_ctx = get_phase_context(phase)
    phase_section = f"\n\nPHASE CONTEXT:\n{phase_ctx}" if phase_ctx else ""
    ctx = f"\n\nSEARCH CONTEXT:\n{search_ctx}" if search_ctx else ""
    format_instr = format_output_schema_instructions() if output_format == "json" else ""

    return f"""You are the Chairman of an AI Council. Your job is to synthesize the collective wisdom of the council into a clear, authoritative final answer.
{phase_section}

QUESTION: {query}
{ctx}

COUNCIL RESPONSES:
{responses_text}

PEER REVIEW RANKINGS:
{rankings_text}

Synthesize the best insights from all responses. Where models agree, present the consensus. 
Where they disagree, acknowledge the dissent and present the strongest argument.
Be balanced, fair, and cite which models made which points.{format_instr}"""


def stage1_prompt_compare(query: str, labels: list[str], search_ctx: str = "", phase: str | None = None) -> str:
    """Prompt for compare mode: multiple models, side-by-side comparison, no peer review."""
    phase_ctx = get_phase_context(phase)
    phase_section = f"\n\nPHASE CONTEXT:\n{phase_ctx}" if phase_ctx else ""
    ctx = f"\n\nSEARCH CONTEXT:\n{search_ctx}" if search_ctx else ""
    model_list = ", ".join(labels)
    return f"""You are an AI model participating in a multi-model comparison on the following question.
{phase_section}

QUESTION: {query}
{ctx}

Available models for this comparison: {model_list}

Provide your best answer. You are NOT reviewing other responses — this is a standalone answer for side-by-side comparison."""


def phase_available_phases() -> list[str]:
    """List all available phase contexts."""
    from skillweave.council.synthesis import PHASE_PROMPTS
    return list(PHASE_PROMPTS.keys())
