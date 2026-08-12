from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from skillweave.runtime.authority import (
    AuthorityGuard, AuthorityError, Role, can_approve_gate,
    can_mutate_run_state, HumanApproval,
)
import hashlib


@dataclass
class BinaryGateResult:
    passed: bool
    reason: str
    details: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approver_role: Optional[str] = None
    approver_actor: Optional[str] = None
    evaluation_level: str = "node_completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "details": self.details,
            "timestamp": self.timestamp,
            "approver_role": self.approver_role,
            "approver_actor": self.approver_actor,
            "evaluation_level": self.evaluation_level,
        }


class GatePolicy:
    def __init__(self, name: str = "default", authority: Optional[AuthorityGuard] = None):
        self.name = name
        self.checks: list[Callable[[], BinaryGateResult]] = []
        self.history: list[BinaryGateResult] = []
        self._authority = authority or AuthorityGuard()

    def add_check(self, check_fn: Callable[[], BinaryGateResult]) -> None:
        self.checks.append(check_fn)

    def evaluate(self) -> BinaryGateResult:
        failures: list[str] = []
        for check in self.checks:
            result = check()
            self.history.append(result)
            if not result.passed:
                failures.append(result.reason)
                if result.details:
                    failures.extend(result.details)
        if failures:
            return BinaryGateResult(passed=False, reason="; ".join(failures))
        return BinaryGateResult(passed=True, reason=f"Gate '{self.name}' passed all checks")

    def evaluate_binary(self, conditions: list[tuple[bool, str]]) -> BinaryGateResult:
        failures = [reason for passed, reason in conditions if not passed]
        if failures:
            result = BinaryGateResult(passed=False, reason="; ".join(failures))
        else:
            result = BinaryGateResult(passed=True, reason=f"Gate '{self.name}' passed all binary conditions")
        self.history.append(result)
        return result

    def evaluate_with_approval(
        self,
        conditions: list[tuple[bool, str]],
        approver_role: str,
        approver_actor: str,
        scope: str,
        policy_digest: Optional[str] = None,
    ) -> BinaryGateResult:
        capabilities = self._authority.get_capabilities(approver_role)
        if not capabilities.get("can_approve_gate", False):
            raise AuthorityError(
                approver_role, "approve_gate",
                f"Role '{approver_role}' cannot approve gates",
                {"scope": scope},
            )

        failures = [reason for passed, reason in conditions if not passed]
        if failures:
            result = BinaryGateResult(
                passed=False,
                reason="; ".join(failures),
                approver_role=approver_role,
                approver_actor=approver_actor,
            )
        else:
            result = BinaryGateResult(
                passed=True,
                reason=f"Gate '{self.name}' passed all binary conditions — approved by {approver_role}/{approver_actor}",
                approver_role=approver_role,
                approver_actor=approver_actor,
            )
        self.history.append(result)
        return result

    def prevent_self_approval(self, actor_role: str, gate_scope: str) -> bool:
        if actor_role == Role.OPS.value:
            raise AuthorityError(
                actor_role, "approve_gate",
                "Ops role cannot self-approve — separation of duties",
                {"scope": gate_scope},
            )
        return True

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "check_count": len(self.checks),
            "total_evaluations": len(self.history),
            "last_result": self.history[-1].to_dict() if self.history else None,
            "passed_ratio": sum(1 for r in self.history if r.passed) / max(len(self.history), 1),
        }
