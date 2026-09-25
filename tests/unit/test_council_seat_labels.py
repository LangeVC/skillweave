"""Unit tests for dynamic council seat labels (SW-COUNCIL-LABEL-001).

Verifies dynamic seat label generation and deliberation with:
- Standard small seat counts (2-8 seats)
- 9 seats (Seat I) without IndexError
- 26 seats (Seats A-Z) without IndexError
- >26 seats (Seats AA, AB, etc.) without IndexError
- Rankings parsing with multi-seat formats
"""

import asyncio
import json
import pytest
from skillweave.council.engine import (
    CouncilConfig,
    CouncilEngine,
    ModelResponse,
    seat_label,
    _parse_rankings,
)


class MultiSeatMockProvider:
    """Mock provider supporting arbitrary number of seats."""

    def __init__(self):
        self.queries = []

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        self.queries.append({"model": model, "messages": messages, "temperature": temperature})
        user_msg = messages[-1]["content"] if messages else ""
        
        # If it's a review stage prompt, return structured JSON or FINAL RANKING
        if "Rank these responses" in user_msg or "FINAL RANKING" in user_msg:
            # Extract labels from prompt
            import re
            m = re.findall(r"---\s*Response\s*([A-Za-z0-9]+)\s*---", user_msg)
            if m:
                rankings = [{"label": lbl, "rank": idx + 1, "score": 1.0 / (idx + 1), "reason": f"Seat {lbl} rationale"} for idx, lbl in enumerate(m)]
                return json.dumps({"rankings": rankings, "best": m[0], "consensus_note": "high agreement"})
            return "FINAL RANKING:\n1. Response A — best\n2. Response B — ok"
        
        # If chairman synthesis
        if "Chairman of an AI Council" in user_msg:
            return "# Chairman Synthesis\nDeliberation completed across all seats."

        return f"Response from {model}: Comprehensive deliberation answer."


def test_seat_label_function_sequence():
    """Verify seat_label maps 0-based indices to alphabetical/multi-letter labels."""
    assert seat_label(-1) == "?"
    assert seat_label(0) == "A"
    assert seat_label(1) == "B"
    assert seat_label(7) == "H"
    assert seat_label(8) == "I"  # 9th seat
    assert seat_label(24) == "Y"
    assert seat_label(25) == "Z"  # 26th seat
    assert seat_label(26) == "AA"  # 27th seat
    assert seat_label(27) == "AB"
    assert seat_label(51) == "AZ"
    assert seat_label(52) == "BA"
    assert seat_label(701) == "ZZ"
    assert seat_label(702) == "AAA"


def test_9_seats_deliberation_without_index_error():
    """Verify full deliberation with 9 seats executes with labels A through I without IndexError."""
    models = [f"model-{seat_label(i).lower()}" for i in range(9)]
    assert len(models) == 9

    provider = MultiSeatMockProvider()
    engine = CouncilEngine(provider)
    config = CouncilConfig(
        models=models,
        chairman=models[0],
        mode="full",
        min_models_required=2,
    )

    result = asyncio.run(engine.deliberate("Evaluate architectural options for scaling", config))

    assert len(result.stage1) == 9
    assert len(result.stage2) == 9
    assert result.stage3 is not None
    assert result.seats_requested == 9
    assert result.models_distinct == 9
    assert not result.degraded
    assert result.consensus is True

    # Verify all 9 labels exist in label_to_model map
    assert len(result.label_to_model) == 9
    assert "A" in result.label_to_model
    assert "H" in result.label_to_model
    assert "I" in result.label_to_model
    assert result.label_to_model["I"] == "model-i"

    # Verify aggregate rankings computed across all 9 seats
    assert len(result.aggregate_rankings) == 9
    assert "I" in result.aggregate_rankings


def test_26_seats_deliberation_without_index_error():
    """Verify full deliberation with 26 seats executes with labels A through Z without IndexError."""
    models = [f"seat-{seat_label(i).lower()}" for i in range(26)]
    assert len(models) == 26

    provider = MultiSeatMockProvider()
    engine = CouncilEngine(provider)
    config = CouncilConfig(
        models=models,
        chairman=models[0],
        mode="full",
        min_models_required=2,
    )

    result = asyncio.run(engine.deliberate("Evaluate complete capability taxonomy", config))

    assert len(result.stage1) == 26
    assert len(result.stage2) == 26
    assert result.stage3 is not None
    assert result.seats_requested == 26
    assert result.models_distinct == 26
    assert not result.degraded
    assert result.consensus is True

    # Verify all 26 labels exist in label_to_model map
    assert len(result.label_to_model) == 26
    assert result.label_to_model["A"] == "seat-a"
    assert result.label_to_model["Z"] == "seat-z"

    # Verify aggregate rankings
    assert len(result.aggregate_rankings) == 26
    assert "A" in result.aggregate_rankings
    assert "Z" in result.aggregate_rankings


def test_beyond_26_seats_deliberation():
    """Verify deliberation works with >26 seats (e.g. 30 seats) with AA, AB, AC, AD."""
    models = [f"seat-{i}" for i in range(30)]
    provider = MultiSeatMockProvider()
    engine = CouncilEngine(provider)
    config = CouncilConfig(
        models=models,
        chairman=models[0],
        mode="standard",
        min_models_required=2,
    )

    result = asyncio.run(engine.deliberate("Stress testing seat allocation", config))

    assert len(result.stage1) == 30
    assert len(result.stage2) == 30
    assert result.label_to_model["AA"] == "seat-26"
    assert result.label_to_model["AD"] == "seat-29"


def test_parse_rankings_dynamic_labels():
    """Verify _parse_rankings parses single and multi-letter seat labels."""
    labels = ["A", "B", "I", "Z", "AA"]
    raw_json = json.dumps({
        "rankings": [
            {"label": "A", "rank": 1},
            {"label": "I", "rank": 2},
            {"label": "Z", "rank": 3},
            {"label": "AA", "rank": 4},
            {"label": "B", "rank": 5},
        ]
    })
    parsed = _parse_rankings(raw_json, labels)
    assert parsed == {"A": 1, "I": 2, "Z": 3, "AA": 4, "B": 5}

    # Text fallback format
    raw_text = """FINAL RANKING:
1. Response A — highest quality
2. Response I — very thorough
3. Response Z — good edge cases
4. Response AA — innovative perspective
5. Response B — acceptable
"""
    parsed_text = _parse_rankings(raw_text, labels)
    assert parsed_text == {"A": 1, "I": 2, "Z": 3, "AA": 4, "B": 5}
