"""Read-only assessment service (SW-157-ASSESS-002).

This service turns a declarative :class:`AssessmentRequest` into a sealed,
tamper-evident assessment receipt (``skillweave.assessment_contracts``). It owns
the *mechanics* the contract deliberately leaves out: reading the subject's
sources, deciding whether the assessment could actually be completed, and
producing either an ``available`` receipt whose evidence a third party can
independently re-resolve, or an ``unavailable`` one whose explicit ``limits``
say exactly what could not be established.

Read-only authority
-------------------
An assessment never mutates the tree it assesses. That is enforced three ways:

* the service refuses to be constructed with any authority that is not
  read-only (:class:`ReadOnlyViolation`);
* every file it touches is opened ``rb`` and every action goes through
  :meth:`ReadOnlyAuthority.assert_readable` -- there is no write path to add;
* the module imports only the standard library and
  :mod:`skillweave.assessment_contracts`, so it cannot drag in a
  write-on-import subsystem (``skillweave.persistence``, ``observation.*``,
  ``runtime.store``). ``tests/integration/test_assessment_service.py`` pins this
  import closure.

Available vs unavailable
------------------------
``available`` is a claim that the receipt's evidence is complete and
re-resolvable: the subject is a commit that exists, at least one source was
named, and every source lies inside the root and hashes exactly as recorded. Any
shortfall -- a subject that is not a commit in this repository, a source that is
missing, escapes the root or whose digest does not match, no sources at all, or
a probe that could not run -- produces ``unavailable`` with a limit naming that
shortfall, and an unavailable receipt attests nothing it did not establish (no
sources, no commands).

A *malformed* request is different from a shortfall: the contract requires every
receipt -- available or unavailable -- to carry a canonical subject SHA, so a
subject that is not a canonical lowercase full 40-hex SHA cannot be represented
at all. The service therefore refuses such a request with
:class:`~skillweave.assessment_contracts.AssessmentError` rather than sealing an
``unavailable`` receipt, so no unrepresentable claim is ever recorded.

Determinism
-----------
Identical inputs produce a byte-identical sealed receipt: ``produced_at`` is
supplied, never read from the clock; sources are root-relative and stored as
posix; the probe command carries no absolute path; the contract's canonical JSON
sorts keys. :func:`verify` re-resolves a receipt's sources from the same inputs.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from skillweave.assessment_contracts import (
    RESULT_AVAILABLE,
    RESULT_UNAVAILABLE,
    SCHEMA_VERSION,
    AssessmentError,
    AssessmentReceipt,
    canonicalize,
    seal,
)

#: Canonical lowercase full 40-hex SHA (the subject identity).
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

#: Canonical lowercase sha256 (the source content address).
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

#: Source resolution statuses.
RESOLVED = "resolved"
MISSING = "missing"
ESCAPED = "escaped"
MISMATCH = "mismatch"


class ReadOnlyViolation(AssessmentError):
    """A mutating operation was attempted against the read-only assessor."""


class ReadOnlyAuthority:
    """A capability holder that can only ever refuse writes.

    The assessor carries exactly this authority: every mutating action is
    refused by construction, so a write path cannot be added to the service
    without also changing this contract.
    """

    #: The property the service checks at construction. Never False.
    read_only = True

    def assert_writable(self, action: str) -> None:
        """Refuse ``action``; the assessor never mutates its subject."""
        raise ReadOnlyViolation(
            f"read-only authority refuses to {action}; "
            "an assessment never mutates the tree it assesses"
        )

    def assert_readable(self, action: str) -> None:
        """Permit ``action`` -- the only thing this authority can do."""
        return None


# ── Request shape ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceSpec:
    """One source to inspect, as a path relative to the assessment root.

    ``sha256`` is optional: when supplied it is the content address the caller
    expects, and a mismatch makes the assessment unavailable rather than
    silently recording an unexpected digest.
    """

    path: str
    sha256: Optional[str] = None


@dataclass(frozen=True)
class CommandSpec:
    """One read-only command and the exit code it returned."""

    command: str
    exit: int


@dataclass(frozen=True)
class Finding:
    """One assessment finding."""

    id: str
    severity: str
    summary: str


@dataclass(frozen=True)
class AssessmentRequest:
    """Everything an assessment needs, as plain immutable facts.

    There is no clock and no cwd here: ``produced_at`` is supplied and every
    source is root-relative, so the same request always seals to the same
    digest (Step B).
    """

    subject_sha: str
    assessor: str
    run_id: str
    produced_at: str
    sources: tuple[SourceSpec, ...] = ()
    findings: tuple[Finding, ...] = ()
    model: Optional[str] = None
    repo: Optional[str] = None
    ref: Optional[str] = None
    limits: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceResolution:
    """The result of re-resolving one source against a root, read-only."""

    path: str
    status: str
    expected_sha256: Optional[str]
    actual_sha256: Optional[str]
    note: str


# ── Read-only primitives ────────────────────────────────────────────────────


def hash_file(path: Any) -> str:
    """Return the canonical lowercase sha256 of ``path``'s content, read-only."""
    digest = hashlib.sha256()
    with open(os.fspath(path), "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _within_root(candidate: str, root_real: str) -> bool:
    """True when the fully-resolved ``candidate`` stays within ``root_real``."""
    candidate_real = os.path.realpath(candidate)
    try:
        common = os.path.commonpath([candidate_real, root_real])
    except ValueError:
        return False
    return common == root_real


def resolve_source(
    root: Any, path: str, expected_sha256: Optional[str] = None
) -> SourceResolution:
    """Re-resolve one declared source, read-only and confined to ``root``.

    Returns a :class:`SourceResolution` rather than raising: "cannot resolve" is
    an assessment outcome, not an exception. A path that escapes the root, is
    absent, or whose content does not match the declared address is refused
    fail-closed -- never lowered into a weaker claim.
    """
    root_real = os.path.realpath(os.fspath(root))
    candidate = os.path.join(root_real, path)
    if not _within_root(candidate, root_real):
        return SourceResolution(
            path=path,
            status=ESCAPED,
            expected_sha256=expected_sha256,
            actual_sha256=None,
            note="declared path escapes the assessment root",
        )
    if not os.path.isfile(candidate):
        return SourceResolution(
            path=path,
            status=MISSING,
            expected_sha256=expected_sha256,
            actual_sha256=None,
            note="declared source does not exist under the assessment root",
        )
    actual = hash_file(candidate)
    relative = Path(os.path.relpath(os.path.realpath(candidate), root_real)).as_posix()
    if expected_sha256 is not None and actual != expected_sha256:
        return SourceResolution(
            path=relative,
            status=MISMATCH,
            expected_sha256=expected_sha256,
            actual_sha256=actual,
            note="source content address differs from the declared sha256",
        )
    return SourceResolution(
        path=relative,
        status=RESOLVED,
        expected_sha256=expected_sha256,
        actual_sha256=actual,
        note="source resolved and content address verified",
    )


def tree_fingerprint(root: Any, *, skip: Sequence[str] = (".git",)) -> str:
    """Return a sha256 over every file under ``root`` (path + content digest).

    Read-only. Two fingerprints compare equal exactly when the tree is
    byte-identical, which is how the read-only negative case proves the assessor
    left the tree untouched.
    """
    root_path = Path(root)
    skip_set = set(skip)
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_set)
        for name in sorted(filenames):
            full = Path(dirpath) / name
            relative = full.relative_to(root_path).as_posix()
            lines.append(f"{relative}\0{hash_file(full)}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def read_only_git(cwd: Any, *args: str) -> Optional[subprocess.CompletedProcess]:
    """Run a read-only git command; ``None`` when git itself is unavailable.

    Mirrors the repository's read-only git convention: optional locks disabled,
    no terminal prompt, a fixed locale so output does not vary by environment.
    """
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError:
        return None


def _default_probe(root: Any, subject_sha: str) -> Optional[CommandSpec]:
    """Verify the subject is a commit, read-only. ``None`` when git is absent."""
    command = f"git rev-parse --verify --quiet {subject_sha}^{{commit}}"
    proc = read_only_git(root, "rev-parse", "--verify", "--quiet", f"{subject_sha}^{{commit}}")
    if proc is None:
        return None
    return CommandSpec(command=command, exit=proc.returncode)


#: A probe maps (root, subject_sha) to the read-only command it ran, or ``None``
#: when it could not run at all.
Probe = Callable[[Any, str], Optional[CommandSpec]]


# ── Service ─────────────────────────────────────────────────────────────────


class AssessmentService:
    """Produce sealed, read-only assessment receipts from requests.

    ``root`` is the tree the assessment is confined to. ``probe`` is injectable
    so a caller (or a test) can supply the read-only subject check without a
    real repository; the default verifies the subject with read-only git.
    """

    def __init__(
        self,
        root: Any,
        *,
        authority: Optional[ReadOnlyAuthority] = None,
        probe: Optional[Probe] = None,
    ) -> None:
        auth = ReadOnlyAuthority() if authority is None else authority
        if not getattr(auth, "read_only", False):
            raise ReadOnlyViolation(
                "AssessmentService requires a read-only authority; "
                f"got {auth!r}"
            )
        self._root = Path(root)
        self._authority = auth
        self._probe: Probe = _default_probe if probe is None else probe

    @property
    def root(self) -> Path:
        return self._root

    @property
    def authority(self) -> ReadOnlyAuthority:
        return self._authority

    def assess(self, request: AssessmentRequest) -> AssessmentReceipt:
        """Seal ``request`` into a receipt, available or unavailable.

        Never raises :class:`ReadOnlyViolation` in normal use -- the guard is
        exercised and released on the read path; a shortfall is reported as an
        unavailable result with explicit limits. A malformed subject is refused
        (:class:`AssessmentError`), because no receipt may carry a non-canonical
        SHA -- see the module docstring.
        """
        self._authority.assert_readable("assess")

        subject = request.subject_sha
        limits: list[str] = []

        if not isinstance(subject, str) or not _FULL_SHA.match(subject):
            raise AssessmentError(
                "subject is not a canonical lowercase full 40-hex SHA: "
                f"{subject!r}; an assessment receipt cannot represent it"
            )

        probe = self._probe(self._root, subject)
        if probe is None:
            limits.append(
                "the read-only subject probe could not run (git unavailable); "
                "the subject commit was not verified"
            )
            return self._seal_unavailable(request, limits)
        if probe.exit != 0:
            limits.append(
                f"subject {subject} is not a commit in this repository "
                f"({probe.command!r} exited {probe.exit})"
            )
            return self._seal_unavailable(request, limits)

        if not request.sources:
            limits.append("no sources were named, so there is no evidence to resolve")
            return self._seal_unavailable(request, limits)

        resolutions: list[SourceResolution] = []
        for spec in request.sources:
            self._authority.assert_readable(f"read source {spec.path!r}")
            resolution = resolve_source(self._root, spec.path, spec.sha256)
            if resolution.status != RESOLVED:
                limits.append(f"{spec.path}: {resolution.note}")
            resolutions.append(resolution)

        if limits:
            return self._seal_unavailable(request, limits)

        return self._seal_available(request, resolutions, probe)

    # ── Receipt construction ────────────────────────────────────────────────

    def _subject(self, request: AssessmentRequest) -> dict[str, Any]:
        subject: dict[str, Any] = {"full_sha": request.subject_sha}
        if request.repo is not None:
            subject["repo"] = request.repo
        if request.ref is not None:
            subject["ref"] = request.ref
        return subject

    def _provenance(self, request: AssessmentRequest) -> dict[str, Any]:
        provenance: dict[str, Any] = {
            "assessor": request.assessor,
            "run_id": request.run_id,
            "produced_at": request.produced_at,
        }
        if request.model is not None:
            provenance["model"] = request.model
        return provenance

    def _seal_available(
        self,
        request: AssessmentRequest,
        resolutions: Sequence[SourceResolution],
        probe: CommandSpec,
    ) -> AssessmentReceipt:
        core = {
            "schema_version": SCHEMA_VERSION,
            "result": {
                "status": RESULT_AVAILABLE,
                "summary": "read-only assessment completed and evidence resolved",
            },
            "subject": self._subject(request),
            "sources": [
                {"path": resolution.path, "sha256": resolution.actual_sha256}
                for resolution in resolutions
            ],
            "commands": [{"command": probe.command, "exit": probe.exit}],
            "findings": [
                {"id": f.id, "severity": f.severity, "summary": f.summary}
                for f in request.findings
            ],
            "limits": list(request.limits),
            "provenance": self._provenance(request),
        }
        return canonicalize(seal(core))

    def _seal_unavailable(
        self, request: AssessmentRequest, limits: Sequence[str]
    ) -> AssessmentReceipt:
        # An unavailable assessment attests nothing it did not establish: no
        # sources, no commands -- only the explicit limits naming the shortfall.
        core = {
            "schema_version": SCHEMA_VERSION,
            "result": {
                "status": RESULT_UNAVAILABLE,
                "summary": "read-only assessment could not be completed",
            },
            "subject": self._subject(request),
            "sources": [],
            "commands": [],
            "findings": [],
            "limits": list(limits),
            "provenance": self._provenance(request),
        }
        return canonicalize(seal(core))


# ── Independent re-verification ─────────────────────────────────────────────


def verify(
    root: Any, receipt: Mapping[str, Any]
) -> tuple[bool, list[SourceResolution]]:
    """Re-resolve a receipt's evidence; ``(ok, resolutions)``.

    Validates the receipt fail-closed (including its digest) and then re-hashes
    every recorded source under ``root``. ``ok`` is True only when the receipt
    is available and every source still resolves to the recorded digest -- the
    property that makes the evidence *resolvable* by a third party.
    """
    checked = canonicalize(receipt)
    payload = checked.payload
    resolutions = [
        resolve_source(root, entry["path"], entry["sha256"])
        for entry in payload["sources"]
    ]
    ok = (
        payload["result"]["status"] == RESULT_AVAILABLE
        and bool(resolutions)
        and all(resolution.status == RESOLVED for resolution in resolutions)
    )
    return ok, resolutions


__all__ = [
    "RESOLVED",
    "MISSING",
    "ESCAPED",
    "MISMATCH",
    "ReadOnlyViolation",
    "ReadOnlyAuthority",
    "SourceSpec",
    "CommandSpec",
    "Finding",
    "AssessmentRequest",
    "SourceResolution",
    "AssessmentService",
    "hash_file",
    "resolve_source",
    "tree_fingerprint",
    "read_only_git",
    "verify",
]
