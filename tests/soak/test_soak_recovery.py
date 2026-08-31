"""Recovery and crash resilience tests under soak conditions (SW-SOAK-001 / SW-RECOVERY-001).

Validates crash recovery, orphan handling, kill matrix execution, zero-transcript state
reconstruction, and cold coordinator resumes across sustained soak cycles.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.core.observer.observer import ReadOnlyObserver
from skillweave.core.planning.decomposition import (
    DecompositionPlan,
    DecompositionUnit,
    create_decomposition_plan,
)
from skillweave.core.recovery.manager import RecoveryManager
from skillweave.coordinator import Coordinator
from skillweave.runtime.store import SQLiteRunStore
from skillweave.trace.handoff import (
    ControllerCheckpoint,
    FrozenCandidate,
    build_checkpoint,
    build_ops_handoff,
    build_review_handoff,
    build_correction_handoff,
    reconstruct_next_action,
)
from skillweave.trace.review import ReviewVerdict


class TestSoakRecovery:
    """Crash recovery and state reconstruction tests during soak runs."""

    def test_kill_matrix_scenarios_during_soak(self):
        """Execute complex kill matrix crash scenarios repeatedly to verify recovery handling."""
        with tempfile.TemporaryDirectory() as tmp:
            obs_file = os.path.join(tmp, "observer_recovery.json")
            with open(obs_file, "w") as f:
                json.dump({"lease": {"id": "lease-rec-1", "owner": "ops"}, "journal_offset": 10}, f)

            observer = ReadOnlyObserver(obs_file)
            recovery_mgr = RecoveryManager(observer)

            for round_num in range(25):
                kill_matrix = [
                    {"target": "worker", "id": f"worker-crashed-{round_num}-a"},
                    {"target": "orphan", "id": 80000 + round_num},
                    {"target": "coordinator", "id": f"coord-died-{round_num}"},
                    {"target": "worker", "id": f"worker-crashed-{round_num}-b"},
                ]
                # Must handle kill matrix gracefully without raising unhandled errors
                recovery_mgr.handle_kill_matrix(kill_matrix)

    def test_zero_transcript_state_reconstruction_cycle(self):
        """Reconstruct DAG, Gate, Claims, and Next Action from Checkpoint + Observer without Transcripts."""
        with tempfile.TemporaryDirectory() as tmp:
            obs_file = os.path.join(tmp, "observer_recon.json")
            with open(obs_file, "w") as f:
                json.dump({"lease": {"id": "lease-rec-2", "owner": "ops"}, "journal_offset": 42}, f)

            observer = ReadOnlyObserver(obs_file)
            recovery_mgr = RecoveryManager(observer)

            for i in range(20):
                base_sha = "0000000000000000000000000000000000000000"
                subject_sha = f"{i:040x}"
                candidate_sha = f"{i+1:040x}"

                checkpoint = build_checkpoint(
                    frozen_candidates=[
                        FrozenCandidate(candidate_sha=candidate_sha, base_sha=base_sha)
                    ],
                    latest_verdict=ReviewVerdict.REVIEW_FAIL if i % 2 == 0 else ReviewVerdict.REVIEW_PASS,
                    accepted_finding_ids=[f"find-{i}"] if i % 2 == 0 else [],
                    correction_budgets={"lane-1": 3},
                    current_batch=i,
                    active_job=False,
                )

                handoff = (
                    build_correction_handoff(
                        source_receipt_id=f"rcpt-fail-{i}",
                        base_sha=base_sha,
                        subject_sha=subject_sha,
                        allowed_paths=["src/"],
                        required_inputs=["in1"],
                        criteria=["crit1"],
                        commands=["make test"],
                        correction_budget=3,
                    )
                    if i % 2 == 0
                    else build_ops_handoff(
                        source_receipt_id=f"rcpt-pass-{i}",
                        base_sha=base_sha,
                        subject_sha=subject_sha,
                        allowed_paths=["src/"],
                        required_inputs=["in1"],
                        criteria=["crit1"],
                        commands=["make test"],
                    )
                )

                unit = DecompositionUnit(id=f"unit-{i}", name=f"Unit {i}", role="ops")
                dag = create_decomposition_plan(plan_id=f"plan-{i}", objective="Reconstruction", units=[unit])

                recovery_mgr.reconstruct_state(
                    checkpoint=checkpoint,
                    handoffs=[handoff],
                    gate={"open": True, "round": i},
                    claims={"held_locks": [f"scope-{i}"]},
                    dag=dag,
                )

                assert recovery_mgr.dag == dag
                assert recovery_mgr.claims == {"held_locks": [f"scope-{i}"]}
                assert recovery_mgr.next_action is not None
                if i % 2 == 0:
                    assert recovery_mgr.next_action.action == "correct"
                else:
                    assert recovery_mgr.next_action.action in ("integrate", "complete", "dispatch_next_batch")

    def test_coordinator_cold_restart_resume_continuity(self):
        """Simulate coordinator dying mid-run and fresh instance resuming from exact cursor."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "coord_crash.db")

            # Phase 1: Coordinator 1 runs and commits 5 nodes, then dies
            store1 = SQLiteRunStore(db_path)
            coord1 = Coordinator(store1)
            coord1.ensure_root("crash-seq", "wave-1", "LANE-1", role="ops")
            for step in range(1, 6):
                c = coord1.load("crash-seq", "wave-1")
                coord1.advance("crash-seq", "wave-1", f"step-{step}", role="ops", expected_version=c.version)
            store1.close()

            # Phase 2: Coordinator 2 (fresh process instance) starts up cold
            store2 = SQLiteRunStore(db_path)
            coord2 = Coordinator(store2)
            resumed_cursor = coord2.load("crash-seq", "wave-1", role="ops")

            assert resumed_cursor is not None
            assert resumed_cursor.cursor_index == 5
            assert resumed_cursor.committed_nodes == ["step-1", "step-2", "step-3", "step-4", "step-5"]

            # Advance 5 more steps
            for step in range(6, 11):
                c = coord2.load("crash-seq", "wave-1")
                coord2.advance("crash-seq", "wave-1", f"step-{step}", role="ops", expected_version=c.version)

            final_cursor = coord2.load("crash-seq", "wave-1")
            assert final_cursor.cursor_index == 10
            assert len(final_cursor.committed_nodes) == 10
            assert final_cursor.committed_nodes[-1] == "step-10"
            store2.close()
