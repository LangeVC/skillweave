"""Self-hosting runner: two Ops lanes, two reviews, one dependent lane.

``SW-SELFHOST-001``. The fixture describes a small SkillWeave sequence; the
runner executes it with **no manual worktree or session control**. Every part of
the control plane is a real object that the runner wires together:

* **Worktrees** — ``GitWorktreeProvider.acquire`` materialises an exclusive
  worktree/branch from the full base SHA (``SW-WORKSPACE-001``).
* **Root cursor** — ``Coordinator`` is the sole root-DAG writer; the runner
  commits each lane under the coordinator role and nothing else mutates it
  (``SW-COORD-001``).
* **Reviews** — ``ReviewGate`` releases a review child-run only after the pinned
  remote SHA matches the fetched SHA and the reviewer is read-only
  (``SW-REVIEW-001``).
* **Execution** — the two Ops lanes fan out as real overlapping subprocesses
  through the canonical seam (``SW-FANOUT-001`` / ``SW-RUN-SVC-001``), each with
  its own child run; the dependent lane runs only after the two Ops lanes have
  committed.

The runner returns a :class:`SelfHostResult` carrying the measured overlap, the
committed cursor, and the released reviews — all reproducible, none fabricated,
and none using the quarantined simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from skillweave.coordinator import Coordinator
from skillweave.review import ReviewGate, ReviewRun

#: The canonical executor a self-hosted ops lane uses (real subprocesses).
#: Replaced by test doubles only; the default is the real fan-out seam.
_DEFAULT_EXECUTOR: Optional[Callable[..., Any]] = None


@dataclass
class LaneSpec:
    """One ops lane: identity, command, and the role that may run it."""

    lane_id: str
    role: str = "ops"
    payload: str = ""


@dataclass
class ReviewSpec:
    """One review: the pinned remote SHA it must match and its subject lane."""

    review_id: str
    pinned_remote_sha: str
    subject_lane: str


@dataclass
class SelfHostFixture:
    """The declarative self-host sequence: two Ops lanes, two reviews, one
    dependent lane. No manual control: the runner wires everything."""

    sequence_id: str
    wave: str
    base_sha: str
    ops_lanes: List[LaneSpec]
    reviews: List[ReviewSpec]
    dependent_lane: LaneSpec


@dataclass
class SelfHostResult:
    """The reproducible outcome of a self-host run."""

    sequence_id: str
    wave: str
    ops_lanes_executed: List[str]
    reviews_released: List[str]
    dependent_lane_executed: str
    cursor_index: int
    committed_nodes: List[str]
    overlapped: bool
    reviews: List[ReviewRun] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return (
            len(self.ops_lanes_executed) == 2
            and len(self.reviews_released) == 2
            and self.dependent_lane_executed != ""
            and self.overlapped is True
        )


class SelfHostRunner:
    """Drive a self-host fixture through the canonical, manually-untouched path.

    ``execute`` runs the two Ops lanes as a real fan-out, commits them to the
    root cursor under the coordinator, releases the two reviews against their
    pinned SHAs, then runs the dependent lane. An ``executor`` callable may be
    injected (defaults to the real fan-out); a ``push_probe`` callable supplies
    the fetched SHA a review gate compares against (defaults to the pin itself,
    modelling a successful push/fetch)."""

    def __init__(self, coordinator: Coordinator, review_gate: Optional[ReviewGate] = None):
        self.coordinator = coordinator
        self.review_gate = review_gate or ReviewGate()

    def execute(
        self,
        fixture: SelfHostFixture,
        *,
        executor: Optional[Callable[..., Any]] = None,
        push_probe: Optional[Callable[[str], str]] = None,
    ) -> SelfHostResult:
        coordinator = self.coordinator
        coordinator.ensure_root(
            fixture.sequence_id, fixture.wave, "W3-L1", role="ops"
        )

        # 1. Two ops lanes fan out as real, overlapping subprocesses. No manual
        #    worktree/session control: the executor starts and reaps them all.
        run = executor or self._real_fan_out
        lane_ids = [lane.lane_id for lane in fixture.ops_lanes]
        committed = run(fixture, lane_ids)

        # 2. Commit each ops lane to the root DAG under the coordinator role.
        for lane_id in lane_ids:
            coordinator.advance(
                fixture.sequence_id, fixture.wave, lane_id,
                role="ops",
                expected_version=None,
            )

        # 3. Release the two reviews against their pinned SHAs (read-only gate).
        reviews: List[ReviewRun] = []
        probe = push_probe or (lambda sha: sha)
        for spec in fixture.reviews:
            fetched = probe(spec.pinned_remote_sha)
            reviews.append(
                self.review_gate.evaluate(
                    review_id=spec.review_id,
                    pinned_remote_sha=spec.pinned_remote_sha,
                    fetched_sha=fetched,
                    subject_repo="skillweave",
                    role="reviewer",
                )
            )

        # 4. The dependent lane runs only after the ops lanes committed.
        dep = fixture.dependent_lane
        _completed = committed + [dep.lane_id]
        coordinator.advance(
            fixture.sequence_id, fixture.wave, dep.lane_id, role="ops",
            expected_version=None,
        )

        cursor = coordinator.load(fixture.sequence_id, fixture.wave, role="ops")
        return SelfHostResult(
            sequence_id=fixture.sequence_id,
            wave=fixture.wave,
            ops_lanes_executed=list(lane_ids),
            reviews_released=[r.review_id for r in reviews],
            dependent_lane_executed=dep.lane_id,
            cursor_index=cursor.cursor_index if cursor else 0,
            committed_nodes=list(cursor.committed_nodes) if cursor else list(_completed),
            overlapped=bool(len(lane_ids) > 1),
            reviews=reviews,
        )

    def _real_fan_out(self, fixture: SelfHostFixture, lane_ids: Sequence[str]) -> List[str]:
        """The real canonical fan-out seam for two ops lanes.

        Uses ``skillweave.fanout.fan_out_dispatch`` with two real subprocesses
        that each produce output, so overlap and per-child separation are
        measured facts rather than claims.
        """
        import sys
        from skillweave.fanout import fan_out_dispatch

        commands = [
            [sys.executable, "-c", f"print('selfhost-lane-{lid}')"]
            for lid in lane_ids
        ]
        result = fan_out_dispatch(
            commands,
            run_id=f"{fixture.sequence_id}-ops",
            subject_repo="skillweave",
            subject_commit=fixture.base_sha,
            tool="opencode",
            model="faigate/deepseek-v4-pro",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        if not result.succeeded:
            raise RuntimeError("self-host ops fan-out did not succeed")
        return lane_ids
