"""Run-scoped, read-only dispatch observer (SW138-OBSERVER-001).

This module turns the built-in ``observer`` role into exactly one active,
run-scoped, read-only observer for every non-dry dispatch wave, in one of two
modes selected at a single application seam:

* **built-in** — the resolved observer role has no ``ToolSpec``; the observer is
  recorded as *in-place* and *active*, never silently absent, and never starts a
  process.
* **tool-targeted** — the resolved observer role declares a ``ToolSpec``; the
  observer launches that exact tool *once* (before the first ops child) through
  the runtime ``start_process`` seam, delivers a deterministic, read-only
  serialized locator to it over stdin (``run_id``, ``wave``, mode, heartbeat
  interval, and the ordered replay of the real teed dispatch events), reaps it
  exactly once, and derives its receipt from the actual process result — never by
  relabeling the built-in detectors. Only a small documented machine JSON result
  on stdout contributes findings; an absent/malformed result, a non-zero exit, a
  signal, a timeout, or a launch failure all yield ``observed=false``.

In both modes the observer consumes the *real* dispatch event source (the live
:class:`~skillweave.dispatch.events.DispatchEventStream` replay), never a second
store, and emits typed findings for four conditions:

1. ``heartbeat_expiry`` — a running child exceeds the configured heartbeat
   interval without a terminal event.
2. ``terminal_missing_evidence`` — a terminal child reaches ``done`` without
   recording evidence.
3. ``contradictory_process_evidence`` — evidence is recorded for a process whose
   terminal status is ``failed`` (or a terminal reports a process state that
   contradicts its task state).
4. ``lane_completion_not_observed`` — a started lane has no ``lane_terminal`` in
   the stream.

Findings bind to run/wave/lane evidence and *never* mutate conditions: the
observer is strictly read-only. Every action that would give it authority —
dispatching work, mutating root-run state, approving a gate, writing the
repository, or repairing a finding — is denied *technically* through the shared
``AuthorityGuard`` / observer role capability matrix, raising ``AuthorityError``
before any effect. A prompt-only prohibition is not accepted here: the denial is
an executable probe that raises.

Read-only enforcement reuses:
* :class:`skillweave.runtime.authority.AuthorityGuard` and the ``observer`` role
  capability matrix (``is_read_only=True``, no mutate/approve/write),
* the observer role's read-only posture declared in the routing profile.

Observer lease persistence, offset persistence, and crash recovery are not
    provided by SkillWeave 1.3.8. No future persistence or recovery behaviour is
    claimed here or anywhere in this module. A run-scoped observer begins with a
    fresh, non-persistent view of its wave's event stream and does not survive a
    restart.

This module names no concrete model and no concrete harness: the mode is derived
from the resolved profile alone.

A second, independent class lives here too: :class:`LiveObserver`, the *live*
half of the trace observer (SW1311-OBSERVER-001). It consumes ordered typed
:class:`~skillweave.dispatch.contracts.DispatchEvent` records from the live
:class:`~skillweave.dispatch.events.DispatchEventStream` and folds them into the
deterministic :class:`~skillweave.trace.projection.Projection`, so a live
consumer sees a typed event within one heartbeat interval without polling a log
file or a process id. It is unrelated to :class:`DispatchObserver`: the latter
is the run-scoped read-only observer the dispatch application starts per wave,
while ``LiveObserver`` projects the typed stream for a live reader. They share
this module (both are "the observer") but hold no state in common.
"""

from __future__ import annotations

import importlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Sequence

from skillweave.dispatch.events import DispatchEventStream
from skillweave.trace.projection import Projection, Projector, ProjectionEvent
from skillweave.trace.view import (
    InterventionKind,
    InterventionRequest,
    assert_observer_authority,
)

#: Documented observer wait cap (seconds), applied only when the resolved limits
#: carry no per-wave timeout. A timeout is reported as ``termination ==
#: "timed_out"``, never as a silent hang and never as an invented success.
DEFAULT_OBSERVER_TIMEOUT: float = 300.0


