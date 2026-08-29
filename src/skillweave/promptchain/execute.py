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


class TopologyGateError(Exception):
    """Raised when a sequence's topology declarations are invalid or colliding.

    The topology/integration contract (SW1311-TOPOLOGY-001) is fail-closed at
    the execution seam: an incomplete manifest or a collision between two
    mutating lanes that is not absorbed by an explicit integration lane stops
    the seam before any worker (fan-out) or integration action. This is the
    live counterpart to :class:`ManifestError` — the seam refuses rather than
    launch, and never re-schedules or rewrites on its own.
    """

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(f"topology gate refused: {detail}")


@dataclass
class IntegrationGateInput:
    """Typed integration facts the execution seam consumes before fan-out.

    Each field is an *observed* fact supplied by the controller (SHAs, worktree
    states, review binding, receipt, dependency pass-set, semantic conflict).
    The gate fails closed on incomplete facts — a missing or non-full SHA, a
    verification that was not rerun, or a receipt that omits a reviewed parent
    all refuse rather than proceed. No field names a model, provider, gateway
    or harness default, and nothing here performs a product edit.
    """

    #: The lane being integrated/rebased (matches a topology ``lane_id``).
    lane_id: Optional[str] = None
    #: The candidate's current head SHA (full 40-hex).
    candidate_sha: Optional[str] = None
    #: The current full integration-tip SHA the lane must rebase onto.
    integration_tip_sha: Optional[str] = None
    #: Whether the controller re-ran its verification after the rebase.
    reran_verification: bool = False
    #: Whether that post-rebase controller verification passed.
    verification_passed: bool = False
    #: The review bound to a specific candidate SHA (``dispatch.integration.Review``).
    review: Optional[Any] = None
    #: The multi-parent integration receipt (``dispatch.integration.IntegrationReceipt``).
    receipt: Optional[Any] = None
    #: The parent lane ids every reviewed outcome must be present for.
    expected_parents: Optional[Sequence[str]] = None
    #: The lane ids already independently passed and integrated (dependency gate).
    passed_lane_ids: Optional[Sequence[str]] = None
    #: A semantic conflict subject; when set, routes to the Integrator.
    semantic_conflict: Optional[str] = None
    #: The bounded write scope for a semantic-conflict Integrator assignment.
    conflict_write_scope: Optional[Sequence[str]] = None
    #: The test contract for a semantic-conflict Integrator assignment.
    conflict_test_contract: Optional[Sequence[str]] = None


@dataclass
class IntegrationGateResult:
    """The verdict of the integration gate (criterion 4-7, 9).

    A refusal is signalled by :class:`TopologyGateError`; a result that
    ``execute_sequence`` is handed continues. ``integrator_assignment`` carries
    the bounded Integrator hand-off for a semantic conflict — the only output
    the controller produces, never a product edit.
    """

    rebase: Optional[Any] = None
    review: Optional[Any] = None
    pending_lane_ids: List[str] = field(default_factory=list)
    integrator_assignment: Optional[Any] = None


@dataclass
class Lane:
    """One lane as declared in a phase's ``parallel_lanes`` or
    ``serialized_lanes`` block."""

    id: str
    #: ``"parallel"`` or ``"serialized"``, from which block the lane came.
    kind: str
    #: The raw lane declaration, retained so the topology gate can derive a
    #: :class:`~skillweave.dispatch.topology.LaneTopology` manifest from the
    #: same file the seam already consumes (write scope, base, dependency set,
    #: worktree, branch, integration policy, harness namespace).
    manifest: Optional[Mapping[str, Any]] = None


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
            parallel.append(Lane(id=lane.get("id"), kind="parallel", manifest=lane))
        for lane in phase.get("serialized_lanes", []) or []:
            serialized.append(Lane(id=lane.get("id"), kind="serialized", manifest=lane))

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


#: The topology fields a lane may declare that mark it as topology-governed.
_TOPOLOGY_KEYS = (
    "base",
    "depends_on",
    "write_scope",
    "worktree",
    "branch",
    "integration_policy",
    "harness_state_namespace",
)


def _is_topology_governed(lane: Lane) -> bool:
    manifest = lane.manifest or {}
    return any(key in manifest for key in _TOPOLOGY_KEYS)


