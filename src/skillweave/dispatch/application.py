"""Operator-dispatch application seam (SW138-DISPATCH-001).

This module is the *single experimental application seam* that consumes the
reviewed dispatch contract (:mod:`skillweave.dispatch.contracts`), the
authoritative profile resolver (:mod:`skillweave.dispatch.profile_resolution`)
and the typed event stream (:mod:`skillweave.dispatch.events`), and drives one
wave of work through the existing routing / fan-out / run / workspace services.

It is deliberately **not** a second subprocess adapter, a second artifact store,
or a second state machine: every concern that already has a home lives there.

* **Process launch** is delegated to
  :func:`skillweave.fanout.dispatch.fan_out_dispatch` (which uses the runtime
  ``runner_adapter``). Nothing here calls ``subprocess.Popen``.
* **Workspace provision/attestation** is delegated to
  :class:`skillweave.workspace.provider.GitWorktreeProvider`. Nothing here
  materialises a worktree itself.
* **Run identity and event emission** use the shared event stream.

The ``execution_model`` enum is enforced *here*, at the live consumer: the legal
values are ``cold``/``warm``/``resume`` and anything else (``hot``) fails before
launch. This is the carry-forward from the contract review.

This seam is **experimental and wave-scoped**: it executes exactly one wave (the
wave the caller names) and makes no claim of stable 1.4 transport compatibility.
"""

from __future__ import annotations

import importlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import yaml

from skillweave.dispatch.contracts import (
    EventType,
    Lane,
    ProcessStatus,
    SequenceDeclaration,
    TaskStatus,
    load_sequence,
    validate_for_dispatch,
)
from skillweave.dispatch.events import DispatchEventStream
from skillweave.dispatch.profile_resolution import (
    ProfileResolutionError,
    ResolvedDispatch,
    resolve_dispatch_profile,
)
from skillweave.routing.harness import HarnessError

#: The legal execution-model vocabulary at the live consumer (contract
#: carry-forward: ``cold``/``warm``/``resume``; ``hot`` is refused).
EXECUTION_MODELS: tuple[str, ...] = ("cold", "warm", "resume")

#: The terminal fact emitted when a wave has spent its whole correction budget
#: without converging; it starts no further correction child.
HALT_REQUIRES_OPERATOR = "HALT_REQUIRES_OPERATOR"

#: The four machine outcomes a child reports (mirrors the fan-out vocabulary).
CHILD_OUTCOMES = ("exit_code", "signal", "timed_out", "launch_failed")


class OperatorDispatchError(Exception):
    """A dispatch request could not be satisfied (raised before any launch)."""


class RequiredEvidenceError(OperatorDispatchError):
    """A lane's required evidence cannot be satisfied.

    Raised when a lane declares an empty required-evidence list, or when one of
    its referenced artifacts cannot be resolved or fails integrity validation —
    in every case the lane must not reach ``done``.
    """

    def __init__(self, lane_id: str, reason: str):
        self.lane_id = lane_id
        super().__init__(f"lane '{lane_id}' required evidence unsatisfied: {reason}")


class ExecutionModelError(OperatorDispatchError):
    """The sequence's ``execution_model`` is not a legal contract value."""

    def __init__(self, value: Any):
        self.value = value
        super().__init__(
            f"execution_model {value!r} is not one of {list(EXECUTION_MODELS)}; "
            "refusing to launch"
        )


class WorkspaceMismatchError(OperatorDispatchError):
    """A lane's attested base SHA differs from its declared base SHA.

    Raised before any child for that lane starts: running the wrong tree is a
    block, never a warning.
    """

    def __init__(self, lane_id: str, declared: str, attested: str):
        self.lane_id = lane_id
        super().__init__(
            f"lane '{lane_id}' base mismatch: declared {declared!r}, attested {attested!r}"
        )


class TopologyGateError(OperatorDispatchError):
    """The topology/integration gate refused a wave before any launch.

    This is the live, authoritative counterpart to
    :class:`~skillweave.dispatch.topology.ManifestError`: the operator dispatcher
    refuses an incomplete/absent topology manifest, an unabsorbed collision, a
    ``requires_integrator`` lane without an eligible integrator, a semantic
    conflict that must route to the bounded Integrator, or an ineligible
    (detached/uncommitted/wrong-branch/product-dirty) candidate — never launches
    through the bad state, and never re-schedules or rewrites on its own.
    """

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(f"topology gate refused: {detail}")


def _lane_is_topology_governed(lane: Lane) -> bool:
    """True when ``lane`` carries any topology manifest field.

    Note: governed-ness here is *declaration-presence*, not the launch policy.
    Every mutating lane must be governed (carry the complete manifest); a
    non-mutating lane is never governed and keeps its pre-governance behavior.
    The mutating-lane completeness obligation is enforced in
    :func:`derive_topology_manifests`, not here.
    """
    return bool(
        lane.write_scope is not None
        or lane.worktree
        or lane.branch
        or lane.harness_state_namespace
        or (lane.integration_policy is not None)
        or (lane.depends_on is not None)
    )


@dataclass
class TopologyGateInput:
    """Observed topology/integration facts the operator dispatcher consumes.

    Each field is an *observed* fact supplied by the operator (explicit
    integration lanes, a semantic-conflict subject and its bounded scope/contract,
    and per-lane worktree eligibility). The gate fails closed on incomplete facts
    and never performs a product edit itself.
    """

    #: Lane ids explicitly declared as integration lanes that may absorb a
    #: collision or satisfy a ``requires_integrator`` lane.
    integration_lanes: Optional[Sequence[str]] = None
    #: The lane id in a semantic conflict (routed to the bounded Integrator).
    semantic_conflict: Optional[str] = None
    #: Bounded write scope for the semantic-conflict Integrator assignment.
    conflict_write_scope: Optional[Sequence[str]] = None
    #: Test contract for the semantic-conflict Integrator assignment.
    conflict_test_contract: Optional[Sequence[str]] = None
    #: Per-lane worktree state (``dispatch.topology.WorktreeState``) assessed for
    #: integration eligibility before launch.
    eligibility: Optional[Mapping[str, Any]] = None
    #: Optional cache allowlist overriding the module default for eligibility.
    cache_allowlist: Optional[Sequence[str]] = None


@dataclass
class TopologyEnforcement:
    """The authoritative topology/integration verdict.

    ``groups`` are the collision-safe serialization batches (lane ids) in
    dispatch order; ``governed`` lists every governed mutating lane id in
    declaration order; ``removed_lane_ids`` names lanes removed from normal
    fan-out (a semantic conflict) so they are routed to the Integrator, not
    launched by the controller; ``integrator_assignment`` is the bounded
    Integrator hand-off (never a controller product edit).
    """

    groups: list[list[str]] = field(default_factory=list)
    governed: list[str] = field(default_factory=list)
    removed_lane_ids: list[str] = field(default_factory=list)
    integrator_assignment: Optional[Any] = None


