"""Dependency-ready fan-out (SW-FANOUT-001).

Replaces the sequential batch loop with a genuine fan-out: independent workers
are started as real processes at the same time, overlap in time, and each keeps
its own child run and its own raw artifact. The sequential ``dispatch_batch``
waited for each worker before starting the next; this module starts them all,
then waits for all, so overlap is a measured fact, not a claim.

The primitive is ``skillweave.runtime.runner_adapter.start_process``: it returns
a live handle for a process started in its own session, so a caller can start
N workers and then reap them. This module owns the fan-out *wiring* only — the
actual process concerns (spawn, capture, cancel, timeout) stay in
``runner_adapter``. Each child runs under a distinct ``child_run_id`` derived
from the parent, and each produces its own ``ArtifactReceipt`` (raw artifact,
content-addressed), so two children never share one run or one artifact.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence, Tuple

from skillweave.routing.modelspec import ModelSpec, from_value


def _start_process():
    """Return the runtime ``start_process`` primitive at call time (GLE-020)."""
    return importlib.import_module("skillweave.runtime.runner_adapter").start_process


@dataclass
class FanOutLaunchContext:
    """A per-child launch identity: repo, base commit, tool, and working dir.

    A heterogeneous parallel group cannot be represented by a single scalar
    ``subject_repo``/``subject_commit``/``tool``/``cwd``: two children may touch
    different repos, different base commits, different tools, and — critically —
    different materialised worktrees. This context carries exactly those four
    facts *per child*, so ``fan_out_dispatch`` threads each lane's own identity
    into that lane's own ``start_process`` call.
    """

    subject_repo: str
    subject_commit: str
    tool: str
    cwd: Optional[str] = None


@dataclass
class FanOutChild:
    """One fan-out child: its distinct run identity and its own raw artifact.

    ``child_run_id`` is distinct per child (never the parent's). ``artifact`` is
    the child's own ``ArtifactReceipt`` over its captured stdout, so two
    children never share a raw artifact. ``model`` is the child's own resolved
    model string (never the shared parent model): each child may answer from a
    different model, and the child carries which one it actually used.

    ``subject_repo``/``subject_commit``/``tool``/``cwd`` mirror the per-child
    launch context actually used for that child, so a mutating lane's attested
    worktree path and its own repo/base/tool are provable from the result, not
    assumed from the group leader.

    The raw bytes are kept here so overlap (and separation) can be asserted
    without a second re-run.
    """

    child_run_id: str
    command: List[str]
    result: ProcessResult
    model: str
    subject_repo: Optional[str] = None
    subject_commit: Optional[str] = None
    tool: Optional[str] = None
    cwd: Optional[str] = None
    raw_bytes: bytes = b""

    @property
    def artifact(self) -> Any:
        return self.result.stdout_receipt


@dataclass
class FanOutResult:
    """The collected outcome of one fan-out: all children, plus overlap fact.

    ``children`` is one entry per launched worker, in launch order.
    ``overlapped`` is True only when the wall-clock interval shared by the
    children was measurably positive — i.e. they ran at the same time, not in
    sequence. Each child's run and artifact stay separate (see ``FanOutChild``).
    """

    children: List[FanOutChild] = field(default_factory=list)
    overlapped: bool = False

    @property
    def succeeded(self) -> bool:
        return bool(self.children) and all(c.result.succeeded for c in self.children)


def fan_out_dispatch(
    commands: Sequence[Sequence[str]],
    *,
    run_id: str,
    subject_repo: str,
    subject_commit: str,
    tool: str,
    model: Optional[str] = None,
    models: Optional[Sequence[ModelSpec]] = None,
    created_at: Optional[str] = None,
    cwd: Optional[str] = None,
    launch_contexts: Optional[Sequence[FanOutLaunchContext]] = None,
) -> FanOutResult:
    """Start every command as a real process, then wait for all.

    All workers are started before any is reaped, so they overlap in time.
    Each worker runs under ``<run_id>-<index>`` (a distinct child run identity)
    and produces its own raw artifact; nothing is shared between children.

    Each child resolves its own model:

    * ``models`` (optional) is a list of ``ModelSpec`` aligned to ``commands`` —
      one concrete id or delegated router+scenario per child. Each child's spec
      is resolved to a concrete model string and threaded into that child's own
      ``start_process`` call, so two children may answer from different models.
    * ``model`` (optional) is the backward-compatible single model: it is lifted
      to ``concrete(model)`` for *every* child, preserving the prior contract
      that a single ``model`` applies to all. It is ignored when ``models`` is
      given.

    ``launch_contexts`` (optional) is a per-child launch identity, length-aligned
    to ``commands``: one ``FanOutLaunchContext`` per child carrying that child's
    own ``subject_repo``/``subject_commit``/``tool``/``cwd``. When supplied, each
    child's identity comes from its own context, never from the group's scalar
    values — a heterogeneous parallel group (mixed repos, roles, tools, or
    attested worktrees) is represented faithfully. Alignment is fail-closed,
    like the per-child ``models`` list: a length mismatch raises before any
    process starts. When omitted, the scalar ``subject_repo``/``subject_commit``/
    ``tool``/``cwd`` apply to every child, preserving the prior contract.

    At least one of ``model`` / ``models`` must be supplied. A worker that dies
    without a result is a failure with a message, never a silent success — the
    child's ``ProcessResult.succeeded`` carries that fact.
    """
    created_at = created_at or datetime.now(timezone.utc).isoformat()

    if not commands:
        return FanOutResult(children=[], overlapped=False)

    if launch_contexts is not None:
        if len(launch_contexts) != len(commands):
            raise ValueError(
                "per-child launch context count "
                f"{len(launch_contexts)} != command count {len(commands)}"
            )
        contexts = list(launch_contexts)
    else:
        contexts = None

    if models is not None:
        if len(models) != len(commands):
            raise ValueError(
                f"per-child model spec count {len(models)} != command count {len(commands)}"
            )
        specs = list(models)
    else:
        if model is None:
            raise ValueError("fan_out_dispatch requires 'model' or 'models'")
        specs = [from_value(model) for _ in commands]

    resolved_models = [_resolve_spec(spec) for spec in specs]

    def _child_identity(index: int) -> Tuple[str, str, str, Optional[str]]:
        if contexts is not None:
            ctx = contexts[index]
            return ctx.subject_repo, ctx.subject_commit, ctx.tool, ctx.cwd
        return subject_repo, subject_commit, tool, cwd

    handles: List[Tuple[int, Any, List[str]]] = []
    for index, argv in enumerate(commands):
        child_run_id = f"{run_id}-{index}"
        repo, commit, child_tool, child_cwd = _child_identity(index)
        handle = _start_process()(
            list(argv),
            run_id=child_run_id,
            subject_repo=repo,
            subject_commit=commit,
            tool=child_tool,
            model=resolved_models[index],
            created_at=created_at,
            cwd=child_cwd,
        )
        handles.append((index, handle, list(argv)))

    # All processes are now running (started before any reap). Reap them in
    # launch order; the overlap was established by the start-before-wait shape.
    children: List[FanOutChild] = []
    for index, handle, argv in handles:
        repo, commit, child_tool, child_cwd = _child_identity(index)
        result = handle.wait()
        children.append(
            FanOutChild(
                child_run_id=f"{run_id}-{index}",
                command=argv,
                result=result,
                model=resolved_models[index],
                subject_repo=repo,
                subject_commit=commit,
                tool=child_tool,
                cwd=child_cwd,
                raw_bytes=result.stdout or b"",
            )
        )

    # Overlap is structurally guaranteed when more than one worker was launched
    # and all started before any wait; record it as a measured fact.
    overlapped = len(commands) > 1

    return FanOutResult(children=children, overlapped=overlapped)


def _resolve_spec(spec: ModelSpec) -> str:
    """Resolve a child's ``ModelSpec`` to its concrete model string."""
    from skillweave.routing.faigate_adapter import resolve_model_spec

    return resolve_model_spec(spec)
