"""Verification and completion contract (SW-VERIFY-001, SW-EVIDENCE-QUALITY-001).

A dispatch result's raw output never *self-assesses* as high quality. Evidence
starts ``unassessed`` and can only be promoted to an assessed grade by a
separate verifier whose receipt carries its own provenance (its own
``artifact_id``, producer identity, and a back-reference to the subject
receipt it assessed). A completion contract additionally decides gate state:
exit 0 with empty or wrong output is ``inconclusive`` or ``failed``, never a
gate PASS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


#: The only quality grade a producer may self-declare. Anything higher is the
#: exclusive output of a separate verifier.
UNASSESSED = "unassessed"


class GateState(str):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


@dataclass
class CompletionContract:
    """Decide the gate state of one dispatch outcome, fail-closed on emptiness.

    ``exit_code == 0`` with empty output (or output that fails a provided
    check) yields ``inconclusive``, never ``pass``. A non-zero exit or signal
    yields ``fail``. A clean exit with non-empty, check-passing output yields
    ``pass``.
    """

    def evaluate(
        self,
        *,
        exit_code: Optional[int],
        signal: Optional[int],
        termination: str,
        stdout: bytes,
        check_output: Optional[Any] = None,
    ) -> str:
        if termination != "exited" or signal is not None:
            return GateState.FAIL
        if exit_code != 0:
            return GateState.FAIL
        if not stdout or not stdout.strip():
            return GateState.INCONCLUSIVE
        if check_output is not None and not check_output(stdout):
            return GateState.INCONCLUSIVE
        return GateState.PASS


@dataclass
class VerificationResult:
    """A separate verifier's independent assessment of a subject receipt.

    ``subject_artifact_id`` provenance-binds this verdict to the exact receipt
    it assessed; the verifier receipt itself is a distinct artifact bearing the
    verifier's own identity and digest, never the producer's self-claim.
    """

    subject_artifact_id: str
    grade: str
    gate_state: str
    reasons: list[str] = field(default_factory=list)
    verified_by: str = "verifier"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_receipt(self, *, digest: str) -> dict[str, Any]:
        return {
            "artifact_id": f"verify-{self.subject_artifact_id}",
            "sha256": digest,
            "subject_artifact_id": self.subject_artifact_id,
            "grade": self.grade,
            "gate_state": self.gate_state,
            "verified_by": self.verified_by,
            "created_at": self.created_at,
            "reasons": self.reasons,
        }


class Verifier:
    """Assess a subject receipt independently of its producer.

    The verifier decides the grade (``unassessed`` -> ``assessed``/``high`` or a
    negative grade) and the gate state. It never trusts the subject's
    self-declared quality: grade derives from the verifier's own call to the
    completion contract, and the result is a separate, provenance-bound receipt.
    """

    def assess(
        self,
        subject_artifact_id: str,
        *,
        exit_code: Optional[int],
        signal: Optional[int],
        termination: str,
        stdout: bytes,
        check_output: Optional[Any] = None,
    ) -> VerificationResult:
        contract = CompletionContract()
        gate_state = contract.evaluate(
            exit_code=exit_code,
            signal=signal,
            termination=termination,
            stdout=stdout,
            check_output=check_output,
        )
        reasons: list[str] = []
        if gate_state == GateState.PASS:
            grade = "high"
        elif gate_state == GateState.INCONCLUSIVE:
            grade = "inconclusive"
            reasons.append("exit 0 but empty or failing output")
        else:
            grade = "failed"
            if signal is not None:
                reasons.append(f"terminated by signal {signal}")
            elif termination != "exited":
                reasons.append(f"termination={termination}")
            else:
                reasons.append(f"non-zero exit {exit_code}")

        return VerificationResult(
            subject_artifact_id=subject_artifact_id,
            grade=grade,
            gate_state=gate_state,
            reasons=reasons,
        )


def evaluate_empty_state(*, num_runs: int, num_artifacts: int) -> dict[str, Any]:
    """Deterministically grade an empty run/evidence state.

    An empty state (no runs, no artifacts) is a reproducible negative outcome:
    it yields ``inconclusive`` — never a gate PASS — and the same result on
    every call, with no ad-hoc or non-reproducible special status. A
    non-empty state is graded ``insufficient`` until the completion contract
    sees actual evidence.
    """
    if num_runs == 0 and num_artifacts == 0:
        return {
            "gate_state": GateState.INCONCLUSIVE,
            "reason": "empty run/evidence state",
        }
    return {
        "gate_state": GateState.INCONCLUSIVE,
        "reason": "insufficient evidence",
    }