def derive_topology_manifests(declaration: SequenceDeclaration) -> list[Any]:
    """Build :class:`~skillweave.dispatch.topology.LaneTopology` manifests.

    Every *mutating* lane must carry the complete topology manifest: a lane with
    zero (or partial) topology fields raises :class:`TopologyGateError` before
    any workspace is provisioned or worker launched (F6). Only a **non-mutating**
    lane bypasses governance — there is no legacy path that lets a mutating lane
    skip its manifest. The contract lane's ``id`` maps to the manifest's
    ``lane_id`` so the two seams agree. The import is deferred so this module's
    own import closure stays free of any optional subpackage.
    """
    from skillweave.dispatch.topology import LaneTopology

    manifests: list[Any] = []
    for lane in declaration.mutating_lanes():
        if not _lane_is_topology_governed(lane):
            raise TopologyGateError(
                f"mutating lane {lane.id!r} declares no topology manifest; every "
                "mutating lane must declare a complete topology manifest "
                "(depends_on, write_scope, worktree, branch, integration_policy)"
            )
        manifests.append(
            LaneTopology(
                lane_id=lane.id,
                base=lane.base or "",
                depends_on=list(lane.depends_on or []),
                write_scope=list(lane.write_scope or []),
                worktree=lane.worktree,
                branch=lane.branch,
                integration_policy=lane.integration_policy or "independent",
                harness_state_namespace=lane.harness_state_namespace,
            )
        )
    return manifests


def enforce_topology(
    declaration: SequenceDeclaration,
    *,
    gate_input: Optional[TopologyGateInput] = None,
) -> TopologyEnforcement:
    """The authoritative topology/integration gate consumed *before* launch.

    Reuses :mod:`skillweave.dispatch.topology` and
    :mod:`skillweave.dispatch.integration` decisions verbatim — it only orders and
    enforces them at the operator dispatcher's live seam:

    * every governed mutating lane's manifest is complete (F6): a partial or
      absent field raises :class:`TopologyGateError` before any worker starts;
    * overlapping write scope / incompatible base / shared harness state namespace
      serialize into separate batches (acceptance criterion 2);
    * a ``requires_integrator`` lane without an explicit eligible integrator fails
      closed (F3);
    * a semantic conflict removes the conflicted lane from normal fan-out and
      returns a bounded Integrator assignment (F2);
    * a dirty/detached/wrong-branch/uncommitted candidate is refused before
      integration (F5).

    The returned :class:`TopologyEnforcement` drives the actual fan-out grouping;
    nothing here edits product paths.
    """
    from skillweave.dispatch.topology import (
        CycleError,
        ManifestError,
        assess_eligibility,
        build_serialization_plan,
    )
    from skillweave.dispatch.integration import (
        SemanticConflictError,
        assign_semantic_conflict,
    )

    gate_input = gate_input or TopologyGateInput()
    manifests = derive_topology_manifests(declaration)
    by_id = {m.lane_id: m for m in manifests}

    for manifest in manifests:
        try:
            manifest.validate()
        except ManifestError as exc:
            raise TopologyGateError(str(exc)) from exc

    integration_ids = list(gate_input.integration_lanes or [])
    eligibility = dict(gate_input.eligibility or {})
    eligibility_supplied = gate_input.eligibility is not None

    # F3: every declared integration lane must be a real, declared governed
    # lane — an arbitrary id in ``integration_lanes`` does not release
    # ``requires_integrator``.
    for iid in integration_ids:
        if iid not in by_id:
            raise TopologyGateError(
                f"integration lane {iid!r} is not a declared lane in the wave"
            )

    requires = [
        manifest
        for manifest in manifests
        if manifest.integration_policy == "requires_integrator"
    ]

    for manifest in requires:
        lid = manifest.lane_id
        # A lane declaring ``requires_integrator`` must be folded by a *distinct,
        # declared, ordered-after* integration lane: an integrator declares the
        # requiring lane in its own ``depends_on`` (matching dependency/policy
        # semantics). Self, unknown, concurrent, dependency-mismatched, or a
        # missing/ failing eligibility observation all fail closed.
        candidates = [
            iid
            for iid in integration_ids
            if iid != lid and lid in (by_id[iid].depends_on or [])
        ]
        if not candidates:
            raise TopologyGateError(
                f"lane {lid!r} declares requires_integrator but no distinct "
                "declared integration lane is ordered after it (a matching "
                "depends_on) to fold it"
            )
        for iid in candidates:
            if by_id[iid].integration_policy != "independent":
                raise TopologyGateError(
                    f"integration lane {iid!r} must declare integration_policy "
                    f"'independent' to fold lane {lid!r}, got "
                    f"{by_id[iid].integration_policy!r}"
                )

    # CTRL-C4-INTEGRATION-GRAPH: an explicit integration lane must integrate at
    # least one in-wave dependency, and every dependency it names for integration
    # must exist in the declared wave. A mere ``integration_lanes`` label without
    # the dependency relation grants no fail-open exception.
    for iid in integration_ids:
        deps = list(by_id[iid].depends_on or [])
        in_wave = [d for d in deps if d in by_id]
        if not in_wave:
            raise TopologyGateError(
                f"integration lane {iid!r} declares no in-wave dependency to "
                "integrate; a mere integration-lane label does not grant an "
                "exception"
            )
        missing = [d for d in deps if d not in by_id]
        if missing:
            raise TopologyGateError(
                f"integration lane {iid!r} depends on undeclared lane(s) "
                f"{sorted(missing)}; dependencies used for integration must "
                "exist in the wave"
            )

    # F5: eligibility is fail-closed at the pre-integration boundary. An
    # observed (non-``None``) eligibility map must cover *every* governed lane —
    # a governed lane whose state is absent is refused, not skipped. A
    # ``requires_integrator`` lane (and its integrator) must always carry a
    # present, passing observation, even when no map was supplied at all.
    def _require_eligible(lane_id: str) -> None:
        manifest = by_id[lane_id]
        state = eligibility.get(lane_id)
        if state is None:
            raise TopologyGateError(
                f"lane {lane_id!r} has no observed worktree state before integration"
            )
        reasons = assess_eligibility(
            manifest, state, cache_allowlist=gate_input.cache_allowlist
        )
        if reasons:
            raise TopologyGateError(
                f"lane {lane_id!r} is not eligible to integrate: " + "; ".join(reasons)
            )

    if eligibility_supplied:
        for manifest in manifests:
            _require_eligible(manifest.lane_id)
    else:
        # Even when no eligibility map was supplied, a pre-integration boundary
        # cannot release: every explicit integration lane and every in-wave lane
        # it integrates must carry a present, passing observation. Merely naming
        # ``integration_lanes`` never grants a fail-open exception, whether or
        # not any lane declares ``requires_integrator``.
        observed: list[str] = []
        seen: set[str] = set()
        for iid in integration_ids:
            if iid not in seen:
                seen.add(iid)
                observed.append(iid)
            for dep in by_id[iid].depends_on or []:
                if dep in by_id and dep not in seen:
                    seen.add(dep)
                    observed.append(dep)
        for lid in observed:
            _require_eligible(lid)

    # F2: a semantic conflict is routed out of normal fan-out to the bounded
    # Integrator. The controller launches no worker for the conflicted lane and
    # performs no product edit — it only produces the assignment.
    removed: list[str] = []
    integrator_assignment = None
    if gate_input.semantic_conflict is not None:
        conflict_id = gate_input.semantic_conflict
        lane = by_id.get(conflict_id)
        if lane is None:
            raise TopologyGateError(
                f"semantic conflict names lane {conflict_id!r} with no topology manifest"
            )
        try:
            integrator_assignment = assign_semantic_conflict(
                lane,
                conflict=f"semantic conflict in lane {conflict_id}",
                write_scope=list(gate_input.conflict_write_scope or []),
                test_contract=list(gate_input.conflict_test_contract or []),
            )
        except SemanticConflictError as exc:
            raise TopologyGateError(str(exc)) from exc
        removed.append(conflict_id)

    remaining = [m for m in manifests if m.lane_id not in removed]
    groups: list[list[str]] = []
    if remaining:
        try:
            plan = build_serialization_plan(remaining, integration_lanes=integration_ids)
        except ManifestError as exc:
            raise TopologyGateError(str(exc)) from exc
        except CycleError as exc:
            raise TopologyGateError(str(exc)) from exc
        groups = [list(group) for group in plan.groups]

    return TopologyEnforcement(
        groups=groups,
        governed=[m.lane_id for m in manifests],
        removed_lane_ids=removed,
        integrator_assignment=integrator_assignment,
    )


