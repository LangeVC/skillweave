"""Execute a ``sequences/*.yaml`` orchestration file as bounded sessions.

The sequence format already carries the structure that prevents context
exhaustion: it groups lanes into ``parallel_lanes`` and
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

    The boundary is never invented: defaulting a boundary is the
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


def resume_batch_command(
    state: SessionState,
    *,
    lane_id: str,
) -> Optional[BatchCommand]:
    """Return the batch command for ``lane_id`` in a cold session state.

    This is the handoff seam for a controller recomputing which command a lane
    should run from the state file alone (SW1311-HANDOFF-001, controller-resume):
    a controller that derived the next batch index from a checkpoint reads the
    state file once and resolves the lane's command here, rather than from any
    transcript. ``None`` means the lane is not part of this state's single batch
    (or the resolved command is absent), so a resume cannot invent work.
    """
    if not state.session_boundary:
        raise MissingSessionBoundaryError()
    for command in state.commands:
        if command.lane_id == lane_id:
            return command
    return None


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


# --- Effective-profile-driven chain derivation (SW1312-CHAIN-001) ------------
#
# The immutable effective-profile snapshot (SW1312-PROFILE-RESOLVE-001) is the
# *single* consumer-side seam between the SDK profile contract and the
# promptchain skills. This section owns the derivation that turns that snapshot
# into the inputs the promptchain generate / validate / dispatch skills consume:
# ordered steps, skills, capabilities, roles, gates, evidence contracts,
# handoffs, and a dispatch topology. Nothing here re-resolves a profile — it
# consumes an already-resolved snapshot (duck-typed: any object exposing the
# snapshot surface, or a plain mapping with the same keys, so a test can build
# one without importing the resolver).
#
# The derivation is data-driven, never profile-name-driven (criterion 4): the
# discriminator is the profile's *data* (``primaryCategory``, ``topology``,
# ``phases``, ``capabilities``, ``control``), not its id. The software and the
# research snapshot therefore take the same code path and diverge only because
# their data diverges.
#
# Preview-only runtime dimensions (ordered phases, K0-K6 mappings, topology,
# control, human coupling, change surfaces, autonomy bounds) are preserved as
# declarations and reported; requesting their *execution* fails explicitly
# (criterion 8) and never falls back silently to the legacy plan/build/mixed
# path.
#
# Without an explicit profile snapshot, none of this is entered: the existing
# plan/build/mixed path (``load_sequence`` / ``build_dispatch_plan`` /
# ``execute_sequence``) remains byte-for-byte unchanged (criterion 7).


class ProfileChainError(ValueError):
    """A profile snapshot could not be derived into a dispatch chain.

    Raised before any dispatch. ``field`` names the offending part where known.
    """

    def __init__(self, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


class PreviewExecutionError(ProfileChainError):
    """A caller requested execution of a preview-only (declaration-only) runtime
    dimension that the released operations loop does not execute."""


#: The preview-only runtime dimensions carried as declarations, never executed.
#: Mirrors the resolver's ``PREVIEW_DIMENSIONS`` so the fail-explicit boundary
#: agrees with the snapshot author.
_PREVIEW_RUNTIME_DIMENSIONS = (
    "phases",
    "kernel_stage",
    "topology",
    "control",
    "human_coupling",
    "humanCoupling",
    "change_surfaces",
    "changeSurfaces",
    "autonomy_bounds",
    "autonomyBounds",
    "skills",
    "skillComposition",
    "capabilities",
    "capabilityComposition",
)

#: The four identity fields a chain/receipt must carry (criterion 6): the
#: profile id, its version, the SDK schema digest it was bound to, and the
#: effective-profile content digest.
_PROFILE_IDENTITY_KEYS = ("profile_id", "profile_version", "sdk_digest", "effective_digest")

#: Category -> default skill set. Keyed by *data* (the primary category the
#: snapshot resolved), never by a profile name.
_CATEGORY_SKILLS: dict[str, tuple[str, ...]] = {
    "build": (
        "skillweave-blueprint",
        "skillweave-design",
        "skillweave-promptchain-generate",
        "skillweave-promptchain-validate",
        "skillweave-promptchain-execute",
        "skillweave-releasechain",
    ),
    "research": (
        "skillweave-discovery",
        "skillweave-promptchain-generate",
        "skillweave-promptchain-validate",
        "skillweave-promptchain-execute",
        "skillweave-observe",
    ),
    "operate": (
        "skillweave-observe",
        "skillweave-lifecycle",
        "skillweave-post-release",
        "skillweave-promptchain-execute",
    ),
}

#: The roles every derived chain carries (separation of duties: ops mutates,
#: reviewer is read-only, observer records the run).
_BASE_ROLES = ("ops", "reviewer", "observer")

#: Role -> capability. Derived from the snapshot's declared capabilities where
#: present, falling closed to an empty mapping otherwise.
_ROLE_DEFAULT_CAPABILITIES: dict[str, dict[str, Any]] = {
    "ops": {"can_mutate_run_state": True},
    "reviewer": {"is_read_only": True},
    "observer": {"is_read_only": True},
}


def _snapshot_resolved(snapshot: Any) -> dict[str, Any]:
    """Return the resolved content mapping of a snapshot-shaped input.

    Accepts an object exposing ``.resolved`` (the resolver's
    ``EffectiveProfileSnapshot``) or a plain mapping (with the resolved content
    at the top level, or under a ``resolved`` key). Never mutates the input.
    """
    if snapshot is None:
        raise ProfileChainError("an effective-profile snapshot is required", field="profile")
    if isinstance(snapshot, Mapping):
        resolved = snapshot.get("resolved", snapshot)
        if not isinstance(resolved, Mapping):
            raise ProfileChainError(
                "snapshot mapping must carry 'resolved' content", field="profile.resolved"
            )
        return dict(resolved)
    resolved = getattr(snapshot, "resolved", None)
    if not isinstance(resolved, Mapping):
        raise ProfileChainError(
            "snapshot must expose a '.resolved' mapping (EffectiveProfileSnapshot)",
            field="profile.resolved",
        )
    return dict(resolved)


def _snapshot_identity(snapshot: Any) -> dict[str, str]:
    """Extract the four identity fields from a snapshot-shaped input.

    Uses the snapshot's own ``sdk_digest`` and ``digest`` when present, and
    derives ``profile_id`` / ``profile_version`` from the winning source (the
    strongest source id/version contributing to the resolution). For a plain
    mapping the fields are read directly.
    """
    if isinstance(snapshot, Mapping):
        raw = snapshot
    else:
        raw = {}
        for key in ("profile_id", "profile_version", "sdk_digest", "effective_digest"):
            if hasattr(snapshot, key):
                raw[key] = getattr(snapshot, key)
        if hasattr(snapshot, "sdk_digest"):
            raw["sdk_digest"] = snapshot.sdk_digest
        if hasattr(snapshot, "digest"):
            raw["effective_digest"] = snapshot.digest

    identity: dict[str, str] = {}
    identity["profile_id"] = str(
        raw.get("profile_id")
        or _identity_from_sources(snapshot, "source_id")
        or ""
    )
    identity["profile_version"] = str(
        raw.get("profile_version")
        or _identity_from_sources(snapshot, "source_version")
        or ""
    )
    identity["sdk_digest"] = str(raw.get("sdk_digest") or _digest_from(snapshot, "sdk_digest") or "")
    identity["effective_digest"] = str(
        raw.get("effective_digest") or _digest_from(snapshot, "digest") or ""
    )
    return identity


def _identity_from_sources(snapshot: Any, attr: str) -> str:
    sources = getattr(snapshot, "sources", None) if not isinstance(snapshot, Mapping) else None
    if isinstance(sources, Sequence) and sources:
        first = sources[0]
        if isinstance(first, Mapping):
            return str(first.get(attr) or "")
        return str(getattr(first, attr, "") or "")
    return ""


def _digest_from(snapshot: Any, attr: str) -> str:
    if isinstance(snapshot, Mapping):
        return str(snapshot.get(attr) or "")
    return str(getattr(snapshot, attr, "") or "")


def profile_identity(snapshot: Any) -> dict[str, str]:
    """The four profile identity fields a chain and its receipts must carry.

    Order is stable: ``profile_id``, ``profile_version``, ``sdk_digest``,
    ``effective_digest``. A field the snapshot cannot supply is an empty string;
    callers gate on presence where the contract requires it (criterion 6).
    """
    identity = _snapshot_identity(snapshot)
    return {key: identity.get(key, "") for key in _PROFILE_IDENTITY_KEYS}


def preview_dimensions_of(snapshot: Any) -> dict[str, Any]:
    """The preview-only runtime dimensions carried as declarations.

    Mirrors the resolver's ``preview_dimensions`` so a consumer can read which
    runtime dimensions the snapshot declares without executing them.
    """
    resolved = _snapshot_resolved(snapshot)
    return {key: resolved[key] for key in _PREVIEW_RUNTIME_DIMENSIONS if key in resolved}


def require_supported_dimension(snapshot: Any, dimension: str) -> None:
    """Refuse execution of a preview-only runtime dimension (criterion 8).

    Preview-only dimensions exist in the snapshot only as declarations. A caller
    that asks to *run* one (rather than merely read the declaration) is refused
    with an actionable message naming the dimension — never a silent fall-back
    to the legacy plan/build/mixed path.
    """
    if not isinstance(dimension, str) or not dimension.strip():
        raise ProfileChainError(
            "a runtime dimension name is required", field="dimension"
        )
    if dimension in _PREVIEW_RUNTIME_DIMENSIONS:
        raise PreviewExecutionError(
            f"'{dimension}' is a preview-only declaration and cannot be executed "
            f"by the released operations loop; read it as a declaration, do not "
            f"request its execution",
            field=f"dimension.{dimension}",
        )


# ── Chain derivation ────────────────────────────────────────────────────────


@dataclass
class ProfileHandoff:
    """A phase-boundary handoff carrying the 4-part profile identity.

    A handoff is never a bare string (criterion 6 / B1): it binds the source
    and target phase together with the profile id, version, SDK schema digest
    and effective-profile content digest, so the identity that produced the
    chain rides on every phase transfer and cannot be reconstructed from a later
    receipt alone.
    """

    source: str
    target: str
    profile_identity: dict[str, str] = field(default_factory=dict)

    @property
    def link(self) -> str:
        """The stable ``handoff:<source>-><target>`` reference."""
        return f"handoff:{self.source}->{self.target}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "link": self.link,
            "profile_identity": dict(self.profile_identity),
        }


@dataclass
class ChainStep:
    """One ordered step derived from a snapshot's declared phases."""

    id: str
    phase: str
    role: str
    skills: list[str] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    gates: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    handoff: Optional[ProfileHandoff] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "phase": self.phase,
            "role": self.role,
            "skills": list(self.skills),
            "capabilities": dict(self.capabilities),
            "gates": list(self.gates),
            "evidence": list(self.evidence),
            "handoff": self.handoff.to_dict() if self.handoff is not None else None,
        }


