"""Synthesis utilities for CouncilEngine: JSON schema output, phase-context prompts."""

import json
from typing import Optional


# JSON Schema for structured council output
COUNCIL_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["title", "summary", "key_insights", "consensus_score"],
    "properties": {
        "title": {
            "type": "string",
            "description": "Concise title summarizing the council's answer",
            "minLength": 5,
            "maxLength": 200,
        },
        "summary": {
            "type": "string",
            "description": "2-3 sentence executive summary of findings",
            "minLength": 20,
            "maxLength": 1000,
        },
        "key_insights": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {"type": "string", "minLength": 10, "maxLength": 500},
            "description": "Key insights from the council deliberation",
        },
        "consensus_score": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "How strongly the council agrees (1.0 = unanimous)",
        },
        "dissent": {
            "type": ["string", "null"],
            "description": "Areas of disagreement, or null if council reached consensus",
        },
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Sources cited across council responses",
        },
    },
}


def validate_output(content: str) -> tuple[bool, dict | None, str]:
    """Validate JSON output against council schema.
    
    Returns (is_valid, parsed_dict, error_message).
    """
    # Strip markdown code blocks if present
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON: {e}"

    # Basic schema validation
    errors = []
    for field in COUNCIL_OUTPUT_SCHEMA["required"]:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return False, data, "; ".join(errors)

    # Type checks
    if not isinstance(data.get("title"), str):
        errors.append("title must be a string")
    if not isinstance(data.get("summary"), str):
        errors.append("summary must be a string")
    if not isinstance(data.get("key_insights"), list):
        errors.append("key_insights must be an array")
    if "consensus_score" in data and not isinstance(data["consensus_score"], (int, float)):
        errors.append("consensus_score must be a number")

    if errors:
        return False, data, "; ".join(errors)

    return True, data, ""


def format_output_schema_instructions() -> str:
    """Return the JSON output format instructions for the chairman prompt."""
    return """
OUTPUT FORMAT: Return ONLY valid JSON (no markdown code blocks, no surrounding text):
{
  "title": "concise title summarizing the answer",
  "summary": "2-3 sentence executive summary",
  "key_insights": ["insight 1", "insight 2", "..."],
  "consensus_score": 0.0-1.0 (how strongly the council agrees),
  "dissent": "areas of disagreement or null if none",
  "sources": ["source description 1", "..."]
}"""


# Phase-context prompt modifiers
PHASE_PROMPTS = {
    "discovery": """
You are assisting with a DISCOVERY PHASE analysis. Focus on:
- Market landscape and competitive positioning
- User needs, pain points, and opportunity spaces
- Trend identification and pattern recognition
- Actionable insights for product strategy

Frame your response to inform a Product Requirements Document (PRD).""",

    "design": """
You are evaluating DESIGN decisions. Focus on:
- Usability, accessibility, and user experience principles
- Visual hierarchy, information architecture, and interaction patterns
- Design token consistency (colors, typography, spacing)
- Identify potential UX problems and suggest improvements

Frame your response as a structured design critique.""",

    "code_review": """
You are reviewing CODE or ARCHITECTURE decisions. Focus on:
- Correctness, performance, and security implications
- Code quality, maintainability, and testability
- Architecture trade-offs and alternative approaches
- Identify bugs, edge cases, and potential improvements

Frame your response as a structured code review.""",

    "post_release": """
You are analyzing POST-RELEASE feedback. Focus on:
- Categorizing feedback into bugs, features, improvements
- Identifying patterns and systemic issues
- Prioritizing action items by impact and urgency
- Recommending next iteration focus areas

Frame your response to inform the iteration backlog.""",
}


def get_phase_context(phase: str | None) -> str:
    """Get phase-specific prompt modifier. Returns empty string for generic/standalone use."""
    if phase and phase in PHASE_PROMPTS:
        return PHASE_PROMPTS[phase]
    return ""


def json_schema_to_markdown() -> str:
    """Render the JSON output schema as Markdown documentation."""
    props = COUNCIL_OUTPUT_SCHEMA["properties"]
    lines = ["## Council JSON Output Schema", "", "| Field | Type | Required | Description |", "|-------|------|----------|-------------|"]
    required = COUNCIL_OUTPUT_SCHEMA["required"]
    for field, spec in props.items():
        req = "✅" if field in required else "❌"
        type_str = spec.get("type", "any")
        if isinstance(type_str, list):
            type_str = " | ".join(str(t) for t in type_str)
        lines.append(f"| {field} | {type_str} | {req} | {spec.get('description', '')} |")
    return "\n".join(lines)