class ProfileLocationError(OperatorDispatchError):
    """The declared profile path could not be loaded (a precise product error).

    The carry-forward tightening: instead of surfacing the loader's raw exception
    (``HarnessError`` or a bare ``ProfileResolutionError``) the application names
    the missing profile location with a stable field, so the failure is
    attributable to the caller's path before any launch is attempted.
    """

    def __init__(self, path: str, detail: str):
        self.path = path
        super().__init__(f"profile location '{path}' could not be loaded: {detail}")


def generate_run_id() -> str:
    """Return a machine-readable, collision-resistant run identifier.

    A bare hex UUID carries no prefix or punctuation a parser must decode.
    """
    return uuid.uuid4().hex


def _new_raw_artifact_store() -> Any:
    """Return a fresh :class:`RawArtifactStore` (lazy runtime import).

    The registry is an optional (lazy-bound) subpackage; it is resolved via
    ``importlib.import_module`` (a string, not an import statement) so the
    dispatch application module keeps a runtime-free eager import closure
    (GLE-020), exactly like the fan-out's runner adapter.
    """
    return importlib.import_module("skillweave.runtime.registry").RawArtifactStore()


# ── Lane plan / report (dry-run and post-run) ───────────────────────────────


@dataclass
class LanePlan:
    lane_id: str
    role: str
    repo: Optional[str]
    base: Optional[str]
    execution_model: Optional[str]
    mutating: bool
    model: Optional[str]
    launch: bool
    in_place: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "role": self.role,
            "repo": self.repo,
            "base": self.base,
            "execution_model": self.execution_model,
            "mutating": self.mutating,
            "model": self.model,
            "launch": self.launch,
            "in_place": self.in_place,
        }


@dataclass
class DispatchReport:
    profile: str
    execution_model: str
    max_parallel: int
    max_correction_rounds_per_wave: int
    lanes: list[LanePlan] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "execution_model": self.execution_model,
            "max_parallel": self.max_parallel,
            "max_correction_rounds_per_wave": self.max_correction_rounds_per_wave,
            "lanes": [lane.to_dict() for lane in self.lanes],
            "parallel_groups": [list(group) for group in self.parallel_groups],
        }


# ── Workspace seam ──────────────────────────────────────────────────────────


@dataclass
class ProvisionedWorkspace:
    """A lane's materialised workspace: attested base SHA and its exact path.

    The path is the *materialised* worktree the provider created for that lane.
    It is the only correct working directory for that lane's mutating worker:
    never substitute the operator/global cwd for a lane whose workspace was
    attested.
    """

    base_sha: str
    path: Optional[str] = None


class WorkspaceSeam:
    """Adapter over the shared workspace provider.

    ``provision`` materialises a lane's declared base into an attested workspace
    and returns the attested base SHA *and* the materialised path; ``release``
    tears it down.
    """

    def provision(self, lane: Lane, run_id: str) -> ProvisionedWorkspace:
        raise NotImplementedError

    def release(self, lane: Lane, run_id: str) -> None:
        raise NotImplementedError


class GitWorkspaceSeam(WorkspaceSeam):
    """Default seam over :class:`GitWorktreeProvider`.

    Provisioning is per-lane on a run/lane-derived branch, so two lanes never
    share a branch. The attested base SHA is the provider's resolved full SHA;
    the materialised path is the provider's worktree path.
    """

    def __init__(self, repo_root: str):
        from skillweave.workspace.provider import GitWorktreeProvider

        self._provider = GitWorktreeProvider(repo_root)
        self._workspaces: dict[str, Any] = {}

    def provision(self, lane: Lane, run_id: str) -> ProvisionedWorkspace:
        branch = f"sw-dispatch/{run_id[:8]}/{lane.id}".replace("/", "-")
        workspace = self._provider.acquire(lane.base or "", branch)
        self._workspaces[lane.id] = workspace
        return ProvisionedWorkspace(
            base_sha=workspace.attestation.base_sha,
            path=workspace.attestation.path,
        )

    def release(self, lane: Lane, run_id: str) -> None:
        workspace = self._workspaces.pop(lane.id, None)
        if workspace is not None:
            self._provider.release(workspace.attestation)


# ── Lane grouping: disjoint overlap vs mutually-exclusive serialisation ─────


def _pare_lanes(lanes: Sequence[Lane], max_parallel: int) -> list[list[Lane]]:
    """Group lanes into fan-out groups by repo exclusivity and ``max_parallel``.

    Two lanes are *disjoint* (and may overlap) when they touch different repos;
    lanes sharing a repo are *mutually exclusive* over the workspace and must
    serialise into separate groups (criterion 3). ``max_parallel`` caps a group's
    size, folding overflow into a following group.
    """
    groups: list[list[Lane]] = []
    current: list[Lane] = []
    occupied: set[str] = set()

    def _flush() -> None:
        if current:
            groups.append(list(current))
        current.clear()
        occupied.clear()

    for lane in lanes:
        repo = lane.repo or ""
        if (repo and repo in occupied) or len(current) >= max_parallel:
            _flush()
        current.append(lane)
        if repo:
            occupied.add(repo)
    _flush()
    return groups