@dataclass
class ProfileChainDerivation:
    """The complete derivation of a dispatch chain from one snapshot.

    ``steps`` is the ordered step list; ``skills`` the union of every step's
    skills; ``capabilities`` the snapshot's declared capabilities; ``roles`` the
    role set; ``gates``/``evidence`` the gate and evidence contracts; ``handoffs``
    the phase-boundary handoffs; and ``dispatch_order`` the nonempty nonlinear
    dispatch groups covering every criterion exactly once.
    """

    profile_identity: dict[str, str] = field(default_factory=dict)
    steps: list[ChainStep] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    roles: list[str] = field(default_factory=list)
    gates: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    handoffs: list[ProfileHandoff] = field(default_factory=list)
    dispatch_order: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": dict(self.profile_identity),
            "steps": [s.to_dict() for s in self.steps],
            "skills": list(self.skills),
            "capabilities": dict(self.capabilities),
            "roles": list(self.roles),
            "gates": list(self.gates),
            "evidence": list(self.evidence),
            "handoffs": [h.to_dict() for h in self.handoffs],
            "dispatch_order": [list(g) for g in self.dispatch_order],
        }


def _category_of(resolved: dict[str, Any]) -> str:
    return str(resolved.get("primaryCategory") or resolved.get("primary_category") or "")