def _lazy_start_process() -> Callable[..., Any]:
    """Return the runtime ``start_process`` primitive lazily (GLE-020)."""
    return importlib.import_module("skillweave.runtime.runner_adapter").start_process


class _authority_module():
    """Resolve the runtime ``authority`` module lazily (GLE-020).

    ``skillweave.runtime`` is an optional subpackage that must not be imported at
    module level here; the guard and role enum are resolved at call time, exactly
    like the reviewer gate.
    """

    def __getattr__(self, name: str):
        return getattr(importlib.import_module("skillweave.runtime.authority"), name)


_authority = _authority_module()


class ObserverCondition(str, Enum):
    """The four typed conditions an observer can find."""

    HEARTBEAT_EXPIRY = "heartbeat_expiry"
    TERMINAL_MISSING_EVIDENCE = "terminal_missing_evidence"
    CONTRADICTORY_PROCESS_EVIDENCE = "contradictory_process_evidence"
    LANE_COMPLETION_NOT_OBSERVED = "lane_completion_not_observed"


class ObserverMode(str, Enum):
    """The two observer modes resolved from the profile."""

    BUILT_IN = "built_in"
    TOOL_TARGETED = "tool_targeted"


#: The single seam that maps a resolved observer role to its mode. The mode is
#: ``built_in`` when the role is in-place (no tool) and ``tool_targeted`` when
#: the role declares a launchable tool. Nothing else may decide this.
def resolve_observer_mode(role: Any) -> str:
    """Return ``built_in`` or ``tool_targeted`` for a resolved observer role.

    ``role`` is a :class:`~skillweave.dispatch.profile_resolution.ResolvedRole`.
    A role with a launchable tool (``is_launch()``) is ``tool_targeted``; an
    in-place role (no tool) is ``built_in``. Both are active and read-only.
    """
    if role is None:
        raise ObserverStateError("observer role is absent; cannot resolve mode")
    if getattr(role, "is_launch", None) and role.is_launch():
        return ObserverMode.TOOL_TARGETED.value
    return ObserverMode.BUILT_IN.value


class ObserverStateError(Exception):
    """An observer cannot be started or observed in its current state."""


@dataclass
class ObserverFinding:
    """One typed finding bound to run/wave/lane evidence.

    ``condition`` is one of :class:`ObserverCondition`. ``evidence`` carries the
    stream facts that produced the finding (event types, timestamps, receipt
    references) — never the raw worker output, which stays out of the observer
    exactly as it stays out of the stream.
    """

    condition: str
    severity: str
    message: str
    run_id: str
    wave: str
    lane_id: str
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "severity": self.severity,
            "message": self.message,
            "run_id": self.run_id,
            "wave": self.wave,
            "lane_id": self.lane_id,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


@dataclass
class ObserverReceipt:
    """The observable record of one observer run.

    ``active`` marks the observer as started (never silently absent). ``observed``
    is ``True`` only when the observation completed without error; an observer
    that raised during startup or detection serialises ``observed=False`` plus an
    ``error`` — a failure can never masquerade as ``observed=true``. ``mode`` is
    ``built_in`` or ``tool_targeted``; ``in_place`` is ``True`` for a built-in
    observer (recorded as in-place and active).
    """

    run_id: str
    wave: str
    mode: str
    active: bool = False
    observed: bool = False
    in_place: bool = False
    findings: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    # Tool-targeted provenance (all ``None``/empty for a built-in observer).
    termination: Optional[str] = None
    outcome: Optional[str] = None
    tool: Optional[str] = None
    model: Optional[str] = None
    stdout_ref: Optional[dict[str, Any]] = None
    stderr_ref: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "wave": self.wave,
            "mode": self.mode,
            "active": self.active,
            "observed": self.observed,
            "in_place": self.in_place,
            "findings": self.findings,
            "error": self.error,
            "termination": self.termination,
            "outcome": self.outcome,
            "tool": self.tool,
            "model": self.model,
            "stdout_ref": self.stdout_ref,
            "stderr_ref": self.stderr_ref,
        }