def _group_for_launch(
    mutating: Sequence[Lane],
    max_parallel: int,
    enforcement: TopologyEnforcement,
) -> list[list[Lane]]:
    """Choose the launch batches for the mutating lanes.

    When the wave is topology-governed (:attr:`enforcement.governed` non-empty),
    the collision-safe serialization groups drive fan-out: every governed lane is
    placed in its serialization batch so two colliding lanes never share a
    fan-out call, and serialized (colliding) lanes each get their own single-lane
    batch. Non-governed lanes keep the legacy repo-exclusivity grouping. When
    nothing is governed, the legacy :func:`_pare_lanes` path is preserved
    unchanged (v1.3.10 compatibility).
    """
    if not enforcement.governed:
        return _pare_lanes(list(mutating), max_parallel)

    by_id = {lane.id: lane for lane in mutating}
    governed_ids = set(enforcement.governed)
    groups: list[list[Lane]] = []
    for group_ids in enforcement.groups:
        lane_group = [by_id[lid] for lid in group_ids if lid in by_id]
        if lane_group:
            groups.append(lane_group)

    non_governed = [lane for lane in mutating if lane.id not in governed_ids]
    if non_governed:
        groups.extend(_pare_lanes(non_governed, max_parallel))
    return groups


def _default_inline_seam(
    command: Sequence[str],
    *,
    run_id: str,
    subject_repo: str,
    subject_commit: str,
    tool: str,
    model: str,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    artifact_store: Optional[Any] = None,
) -> Any:
    """Run a single lane through the single-process seam, never the fan-out path.

    This is the default transport for serialized/INLINE lanes: it launches
    exactly one process via ``runtime.runner_adapter.run_command`` (one blocking
    child, no start-before-reap overlap) and wraps the resulting
    :class:`ProcessResult` into the same :class:`FanOutChild` shape the multi-child
    fan-out path produces, so callers record child outcomes and receipt
    references uniformly without the fan-out wiring. The single process is
    launched synchronously — it is a distinct seam from ``fan_out_dispatch`` and
    must never be reached for a lane that belongs to a parallel group.
    """
    from skillweave.routing.modelspec import from_value
    from skillweave.routing.faigate_adapter import resolve_model_spec
    from skillweave.fanout.dispatch import (
        FanOutChild,
        FanOutResult,
        _make_receipt_reference,
        _resolve_outcome,
        _store_child_bytes,
    )

    runner_adapter = importlib.import_module("skillweave.runtime.runner_adapter")

    child_run_id = f"{run_id}-0"
    resolved_model = resolve_model_spec(from_value(model))
    result = runner_adapter.run_command(
        list(command),
        run_id=child_run_id,
        subject_repo=subject_repo,
        subject_commit=subject_commit,
        tool=tool,
        model=resolved_model,
        timeout=timeout,
        cwd=cwd,
    )
    outcome = _resolve_outcome(result)
    child = FanOutChild(
        child_run_id=child_run_id,
        command=list(command),
        result=result,
        model=resolved_model,
        subject_repo=subject_repo,
        subject_commit=subject_commit,
        tool=tool,
        cwd=cwd,
        raw_bytes=result.stdout or b"",
        stderr_bytes=result.stderr or b"",
        outcome=outcome,
        stdout_ref=_make_receipt_reference(result.stdout_receipt, stream="stdout"),
        stderr_ref=_make_receipt_reference(result.stderr_receipt, stream="stderr"),
    )
    if artifact_store is not None:
        _store_child_bytes(artifact_store, child)
    return FanOutResult(children=[child], overlapped=False)


# ── The application ─────────────────────────────────────────────────────────


@dataclass
class DispatchRun:
    """The outcome of one executed wave.

    ``run_id`` is the machine-readable identifier. ``report`` is the resolved
    plan. ``halted``/``halt_reason`` record whether the correction budget was
    exhausted (``HALT_REQUIRES_OPERATOR``) and no further child started.

    ``results`` returns the per-child machine outcomes and receipt references
    directly to the caller (criterion 3): each entry carries one child's
    ``outcome`` (``exit_code``/``signal``/``timed_out``/``launch_failed``) and
    its resolvable stdout/stderr receipt references. Empty inline stdout/stderr
    never hides an available artifact — the reference rides beside the outcome.
    """

    run_id: str
    wave: str
    report: DispatchReport
    halted: bool = False
    halt_reason: Optional[str] = None
    correction_rounds: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    failure_policy: Optional[str] = None
    artifact_store: Optional[Any] = None
    integrator_assignment: Optional[Any] = None

    @property
    def resolver(self) -> Optional[Callable[[str], bytes]]:
        """The content-addressed resolver bound to this run's artifact store.

        A caller that received this run's ``results`` (receipt references) can
        resolve any returned reference to its raw bytes through this resolver
        without re-inserting the bytes: the fan-out already stored stdout and
        stderr under their digests, so ``raw = ref.resolve(run.resolver)`` works
        immediately. ``None`` only for a run produced with no store (e.g. a
        dry-run).
        """
        return self.artifact_store.resolve if self.artifact_store is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "wave": self.wave,
            "report": self.report.to_dict(),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "correction_rounds": self.correction_rounds,
            # Child machine outcomes and receipt references ride back to the
            # caller directly, so a consumer never reaches into a ProcessResult.
            "results": [dict(r) for r in self.results],
            "failures": [dict(f) for f in self.failures],
            # The configured wave failure policy (profile ``on_model_failure``)
            # is applied to the surface so unlike failures never collapse.
            "failure_policy": self.failure_policy,
            # A semantic conflict routed to the bounded Integrator is surfaced as
            # a hand-off, never a controller product edit.
            "integrator_assignment": (
                self.integrator_assignment.to_dict()
                if self.integrator_assignment is not None
                else None
            ),
            # Result metadata is explicit about the experimental, wave-scoped
            # nature of this command and makes no stable-transport claim.
            "experimental": True,
            "scope": "wave",
            "transport_compatibility": "none (no stable 1.4 contract)",
        }


def enforce_execution_model(value: Any) -> str:
    """Enforce the legal execution-model vocabulary at the live consumer."""
    if value not in EXECUTION_MODELS:
        raise ExecutionModelError(value)
    return str(value)