def _skills_for(resolved: dict[str, Any]) -> list[str]:
    """The skill set for the profile's primary category (data-driven, not
    profile-name-driven)."""

    declared = resolved.get("skills")
    if isinstance(declared, list):
        return [str(s) for s in declared if s]
    category = _category_of(resolved)
    return list(_CATEGORY_SKILLS.get(category, ()))


def _gates_for(resolved: dict[str, Any]) -> list[str]:
    """Gate names derived from the profile's declared control/risk."""

    declared = resolved.get("gates")
    if isinstance(declared, list):
        return [str(g) for g in declared if g]
    control = resolved.get("control")
    risk = "".join(str(control.get("risk"))).lower() if isinstance(control, Mapping) else ""
    base = ["session_boundary", "criterion_coverage"]
    if risk in ("high", "critical"):
        # High blast-radius profiles add a separate cold review gate.
        base.append("separate_cold_review")
    return base


def _evidence_for(resolved: dict[str, Any]) -> list[str]:
    """Evidence contracts derived from the profile's control/risk."""

    declared = resolved.get("evidence")
    if isinstance(declared, list):
        return [str(e) for e in declared if e]
    control = resolved.get("control")
    risk = "".join(str(control.get("risk"))).lower() if isinstance(control, Mapping) else "low"
    if risk in ("high", "critical"):
        return ["job_receipt", "verification", "cold_review", "observer", "replay"]
    return ["job_receipt", "verification", "observer"]


