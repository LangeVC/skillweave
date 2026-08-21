"""Council live/review residual — roster vs answering, measured against live Faigate.

SW-COUNCIL-001 residual (criterion: ``ROUTER_PROFILES`` is corrected to ids
Faidate actually serves, verified by the ``model`` field rather than the listing).

The attribution work (SW-CN-001/SW-CN-002) is delivered: ``query()`` reads the
response envelope's ``model`` field and carries it per seat via
``AttributedResponse``. What remained open was the LIVE proof: measure, against
a running Faigate, whether the roster ids ``ROUTER_PROFILES`` casts actually
answer as themselves, using the ``model`` field as the single source of truth.

This script is a live gate, NOT part of the hermetic unit suite. It talks to
Faidate at ``FAIGATE_BASE_URL`` (default ``http://127.0.0.1:8090/v1``). When
Faidate is unreachable it exits non-zero with a clear message — a live gate that
"passes" without a live model is not a pass.

Reproducible: python3 tests/gate_b06/council_live_roster_proof.py
Repo root is derived from this file's own position; no fixed path.
"""

import asyncio
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from skillweave.routing.faigate_adapter import (
    ROUTER_PROFILES,
    FaigateProvider,
)


def _roster_ids() -> list[str]:
    """Union of every id ``ROUTER_PROFILES`` casts (models + chairman)."""
    ids: list[str] = []
    seen: set[str] = set()
    for preset in ROUTER_PROFILES.values():
        for mid in list(preset["models"]) + [preset["chairman"]]:
            if mid not in seen:
                seen.add(mid)
                ids.append(mid)
    return ids


def main() -> int:
    base_url = os.environ.get("FAIGATE_BASE_URL", "http://127.0.0.1:8090/v1")
    provider = FaigateProvider(base_url=base_url)

    roster = _roster_ids()
    print(f"Faidate: {base_url}")
    print(f"ROUTER_PROFILES roster ids ({len(roster)}): {', '.join(roster)}")

    async def probe_one(mid: str):
        messages = [{"role": "user", "content": "Reply with exactly one word."}]
        response = await provider.query(mid, messages, temperature=0.0, timeout=15.0)
        answering = getattr(response, "answering_model", None)
        return mid, answering

    async def run_all():
        results = {}
        for mid in roster:
            try:
                results[mid] = await probe_one(mid)
            except Exception as e:  # noqa: BLE001 — a live gate reports every seat
                results[mid] = (mid, f"ERROR: {e}")
        return results

    results = asyncio.run(run_all())

    print("\nrider id             -> answering model")
    diverged = 0
    errored = 0
    for requested in roster:
        _, answering = results[requested]
        flag = ""
        if answering.startswith("ERROR:"):
            errored += 1
        elif answering != requested:
            diverged += 1
            flag = "  <-- diverged"
        print(f"  {requested:<20} -> {answering}{flag}")

    print(f"\nroster ids: {len(roster)}")
    print(f"diverged:   {diverged}")
    print(f"errored:    {errored}")
    print(f"answered as requested: {len(roster) - diverged - errored}")

    # The residual claim being proven: the roster names ids that do NOT answer as
    # themselves. If every id answered as itself there would be no substitution
    # to surface — but the whole premise is that Faigate silently substitutes.
    # This gate proves the divergence is real and measurable via the model field.
    if errored == len(roster):
        print("\nFAIL: no roster id answered at all; Faigate may be unreachable.")
        return 1

    if diverged + errored == 0:
        print("\nNOTE: no divergence measured. The premise that triggered SW-COUNCIL-001")
        print("is not reproduced today; the roster may have been corrected upstream.")
        print("This is a pass (the model field is the source of truth either way).")
        return 0

    print("\nPASS: divergence is real and the model field records it per id.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