class OperatorDispatchApplication:
    """The dispatch application service, with injectable seams.

    ``workspace_seam`` defaults to :class:`GitWorkspaceSeam` over ``repo_root``
    (default the current directory); ``fanout_seam`` defaults to
    :func:`skillweave.fanout.dispatch.fan_out_dispatch`. Both are injectable so a
    test can prove overlap, attestation, and red paths without a live worktree.
    """

    def __init__(
        self,
        *,
        workspace_seam: Optional[WorkspaceSeam] = None,
        fanout_seam: Optional[Callable[..., Any]] = None,
        inline_seam: Optional[Callable[..., Any]] = None,
        repo_root: Optional[str] = None,
        cwd: Optional[str] = None,
        artifact_store: Optional[Any] = None,
    ):
        self._workspace_seam = workspace_seam
        self._fanout_seam = fanout_seam
        self._inline_seam = inline_seam
        self._repo_root = repo_root
        self._cwd = cwd
        self._artifact_store = artifact_store
        self._active_store: Optional[Any] = None
        self._last_success: dict[str, bool] = {}
        self._typed_failure: dict[str, bool] = {}

    def _fanout(self) -> Callable[..., Any]:
        if self._fanout_seam is not None:
            return self._fanout_seam
        from skillweave.fanout.dispatch import fan_out_dispatch

        return fan_out_dispatch

    def _inline(self) -> Callable[..., Any]:
        """The single-lane execution seam (never the multi-child fan-out path).

        A serialized/INLINE lane runs exactly once through this distinct seam;
        only a parallel, subagent-safe group enters :func:`_fanout`. The default
        launches a single process through the single-process runner primitive
        (``run_command``), wrapping it into the same child shape the fan-out
        path yields, so a recording seam can tell ``inline`` from ``fanout``.
        """
        if self._inline_seam is not None:
            return self._inline_seam
        return _default_inline_seam

    def _workspace(self) -> WorkspaceSeam:
        if self._workspace_seam is not None:
            return self._workspace_seam
        return GitWorkspaceSeam(self._repo_root or str(Path.cwd()))

    def load(
        self,
        sequence_path: str,
        profile_path: str,
        *,
        required_criteria: Optional[Sequence[int]] = None,
    ) -> tuple[SequenceDeclaration, ResolvedDispatch, DispatchReport]:
        """Parse and resolve a sequence + profile fail-closed.

        Enforces the execution-model enum (sequence and per-lane), loads the
        sequence through the contract, validates it fail-closed, and resolves
        the profile. No side effects.
        """
        raw = yaml.safe_load(Path(sequence_path).read_text(encoding="utf-8")) or {}
        declaration = load_sequence(raw)

        enforce_execution_model(declaration.execution_model)
        for lane in declaration.mutating_lanes():
            enforce_execution_model(lane.execution_model)

        # Attach each lane's optional required-evidence declaration. The
        # contract dataclass owns no such field, so it rides here (raw YAML ->
        # lane instance) and is consumed by the done-gate in :func:`dispatch`.
        raw_lanes = {ln.get("id"): ln for ln in (raw.get("lanes") or [])}
        for lane in declaration.lanes:
            raw_lane = raw_lanes.get(lane.id) or {}
            required = raw_lane.get("required_evidence")
            if isinstance(required, list):
                lane.required_evidence = list(required)
            else:
                # Undeclared -> no evidence gate; the lane carries ``None`` so
                # the done-gate skips it. A declared-but-empty list is the
                # fail-closed case and is preserved as ``[]``.
                lane.required_evidence = (
                    [] if "required_evidence" in raw_lane else None
                )

        try:
            resolved = resolve_dispatch_profile(
                profile_path,
                [lane.role for lane in declaration.lanes],
            )
        except (ProfileResolutionError, HarnessError) as exc:
            # A precise product error for a missing/un-loadable profile path,
            # named before any launch (carry-forward tightening).
            raise ProfileLocationError(profile_path, str(exc)) from exc

        criteria = (
            list(required_criteria) if required_criteria else _all_criteria(declaration)
        )
        validate_for_dispatch(declaration, criteria)

        return declaration, resolved, _build_report(declaration, resolved)

    def dry_run(
        self,
        sequence_path: str,
        profile_path: str,
        *,
        wave: str = "0",
        required_criteria: Optional[Sequence[int]] = None,
    ) -> DispatchRun:
        """Resolve and report without launching any worker (criterion 5)."""
        _, _, report = self.load(
            sequence_path, profile_path, required_criteria=required_criteria
        )
        return DispatchRun(run_id=generate_run_id(), wave=wave, report=report)

    def dispatch(
        self,
        sequence_path: str,
        profile_path: str,
        *,
        wave: str = "0",
        required_criteria: Optional[Sequence[int]] = None,
        sink: Optional[Any] = None,
        work: bytes = b"",
        gate_input: Optional[TopologyGateInput] = None,
    ) -> DispatchRun:
        """Execute one wave and return a machine-readable run identifier.

        ``sink`` is the JSONL text stream the event stream appends to (defaults
        to ``sys.stdout``). Returns a :class:`DispatchRun` whose ``run_id`` is
        the machine-readable identifier.

        ``gate_input`` (optional) carries the observed topology/integration facts
        (explicit integration lanes, a semantic conflict, per-lane eligibility).
        When supplied, :func:`enforce_topology` runs *before* any workspace is
        provisioned or worker launched; a governed mutating lane with an
        incomplete manifest, an unabsorbed collision, a missing eligible
        integrator, a semantic conflict, or an ineligible worktree refuses the
        wave fail-closed.
        """
        import sys

        declaration, resolved, report = self.load(
            sequence_path, profile_path, required_criteria=required_criteria
        )

        enforcement = enforce_topology(declaration, gate_input=gate_input)
        removed = set(enforcement.removed_lane_ids)

        run_id = generate_run_id()
        self._last_success = {}
        self._typed_failure = {}
        self._active_store = (
            self._artifact_store
            if self._artifact_store is not None
            else _new_raw_artifact_store()
        )
        self._results: list[dict[str, Any]] = []
        self._failures: list[dict[str, Any]] = []
        stream = DispatchEventStream(run_id, sink if sink is not None else sys.stdout)
        stream.wave_started(wave=wave)

        ws = self._workspace()
        mutating = [
            lane for lane in declaration.mutating_lanes() if lane.id not in removed
        ]

        # Provision + attest every mutating lane; a base mismatch blocks before
        # any child starts (criterion 4). The materialised path is retained
        # per lane so the worker runs *inside* its attested worktree.
        provisioned: dict[str, ProvisionedWorkspace] = {}
        for lane in mutating:
            pw = ws.provision(lane, run_id)
            provisioned[lane.id] = pw
            if (lane.base or "") != pw.base_sha:
                raise WorkspaceMismatchError(lane.id, lane.base or "", pw.base_sha)

        groups = _group_for_launch(mutating, declaration.max_parallel, enforcement)
        halted = False
        halt_reason: Optional[str] = None
        rounds = 0

        try:
            for group in groups:
                if len(group) == 1:
                    self._run_lane(
                        run_id,
                        wave,
                        group[0],
                        resolved,
                        stream,
                        work,
                        round_=0,
                        provisioned=provisioned,
                    )
                else:
                    self._fanout_group(
                        run_id,
                        wave,
                        group,
                        resolved,
                        stream,
                        work,
                        round_=0,
                        provisioned=provisioned,
                    )

            # Failure policy applied to typed failures; the legacy/untyped
            # verification failures keep the correction-budget path.
            failed = self._reconcile_failed(declaration, resolved, stream, run_id, wave)
            policy = _failure_policy_of(resolved)
            max_retries = _max_retries_of(resolved)

            def _typed(failed_lanes: list[Any]) -> list[Any]:
                return [ln for ln in failed_lanes if self._typed_failure.get(ln.id, False)]

            def _legacy(failed_lanes: list[Any]) -> list[Any]:
                return [ln for ln in failed_lanes if not self._typed_failure.get(ln.id, False)]

            typed = _typed(failed)
            legacy = _legacy(failed)

            # ``abort`` halts immediately after the first policy-managed failure
            # and starts zero correction children.
            if policy == "abort" and typed:
                halted = True
                halt_reason = HALT_REQUIRES_OPERATOR
            else:
                # Legacy (untyped) lanes are budget-managed as before; typed
                # lanes are retried only under ``retry``, bounded by both
                # ``limits.max_retries`` and ``max_correction_rounds_per_wave``.
                while (
                    legacy or (policy == "retry" and typed)
                ) and rounds < declaration.max_correction_rounds_per_wave:
                    typed_eligible = (
                        typed if (policy == "retry" and rounds < max_retries) else []
                    )
                    if not legacy and not typed_eligible:
                        break
                    rounds += 1
                    for lane in legacy + typed_eligible:
                        self._run_lane(
                            run_id,
                            wave,
                            lane,
                            resolved,
                            stream,
                            work,
                            round_=rounds,
                            provisioned=provisioned,
                        )
                    failed = self._reconcile_failed(
                        declaration, resolved, stream, run_id, wave
                    )
                    typed = _typed(failed)
                    legacy = _legacy(failed)

                if legacy:
                    # Budget exhausted on untyped verification failures.
                    halted = True
                    halt_reason = HALT_REQUIRES_OPERATOR
                elif policy == "retry" and typed:
                    # Retry-policy lanes still failing after max_retries.
                    halted = True
                    halt_reason = HALT_REQUIRES_OPERATOR
                # ``skip``-policy typed failures stay failed (not done) without
                # a halt: other lanes and the wave continue.

            if halted:
                stream.emit(
                    wave=wave,
                    lane_id="",
                    dispatch_id="",
                    event_type=EventType.PROCESS_TERMINAL,
                    process_status=ProcessStatus.EXITED,
                    task_status=TaskStatus.FAILED,
                    payload={"halt_reason": HALT_REQUIRES_OPERATOR},
                )
        finally:
            for lane in mutating:
                ws.release(lane, run_id)

        return DispatchRun(
            run_id=run_id,
            wave=wave,
            report=report,
            halted=halted,
            halt_reason=halt_reason,
            correction_rounds=rounds,
            results=self._results,
            failures=self._failures,
            failure_policy=_failure_policy_of(resolved),
            artifact_store=self._active_store,
            integrator_assignment=enforcement.integrator_assignment,
        )

    # -- lane execution helpers --------------------------------------------

    def _command_for(
        self, lane: Lane, resolved: ResolvedDispatch
    ) -> Optional[list[str]]:
        role = resolved.role(lane.role)
        if role is None or not role.is_launch():
            return None
        from skillweave.routing.dispatch import tokenize_launch

        return tokenize_launch(role.tool.launch_command) + [
            str(a) for a in role.tool.args
        ]

    def _model_for(self, lane: Lane, resolved: ResolvedDispatch) -> str:
        role = resolved.role(lane.role)
        return (
            role.model.resolved
            if (role is not None and role.model is not None)
            else "in-place"
        )

    def _emit_status(
        self,
        stream: DispatchEventStream,
        run_id: str,
        wave: str,
        lane: Lane,
        succeeded: bool,
        round_: int,
        *,
        outcome: Optional[str] = None,
        receipt_refs: Optional[list[str]] = None,
    ) -> None:
        dispatch_id = f"{run_id}-{lane.id}-r{round_}"
        status = TaskStatus.DONE if succeeded else TaskStatus.FAILED
        ps = _process_status_for(outcome, succeeded)
        payload = {"correction_round": round_} if round_ else None
        stream.process_terminal(
            wave=wave,
            lane_id=lane.id,
            dispatch_id=dispatch_id,
            process_status=ps,
            task_status=status,
            payload=payload,
        )
        stream.lane_terminal(
            wave=wave,
            lane_id=lane.id,
            dispatch_id=dispatch_id,
            task_status=status,
        )
        if receipt_refs:
            stream.evidence_recorded(
                wave=wave, lane_id=lane.id, dispatch_id=dispatch_id,
                receipt_refs=receipt_refs,
            )
        self._last_success[lane.id] = succeeded

    def _record_child_results(
        self,
        lane: Lane,
        children: list[Any],
        *,
        round_: int,
    ) -> None:
        """Record each child's one machine outcome and its receipt references.

        This is the criterion-3 surface: the child outcome and its resolvable
        stdout/stderr references are returned to the caller directly. An empty
        inline stdout/stderr never hides an available artifact — the reference
        is emitted even when the referenced stream has zero bytes.
        """
        for child in children:
            outcome = _child_outcome(child)
            entry: dict[str, Any] = {
                "lane_id": lane.id,
                "round": round_,
                "outcome": outcome,
            }
            child_dict = getattr(child, "to_dict", None)
            if callable(child_dict):
                cd = child_dict()
                entry["child_run_id"] = cd.get("child_run_id")
                entry["model"] = cd.get("model")
                entry["exit_code"] = cd.get("exit_code")
                entry["signal"] = cd.get("signal")
                entry["termination"] = cd.get("termination")
                entry["stdout"] = cd.get("stdout")
                entry["stderr"] = cd.get("stderr")
            self._results.append(entry)

    def _record_failure(
        self,
        lane: Lane,
        *,
        outcome: str,
        detail: str,
        round_: int = 0,
    ) -> None:
        """Record one distinct machine failure so unlike cases never collapse.

        Non-zero exit, timeout, signal, launch failure and missing required
        evidence each produce their own entry (distinct ``outcome``), and the
        configured wave failure policy is applied to the dispatcher's surface.
        """
        self._failures.append(
            {
                "lane_id": lane.id,
                "round": round_,
                "outcome": outcome,
                "detail": detail,
            }
        )

    def _gate_required_evidence(
        self,
        lane: Lane,
        refs: list[Any],
    ) -> None:
        """Enforce the required-evidence done-gate for a lane (criterion 4).

        A lane cannot reach ``done`` when its declared required-evidence list is
        empty, when any referenced stream has no resolvable receipt, or when a
        referenced artifact cannot resolve / fails integrity. This is checked
        here (the done-gate) so a lane whose evidence is unsatisfied is reported
        ``failed``, never ``done``.
        """
        by_stream: dict[str, Any] = {}
        for ref in refs:
            if ref is not None:
                by_stream[ref.stream] = ref
        resolver = (
            self._active_store.resolve if self._active_store is not None else None
        )
        resolve_required_evidence(
            lane, reference_by_stream=by_stream, resolver=resolver
        )

    def _lane_cwd(self, lane: Lane, provisioned: dict[str, ProvisionedWorkspace]) -> Optional[str]:
        """Return the exact attested worktree path for a mutating lane.

        A mutating lane with an attested workspace must run *inside* that
        materialised path — never the operator/global ``self._cwd``. For a
        lane with no provisioned workspace the caller's cwd is the fallback.
        """
        pw = provisioned.get(lane.id)
        if pw is not None and pw.path:
            return pw.path
        return self._cwd

    def _run_lane(
        self,
        run_id: str,
        wave: str,
        lane: Lane,
        resolved: ResolvedDispatch,
        stream: DispatchEventStream,
        work: bytes,
        round_: int,
        provisioned: Optional[dict[str, ProvisionedWorkspace]] = None,
    ) -> bool:
        stream.lane_started(wave=wave, lane_id=lane.id)
        command = self._command_for(lane, resolved)
        if command is None:
            # In-place role: explicit record, never a launch (criterion on
            # explicit in-place). Recorded as done and recorded.
            self._emit_status(stream, run_id, wave, lane, True, round_)
            stream.evidence_recorded(
                wave=wave, lane_id=lane.id, dispatch_id=f"{run_id}-{lane.id}-r{round_}"
            )
            return True

        role = resolved.role(lane.role)
        inline = self._inline()
        provisioned = provisioned or {}
        result = inline(
            command,
            run_id=run_id,
            subject_repo=lane.repo or "",
            subject_commit=lane.base or "",
            tool=role.tool.name,
            model=self._model_for(lane, resolved),
            cwd=self._lane_cwd(lane, provisioned),
            timeout=_resolved_timeout(resolved),
            artifact_store=self._active_store,
        )
        children = _fanout_children(result)
        self._record_child_results(lane, children, round_=round_)
        received_refs = _receipt_refs_of(children)

        succeeded = _result_succeeded(result)
        evidence_failed = False
        try:
            self._gate_required_evidence(lane, received_refs)
        except RequiredEvidenceError as exc:
            succeeded = False
            evidence_failed = True
            self._record_failure(
                lane, outcome="missing_evidence", detail=str(exc), round_=round_
            )

        self._typed_failure[lane.id] = evidence_failed or _typed_process_failure(
            children
        )

        if not succeeded:
            outcome = _first_outcome(children)
            self._record_failure(
                lane,
                outcome=outcome,
                detail=_first_failure_message(children),
                round_=round_,
            )

        self._emit_status(
            stream, run_id, wave, lane, succeeded, round_,
            outcome=_first_outcome(children),
            receipt_refs=[r.artifact_id for r in received_refs],
        )
        return succeeded

    def _fanout_group(
        self,
        run_id: str,
        wave: str,
        group: list[Lane],
        resolved: ResolvedDispatch,
        stream: DispatchEventStream,
        work: bytes,
        round_: int,
        provisioned: Optional[dict[str, ProvisionedWorkspace]] = None,
    ) -> None:
        # Start every lane in the group at once (overlap), then record per-lane.
        commands = [self._command_for(lane, resolved) for lane in group]
        for lane in group:
            stream.lane_started(wave=wave, lane_id=lane.id)

        from skillweave.fanout.dispatch import FanOutLaunchContext
        from skillweave.routing.modelspec import from_value

        provisioned = provisioned or {}
        models = [from_value(self._model_for(lane, resolved)) for lane in group]
        # Each lane carries its own repo/base/tool/cwd; never broadcast the
        # group leader's identity onto its siblings (criterion-4 blocker).
        contexts = [
            FanOutLaunchContext(
                subject_repo=lane.repo or "",
                subject_commit=lane.base or "",
                tool=resolved.role(lane.role).tool.name,
                cwd=self._lane_cwd(lane, provisioned),
            )
            for lane in group
        ]
        fanout = self._fanout()
        result = fanout(
            commands,
            run_id=run_id,
            subject_repo=group[0].repo or "",
            subject_commit=group[0].base or "",
            tool=resolved.role(group[0].role).tool.name,
            models=models,
            cwd=self._cwd,
            launch_contexts=contexts,
            timeout=_resolved_timeout(resolved),
            artifact_store=self._active_store,
        )
        children = getattr(result, "children", None) or []
        for lane, child in zip(group, children):
            child_list = [child]
            self._record_child_results(lane, child_list, round_=round_)
            refs = _receipt_refs_of(child_list)
            succeeded = _child_succeeded(child)
            evidence_failed = False
            try:
                self._gate_required_evidence(lane, refs)
            except RequiredEvidenceError as exc:
                succeeded = False
                evidence_failed = True
                self._record_failure(
                    lane, outcome="missing_evidence", detail=str(exc), round_=round_
                )

            self._typed_failure[lane.id] = evidence_failed or _typed_process_failure(
                child_list
            )

            if not succeeded:
                self._record_failure(
                    lane,
                    outcome=_child_outcome(child),
                    detail=_first_failure_message(child_list),
                    round_=round_,
                )
            self._emit_status(
                stream, run_id, wave, lane, succeeded, round_,
                outcome=_child_outcome(child),
                receipt_refs=[r.artifact_id for r in refs],
            )

    # -- correction budget reconciliation ------------------------------------

    def _reconcile_failed(
        self,
        declaration: SequenceDeclaration,
        resolved: ResolvedDispatch,
        stream: DispatchEventStream,
        run_id: str,
        wave: str,
    ) -> list[Lane]:
        """Return the mutating lanes whose most recent run did not succeed."""
        failed: list[Lane] = []
        for lane in declaration.mutating_lanes():
            command = self._command_for(lane, resolved)
            if command is None:
                continue  # in-place roles are never "failed" here
            if not self._last_success.get(lane.id, True):
                failed.append(lane)
        return failed