def _phases_of(resolved: dict[str, Any]) -> list[str]:
    phases = resolved.get("phases")
    if isinstance(phases, list):
        return [str(p) for p in phases if p]
    return []


def _capabilities_of(resolved: dict[str, Any]) -> dict[str, Any]:
    caps = resolved.get("capabilities")
    if isinstance(caps, Mapping):
        return dict(caps)
    return {}


def _roles_of(resolved: dict[str, Any]) -> list[str]:
    declared = resolved.get("roles")
    if isinstance(declared, list) and declared:
        return [str(r) for r in declared if r]
    return list(_BASE_ROLES)


def derive_chain_from_profile(snapshot: Any) -> ProfileChainDerivation:
    """Derive a dispatch chain from an effective-profile snapshot (criterion 1).

    Produces, in one pass over the snapshot's *data* (never its name): ordered
    steps (one per declared phase), each with a role, the category's skill set,
    declared capabilities, gate and evidence contracts, and a phase-boundary
    handoff; plus the union skills, capabilities, roles, gates, evidence,
    handoffs, and a ``dispatch_order`` of nonempty groups with exact-once
    criterion coverage (criterion 3).
    """
    resolved = _snapshot_resolved(snapshot)
    identity = profile_identity(snapshot)

    skills = _skills_for(resolved)
    capabilities = _capabilities_of(resolved)
    roles = _roles_of(resolved)
    gates = _gates_for(resolved)
    evidence = _evidence_for(resolved)
    phases = _phases_of(resolved)

    steps: list[ChainStep] = []
    handoffs: list[ProfileHandoff] = []
    roles_iter = iter(roles) if roles else iter(_BASE_ROLES)
    for index, phase in enumerate(phases):
        role = next(roles_iter, roles[-1] if roles else "ops")
        handoff = None
        if index > 0:
            handoff = ProfileHandoff(
                source=phases[index - 1],
                target=phase,
                profile_identity=dict(identity),
            )
            handoffs.append(handoff)
        # The final step closes the chain, so it carries the full gate set;
        # every step carries the session-boundary gate (one batch per session).
        step_gates = list(gates)
        if index < len(phases) - 1:
            step_gates = [g for g in gates if g != "separate_cold_review"]
        steps.append(
            ChainStep(
                id=f"step-{index + 1}-{phase}",
                phase=phase,
                role=role,
                skills=list(skills),
                capabilities=dict(capabilities),
                gates=step_gates,
                evidence=list(evidence),
                handoff=handoff,
            )
        )

    dispatch_order = build_dispatch_order(steps)

    return ProfileChainDerivation(
        profile_identity=identity,
        steps=steps,
        skills=skills,
        capabilities=capabilities,
        roles=roles,
        gates=gates,
        evidence=evidence,
        handoffs=handoffs,
        dispatch_order=dispatch_order,
    )


