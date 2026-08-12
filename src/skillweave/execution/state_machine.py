from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from skillweave.runtime.store import RunStore, SQLiteRunStore, RunRecord, RunStateModel
from skillweave.runtime.errors import InvalidTransitionError, VersionConflictError


class RalphLoopState(str, Enum):
    PREFLIGHT = "preflight"
    BATCH_SELECTION = "batch_selection"
    LANE_PLAN = "lane_plan"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    REVIEW_GATE = "review_gate"
    FIX_RETRY = "fix_retry"
    INTEGRATE = "integrate"
    ADVANCE_OR_STOP = "advance_or_stop"


@dataclass
class RalphLoopTransition:
    from_state: RalphLoopState
    to_state: RalphLoopState
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class RalphLoopStateMachine:
    STATES = list(RalphLoopState)

    TRANSITIONS: dict[RalphLoopState, list[RalphLoopState]] = {
        RalphLoopState.PREFLIGHT: [RalphLoopState.BATCH_SELECTION],
        RalphLoopState.BATCH_SELECTION: [RalphLoopState.LANE_PLAN, RalphLoopState.ADVANCE_OR_STOP],
        RalphLoopState.LANE_PLAN: [RalphLoopState.IMPLEMENT],
        RalphLoopState.IMPLEMENT: [RalphLoopState.VERIFY],
        RalphLoopState.VERIFY: [RalphLoopState.REVIEW_GATE, RalphLoopState.FIX_RETRY],
        RalphLoopState.REVIEW_GATE: [RalphLoopState.INTEGRATE, RalphLoopState.FIX_RETRY, RalphLoopState.ADVANCE_OR_STOP],
        RalphLoopState.FIX_RETRY: [RalphLoopState.IMPLEMENT, RalphLoopState.REVIEW_GATE, RalphLoopState.ADVANCE_OR_STOP],
        RalphLoopState.INTEGRATE: [RalphLoopState.VERIFY, RalphLoopState.ADVANCE_OR_STOP],
        RalphLoopState.ADVANCE_OR_STOP: [],
    }

    def __init__(self):
        self.current_state: RalphLoopState = RalphLoopState.PREFLIGHT
        self.transitions: list[RalphLoopTransition] = []
        self.history: list[dict[str, Any]] = []

    def can_transition_to(self, target: RalphLoopState) -> bool:
        allowed = self.TRANSITIONS.get(self.current_state, [])
        return target in allowed

    def transition_to(self, target: RalphLoopState, reason: str = "") -> bool:
        if not self.can_transition_to(target):
            return False
        transition = RalphLoopTransition(
            from_state=self.current_state,
            to_state=target,
            reason=reason or f"Transition {self.current_state.value} -> {target.value}",
        )
        self.transitions.append(transition)
        self.history.append({
            "from": self.current_state.value,
            "to": target.value,
            "reason": transition.reason,
            "timestamp": transition.timestamp,
        })
        self.current_state = target
        return True

    def reset(self) -> None:
        self.current_state = RalphLoopState.PREFLIGHT
        self.transitions.clear()
        self.history.clear()

    def is_terminal(self) -> bool:
        return self.current_state == RalphLoopState.ADVANCE_OR_STOP

    def summary(self) -> dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "transition_count": len(self.transitions),
            "is_terminal": self.is_terminal(),
            "history": self.history[-10:] if self.history else [],
        }


class StateHandler(ABC):
    @abstractmethod
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        ...


class StatePreflight(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ready", "checks": context.get("preflight_checks", [])}


class StateBatchSelection(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "selected", "batch": context.get("next_batch", None)}


class StateLanePlan(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "planned", "steps": context.get("lane_steps", [])}


class StateImplement(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "implemented", "results": context.get("implementation_results", {})}


class StateVerify(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "verified", "passed": context.get("verification_passed", False), "findings": context.get("findings", [])}


class StateReviewGate(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "gated", "passed": context.get("gate_passed", False), "verdict": context.get("verdict", "pending")}


class StateFixRetry(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "retrying", "retry_count": context.get("retry_count", 0), "max_retries": context.get("max_retries", 3)}


class StateIntegrate(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "integrated", "merged": context.get("integration_merged", False)}


class StateAdvanceOrStop(StateHandler):
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "complete", "final_state": context.get("final_state", "stopped")}


STATE_HANDLER_MAP: dict[RalphLoopState, StateHandler] = {
    RalphLoopState.PREFLIGHT: StatePreflight(),
    RalphLoopState.BATCH_SELECTION: StateBatchSelection(),
    RalphLoopState.LANE_PLAN: StateLanePlan(),
    RalphLoopState.IMPLEMENT: StateImplement(),
    RalphLoopState.VERIFY: StateVerify(),
    RalphLoopState.REVIEW_GATE: StateReviewGate(),
    RalphLoopState.FIX_RETRY: StateFixRetry(),
    RalphLoopState.INTEGRATE: StateIntegrate(),
    RalphLoopState.ADVANCE_OR_STOP: StateAdvanceOrStop(),
}


def run_state_handler(state, context: dict[str, Any]) -> dict[str, Any]:
    if isinstance(state, str):
        return {"status": "error", "error": f"No handler for state {state}"}
    state_value = state.value if hasattr(state, 'value') else str(state)
    for k, handler in STATE_HANDLER_MAP.items():
        k_val = k.value if hasattr(k, 'value') else str(k)
        if k_val == state_value:
            return handler.execute(context)
    return {"status": "error", "error": f"No handler for state {state_value}"}


class RunStateMachine:
    def __init__(self, store: Optional[RunStore] = None):
        self._store = store or SQLiteRunStore()

    @property
    def store(self) -> RunStore:
        return self._store

    def create_run(
        self,
        run_id: str,
        root_run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        role: str = "ops",
        metadata: Optional[dict[str, Any]] = None,
    ) -> RunRecord:
        now = datetime.now(timezone.utc).isoformat()
        record = RunRecord(
            run_id=run_id,
            root_run_id=root_run_id or run_id,
            parent_run_id=parent_run_id,
            state=RunStateModel.SANDBOX_PREFLIGHT.value,
            version=1,
            created_at=now,
            updated_at=now,
            ended_at=None,
            role=role,
            metadata=metadata or {},
        )
        return self._store.save_run(record)

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        return self._store.get_run(run_id)

    def transition(
        self,
        run_id: str,
        target_state: str,
        expected_state: Optional[str] = None,
        expected_version: Optional[int] = None,
        reason: str = "",
        role: Optional[str] = None,
    ) -> RunRecord:
        record = self._store.get_run(run_id)
        if record is None:
            raise InvalidTransitionError("nonexistent", target_state, run_id)

        actual_expected_state = expected_state if expected_state is not None else record.state
        actual_expected_version = expected_version if expected_version is not None else record.version

        return self._store.transition(
            run_id=run_id,
            target_state=target_state,
            expected_state=actual_expected_state,
            expected_version=actual_expected_version,
            reason=reason,
            role=role,
        )

    def is_terminal(self, run_id: str) -> bool:
        record = self._store.get_run(run_id)
        if record is None:
            return False
        return record.state in (RunStateModel.ADVANCE_OR_STOP.value, RunStateModel.FAILED.value)

    def list_runs(self, state: Optional[str] = None, limit: int = 100) -> list[RunRecord]:
        return self._store.list_runs(state=state, limit=limit)
