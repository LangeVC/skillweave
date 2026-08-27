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

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

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


class OperatorDispatchError(Exception):
    """A dispatch request could not be satisfied (raised before any launch)."""


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


# ── The application ─────────────────────────────────────────────────────────


@dataclass
class DispatchRun:
    """The outcome of one executed wave.

    ``run_id`` is the machine-readable identifier. ``report`` is the resolved
    plan. ``halted``/``halt_reason`` record whether the correction budget was
    exhausted (``HALT_REQUIRES_OPERATOR``) and no further child started.
    """

    run_id: str
    wave: str
    report: DispatchReport
    halted: bool = False
    halt_reason: Optional[str] = None
    correction_rounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "wave": self.wave,
            "report": self.report.to_dict(),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "correction_rounds": self.correction_rounds,
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
        repo_root: Optional[str] = None,
        cwd: Optional[str] = None,
    ):
        self._workspace_seam = workspace_seam
        self._fanout_seam = fanout_seam
        self._repo_root = repo_root
        self._cwd = cwd
        self._last_success: dict[str, bool] = {}

    def _fanout(self) -> Callable[..., Any]:
        if self._fanout_seam is not None:
            return self._fanout_seam
        from skillweave.fanout.dispatch import fan_out_dispatch

        return fan_out_dispatch

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
    ) -> DispatchRun:
        """Execute one wave and return a machine-readable run identifier.

        ``sink`` is the JSONL text stream the event stream appends to (defaults
        to ``sys.stdout``). Returns a :class:`DispatchRun` whose ``run_id`` is
        the machine-readable identifier.
        """
        import sys

        declaration, resolved, report = self.load(
            sequence_path, profile_path, required_criteria=required_criteria
        )
        run_id = generate_run_id()
        self._last_success = {}
        stream = DispatchEventStream(run_id, sink if sink is not None else sys.stdout)
        stream.wave_started(wave=wave)

        ws = self._workspace()
        mutating = declaration.mutating_lanes()

        # Provision + attest every mutating lane; a base mismatch blocks before
        # any child starts (criterion 4). The materialised path is retained
        # per lane so the worker runs *inside* its attested worktree.
        provisioned: dict[str, ProvisionedWorkspace] = {}
        for lane in mutating:
            pw = ws.provision(lane, run_id)
            provisioned[lane.id] = pw
            if (lane.base or "") != pw.base_sha:
                raise WorkspaceMismatchError(lane.id, lane.base or "", pw.base_sha)

        groups = _pare_lanes(mutating, declaration.max_parallel)
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

            # Correction budget: a failed lane is re-run up to the declared
            # budget; past that, halt and start no further correction child.
            failed = self._reconcile_failed(declaration, resolved, stream, run_id, wave)
            while failed and rounds < declaration.max_correction_rounds_per_wave:
                rounds += 1
                for lane in failed:
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

            if failed:
                halted = True
                halt_reason = HALT_REQUIRES_OPERATOR
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
    ) -> None:
        dispatch_id = f"{run_id}-{lane.id}-r{round_}"
        status = TaskStatus.DONE if succeeded else TaskStatus.FAILED
        ps = ProcessStatus.EXITED if succeeded else ProcessStatus.LAUNCH_FAILED
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
        self._last_success[lane.id] = succeeded

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
        fanout = self._fanout()
        provisioned = provisioned or {}
        result = fanout(
            [command],
            run_id=run_id,
            subject_repo=lane.repo or "",
            subject_commit=lane.base or "",
            tool=role.tool.name,
            model=self._model_for(lane, resolved),
            cwd=self._lane_cwd(lane, provisioned),
        )
        succeeded = _result_succeeded(result)
        self._emit_status(stream, run_id, wave, lane, succeeded, round_)
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
        )
        children = getattr(result, "children", None) or []
        for lane, child in zip(group, children):
            succeeded = _child_succeeded(child)
            self._emit_status(stream, run_id, wave, lane, succeeded, round_)

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