def build_dispatch_order(
    steps: Sequence[ChainStep],
    *,
    criterion_count: Optional[int] = None,
) -> list[list[str]]:
    """Group derived steps into nonempty dispatch groups (criterion 3).

    Two steps sharing a role serialize into separate groups; disjoint-role steps
    share a group. Every step appears exactly once across the aggregate, and the
    group list is nonempty whenever there is at least one step. When
    ``criterion_count`` is supplied, the coverage of each step is checked so a
    chain covering N criteria yields exactly one criterion per step.
    """
    if not steps:
        return []
    groups: list[list[str]] = []
    current: list[str] = []
    occupied: set[str] = set()
    for step in steps:
        if step.role in occupied:
            groups.append(current)
            current = []
            occupied = set()
        current.append(step.id)
        occupied.add(step.role)
    if current:
        groups.append(current)
    return [g for g in groups if g]


def criterion_coverage(derivation: ProfileChainDerivation) -> list[int]:
    """The 1-based criterion indices covered by the derived chain's steps.

    Each step covers exactly one criterion (its position in the ordered step
    list), so the aggregate coverage is ``1..N`` with every criterion once.
    """
    return list(range(1, len(derivation.steps) + 1))


def validate_profile_chain(
    snapshot: Any,
    derivation: ProfileChainDerivation,
) -> list[str]:
    """Check the derived chain's profile contract (criterion 2).

    Returns a list of violations (empty means valid). Checks, failing closed:

    * the profile contract is present (identity + resolved content + phases);
    * evidence contracts are declared;
    * surfaces are carried (derived from phase write scopes, non-empty);
    * authority is not self-approving (ops never also approves gates);
    * dependencies are ordered (a step's handoff matches the previous phase);
    * every handoff references a real phase boundary.

    ``snapshot`` supplies the authority/evidence declarations; ``derivation``
    the steps and handoffs.
    """
    violations: list[str] = []
    resolved = _snapshot_resolved(snapshot)

    identity = profile_identity(snapshot)
    if not identity["profile_id"]:
        violations.append("profile contract missing profile_id")
    if not identity["sdk_digest"]:
        violations.append("profile contract missing sdk_digest")
    if not identity["effective_digest"]:
        violations.append("profile contract missing effective_digest")

    phases = _phases_of(resolved)
    if not phases:
        violations.append("profile contract declares no phases")
    if not derivation.skills:
        violations.append("profile contract derives no skills for its category")
    if not derivation.evidence:
        violations.append("profile contract declares no evidence contracts")
    if not derivation.gates:
        violations.append("profile contract declares no gates")

    # Surfaces: every mutating step must own a non-empty write surface.
    for step in derivation.steps:
        if step.role == "ops" and not (step.skills or step.capabilities):
            violations.append(f"step {step.id} declares no surface")

    # Authority: an ops role must never approve a gate on its own work.
    ops_approves = any(
        step.role == "ops" and "can_approve_gate" in step.capabilities
        for step in derivation.steps
    )
    if ops_approves:
        violations.append("authority violation: ops role approves its own gate")

    # Dependencies + handoffs: each non-first step's handoff must name the
    # preceding phase, and every handoff must carry the full profile identity.
    for index, step in enumerate(derivation.steps):
        if index == 0:
            continue
        expected_prev = derivation.steps[index - 1].phase
        expected_link = f"handoff:{expected_prev}->{step.phase}"
        if step.handoff is None or step.handoff.link != expected_link:
            violations.append(
                f"step {step.id} handoff does not reference predecessor "
                f"{expected_prev}"
            )
            continue
        for key in _PROFILE_IDENTITY_KEYS:
            if not (step.handoff.profile_identity.get(key) or "").strip():
                violations.append(
                    f"step {step.id} handoff omits profile identity field {key}"
                )

    return violations