def _result_succeeded(result: Any) -> bool:
    if result is None:
        return True
    children = getattr(result, "children", None)
    if children is not None:
        return bool(children) and all(_child_succeeded(c) for c in children)
    if isinstance(result, dict):
        return bool(result.get("succeeded", True))
    return bool(getattr(result, "succeeded", True))


def _child_succeeded(child: Any) -> bool:
    if child is None:
        return True
    if isinstance(child, dict):
        return bool(child.get("succeeded", True))
    process_result = getattr(child, "result", child)
    return bool(getattr(process_result, "succeeded", True))


def _process_status_for(outcome: Optional[str], succeeded: bool) -> ProcessStatus:
    """Map a child's machine outcome to its dispatch process status.

    The four machine outcomes map to distinct ``ProcessStatus`` values, so a
    non-zero exit, a signal, a timeout and a launch failure are distinguishable
    in the stream rather than collapsing onto one "failed" bucket. A plain
    success is ``exited``; a launch failure is ``launch_failed``.
    """
    if outcome == "launch_failed":
        return ProcessStatus.LAUNCH_FAILED
    if outcome == "timed_out":
        return ProcessStatus.TIMED_OUT
    if outcome == "signal":
        return ProcessStatus.SIGNALED
    if succeeded:
        return ProcessStatus.EXITED
    return ProcessStatus.EXITED