def derive_topologies(declaration: SequenceDeclaration) -> List[Any]:
    """Build :class:`~skillweave.dispatch.topology.LaneTopology` manifests from
    the lanes whose declarations carry topology fields.

    Only lanes that declare any topology key are governed; a lane with no
    topology declaration is left to the session-boundary-only path unchanged.
    The import is deferred so this module's eager import closure stays free of
    the dispatch application surface (GLE-020).
    """
    from skillweave.dispatch.topology import LaneTopology

    result: List[Any] = []
    for lane in declaration.all_lanes():
        if not _is_topology_governed(lane):
            continue
        manifest = dict(lane.manifest or {})
        # The promptchain lane declaration names the lane ``id``; the topology
        # manifest names it ``lane_id``. Map the field so the two seams agree on
        # which governed lane is which.
        if "lane_id" not in manifest and lane.id:
            manifest["lane_id"] = lane.id
        result.append(LaneTopology.from_dict(manifest))
    return result


def gate_topology(
    declaration: SequenceDeclaration,
    *,
    topologies: Optional[Sequence[Any]] = None,
    integration_lanes: Optional[Sequence[str]] = None,
) -> List[List[str]]:
    """Fail-closed topology gate applied *before* any worker launch.

    Derives (or accepts) the lane topology manifests, validates every governed
    manifest, and returns the serialization plan's groups as parallel-batch
    boundaries. A manifest that is incomplete or malformed, or a collision
    between two governed lanes that is not absorbed by an explicit integration
    lane, raises :class:`TopologyGateError` — the seam refuses rather than
    launch. The returned groups mean colliding lanes never share a fan-out
    batch; separate groups are fanned out sequentially.
    """
    from skillweave.dispatch.topology import (
        ManifestError,
        build_serialization_plan,
    )

    resolved = list(topologies) if topologies is not None else derive_topologies(declaration)
    if not resolved:
        return []

    try:
        return [
            list(group)
            for group in build_serialization_plan(
                resolved, integration_lanes=integration_lanes
            ).groups
        ]
    except ManifestError as exc:
        raise TopologyGateError(str(exc)) from exc


def _resolve_integrating_lane(
    integration_input: IntegrationGateInput,
    by_id: Mapping[str, Any],
) -> Any:
    """Resolve the :class:`~skillweave.dispatch.topology.LaneTopology` the gate
    acts upon, fail-closed when it cannot be identified."""
    lane_id = integration_input.lane_id
    if lane_id and lane_id in by_id:
        return by_id[lane_id]
    if lane_id:
        # A rebase/integration is always about a mutating lane; if its manifest
        # was not derived then the integration facts are incomplete.
        raise TopologyGateError(
            f"integrating lane {lane_id!r} has no topology manifest"
        )
    # No lane id: the gate needs a concrete lane to rebase/route. Refuse rather
    # than invent one.
    raise TopologyGateError(
        "integration facts name no integrating lane; refusing incomplete facts"
    )


