from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional


@dataclass
class RetryBudget:
    max_retries: int = 3
    retry_count: int = 0
    last_error: Optional[str] = None
    last_attempt: Optional[str] = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def record_attempt(self, success: bool, error: Optional[str] = None, metadata: Optional[dict] = None) -> None:
        self.retry_count += 1
        self.last_attempt = datetime.now().isoformat()
        self.history.append({
            "attempt": self.retry_count,
            "success": success,
            "error": error,
            "timestamp": self.last_attempt,
            "metadata": metadata or {},
        })
        if not success:
            self.last_error = error

    def reset(self) -> None:
        self.retry_count = 0
        self.last_error = None
        self.last_attempt = None
        self.history.clear()

    def summary(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "exhausted": not self.can_retry(),
            "last_error": self.last_error,
            "last_attempt": self.last_attempt,
            "history": self.history,
        }


class RetryHandler:
    def __init__(self, max_retries: int = 3, on_exhausted: Optional[Callable] = None):
        self.budget = RetryBudget(max_retries=max_retries)
        self.on_exhausted = on_exhausted

    def execute(self, fn: Callable, *args, **kwargs) -> tuple[bool, Any]:
        while self.budget.can_retry():
            try:
                result = fn(*args, **kwargs)
                self.budget.record_attempt(success=True)
                return True, result
            except Exception as e:
                self.budget.record_attempt(success=False, error=str(e))
                if not self.budget.can_retry():
                    if self.on_exhausted:
                        self.on_exhausted(self.budget)
                    return False, RetryBudgetExhaustedError(self.budget.max_retries)
        return False, RetryBudgetExhaustedError(self.budget.max_retries)


class RetryBudgetExhaustedError(Exception):
    def __init__(self, max_retries: int):
        self.max_retries = max_retries
        super().__init__(f"Retry budget exhausted after {max_retries} attempts")