# ── Child-result surface (machine outcome + receipt references) ─────────────


def _fanout_children(result: Any) -> list[Any]:
    """Return the fan-out children of a result, or ``[]`` for an unrecognised shape."""
    children = getattr(result, "children", None)
    if children is not None:
        return list(children)
    return []


def _child_outcome(child: Any) -> Optional[str]:
    """Return a child's single machine outcome, or ``None`` when absent.

    Prefers the fan-out's resolved ``outcome``; falls back to deriving one from
    the wrapped process result so a plain ``ProcessResult`` still yields a
    machine outcome (never leaving a terminal child without one).
    """
    outcome = getattr(child, "outcome", None)
    if outcome is not None:
        return outcome
    result = getattr(child, "result", child)
    termination = getattr(result, "termination", None)
    if termination == "timed_out":
        return "timed_out"
    if termination == "launch_failed":
        return "launch_failed"
    if getattr(result, "signal", None) is not None:
        return "signal"
    return "exit_code"


def _first_outcome(children: list[Any]) -> Optional[str]:
    """The single machine outcome of the first child, or ``None`` when empty."""
    return _child_outcome(children[0]) if children else None


def _first_failure_message(children: list[Any]) -> str:
    """The first child's failure message (or a fallback), for failure records."""
    if not children:
        return "no child result"
    result = getattr(children[0], "result", children[0])
    message = getattr(result, "message", "")
    if message:
        return message
    outcome = _child_outcome(children[0])
    return f"child outcome {outcome}"


