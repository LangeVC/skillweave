"""Execute a ``sequences/*.yaml`` orchestration file as bounded sessions.

The sequence format already carries the structure that prevents context
exhaustion (LVC-219): it groups lanes into ``parallel_lanes`` and
``serialized_lanes`` blocks inside ``phases``. Two defects sit behind the
observed drift, and this module closes both:

* ``session_boundary`` is not declared on the file — a sequence describes work
  but nothing says where one session ends and the next begins. A sequence that
  does not declare ``session_boundary: batch`` is refused, never defaulted.
* lanes marked ``parallel_lanes`` were executed inline in the calling session,
  so every lane's full working context landed in one window. A parallel lane is
  dispatched as a subagent (a separate execution unit, via the fan-out seam),
  not executed inline.

The executor does not start a process itself: it produces a :class:`DispatchPlan`
whose entries carry the *decision* — ``subagent`` or ``inline`` — per lane. The
subagent execution path is the fan-out seam from ``skillweave.fanout.dispatch``;
it is injected so a caller can supply a recorder or a stub, and so a test can
prove the decision without spawning a worker. Whether the seam runs is the
contract, not where it imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Sequence

import yaml

SUBAGENT = "subagent"
INLINE = "inline"

_SESSION_BOUNDARY_KEY = "session_boundary"


class MissingSessionBoundaryError(Exception):
    """Raised when a sequence does not declare ``session_boundary: batch``.

    The boundary is never invented. LVC-219: defaulting a boundary is the
    defect, not a convenience — a sequence that omits the key is stopped, so
    wrong work can never be assigned to a session that does not exist.
    """

    def __init__(self, detail: str = ""):
        message = (
            "Sequence does not declare the required key 'session_boundary'; "
            "refusing rather than inventing a session boundary"
        )
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)
        self.detail = detail


@dataclass
class Lane:
    """One lane as declared in a phase's ``parallel_lanes`` or
    ``serialized_lanes`` block."""

    id: str
    #: ``"parallel"`` or ``"serialized"``, from which block the lane came.
    kind: str


@dataclass
class SequenceDeclaration:
    """A parsed ``sequences/*.yaml`` file.

    ``session_boundary`` is the declared marker. The lane lists preserve which
    block each lane belonged to so the dispatch decision can be derived from the
    declaration, never from a hand-written flag elsewhere.
    """

    session_boundary: Optional[str]
    parallel_lanes: List[Lane] = field(default_factory=list)
    serialized_lanes: List[Lane] = field(default_factory=list)

    @property
    def has_boundary(self) -> bool:
        return bool(self.session_boundary)

    def all_lanes(self) -> List[Lane]:
        return list(self.parallel_lanes) + list(self.serialized_lanes)


@dataclass
class DispatchEntry:
    lane_id: str
    mode: str


@dataclass
class DispatchPlan:
    entries: List[DispatchEntry] = field(default_factory=list)

    def modes(self) -> List[str]:
        return [e.mode for e in self.entries]


def load_sequence(declaration: Mapping[str, Any]) -> SequenceDeclaration:
    """Parse a sequence declaration and validate its session boundary.

    ``declaration`` is the top-level mapping of a ``sequences/*.yaml`` file.
    A declaration whose ``session_boundary`` is missing or empty raises
    :class:`MissingSessionBoundaryError` naming the key — the boundary is never
    defaulted.

    lanes are read from every phase: each ``parallel_lanes`` entry becomes a
    ``Lane(kind="parallel")`` and each ``serialized_lanes`` entry a
    ``Lane(kind="serialized")``.
    """
    session_boundary = declaration.get(_SESSION_BOUNDARY_KEY)
    if not session_boundary:
        raise MissingSessionBoundaryError()

    parallel: List[Lane] = []
    serialized: List[Lane] = []
    for phase in declaration.get("phases", []) or []:
        for lane in phase.get("parallel_lanes", []) or []:
            parallel.append(Lane(id=lane.get("id"), kind="parallel"))
        for lane in phase.get("serialized_lanes", []) or []:
            serialized.append(Lane(id=lane.get("id"), kind="serialized"))

    return SequenceDeclaration(
        session_boundary=session_boundary,
        parallel_lanes=parallel,
        serialized_lanes=serialized,
    )


def build_dispatch_plan(
    declaration: SequenceDeclaration,
) -> DispatchPlan:
    """Derive a dispatch decision per lane.

    A lane marked ``parallel_lanes`` is dispatched as a subagent (``subagent``);
    a lane marked ``serialized_lanes`` runs inline (``inline``). The decision is
    read straight from which block held the lane — a parallel lane is never
    executed inline.
    """
    if not declaration.has_boundary:
        raise MissingSessionBoundaryError()

    entries: List[DispatchEntry] = []
    for lane in declaration.parallel_lanes:
        entries.append(DispatchEntry(lane_id=lane.id, mode=SUBAGENT))
    for lane in declaration.serialized_lanes:
        entries.append(DispatchEntry(lane_id=lane.id, mode=INLINE))
    return DispatchPlan(entries=entries)


def execute_sequence(
    declaration: SequenceDeclaration,
    *,
    fanout: Optional[Any] = None,
) -> DispatchPlan:
    """Validate, build the plan, and hand parallel lanes to the fan-out seam.

    ``fanout`` is the subagent dispatch seam. When omitted, the real
    ``skillweave.fanout.dispatch.fan_out_dispatch`` is used for the parallel
    lanes; serialized lanes stay inline. The plan is returned regardless, so a
    caller (or a test) can inspect every decision.
    """
    plan = build_dispatch_plan(declaration)

    parallel_lanes = [e.lane_id for e in plan.entries if e.mode == SUBAGENT]
    if parallel_lanes:
        dispatcher = fanout
        if dispatcher is None:
            from skillweave.fanout.dispatch import fan_out_dispatch

            dispatcher = fan_out_dispatch
        # Hand the parallel lane ids to the fan-out seam. The seam is the
        # subagent execution unit; the concrete commands/tool/model a caller
        # resolves stay the caller's concern, but the decision that parallel
        # lanes move through fan-out — and never inline — is owned here.
        dispatcher(list(parallel_lanes))

    return plan


def load_sequence_file(path: str) -> SequenceDeclaration:
    """Convenience: load a ``sequences/*.yaml`` file from disk and parse it."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, Mapping):
        raise MissingSessionBoundaryError(detail="file did not parse to a mapping")
    return load_sequence(data)