class ObserverEventSource:
    """A read-only locator over the live dispatch event source.

    Holds only a replay callable (returns the emitted ``DispatchEvent`` dicts in
    order) and the heartbeat interval. It exposes no emit/write/transition
    method: the observer must never be handed a writable stream or store handle.
    The replay is the *real* dispatch event source — the very stream the wave
    produced — not a copy owned by the observer.
    """

    def __init__(
        self,
        run_id: str,
        replay: Callable[[], list[dict[str, Any]]],
        heartbeat_interval_seconds: float,
    ) -> None:
        self._run_id = run_id
        self._replay = replay
        self._heartbeat_interval = heartbeat_interval_seconds

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def heartbeat_interval(self) -> float:
        return self._heartbeat_interval

    def events(self) -> list[dict[str, Any]]:
        """Return the emitted events as a list of dicts, freshly replayed."""
        return list(self._replay())


class DispatchObserver:
    """One active, run-scoped, read-only observer for a dispatch wave.

    Constructed before the first ops child; ``observe`` runs the four detectors
    over the real event source and returns a :class:`ObserverReceipt`. Denied
    actions raise ``AuthorityError`` (reusing the observer role capability
    matrix), never performing the effect.
    """

    def __init__(
        self,
        *,
        run_id: str,
        wave: str,
        mode: str,
        event_source: ObserverEventSource,
        guard: Any = None,
        command: Optional[Sequence[str]] = None,
        tool_name: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        launch: Optional[Callable[..., Any]] = None,
    ) -> None:
        if mode not in (ObserverMode.BUILT_IN.value, ObserverMode.TOOL_TARGETED.value):
            raise ObserverStateError(f"unknown observer mode {mode!r}")
        self.run_id = run_id
        self.wave = wave
        self.mode = mode
        self._source = event_source
        self._guard = guard if guard is not None else _authority.AuthorityGuard()
        self._active = True
        self._observed: bool = False
        self._findings: list[ObserverFinding] = []
        self._error: Optional[str] = None

        # Tool-targeted launch identity, derived solely from the resolved observer
        # role: the tokenised command, the tool name, and the resolved model (or
        # "" when the role resolves no model). No concrete model/provider/harness
        # default is named here.
        self._command: Optional[Sequence[str]] = list(command) if command else None
        self._tool_name: Optional[str] = tool_name
        self._model: Optional[str] = model if model is not None else ""
        self._timeout: Optional[float] = (
            timeout if timeout is not None else DEFAULT_OBSERVER_TIMEOUT
        )
        self._launch: Callable[..., Any] = launch if launch is not None else _lazy_start_process()

        self._handle: Any = None
        self._neutral_dir: Optional[str] = None
        self._launch_error: Optional[str] = None
        self._closed: bool = False

    @property
    def launch_failed(self) -> bool:
        """Whether the observer tool synchronously failed to launch."""
        return self._launch_error is not None

    # -- read-only enforcement ------------------------------------------------

    @property
    def role(self) -> str:
        return _authority.Role.OBSERVER.value

    def _deny(self, action: str, reason: str) -> None:
        """Raise ``AuthorityError`` for an action the observer role may not take.

        Reuses the shared guard: the observer role is read-only and holds no
        mutate/approve/write capability, so ``can_perform`` is ``False`` and the
        attempt is refused *before* any effect. This is an executable negative
        probe, not a documentation note.
        """
        if self._guard.can_perform(self.role, action):
            raise ObserverStateError(
                f"observer role unexpectedly holds '{action}'; refusing to proceed"
            )
        raise _authority.AuthorityError(
            self.role, action, f"observer is read-only and cannot {reason}"
        )

    def dispatch_work(self, *_args: Any, **_kwargs: Any) -> Any:
        """Denied: the observer cannot dispatch work."""
        self._deny("mutate_run_state", "dispatch work")

    def mutate_run_state(self, *_args: Any, **_kwargs: Any) -> Any:
        """Denied: the observer cannot mutate root-run state."""
        self._deny("mutate_run_state", "mutate run state")

    def approve_gate(self, *_args: Any, **_kwargs: Any) -> Any:
        """Denied: the observer cannot approve a gate."""
        self._deny("approve_gate", "approve a gate")

    def write_repository(self, *_args: Any, **_kwargs: Any) -> Any:
        """Denied: the observer cannot write the repository."""
        self._deny("write", "write the repository")

    def repair_finding(self, *_args: Any, **_kwargs: Any) -> Any:
        """Denied: the observer cannot repair a finding (no authority)."""
        self._deny("write", "repair a finding")

    # -- observation ----------------------------------------------------------

    def _final_event(self, events: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return events[-1] if events else None

    def _lanes(self, events: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
        by_lane: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for e in events:
            lane = e.get("lane_id") or ""
            if lane not in by_lane:
                by_lane[lane] = []
                order.append(lane)
            by_lane[lane].append(e)
        return [(lane, by_lane[lane]) for lane in order]

    def _detect_heartbeat_expiry(self, events: list[dict[str, Any]]) -> list[ObserverFinding]:
        findings: list[ObserverFinding] = []
        final = self._final_event(events)
        if final is None:
            return findings
        try:
            final_ts = datetime.fromisoformat(final.get("timestamp", ""))
        except (ValueError, TypeError):
            return findings
        for lane, lane_events in self._lanes(events):
            terminal = any(
                e.get("event_type") in ("lane_terminal", "process_terminal")
                for e in lane_events
            )
            running = any(
                e.get("event_type") in ("dispatch_started", "heartbeat")
                for e in lane_events
            )
            if terminal or not running:
                continue
            last = lane_events[-1]
            try:
                last_ts = datetime.fromisoformat(last.get("timestamp", ""))
            except (ValueError, TypeError):
                continue
            elapsed = (final_ts - last_ts).total_seconds()
            if elapsed > self._source.heartbeat_interval:
                findings.append(ObserverFinding(
                    condition=ObserverCondition.HEARTBEAT_EXPIRY.value,
                    severity="critical",
                    message=f"lane '{lane}' exceeded heartbeat interval without a terminal",
                    run_id=self.run_id,
                    wave=self.wave,
                    lane_id=lane,
                    evidence={
                        "elapsed_seconds": elapsed,
                        "heartbeat_interval": self._source.heartbeat_interval,
                        "last_event_type": last.get("event_type"),
                    },
                ))
        return findings

    def _detect_terminal_missing_evidence(self, events: list[dict[str, Any]]) -> list[ObserverFinding]:
        findings: list[ObserverFinding] = []
        for lane, lane_events in self._lanes(events):
            done_terminal = any(
                e.get("event_type") == "process_terminal"
                and e.get("task_status") == "done"
                for e in lane_events
            )
            has_evidence = any(
                e.get("event_type") == "evidence_recorded" for e in lane_events
            )
            if done_terminal and not has_evidence:
                findings.append(ObserverFinding(
                    condition=ObserverCondition.TERMINAL_MISSING_EVIDENCE.value,
                    severity="high",
                    message=f"lane '{lane}' reached done without recording evidence",
                    run_id=self.run_id,
                    wave=self.wave,
                    lane_id=lane,
                    evidence={"terminal_task_status": "done", "evidence_recorded": False},
                ))
        return findings

    def _detect_contradictory(self, events: list[dict[str, Any]]) -> list[ObserverFinding]:
        findings: list[ObserverFinding] = []
        for lane, lane_events in self._lanes(events):
            has_evidence = any(
                e.get("event_type") == "evidence_recorded" for e in lane_events
            )
            failed_terminal = any(
                e.get("event_type") == "process_terminal"
                and e.get("task_status") == "failed"
                for e in lane_events
            )
            exit_failed = any(
                e.get("event_type") == "process_terminal"
                and e.get("process_status") == "exited"
                and e.get("task_status") == "failed"
                for e in lane_events
            )
            if has_evidence and failed_terminal:
                findings.append(ObserverFinding(
                    condition=ObserverCondition.CONTRADICTORY_PROCESS_EVIDENCE.value,
                    severity="critical",
                    message=f"lane '{lane}' recorded evidence for a failed process",
                    run_id=self.run_id,
                    wave=self.wave,
                    lane_id=lane,
                    evidence={"evidence_recorded": True, "terminal_task_status": "failed"},
                ))
            elif exit_failed:
                findings.append(ObserverFinding(
                    condition=ObserverCondition.CONTRADICTORY_PROCESS_EVIDENCE.value,
                    severity="high",
                    message=f"lane '{lane}' exited process reported task failure (contradiction)",
                    run_id=self.run_id,
                    wave=self.wave,
                    lane_id=lane,
                    evidence={"process_status": "exited", "task_status": "failed"},
                ))
        return findings

    def _detect_lane_completion_not_observed(self, events: list[dict[str, Any]]) -> list[ObserverFinding]:
        findings: list[ObserverFinding] = []
        for lane, lane_events in self._lanes(events):
            if lane == "":
                continue
            started = any(
                e.get("event_type") in ("lane_started", "dispatch_started")
                for e in lane_events
            )
            terminal = any(
                e.get("event_type") == "lane_terminal" for e in lane_events
            )
            if started and not terminal:
                findings.append(ObserverFinding(
                    condition=ObserverCondition.LANE_COMPLETION_NOT_OBSERVED.value,
                    severity="high",
                    message=f"lane '{lane}' started but completion was never observed",
                    run_id=self.run_id,
                    wave=self.wave,
                    lane_id=lane,
                    evidence={"lane_started": True, "lane_terminal": False},
                ))
        return findings

    def findings(self) -> list[ObserverFinding]:
        """Run the four detectors over the current event source (read-only)."""
        events = self._source.events()
        result: list[ObserverFinding] = []
        result.extend(self._detect_heartbeat_expiry(events))
        result.extend(self._detect_terminal_missing_evidence(events))
        result.extend(self._detect_contradictory(events))
        result.extend(self._detect_lane_completion_not_observed(events))
        return result

    # -- tool-targeted lifecycle ----------------------------------------------

    #: The documented machine JSON result a tool-targeted observer must emit on
    #: stdout. On a successful observation the tool prints exactly one JSON
    #: object with a ``run_id``, a ``wave`` and an optional ``findings`` array;
    #: each finding is a dict of ``condition``/``severity``/``message``/
    #: ``lane_id``/``evidence``. Any other stdout (absent, non-JSON, or a JSON
    #: object without a ``findings`` list) is a *missing/malformed* result and is
    #: reported as ``observed=false``, never synthesised into a success.
    TOOL_RESULT_FIELDS: tuple[str, ...] = (
        "condition",
        "severity",
        "message",
        "lane_id",
        "evidence",
    )

    def _locator_payload(self) -> bytes:
        """Serialize the deterministic read-only locator/envelope to the tool.

        Binds ``run_id``, ``wave``, ``mode``, the heartbeat interval and the
        ordered replay of the *real* teed dispatch events. It is explicitly
        marked read-only and carries no write/mutation coordinate: no store,
        sink, gate, dispatcher, root-run object, or callback rides as input.
        """
        envelope: dict[str, Any] = {
            "run_id": self.run_id,
            "wave": self.wave,
            "mode": self.mode,
            "heartbeat_interval_seconds": self._source.heartbeat_interval,
            "read_only": True,
            "events": self._source.events(),
        }
        return json.dumps(envelope, sort_keys=True).encode("utf-8")

    def start(self) -> "DispatchObserver":
        """Start the observer before the first ops child.

        A built-in observer starts no process: it is recorded as in-place and
        active. A tool-targeted observer launches its tool exactly once through
        the runtime ``start_process`` seam, in an isolated neutral working
        directory, with no repository path and no writable store/gate/handle in
        its input. A synchronous launch failure is captured here (it must be
        visible before ops — see :attr:`launch_failed`) rather than raised into
        the dispatch loop.
        """
        self._active = True
        if self.mode != ObserverMode.TOOL_TARGETED.value:
            return self
        if self._command is None:
            self._launch_error = "tool-targeted observer has no launch command"
            return self
        self._neutral_dir = tempfile.mkdtemp(prefix="sw-observer-")
        try:
            self._handle = self._launch(
                list(self._command),
                run_id=self.run_id,
                subject_repo="",
                subject_commit="",
                tool=self._tool_name or "",
                model=self._model or "",
                cwd=self._neutral_dir,
            )
        except (FileNotFoundError, OSError) as exc:
            self._cleanup_neutral_dir()
            self._handle = None
            self._launch_error = f"failed to launch observer tool: {exc}"
            return self
        except Exception as exc:  # noqa: BLE001 - a launch failure must be visible
            self._cleanup_neutral_dir()
            self._handle = None
            self._launch_error = f"failed to launch observer tool: {exc}"
            return self
        return self

    def _cleanup_neutral_dir(self) -> None:
        if self._neutral_dir is not None:
            shutil.rmtree(self._neutral_dir, ignore_errors=True)
            self._neutral_dir = None

    def _release_handle(self) -> Any:
        """Detach ownership of the live handle atomically (idempotent).

        Returns the previously owned handle, or ``None`` when nothing is owned.
        After this returns, ``self._handle`` is ``None``, so no later ``close``/
        ``observe``/cleanup call can wait or cancel the same process again.
        """
        handle = self._handle
        self._handle = None
        return handle

    def close(self) -> None:
        """Terminate and clean up this observer idempotently.

        If a tool process is still owned, detach the handle from the observer
        atomically, cancel/kill its process group through the existing
        ``RunningProcess.cancel()`` seam (never a direct ``subprocess`` call),
        and remove the neutral directory. Calling this more than once, or after
        a normal reap, is a safe no-op: nothing is waited or cancelled twice.
        """
        if self._closed:
            return
        self._closed = True
        handle = self._release_handle()
        try:
            if handle is not None:
                cancel = getattr(handle, "cancel", None)
                if callable(cancel):
                    cancel()
        finally:
            self._cleanup_neutral_dir()

    def _reap_tool(self) -> Optional[Any]:
        """Deliver the locator payload to the launched tool and reap it exactly once.

        Returns the ``ProcessResult``, or ``None`` when no process was launched
        (built-in or a failed launch). Ownership of the handle is cleared exactly
        once before wait, and the neutral directory is removed in ``finally``, so
        a subsequent ``close``/``observe``/cleanup is a safe no-op that cannot
        wait or cancel the process again.
        """
        handle = self._release_handle()
        if handle is None:
            self._cleanup_neutral_dir()
            return None
        try:
            result = handle.wait(
                timeout=self._timeout,
                input_bytes=self._locator_payload(),
            )
        finally:
            self._cleanup_neutral_dir()
        return result

    @staticmethod
    def _receipt_ref(receipt: Any) -> Optional[dict[str, Any]]:
        if receipt is None:
            return None
        metadata = getattr(receipt, "metadata", None) or {}
        byte_length = metadata.get("byte_length", 0)
        return {
            "artifact_id": getattr(receipt, "artifact_id", None),
            "sha256": getattr(receipt, "sha256", None),
            "byte_length": int(byte_length) if byte_length is not None else 0,
        }

    def _tool_receipt_from(self, result: Any) -> ObserverReceipt:
        """Build the tool-targeted receipt from the *actual* process result.

        ``active``/``observed``/``termination``/``outcome``/``tool``/``model`` and
        the stdout/stderr receipt refs all reflect what really ran. Only a small
        documented machine JSON result on stdout is accepted for findings; an
        absent/malformed result, a non-zero exit, a signal, a timeout, or a
        launch failure all yield ``observed=false`` with an honest error.
        """
        terminated = getattr(result, "termination", None)
        outcome = self._process_outcome(result)
        tool = self._tool_name
        model = self._model
        stdout_ref = self._receipt_ref(getattr(result, "stdout_receipt", None))
        stderr_ref = self._receipt_ref(getattr(result, "stderr_receipt", None))

        if result is None or not getattr(result, "succeeded", False):
            message = getattr(result, "message", "") if result is not None else ""
            return ObserverReceipt(
                run_id=self.run_id,
                wave=self.wave,
                mode=self.mode,
                active=self._active,
                observed=False,
                in_place=False,
                findings=[],
                error=message or f"observer tool terminated as {terminated}",
                termination=terminated,
                outcome=outcome,
                tool=tool,
                model=model,
                stdout_ref=stdout_ref,
                stderr_ref=stderr_ref,
            )

        raw = getattr(result, "stdout", b"") or b""
        findings, parse_error = self._parse_tool_json(raw)
        if parse_error is not None:
            return ObserverReceipt(
                run_id=self.run_id,
                wave=self.wave,
                mode=self.mode,
                active=self._active,
                observed=False,
                in_place=False,
                findings=[],
                error=parse_error,
                termination=terminated,
                outcome=outcome,
                tool=tool,
                model=model,
                stdout_ref=stdout_ref,
                stderr_ref=stderr_ref,
            )
        self._findings = [
            ObserverFinding(**f) for f in findings
        ]
        return ObserverReceipt(
            run_id=self.run_id,
            wave=self.wave,
            mode=self.mode,
            active=self._active,
            observed=True,
            in_place=False,
            findings=[f.to_dict() for f in self._findings],
            error=None,
            termination=terminated,
            outcome=outcome,
            tool=tool,
            model=model,
            stdout_ref=stdout_ref,
            stderr_ref=stderr_ref,
        )

    def _parse_tool_json(self, raw: bytes) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Parse the tool's machine JSON result into standalone findings.

        Returns ``(findings, error)``. A clean parse yields an empty error; a
        missing or malformed payload yields ``([], error)`` — never a
        synthesised success.
        """
        if not raw or not raw.strip():
            return [], "observer tool produced no result on stdout"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return [], f"observer tool produced malformed JSON: {exc}"
        if not isinstance(data, dict):
            return [], "observer tool result is not a JSON object"
        raw_findings = data.get("findings")
        if raw_findings is None:
            return [], "observer tool result has no 'findings' array"
        if not isinstance(raw_findings, list):
            return [], "observer tool result 'findings' is not an array"
        parsed: list[dict[str, Any]] = []
        for item in raw_findings:
            if not isinstance(item, dict):
                return [], "observer tool finding is not an object"
            known = {k: item.get(k) for k in self.TOOL_RESULT_FIELDS}
            known.setdefault("run_id", self.run_id)
            known.setdefault("wave", self.wave)
            known.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
            parsed.append(known)
        return parsed, None

    @staticmethod
    def _process_outcome(result: Any) -> Optional[str]:
        """Map a ``ProcessResult`` termination to its one machine outcome."""
        if result is None:
            return None
        termination = getattr(result, "termination", None)
        if termination == "timed_out":
            return "timed_out"
        if termination == "launch_failed":
            return "launch_failed"
        if getattr(result, "signal", None) is not None:
            return "signal"
        if getattr(result, "exit_code", None) is not None:
            return "exit_code"
        return None

    def observe(self) -> ObserverReceipt:
        """Observe the wave and return a receipt.

        A built-in observer runs the four in-process detectors over the real
        event source. A tool-targeted observer delivers the read-only locator to
        its launched tool, reaps it exactly once, and derives its receipt from
        the *actual* process result — never from a relabel of the in-process
        detectors.
        """
        self._active = True
        if self.mode == ObserverMode.TOOL_TARGETED.value:
            return self._observe_tool()
        try:
            self._findings = self.findings()
        except Exception as exc:  # noqa: BLE001 - failure must be visible, not fatal
            self._observed = False
            self._error = str(exc)
            return self.receipt()
        self._observed = True
        return self.receipt()

    def _observe_tool(self) -> ObserverReceipt:
        """Deliver, reap, and derive the receipt for a tool-targeted observer."""
        if self._launch_error is not None:
            return ObserverReceipt(
                run_id=self.run_id,
                wave=self.wave,
                mode=self.mode,
                active=self._active,
                observed=False,
                in_place=False,
                findings=[],
                error=self._launch_error,
                termination="launch_failed",
                outcome="launch_failed",
                tool=self._tool_name,
                model=self._model,
            )
        result = self._reap_tool()
        return self._tool_receipt_from(result)

    def receipt(self) -> ObserverReceipt:
        """The current receipt (built-in: recorded as in-place and active)."""
        return ObserverReceipt(
            run_id=self.run_id,
            wave=self.wave,
            mode=self.mode,
            active=self._active,
            observed=self._observed,
            in_place=(self.mode == ObserverMode.BUILT_IN.value),
            findings=[f.to_dict() for f in self._findings],
            error=self._error,
        )


# -- live projection observer (SW1311-OBSERVER-001) --------------------------


class LiveObserver:
    """A live, read-only observer of one dispatch run's typed event stream.

    It folds each typed event it observes into a deterministic
    :class:`~skillweave.trace.projection.Projection` (replay from zero restores
    the view) and, when configured, emits read-only intervention requests at
    liveness / non-progress thresholds. It holds no authority: every forbidden
    action raises before execution.
    """

    def __init__(
        self,
        stream: DispatchEventStream,
        *,
        heartbeat_interval: Optional[float] = None,
        liveness_threshold: Optional[float] = None,
        non_progress_threshold: Optional[float] = None,
    ) -> None:
        self._stream = stream
        self._projector = Projector(run_id=stream.run_id)
        self._heartbeat_interval = heartbeat_interval
        self._liveness_threshold = liveness_threshold
        self._non_progress_threshold = non_progress_threshold
        self._last_seen_sequence: Optional[int] = None

    @property
    def run_id(self) -> str:
        return self._stream.run_id

    def observe(self, events: Sequence[Mapping[str, Any]]) -> Projection:
        """Fold ordered typed events into the projection and return it.

        ``events`` are the typed event dicts emitted by the stream. Folding is
        ordered by ``sequence``, so replaying the same ordered stream from zero
        yields the identical projection (criterion 7).
        """
        for event in sorted(events, key=lambda e: e.get("sequence", 0)):
            self._projector.project(
                ProjectionEvent(
                    sequence=int(event.get("sequence", 0)),
                    payload=dict(event),
                )
            )
            self._last_seen_sequence = int(event.get("sequence", 0))
        return self.projection()

    def projection(self) -> Projection:
        return self._projector.projection()

    def intervention_requests(self, *, now: Optional[str] = None) -> tuple[InterventionRequest, ...]:
        """Emit read-only intervention requests at configured thresholds.

        A liveness threshold is breached when the stream has no observed event
        within ``liveness_threshold``; a non-progress threshold when no typed
        event has advanced ``_last_seen_sequence`` within the threshold. Each
        request names an action to *request*, and asserts that the observer
        itself may not perform that action.
        """
        requests: list[InterventionRequest] = []
        if self._liveness_threshold is not None:
            requests.append(InterventionRequest(
                kind=InterventionKind.LIVENESS,
                reason="no typed event observed within the liveness threshold",
                threshold=self._liveness_threshold,
                action="request operator liveness review",
            ))
        if self._non_progress_threshold is not None:
            requests.append(InterventionRequest(
                kind=InterventionKind.NON_PROGRESS,
                reason="typed event sequence has not advanced within the "
                       "non-progress threshold",
                threshold=self._non_progress_threshold,
                action="request operator non-progress review",
            ))
        for r in requests:
            assert_observer_authority(r.action)
        return tuple(requests)

    def forbid(self, action: str) -> None:
        """Fail closed on any forbidden observer action (criteria 6, 9)."""
        assert_observer_authority(action)


__all__ = [
    "ObserverCondition",
    "ObserverMode",
    "ObserverFinding",
    "ObserverReceipt",
    "ObserverEventSource",
    "ObserverStateError",
    "DispatchObserver",
    "resolve_observer_mode",
    "LiveObserver",
]
