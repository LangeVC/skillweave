"""Council live roster gate — distinct seats + chairman, full matrix (SW1311-COUNCIL-001).

A live gate (NOT part of the hermetic suite) that measures, against a running
Faidate, whether the council's declared seats resolve to provider-native roster
ids that answer as themselves — using the response envelope's ``model`` field as
the single source of truth. The ``ROUTER_PROFILES`` cast stays symbolic (the
routing lane's contract); each seat resolves through ``resolve_council_seats``
at the query boundary, and the gate proves the resolved set holds the ``>=2``
distinct answering-model gate live.

Contracts enforced here (criterion 6):

* requests at least two distinct seats, plus the configured chairman when the
  preset runs full mode with a chairman;
* records the complete requested→resolved→answering matrix per seat;
* fails (non-zero) when Faidate is unreachable, or when the minimum distinct
  answering-model count is not met, or when every seat is substituted.

Reproducible:  python3 tests/gate_b06/council_live_roster_proof.py
The Faidate address is ``FAIGATE_BASE_URL`` (default ``http://127.0.0.1:8090/v1``).
"""

import asyncio
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from skillweave.routing.faigate_adapter import (  # noqa: E402
    ROUTER_PROFILES,
    FaigateProvider,
    resolve_council_seats,
)

MIN_DISTINCT_SEATS = 2


def _seats_for_preset(preset: dict) -> list[str]:
    """The seats a preset casts: its models plus its chairman (if full mode)."""
    seats = list(preset["models"])
    if preset.get("mode") == "full" and preset.get("chairman"):
        seats.append(preset["chairman"])
    return seats


def main() -> int:
    base_url = os.environ.get("FAIGATE_BASE_URL", "http://127.0.0.1:8090/v1")
    provider = FaigateProvider(base_url=base_url)

    # Use the default preset's declared seats, deduplicated, order-stable. The
    # declared ids are symbolic seat intents; each resolves to a provider-native
    # roster id before the query (the cast itself stays symbolic).
    preset = ROUTER_PROFILES["default"]
    declared = []
    seen = set()
    for mid in _seats_for_preset(preset):
        if mid not in seen:
            seen.add(mid)
            declared.append(mid)

    seats = resolve_council_seats(declared)

    # Resolve each declared seat to its provider-native roster id, keeping the
    # positional pairing declared[i] -> seats[i] for the truth matrix.
    pairs = list(zip(declared, seats))

    # The gate must request at least two distinct resolved seats.
    distinct_seats = len(set(seats))
    print(f"Faidate: {base_url}")
    print(f"declared ({', '.join(declared)}) -> resolved "
          f"({distinct_seats} distinct): {', '.join(seats)}")
    if distinct_seats < MIN_DISTINCT_SEATS:
        print(f"FAIL: fewer than {MIN_DISTINCT_SEATS} distinct seats requested.")
        return 1

    async def probe_one(declared_mid: str, native: str):
        messages = [{"role": "user", "content": "Reply with exactly one word."}]
        try:
            response = await provider.query(native, messages, temperature=0.0, timeout=15.0)
            answering = getattr(response, "answering_model", None)
            requested = getattr(response, "requested_model", None) or native
            return {
                "declared": declared_mid,
                "requested": requested,
                "resolved": native,
                "answering": answering,
                "status": "substituted" if answering and answering != requested else "answered",
            }
        except Exception as e:  # noqa: BLE001 — a live gate reports every seat
            return {
                "declared": declared_mid,
                "requested": native,
                "resolved": native,
                "answering": None,
                "status": f"error: {type(e).__name__}",
            }

    async def run_all():
        return [await probe_one(d, n) for d, n in pairs]

    try:
        rows = asyncio.run(run_all())
    except Exception as e:  # noqa: BLE001
        print(f"\nFAIL: unreachable or unhandled: {e}")
        return 1

    # If every seat errored, Faidate is unreachable — a live gate that "passes"
    # without a live model is not a pass.
    if all(r["status"].startswith("error:") for r in rows):
        print("\nFAIL: no seat answered; Faigate may be unreachable.")
        for r in rows:
            print(f"  {r['requested']:<22} -> {r['status']}")
        return 1

    print("\ndeclared -> requested -> resolved -> answering -> status")
    for r in rows:
        print(
            f"  {r['declared']:<14} -> {r['requested']:<22} -> {r['resolved']:<22} -> "
            f"{str(r['answering']):<22} -> {r['status']}"
        )

    answered = [r for r in rows if r["status"] == "answered"]
    distinct_answering = {r["answering"] for r in answered}
    print(f"\nseats: {len(rows)}, answered: {len(answered)}, "
          f"distinct answering: {len(distinct_answering)}")

    if len(distinct_answering) < MIN_DISTINCT_SEATS:
        print(f"FAIL: minimum distinct answering-model contract "
              f"({MIN_DISTINCT_SEATS}) unmet.")
        return 1

    substitutions = [r for r in rows if r["status"] == "substituted"]
    if substitutions:
        print(f"NOTE: {len(substitutions)} substituted seat(s) recorded via the model field.")
    print("PASS: >=2 distinct seats answered; full requested->answering matrix recorded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
