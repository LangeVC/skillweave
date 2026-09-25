import time
import logging
from typing import Callable, Any, Optional, Dict

class ExecutionPolicy:
    """
    Implements Retry, Backoff, Budget, and Compensation logic as a persistent policy.
    Interacts with Recovery (SW-RECOVERY-001) to ensure restarts do not double-count 
    attempts or budget. Ensures Compensation is idempotent.
    """
    def __init__(self, max_attempts: int = 3, initial_backoff: float = 1.0, max_budget: float = 100.0):
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.max_budget = max_budget
        
        # Persistent state
        self.state = {
            "attempts": 0,
            "budget_used": 0.0,
            "compensation_applied": False
        }

    def load_state(self, state_dict: Dict[str, Any]):
        """
        Load state from a recovery checkpoint to prevent double-counting
        attempts or budget after a crash.
        """
        if state_dict:
            self.state.update(state_dict)

    def dump_state(self) -> Dict[str, Any]:
        """
        Dump state for persistence during a checkpoint.
        """
        return dict(self.state)

    def can_attempt(self, cost: float = 0.0) -> bool:
        if self.state["attempts"] >= self.max_attempts:
            logging.warning("Max attempts reached.")
            return False
        if self.state["budget_used"] + cost > self.max_budget:
            logging.warning("Budget exhausted.")
            return False
        return True

    def record_attempt(self, cost: float = 0.0):
        self.state["attempts"] += 1
        self.state["budget_used"] += cost

    def get_backoff(self) -> float:
        # Exponential backoff
        attempts = self.state["attempts"]
        if attempts <= 1:
            return 0.0
        return self.initial_backoff * (2 ** (attempts - 2))

    def compensate(self, compensation_func: Callable):
        """
        Apply compensation logic idempotently.
        """
        if not self.state.get("compensation_applied", False):
            try:
                compensation_func()
                self.state["compensation_applied"] = True
                logging.info("Compensation applied successfully.")
            except Exception as e:
                logging.error(f"Compensation failed: {e}")
                raise
        else:
            logging.info("Compensation already applied (idempotent).")

    def execute_with_policy(self, func: Callable, compensation_func: Optional[Callable] = None, cost: float = 0.0) -> Any:
        """
        Execute a function applying retry, backoff, budget, and compensation logic.
        """
        while self.can_attempt(cost):
            self.record_attempt(cost)
            backoff_time = self.get_backoff()
            if backoff_time > 0:
                logging.info(f"Applying backoff of {backoff_time}s")
                time.sleep(backoff_time)
                
            try:
                result = func()
                return result
            except Exception as e:
                logging.error(f"Execution failed on attempt {self.state['attempts']}: {e}")
                
        # If we exhausted attempts or budget, apply compensation
        if compensation_func:
            self.compensate(compensation_func)
            
        raise RuntimeError("Execution policy exhausted (budget or max attempts).")