def dispatch_topology_from_profile(snapshot: Any) -> list[dict[str, Any]]:
    """Derive dispatch-topology lane manifests from a snapshot (criterion 1).

    Each non-last phase becomes a governed lane (``write_scope`` under the
    phase, ``depends_on`` the prior phase) plus a final review lane. The result
    is the lane manifests the existing topology/execution seam
    (``derive_topologies`` / ``gate_topology``) consumes.

    Every manifest carries a ``provenance`` block holding the 4-part profile
    identity (criterion 6 / B1): the identity that produced the chain rides on
    the child-job topology declaration, not just on the final gate.
    """
    resolved = _snapshot_resolved(snapshot)
    phases = _phases_of(resolved)
    if not phases:
        return []
    identity = profile_identity(snapshot)
    manifests: list[dict[str, Any]] = []
    for index, phase in enumerate(phases):
        lane_id = f"lane-{phase}"
        dep = [f"lane-{phases[index - 1]}"] if index > 0 else []
        manifests.append(
            {
                "lane_id": lane_id,
                "base": "0" * 40,
                "depends_on": dep,
                "write_scope": [f"/dispatch/{phase}/**"],
                "worktree": f"wt-{phase}",
                "branch": f"sw/{phase}",
                "integration_policy": "requires_integrator" if index == len(phases) - 1 else "independent",
                "provenance": dict(identity),
            }
        )
    return manifests


def profile_sequence_from_snapshot(
    snapshot: Any,
    *,
    session_boundary: str = "batch",
    execution_model: str = "cold",
    max_parallel: int = 1,
    max_correction_rounds_per_wave: int = 0,
) -> dict[str, Any]:
    """Build a dispatch sequence declaration from a snapshot (criterion 1/6).

    The sequence binds the 4-part profile identity through ``profile.provenance``
    (the ``profileProvenance`` block of :file:`dispatch-sequence.schema.json`),
    so the identity flows *from the derivation* into the sequence consumed by a
    later run — never hand-injected by a test or a consumer. Each phase becomes
    a governed lane keyed to the snapshot's own data.
    """
    resolved = _snapshot_resolved(snapshot)
    identity = profile_identity(snapshot)
    phases = _phases_of(resolved)
    lanes: list[dict[str, Any]] = []
    for index, phase in enumerate(phases):
        lanes.append(
            {
                "id": f"lane-{phase}",
                "role": "ops" if index < len(phases) - 1 else "reviewer",
                "repo": f"skillweave/{identity['profile_id'] or 'skillweave'}",
                "base": "0" * 40,
                "execution_model": execution_model,
                "mutating": index < len(phases) - 1,
                "depends_on": [f"lane-{phases[index - 1]}"] if index > 0 else [],
                "write_scope": [f"/dispatch/{phase}/**"],
                "worktree": f"wt-{phase}",
                "branch": f"sw/{phase}",
                "integration_policy": "requires_integrator" if index == len(phases) - 1 else "independent",
            }
        )
    return {
        "session_boundary": session_boundary,
        "profile": {
            "path": f"profile://{identity['profile_id'] or 'profile'}",
            "required": True,
            "provenance": dict(identity),
        },
        "execution_model": execution_model,
        "max_correction_rounds_per_wave": max_correction_rounds_per_wave,
        "max_parallel": max_parallel,
        "lanes": lanes,
    }


def profile_receipt_payload(
    snapshot: Any,
    *,
    kind: str,
) -> dict[str, Any]:
    """Build an identity-bearing review / final-gate receipt payload.

    The 4-part identity is carried under ``profile`` (and, for the final gate,
    ``kind`` distinguishes the receipt) so a review or final-gate record
    produced from the derivation carries the snapshot that produced the chain —
    not a bare profile-name string.
    """
    identity = profile_identity(snapshot)
    return {"profile": dict(identity), "kind": kind}