def _receipt_refs_of(children: list[Any]) -> list[Any]:
    """Flatten the stdout/stderr receipt references across the given children.

    A ``ReceiptReference`` for each captured stream rides into the result so an
    available artifact is never hidden by empty inline output (criterion 3).
    """
    refs: list[Any] = []
    for child in children:
        for attr in ("stdout_ref", "stderr_ref"):
            ref = getattr(child, attr, None)
            if ref is not None:
                refs.append(ref)
    return refs


def _resolved_timeout(resolved: ResolvedDispatch) -> Optional[float]:
    """The resolved per-wave timeout, or ``None`` when no limit is configured."""
    limits = getattr(resolved, "limits", None)
    if limits is None:
        return None
    return getattr(limits, "timeout", None)


def _failure_policy_of(resolved: ResolvedDispatch) -> Optional[str]:
    """The configured wave failure policy (profile ``on_model_failure``)."""
    limits = getattr(resolved, "limits", None)
    if limits is None:
        return None
    return getattr(limits, "on_model_failure", None)


def _max_retries_of(resolved: ResolvedDispatch) -> int:
    """The configured retry bound (profile ``limits.max_retries``)."""
    limits = getattr(resolved, "limits", None)
    if limits is None:
        return 0
    retries = getattr(limits, "max_retries", 0)
    return int(retries) if retries is not None else 0


def _typed_process_failure(children: list[Any]) -> bool:
    """Whether any child is a typed process failure (policy-managed).

    A *typed* failure is a real process result that did not succeed with a
    concrete machine outcome (non-zero ``exit_code``, ``signal``, ``timed_out``
    or ``launch_failed``). A child with no wrapped process result (e.g. a
    synthetic verification marker that only reports ``succeeded=False``) is
    *not* typed: it stays on the legacy/untyped correction-budget path, so the
    existing budget gate is preserved without weakening it.
    """
    for child in children:
        result = getattr(child, "result", None)
        if result is None:
            continue
        if bool(getattr(result, "succeeded", True)):
            continue
        outcome = getattr(child, "outcome", None) or _child_outcome(child)
        if outcome in CHILD_OUTCOMES:
            return True
    return False


def _required_evidence_of(lane: Lane) -> Optional[list[str]]:
    """Return a lane's declared required-evidence list (stream names).

    Carried on the lane instance (attached from the raw sequence, since the
    contract dataclass owns no such field). ``None`` means *undeclared* (no
    evidence gate); an empty list ``[]`` is the declared-empty case, which the
    done-gate fails closed (criterion 4).
    """
    value = getattr(lane, "required_evidence", None)
    return list(value) if value is not None else None


def resolve_required_evidence(
    lane: Lane,
    *,
    reference_by_stream: dict[str, Any],
    resolver: Optional[Callable[[str], bytes]] = None,
) -> list[dict[str, Any]]:
    """Resolve a lane's declared required evidence against its captured refs.

    Fails closed: an undeclared lane passes trivially; a declared *empty*
    required-evidence list, or any referenced stream whose receipt reference is
    missing (``None``) or cannot resolve / fails integrity, raises
    :class:`RequiredEvidenceError` — the lane cannot be ``done``. On success,
    returns one dict per required stream describing the resolvable reference and
    its resolved byte length.

    ``reference_by_stream`` maps a stream name (``"stdout"``/``"stderr"``) to the
    lane's captured :class:`ReceiptReference` (or ``None``). ``resolver`` is the
    content-addressed resolver (``bytes = resolver(sha256)``) used to prove the
    referenced artifact is available and intact; when omitted, the reference's
    own ``verify`` over the captured bytes is the integrity check.
    """
    required = _required_evidence_of(lane)
    if required is None:
        return []
    if not required:
        raise RequiredEvidenceError(
            lane.id, "required-evidence list is empty (nothing declared to satisfy)"
        )
    resolved: list[dict[str, Any]] = []
    for stream in required:
        ref = reference_by_stream.get(stream)
        if ref is None:
            raise RequiredEvidenceError(
                lane.id, f"required evidence '{stream}' has no resolvable receipt"
            )
        try:
            if resolver is not None:
                ref.resolve(resolver)
            length = ref.byte_length
        except Exception as exc:  # noqa: BLE001
            raise RequiredEvidenceError(
                lane.id, f"required evidence '{stream}' failed integrity: {exc}"
            ) from exc
        resolved.append({"stream": stream, "artifact_id": ref.artifact_id, "byte_length": length})
    return resolved


def _build_report(
    declaration: SequenceDeclaration,
    resolved: ResolvedDispatch,
) -> DispatchReport:
    lane_plans: list[LanePlan] = []
    for lane in declaration.lanes:
        role = resolved.role(lane.role)
        lane_plans.append(
            LanePlan(
                lane_id=lane.id,
                role=lane.role,
                repo=lane.repo,
                base=lane.base,
                execution_model=lane.execution_model,
                mutating=lane.mutating,
                model=(
                    role.model.resolved if (role is not None and role.model) else None
                ),
                launch=bool(role is not None and role.is_launch()),
                in_place=bool(role is not None and role.in_place),
            )
        )
    groups = _pare_lanes(declaration.mutating_lanes(), declaration.max_parallel)
    return DispatchReport(
        profile=resolved.profile_name,
        execution_model=declaration.execution_model,
        max_parallel=declaration.max_parallel,
        max_correction_rounds_per_wave=declaration.max_correction_rounds_per_wave,
        lanes=lane_plans,
        parallel_groups=[[lane.id for lane in group] for group in groups],
    )


def _all_criteria(declaration: SequenceDeclaration) -> list[int]:
    seen: set[int] = set()
    for lane in declaration.mutating_lanes():
        for idx in lane.criteria_covered():
            seen.add(idx)
    return sorted(seen)
