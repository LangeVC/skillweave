from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional


@dataclass
class BinaryGateResult:
    passed: bool
    reason: str
    details: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class GatePolicy:
    def __init__(self, name: str = "default"):
        self.name = name
        self.checks: list[Callable[[], BinaryGateResult]] = []
        self.history: list[BinaryGateResult] = []

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

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "check_count": len(self.checks),
            "total_evaluations": len(self.history),
            "last_result": self.history[-1].to_dict() if self.history else None,
            "passed_ratio": sum(1 for r in self.history if r.passed) / max(len(self.history), 1),
        }