def gate_integration(
    declaration: SequenceDeclaration,
    integration_input: Optional[IntegrationGateInput] = None,
    *,
    topologies: Optional[Sequence[Any]] = None,
) -> IntegrationGateResult:
    """Fail-closed integration gate consumed *before* any fan-out/integration.

    Reuses :mod:`skillweave.dispatch.integration` decisions verbatim (rebase,
    review invalidation, multi-parent receipt, dependency DAG, Integrator
    assignment) — the gate only orders and *enforces* them at the live seam. On
    any incomplete or failing fact it raises :class:`TopologyGateError` before a
    worker starts; on success it returns an :class:`IntegrationGateResult` whose
    ``integrator_assignment`` carries a bounded Integrator hand-off (never a
    controller product edit).
    """
    from skillweave.dispatch.integration import (
        IntegrationTip,
        ReceiptError,
        ReviewInvalidatedError,
        SemanticConflictError,
        assign_semantic_conflict,
        build_dependency_graph,
        plan_rebase,
        require_fresh_review,
    )

    result = IntegrationGateResult()
    if integration_input is None:
        return result

    resolved = list(topologies) if topologies is not None else derive_topologies(declaration)
    by_id = {t.lane_id: t for t in resolved}

    # Criterion 4: rebase onto the current full integration tip and a successful
    # post-rebase controller verification. ``plan_rebase`` fails closed on a
    # missing/non-full SHA; the gate additionally refuses a verification that was
    # not rerun or did not pass.
    rebase = None
    has_rebase_facts = integration_input.candidate_sha is not None or (
        integration_input.integration_tip_sha is not None
    )
    if has_rebase_facts:
        lane = _resolve_integrating_lane(integration_input, by_id)
        rebase = plan_rebase(
            lane,
            integration_input.candidate_sha,
            IntegrationTip(tip_sha=integration_input.integration_tip_sha),
        )
        if not (integration_input.reran_verification and integration_input.verification_passed):
            raise TopologyGateError(
                "controller must rerun verification against the post-rebase SHA "
                "and it must pass before integration"
            )
        result.rebase = rebase

    # Criterion 5: a review bound to a pre-rebase SHA is stale once the candidate
    # moved. ``require_fresh_review`` refuses unless the review SHA matches the
    # current (post-rebase) candidate SHA.
    if integration_input.review is not None or has_rebase_facts:
        current_sha = (
            rebase.post_rebase_sha
            if rebase is not None
            else integration_input.candidate_sha
        )
        try:
            result.review = require_fresh_review(integration_input.review, current_sha)
        except ReviewInvalidatedError as exc:
            raise TopologyGateError(str(exc)) from exc

    # Criterion 6: a multi-parent receipt must contain every expected reviewed
    # parent with its outcome present. ``validate`` refuses on sibling omission
    # or an absent outcome even when the included parents passed.
    if integration_input.receipt is not None:
        try:
            integration_input.receipt.validate(
                list(integration_input.expected_parents or [])
            )
        except ReceiptError as exc:
            raise TopologyGateError(str(exc)) from exc

    # Criterion 9: dependency readiness — a dependent stays pending until every
    # required parent is independently passed and integrated. Refuse when any
    # governed dependent is still pending.
    if integration_input.passed_lane_ids is not None:
        if resolved:
            graph = build_dependency_graph(resolved)
            pending = graph.dependents_pending(list(integration_input.passed_lane_ids))
            result.pending_lane_ids = pending
            if pending:
                raise TopologyGateError(
                    f"dependents pending until their required parents are passed: "
                    f"{pending}"
                )

    # Criterion 7: a semantic conflict is routed to the explicit Integrator with
    # a bounded write scope and test contract. The controller produces only the
    # assignment — never a product edit.
    if integration_input.semantic_conflict is not None:
        lane = _resolve_integrating_lane(integration_input, by_id)
        try:
            result.integrator_assignment = assign_semantic_conflict(
                lane,
                conflict=integration_input.semantic_conflict,
                write_scope=list(integration_input.conflict_write_scope or []),
                test_contract=list(integration_input.conflict_test_contract or []),
            )
        except SemanticConflictError as exc:
            raise TopologyGateError(str(exc)) from exc

    return result


def execute_sequence(
    declaration: SequenceDeclaration,
    *,
    fanout: Optional[Any] = None,
    topologies: Optional[Sequence[Any]] = None,
    integration_lanes: Optional[Sequence[str]] = None,
    integration_input: Optional[IntegrationGateInput] = None,
) -> DispatchPlan:
    """Validate, build the plan, and hand parallel lanes to the fan-out seam.

    ``fanout`` is the subagent dispatch seam. When omitted, the real
    ``skillweave.fanout.dispatch.fan_out_dispatch`` is used for the parallel
    lanes; serialized lanes stay inline. The plan is returned regardless, so a
    caller (or a test) can inspect every decision.

    When the sequence's lanes are topology-governed (they declare a write
    scope, base, dependency set, worktree, branch, integration policy or
    harness namespace), the collision-safe serialization plan is applied first:
    a gate that fails closed on any incomplete manifest or unabsorbed
    collision, and which frees parallel lanes in collision-free groups so two
    lanes that overlap in write scope, share an incompatible base, or claim the
    same harness namespace never launch in the same batch.

    When ``integration_input`` is supplied, the integration gate
    (:func:`gate_integration`) is consumed *before* any fan-out action: an
    unverified or failed post-rebase verification, a stale review, an
    incomplete multi-parent receipt, or a still-pending dependency refuses the
    seam before a single worker starts. A semantic conflict is routed to a
    bounded Integrator assignment (returned by the gate), never a controller
    product edit.
    """
    if integration_input is not None:
        gate_integration(
            declaration, integration_input, topologies=topologies
        )

    plan = build_dispatch_plan(declaration)

    parallel_lanes = [e.lane_id for e in plan.entries if e.mode == SUBAGENT]
    if parallel_lanes:
        dispatcher = fanout
        if dispatcher is None:
            from skillweave.fanout.dispatch import fan_out_dispatch

            dispatcher = fan_out_dispatch

        # Topology gate: colliding or incomplete governed lanes stop here,
        # before any fan-out call. When guaranteed safe, the gate returns
        # collision-free groups that each become one fan-out batch, so
        # colliding parallel lanes are serialized rather than launched together.
        groups = gate_topology(
            declaration, topologies=topologies, integration_lanes=integration_lanes
        )
        if groups:
            for group in groups:
                dispatcher(list(group))
        else:
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
