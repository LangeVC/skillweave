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

The lower half of the module is the cold-session resume path (FFR-700-2,
dispatch 2). A sequence is split into batches and every batch is a session
boundary; a cold session receives the *state file* alone — :class:`SessionState`
— and from it executes exactly one batch. A second batch in the same session is
refused (:class:`SessionConsumedError`), and a state file that omits
``session_boundary`` is refused the same way a sequence is.
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


# --- Cold-session resume: one batch from the state file alone (FFR-700-2) ---
#
# A sequence is split into batches, and every batch is a session boundary.
# A cold session does not receive the sequence, the PRD, or a transcript: it
# receives the *state file* and nothing else. From that file it derives exactly
# one batch of work, executes it, and then refuses to run a second batch in the
# same session. The boundary is read from the state file too — a state file
# that does not declare ``session_boundary: batch`` is refused, never defaulted
# (the same refusal as ``load_sequence``, now applied to the resume path).


class SessionConsumedError(Exception):
    """Raised when a session that already executed its one batch is run again.

    A session is a single batch of work. Running a second batch in the same
    session is refused rather than silently serialised: the whole point of the
    boundary is that each batch gets a fresh session.
    """

    def __init__(self, batch_index: int):
        self.batch_index = batch_index
        super().__init__(
            f"session already executed batch {batch_index}; "
            "refusing to run a second batch in the same session"
        )


class SessionExecutionError(Exception):
    """Raised when a session cannot execute its batch without a required seam.

    The fan-out seam (subagent lanes) and the inline seam (serialized lanes)
    are injected, as in ``execute_sequence``. A session asked to run lanes of a
    kind whose seam was not supplied fails rather than importing a mismatched
    runner behind the caller's back.
    """

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(f"session cannot execute its batch: {detail}")


@dataclass
class BatchCommand:
    """One lane's work inside a batch: its role and the argv to run."""

    lane_id: str
    mode: str
    command: List[str]


@dataclass
class SessionState:
    """The state file a cold session resumes from — and nothing else.

    It carries the ``session_boundary`` (required, refused when missing), the
    index of the single batch this session may run, and that batch's lane
    commands. A session resumed from this data alone knows what to execute and
    where the boundary lies; it never sees the sequence, the PRD, or a
    transcript.
    """

    session_boundary: Optional[str]
    batch_index: int
    commands: List[BatchCommand] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SessionState":
        boundary = data.get(_SESSION_BOUNDARY_KEY)
        if not boundary:
            raise MissingSessionBoundaryError()
        commands = [
            BatchCommand(
                lane_id=str(c["lane_id"]),
                mode=str(c["mode"]),
                command=[str(a) for a in c.get("command", [])],
            )
            for c in (data.get("commands") or [])
        ]
        return cls(
            session_boundary=boundary,
            batch_index=int(data.get("batch_index", 0)),
            commands=commands,
        )

    def to_dict(self) -> dict:
        return {
            _SESSION_BOUNDARY_KEY: self.session_boundary,
            "batch_index": self.batch_index,
            "commands": [
                {"lane_id": c.lane_id, "mode": c.mode, "command": list(c.command)}
                for c in self.commands
            ],
        }


def load_state_file(path: str) -> SessionState:
    """Load the state file a cold session receives.

    The file is read as YAML and parsed into :class:`SessionState`. A file
    whose ``session_boundary`` is missing or empty raises
    :class:`MissingSessionBoundaryError` — the boundary is never invented on
    the resume path either.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, Mapping):
        raise MissingSessionBoundaryError(
            detail="state file did not parse to a mapping"
        )
    return SessionState.from_dict(data)


@dataclass
class SessionRun:
    """The outcome of one batch: which lanes ran where, and which ran inline."""

    batch_index: int
    subagent_lane_ids: List[str]
    inline_lane_ids: List[str]

    @property
    def ran_any(self) -> bool:
        return bool(self.subagent_lane_ids or self.inline_lane_ids)


@dataclass
class Session:
    """A cold session bound to exactly one batch, resumed from the state file.

    ``run`` executes the state's single batch — subagent lanes through the
    fan-out seam, serialized lanes inline — and then marks the session consumed.
    A second ``run`` raises :class:`SessionConsumedError`. The session reads
    only ``SessionState``: no sequence, no PRD, no transcript.
    """

    state: SessionState
    _consumed: bool = False

    def run(
        self,
        *,
        fanout: Optional[Any] = None,
        inline: Optional[Any] = None,
    ) -> SessionRun:
        if self._consumed:
            raise SessionConsumedError(self.state.batch_index)
        if not self.state.session_boundary:
            raise MissingSessionBoundaryError()

        subagent_ids = [c.lane_id for c in self.state.commands if c.mode == SUBAGENT]
        inline_ids = [c.lane_id for c in self.state.commands if c.mode == INLINE]

        if subagent_ids and fanout is None:
            raise SessionExecutionError(
                "subagent lanes present but no fan-out seam supplied"
            )
        if inline_ids and inline is None:
            raise SessionExecutionError(
                "serialized lanes present but no inline seam supplied"
            )

        if subagent_ids:
            # Hand the subagent lanes' commands to the fan-out seam — each is a
            # real command, so the seam's execution is the batch's execution.
            # The seam itself is injected (as in ``execute_sequence``): who runs
            # a subagent and how is the caller's concern; that it ran here is
            # this module's contract.
            fanout([list(c.command) for c in self.state.commands if c.mode == SUBAGENT])

        if inline_ids:
            for c in self.state.commands:
                if c.mode == INLINE:
                    inline(list(c.command))

        self._consumed = True
        return SessionRun(
            batch_index=self.state.batch_index,
            subagent_lane_ids=subagent_ids,
            inline_lane_ids=inline_ids,
        )
