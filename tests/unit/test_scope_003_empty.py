"""SW-SCOPE-003-R: the real empty run/evidence state is a reproducible negative.

An empty state produces neither a false PASS nor a non-reproducible special
status: it yields the deterministic ``inconclusive`` outcome on every call.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.verify import evaluate_empty_state, GateState


def test_empty_state_is_not_a_pass():
    result = evaluate_empty_state(num_runs=0, num_artifacts=0)
    assert result["gate_state"] != GateState.PASS
    assert result["gate_state"] == GateState.INCONCLUSIVE


def test_empty_state_is_reproducible():
    a = evaluate_empty_state(num_runs=0, num_artifacts=0)
    b = evaluate_empty_state(num_runs=0, num_artifacts=0)
    assert a == b  # deterministic, no non-reproducible special status


def test_empty_evidence_alone_is_not_a_pass():
    result = evaluate_empty_state(num_runs=5, num_artifacts=0)
    assert result["gate_state"] != GateState.PASS


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in _tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
