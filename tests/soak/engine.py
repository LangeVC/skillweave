"""Authoritative Soak Test Execution Engine (SW-SOAK-001).

Drives sustained load, resource monitoring, chaos/recovery validation, context token
growth, degradation mode testing, and measurable limit enforcement over multi-hour runs.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import SoakConfig, SoakLimits
from .guard import DoubleStartGuard, DoubleStartPreventedError
from .monitor import ResourceTracker, ResourceLimitExceededError

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# SkillWeave imports
from skillweave.core.context import (
    ContextManager,
    TokenLimitProfile,
    TokenThresholdStatus,
    TaskAdmissionRejected,
    ContextStopLimitExceeded,
    InMemoryCheckpointStore,
)
from skillweave.core.observer.observer import ReadOnlyObserver
from skillweave.core.planning.decomposition import (
    DecompositionPlan,
    DecompositionUnit,
    create_decomposition_plan,
)
from skillweave.core.recovery.manager import RecoveryManager
from skillweave.runtime.store import SQLiteRunStore, RunRecord, RunStateModel
from skillweave.runtime.journal import EventJournal, EventType
from skillweave.runtime.write_scope import WriteSetManager, WriteSetConflictError
from skillweave.coordinator import Coordinator
from skillweave.trace.handoff import (
    ControllerCheckpoint,
    FrozenCandidate,
    build_checkpoint,
    build_ops_handoff,
    reconstruct_next_action,
)
from skillweave_degraded import detect_degraded, DegradedSignal


@dataclass
class SoakReport:
    """Consolidated report from a soak test execution."""

    name: str
    success: bool
    iterations_completed: int
    target_iterations: int
    duration_seconds: float
    target_duration_seconds: float
    summary_metrics: Dict[str, Any]
    limit_violations: List[str]
    recovery_events_verified: int
    context_limits_verified: int
    degradation_events_verified: int
    double_start_prevented_verified: bool
    error_message: Optional[str] = None
    artifacts_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "success": self.success,
            "iterations_completed": self.iterations_completed,
            "target_iterations": self.target_iterations,
            "duration_seconds": round(self.duration_seconds, 2),
            "target_duration_seconds": round(self.target_duration_seconds, 2),
            "summary_metrics": self.summary_metrics,
            "limit_violations": self.limit_violations,
            "recovery_events_verified": self.recovery_events_verified,
            "context_limits_verified": self.context_limits_verified,
            "degradation_events_verified": self.degradation_events_verified,
            "double_start_prevented_verified": self.double_start_prevented_verified,
            "error_message": self.error_message,
            "artifacts_path": self.artifacts_path,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class SoakEngine:
    """Multi-hour soak, load, resource, recovery, and degradation test engine."""

    def __init__(self, config: Optional[SoakConfig] = None) -> None:
        self.config: SoakConfig = config or SoakConfig()
        self.tracker: ResourceTracker = ResourceTracker(self.config.limits)
        self.guard: DoubleStartGuard = DoubleStartGuard(
            lock_path=self.config.lock_file_path,
            tag=self.config.name,
        )
        self._stop_event = threading.Event()
        self._recovery_verified_count = 0
        self._context_verified_count = 0
        self._degradation_verified_count = 0
        self._double_start_verified = False

    def run(self) -> SoakReport:
        """Execute the full soak testing suite with double-start protection and measurable limits."""
        # 1. Double-start prevention check
        self.guard.acquire()
        temp_dir = tempfile.mkdtemp(prefix="sw_soak_run_")

        try:
            # Verify double start is actively prevented
            self._verify_double_start_prevention()

            start_time = time.time()
            end_deadline = start_time + self.config.duration_seconds
            iteration = 0

            logging.info(
                f"Starting SkillWeave Soak Test: {self.config.name} "
                f"(Duration: {self.config.duration_seconds}s, Max Iterations: {self.config.iterations})"
            )

            # Setup test workspace databases
            db_path = os.path.join(temp_dir, "soak_store.db")
            store = SQLiteRunStore(db_path)
            journal = EventJournal(db_path)
            coord = Coordinator(store)
            write_mgr = WriteSetManager()

            # Observer setup
            obs_file = os.path.join(temp_dir, "observer.json")
            with open(obs_file, "w") as f:
                json.dump({"lease": {"id": "soak-lease-1", "owner": "ops"}, "journal_offset": 0}, f)
            observer = ReadOnlyObserver(obs_file)
            recovery_mgr = RecoveryManager(observer)

            # Setup context manager with standard/test profile
            context_mgr = ContextManager(
                session_id=f"soak-session-{int(time.time())}",
                profile=self.config.context_profile,
            )

            # Main soak iteration loop
            while not self._stop_event.is_set() and iteration < self.config.iterations:
                current_time = time.time()
                if current_time >= end_deadline:
                    break

                iteration += 1
                op_start = time.time()

                try:
                    # 1. Load Step: Create & transition run through state machine
                    run_id = f"soak-run-{iteration:06d}"
                    store.create_run(run_id)
                    cur_run = store.get_run(run_id)

                    store.transition(
                        run_id,
                        RunStateModel.BATCH_SELECTION.value,
                        expected_state=RunStateModel.PREFLIGHT.value,
                        expected_version=cur_run.version,
                        role="ops",
                        reason=f"soak iteration {iteration}",
                    )
                    cur_run = store.get_run(run_id)

                    store.transition(
                        run_id,
                        RunStateModel.LANE_PLAN.value,
                        expected_state=RunStateModel.BATCH_SELECTION.value,
                        expected_version=cur_run.version,
                        role="ops",
                        reason="lane advance",
                    )
                    cur_run = store.get_run(run_id)

                    store.transition(
                        run_id,
                        RunStateModel.IMPLEMENT.value,
                        expected_state=RunStateModel.LANE_PLAN.value,
                        expected_version=cur_run.version,
                        role="ops",
                        reason="implementation",
                    )
                    cur_run = store.get_run(run_id)

                    store.transition(
                        run_id,
                        RunStateModel.VERIFY.value,
                        expected_state=RunStateModel.IMPLEMENT.value,
                        expected_version=cur_run.version,
                        role="ops",
                        reason="verification",
                    )
                    cur_run = store.get_run(run_id)

                    store.transition(
                        run_id,
                        RunStateModel.REVIEW_GATE.value,
                        expected_state=RunStateModel.VERIFY.value,
                        expected_version=cur_run.version,
                        role="ops",
                        reason="review gate",
                    )
                    cur_run = store.get_run(run_id)

                    store.transition(
                        run_id,
                        RunStateModel.ADVANCE_OR_STOP.value,
                        expected_state=RunStateModel.REVIEW_GATE.value,
                        expected_version=cur_run.version,
                        role="ops",
                        reason="soak pass",
                    )

                    # Journal entry
                    journal.append(
                        run_id,
                        event_type=EventType.GATE_EVALUATION.value,
                        payload={"iteration": iteration, "status": "completed"},
                    )

                    # Scope locking exercise
                    worker_id = f"worker-{iteration % 10}"
                    scope_path = f"src/module_{iteration % 5}"
                    write_mgr.declare(worker_id, [scope_path])
                    write_mgr.release(worker_id)

                    # Coordinator progress
                    coord.ensure_root("soak-seq-1", "wave-1", "W1-L1", role="ops")
                    c_curs = coord.load("soak-seq-1", "wave-1")
                    if c_curs:
                        coord.advance("soak-seq-1", "wave-1", f"node-{iteration}", role="ops", expected_version=c_curs.version)

                    # 2. Context Limits Step: Exercise token accumulation and checkpointing
                    self._exercise_context_limits(context_mgr, iteration)

                    # 3. Chaos & Recovery Step (periodic)
                    if self.config.enable_recovery_testing and (iteration % self.config.chaos_interval_iterations == 0):
                        self._exercise_recovery(recovery_mgr, iteration)

                    # 4. Degradation Testing Step (periodic)
                    if self.config.enable_degradation_testing and (iteration % (self.config.chaos_interval_iterations * 2) == 0):
                        self._exercise_degradation(iteration)

                    self.tracker.record_op(time.time() - op_start, success=True)

                except Exception as exc:
                    self.tracker.record_op(time.time() - op_start, success=False)
                    logging.warning(f"Error during soak iteration {iteration}: {exc}")

                # Sample resources periodically
                if iteration % 10 == 0:
                    self.tracker.record_sample()

            # Clean close of store handles
            store.close()

            # Final metrics evaluation
            duration = time.time() - start_time
            self.tracker.record_sample()
            summary = self.tracker.get_summary()
            violations = self.tracker.verify_limits(self.config.limits)

            success = len(violations) == 0 and iteration > 0

            report = SoakReport(
                name=self.config.name,
                success=success,
                iterations_completed=iteration,
                target_iterations=self.config.iterations,
                duration_seconds=duration,
                target_duration_seconds=self.config.duration_seconds,
                summary_metrics=summary,
                limit_violations=violations,
                recovery_events_verified=self._recovery_verified_count,
                context_limits_verified=self._context_verified_count,
                degradation_events_verified=self._degradation_verified_count,
                double_start_prevented_verified=self._double_start_verified,
                artifacts_path=temp_dir,
            )

            # Persist summary report
            report_file = os.path.join(temp_dir, "soak_report.json")
            with open(report_file, "w") as f:
                f.write(report.to_json())

            return report

        finally:
            self.guard.release()

    def _verify_double_start_prevention(self) -> None:
        """Verify that attempting to acquire the active lock immediately raises DoubleStartPreventedError."""
        competing_guard = DoubleStartGuard(
            lock_path=str(self.guard.lock_path),
            tag="competing-instance",
        )
        try:
            competing_guard.acquire(timeout_seconds=0.0)
            raise AssertionError("Competing guard unexpectedly acquired held lock! Double-start prevention failed.")
        except DoubleStartPreventedError:
            self._double_start_verified = True
            logging.info("Double-start prevention verified successfully.")

    def _exercise_context_limits(self, context_mgr: ContextManager, iteration: int) -> None:
        """Simulate context token growth, checkpointing, and threshold gates."""
        profile = context_mgr.profile
        # Evaluate current token state
        tokens_simulated = (iteration * 1500) % (profile.stop_limit + 5000)

        assessment = profile.evaluate(tokens_simulated)
        if assessment.status == TokenThresholdStatus.NO_NEW_TASK:
            # Verify admission rejection
            assert not profile.can_accept_task(tokens_simulated, estimated_task_tokens=5000)
            self._context_verified_count += 1
        elif assessment.status == TokenThresholdStatus.CHECKPOINT_REQUIRED:
            assert profile.should_checkpoint(tokens_simulated)
            # Create checkpoint snapshot
            cp = context_mgr.checkpoint(metadata={"description": f"soak-cp-{iteration}"})
            assert cp.checkpoint_id is not None
            self.tracker.record_context_checkpoint()
            self._context_verified_count += 1
        elif assessment.status == TokenThresholdStatus.STOP:
            assert profile.should_stop(tokens_simulated)
            self._context_verified_count += 1

    def _exercise_recovery(self, recovery_mgr: RecoveryManager, iteration: int) -> None:
        """Exercise crash recovery kill matrix and state reconstruction."""
        # 1. Execute kill matrix
        matrix = [
            {"target": "worker", "id": f"worker-killed-{iteration}"},
            {"target": "orphan", "id": 99900 + iteration},
            {"target": "coordinator", "id": f"coord-killed-{iteration}"},
        ]
        recovery_mgr.handle_kill_matrix(matrix)

        # 2. State reconstruction without transcripts
        cp = build_checkpoint(
            frozen_candidates=[
                FrozenCandidate(
                    candidate_sha="1111111111111111111111111111111111111111",
                    base_sha="0000000000000000000000000000000000000000",
                )
            ],
            latest_verdict=None,
            accepted_finding_ids=[],
            correction_budgets={"lane-1": 2},
            current_batch=1,
            active_job=False,
        )
        handoff = build_ops_handoff(
            source_receipt_id="rcpt-001",
            base_sha="0000000000000000000000000000000000000000",
            subject_sha="1111111111111111111111111111111111111111",
            allowed_paths=["src/soak"],
            required_inputs=["input1"],
            criteria=["crit1"],
            commands=["pytest"],
        )
        unit = DecompositionUnit(id=f"rec-unit-{iteration}", name="Unit", role="ops")
        dag = create_decomposition_plan(plan_id=f"plan-{iteration}", objective="Soak Recovery", units=[unit])

        recovery_mgr.reconstruct_state(
            checkpoint=cp,
            handoffs=[handoff],
            gate={"status": "open"},
            claims={"held": []},
            dag=dag,
        )
        assert recovery_mgr.next_action is not None
        self._recovery_verified_count += 1
        self.tracker.record_recovery()

    def _exercise_degradation(self, iteration: int) -> None:
        """Exercise degraded detection and fallback handling."""
        signal = detect_degraded()
        # Degraded signal should be valid dataclass
        assert isinstance(signal, DegradedSignal)
        self._degradation_verified_count += 1
        self.tracker.record_degradation()
