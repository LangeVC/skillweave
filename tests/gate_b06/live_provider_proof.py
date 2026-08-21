"""Live provider proof — real Faigate wiring, separate from the unit suite.

SW-UNIT-HERMETIC-001 separates the unit suite from live Faigate. The unit suite
(tests/unit) is hermetic: it blocks every socket and clears provider env vars,
and its routing tests inject a fake provider. This script is the other half of
the split — the proof that the REAL wiring (``detect_providers`` →
``check_availability`` → ``query``) works against a genuinely reachable Faigate.

It is NOT part of ``pytest tests/unit`` and must never be: it opens a real
socket to ``127.0.0.1:${FAIGATE_PORT}`` and, if configured, queries a live
model. Run it deliberately:

    python3 tests/gate_b06/live_provider_proof.py

Exit contract (measured, not a code claim):

* 2  — SKIP: no reachable Faigate (port closed, no key, no tokens file). The
       script is not run on a host with a live provider; this is not a failure.
* 1  — FAIL: a live Faigate is reachable but the real provider path broke.
* 0  — PASS: availability resolution and (when FAIGATE_LIVE_QUERY=1) a real
       query round-trip both succeeded against the live provider.
"""

import asyncio
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from skillweave.routing import faigate_adapter as adapter  # noqa: E402

FAIGATE_HOST = os.environ.get("FAIGATE_HOST", adapter.FAIGATE_DEFAULT_HOST)
FAIGATE_PORT = int(os.environ.get("FAIGATE_PORT", adapter.FAIGATE_DEFAULT_PORT))


def main() -> int:
    print("=== live provider proof (Faigate) ===")
    print(f"HOST={FAIGATE_HOST} PORT={FAIGATE_PORT}")

    # A live provider, not a stub: detect_providers() runs its real probe.
    providers = adapter.detect_providers()
    faigate = providers.get("faigate")
    if faigate is None:
        print(
            f"SKIP: no reachable Faigate at {FAIGATE_HOST}:{FAIGATE_PORT} "
            "(port closed, no API key, no tokens file)."
        )
        print(
            "The unit suite covers routing logic hermetically; this proof "
            "needs a live provider."
        )
        return 2

    print(f"detected: {faigate.provider_name()}")

    # 1. Availability is a real /v1/models round-trip.
    roster = asyncio.run(
        faigate.check_availability(["deepseek-v4-pro", "no-such-model-xyzzy"])
    )
    print(f"availability: {roster}")
    assert isinstance(roster, dict) and set(roster) == {
        "deepseek-v4-pro",
        "no-such-model-xyzzy",
    }, "availability must return a verdict per requested model"

    # 2. A live query round-trip (opt-in: burns a real inference call).
    if os.environ.get("FAIGATE_LIVE_QUERY") == "1":
        model = os.environ.get("FAIGATE_LIVE_MODEL", "deepseek-v4-pro")
        answer = asyncio.run(
            faigate.query(
                model,
                [{"role": "user", "content": "Reply with exactly: OK"}],
                timeout=60.0,
            )
        )
        print(f"query({model}) -> {answer[:120]!r}")
        assert answer and answer.strip(), "live query returned an empty answer"

    print("PASS: live provider wiring works end to end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
