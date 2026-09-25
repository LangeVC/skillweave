import logging
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)

class DecisionScope(Enum):
    IN_SCOPE = auto()
    OUT_OF_SCOPE = auto()

class ActionType(Enum):
    REVERSIBLE = auto()
    IRREVERSIBLE = auto()

class EscalationRequired(Exception):
    """Raised when a decision requires escalation (out-of-scope or irreversible)."""
    pass

class OperatorAgent:
    """
    An agent that operates within a delegated decision scope.
    It can run reversible, in-scope decisions autonomously.
    Any decision that is irreversible or out-of-scope will escalate
    immediately without mutating state.
    """

    def __init__(self, name: str, delegated_scope: Set[str] = None):
        self.name = name
        self.delegated_scope = delegated_scope or set()
        self.state: Dict[str, Any] = {}

    def run_decision(
        self,
        decision_id: str,
        action_type: ActionType,
        action_func: Callable[[], Any]
    ) -> Any:
        """
        Runs a decision if it is in-scope and reversible.
        Escalates if the decision is irreversible or out-of-scope.
        """
        # Determine scope
        scope = self._check_scope(decision_id)

        # Escalate immediately if out of scope or irreversible
        if scope == DecisionScope.OUT_OF_SCOPE or action_type == ActionType.IRREVERSIBLE:
            self._escalate(decision_id, scope, action_type)

        # Execute if safe (in-scope and reversible)
        logger.info(f"[{self.name}] Executing safe decision: {decision_id}")
        return action_func()

    def _check_scope(self, decision_id: str) -> DecisionScope:
        if decision_id in self.delegated_scope:
            return DecisionScope.IN_SCOPE
        return DecisionScope.OUT_OF_SCOPE

    def _escalate(self, decision_id: str, scope: DecisionScope, action_type: ActionType):
        msg = (
            f"Escalation required for decision '{decision_id}'. "
            f"Scope: {scope.name}, Type: {action_type.name}"
        )
        logger.warning(f"[{self.name}] {msg}")
        raise EscalationRequired(msg)
