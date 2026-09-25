"""Degradation mode and fallback behavior tests under soak conditions (SW-SOAK-001).

Validates that SkillWeave gracefully degrades when runtime foundations or council seats
are impaired, operating transparently with explicit degraded signalling rather than crashing.
"""

import asyncio
import sys
from pathlib import Path
import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave_degraded import detect_degraded, DegradedSignal
from skillweave.council.engine import (
    CouncilConfig,
    CouncilEngine,
    CouncilResult,
)
from skillweave.routing.faigate_adapter import AttributedResponse


class _MockAttributingProvider:
    """Mock provider for attributing distinct or collapsed models."""

    def __init__(self, answering_map: dict):
        self.answering_map = dict(answering_map)

    async def query(self, model: str, messages: list, temperature: float = 0.5):
        answering = self.answering_map.get(model, model)
        return AttributedResponse(
            f"Response for {model}",
            requested_model=model,
            answering_model=answering,
        )


class TestSoakDegradation:
    """Degradation signalling and fallback tests during soak execution."""

    def test_detect_degraded_probe_is_safe_and_transparent(self):
        """Verify detect_degraded returns a structured DegradedSignal without crashing."""
        for _ in range(50):
            signal = detect_degraded()
            assert isinstance(signal, DegradedSignal)
            assert isinstance(signal.active, bool)
            assert isinstance(signal.reason, str)
            assert isinstance(signal.missing_modules, tuple)
            assert isinstance(signal.fallback_version, str)

    def test_council_collapsed_roster_marks_result_degraded(self):
        """Verify council deliberation marks result degraded when distinct models collapse below seats requested."""
        provider = _MockAttributingProvider({
            "seat-a": "deepseek-v4-flash",
            "seat-b": "deepseek-v4-flash",
            "seat-c": "deepseek-v4-flash",
        })
        engine = CouncilEngine(provider)
        config = CouncilConfig(
            models=["seat-a", "seat-b", "seat-c"],
            chairman="seat-a",
            mode="standard",
            min_models_required=1,
        )

        result: CouncilResult = asyncio.run(engine.deliberate("Soak degradation query", config))
        assert result.degraded is True
        assert result.seats_requested == 3
        assert result.models_distinct == 1

    def test_degraded_mode_continuity_under_rapid_polling(self):
        """Test continuous probing of degraded status across multiple rapid cycles."""
        signals = []
        for _ in range(100):
            sig = detect_degraded()
            signals.append(sig)

        assert len(signals) == 100
        first_active = signals[0].active
        assert all(s.active == first_active for s in signals)
