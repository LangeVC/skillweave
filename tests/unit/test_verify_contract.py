"""SW-EVIDENCE-QUALITY-001 + SW-VERIFY-001: quality never self-assessed high;
completion contract keeps exit-0-empty out of PASS.

Four terminal outcomes — exit 0 with empty output, non-zero exit, signal
termination, and timeout — must never be automatically graded "high", and exit
0 with empty/wrong output must land in ``inconclusive``/``failed``, never gate
PASS.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.verify import Verifier, CompletionContract, GateState
from skillweave.runtime.registry import EvidenceQuality
import skillweave.routing.dispatch as dispatch


def _artifact_quality_defaults_unassessed():
    import inspect
    src = inspect.getsource(dispatch._artifact_for)
    return "high" not in src and "unassessed" in src


def test_dispatch_artifact_quality_is_never_self_declared_high():
    receipt = dispatch._artifact_for(
        run_id="r",
        tool="t",
        command=["echo"],
        subject_repo="repo",
        subject_commit="sha",
        created_at="t",
        stdout=b"any output",
        exit_code=0,
        signal=None,
        timeout=None,
        termination="exited",
    )
    q = receipt.quality
    for axis in ("relevance", "sufficiency", "reliability", "integrity"):
        assert getattr(q, axis) != "high", f"{axis} must not self-declare high"
    assert _artifact_quality_defaults_unassessed() is True


def test_exit_zero_empty_output_is_inconclusive_not_pass():
    v = Verifier()
    result = v.assess("evd-1", exit_code=0, signal=None, termination="exited", stdout=b"")
    assert result.grade == "inconclusive"
    assert result.gate_state == GateState.INCONCLUSIVE
    assert result.gate_state != GateState.PASS


def test_exit_zero_wrong_output_is_inconclusive_not_pass():
    v = Verifier()
    result = v.assess(
        "evd-1", exit_code=0, signal=None, termination="exited",
        stdout=b"garbage", check_output=lambda out: b"EXPECTED" in out,
    )
    assert result.gate_state == GateState.INCONCLUSIVE


def test_nonzero_exit_is_failed_not_high():
    v = Verifier()
    result = v.assess("evd-1", exit_code=1, signal=None, termination="exited", stdout=b"x")
    assert result.gate_state == GateState.FAIL
    assert result.grade != "high"


def test_signal_is_failed_not_high():
    v = Verifier()
    result = v.assess("evd-1", exit_code=None, signal=15, termination="signaled", stdout=b"")
    assert result.gate_state == GateState.FAIL
    assert result.grade != "high"


def test_timeout_is_failed_not_high():
    v = Verifier()
    result = v.assess("evd-1", exit_code=None, signal=None, termination="timed_out", stdout=b"")
    assert result.gate_state == GateState.FAIL
    assert result.grade != "high"


def test_clean_nonempty_output_is_the_only_pass():
    v = Verifier()
    result = v.assess("evd-1", exit_code=0, signal=None, termination="exited", stdout=b"ok")
    assert result.gate_state == GateState.PASS
    assert result.grade == "high"


def test_verifier_receipt_is_separate_and_provenance_bound():
    v = Verifier()
    result = v.assess("evd-subject", exit_code=0, signal=None, termination="exited", stdout=b"ok")
    receipt = result.to_receipt(digest="d" * 64)
    assert receipt["artifact_id"] == "verify-evd-subject"
    assert receipt["artifact_id"] != "evd-subject"
    assert receipt["subject_artifact_id"] == "evd-subject"
    assert receipt["verified_by"] == "verifier"
    assert receipt["sha256"] == "d" * 64


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
