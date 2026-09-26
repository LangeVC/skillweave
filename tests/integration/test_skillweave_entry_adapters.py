"""Adapter equivalence integration test (SW-156-ENTRY-002).

Proves MappingEntryAdapter and ObjectEntryAdapter produce the same semantic
result from identical facts:

* Criterion 3 — Two harness adapters produce the same semantic result:
  state_digest, intent_digest and Decision.digest all match when the
  underlying facts are byte-for-byte identical.
* Criterion 4 — The skill delegates lifecycle decisions to EntryService
  instead of reimplementing them in prose; the integration entry point is
  ``EntryService.dispatch()``, not hand-written conditionals.
"""

import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.entry import (
    Decision,
    Disposition,
    EntryService,
    EntryState,
    MappingEntryAdapter,
    ObjectEntryAdapter,
    StartIntent,
    state_digest,
)

# ── Hermetic fixture — same facts, two access paths ────────────────────────

_FACTS = {
    "run_id": "sw-156-run",
    "phase": "build",
    "run_state": "in_progress",
    "onboarding_state": "complete",
    "installed_skills": ["skillweave-lifecycle", "skillweave-releasechain"],
    "active_skill": "skillweave-lifecycle",
}


class _RunRecord:
    """A run record whose attributes mirror the fact keys."""

    def __init__(self, **kwargs: str | list[str] | None) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAdapterEquivalence:
    """MappingEntryAdapter and ObjectEntryAdapter agree on identical facts."""

    def setup_method(self) -> None:
        self.mapping_adapter = MappingEntryAdapter(facts=_FACTS)
        self.object_adapter = ObjectEntryAdapter(source=_RunRecord(**_FACTS))
        self.service = EntryService()

    def test_state_digests_match(self) -> None:
        """Both adapters produce the same state digest."""
        mapping_digest = state_digest(self.mapping_adapter.observe())
        object_digest = state_digest(self.object_adapter.observe())
        assert mapping_digest == object_digest

    def test_state_values_match(self) -> None:
        """Both adapters produce identical EntryState values."""
        mapping_state: EntryState = self.mapping_adapter.observe()
        object_state: EntryState = self.object_adapter.observe()
        assert mapping_state == object_state

    def test_dispatch_digests_match(self) -> None:
        """Both adapters produce the same Decision.digest for the same intent."""
        intent = StartIntent.of("sw-156-run")
        mapping_decision: Decision = self.service.dispatch(intent, self.mapping_adapter)
        object_decision: Decision = self.service.dispatch(intent, self.object_adapter)
        assert mapping_decision.digest == object_decision.digest

    def test_dispatch_disposition_matches(self) -> None:
        """Both adapters agree on EXECUTE for a coherent start intent."""
        intent = StartIntent.of("sw-156-run")
        mapping_decision = self.service.dispatch(intent, self.mapping_adapter)
        object_decision = self.service.dispatch(intent, self.object_adapter)
        assert mapping_decision.disposition is Disposition.EXECUTE
        assert object_decision.disposition is Disposition.EXECUTE
        assert mapping_decision.reasons == object_decision.reasons == ()

    def test_dispatch_guidance_empty_on_execute(self) -> None:
        """EXECUTE decisions carry no guidance text (by contract)."""
        intent = StartIntent.of("sw-156-run")
        decision = self.service.dispatch(intent, self.mapping_adapter)
        assert decision.disposition is Disposition.EXECUTE
        assert not decision.guidance
        assert not decision.reasons
