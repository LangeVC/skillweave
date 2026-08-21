import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


class PreflightError(Exception):
    def __init__(self, reason: str, mismatches: list[dict[str, Any]], code: str = "MISMATCH"):
        self.reason = reason
        self.mismatches = mismatches
        self.code = code
        super().__init__(f"Preflight [{code}]: {reason}")


@dataclass
class SessionEnvelope:
    product: str
    remote_repo: str
    worktree: str
    branch: str
    role: str
    prd_digest: str
    chain_digest: str
    allowed_write_scopes: list[str]
    state_vocabulary: list[str]
    forbidden_transitions: list[str]
    pin_sha: str = ""
    pinned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return {
            "product": self.product,
            "remote_repo": self.remote_repo,
            "worktree": self.worktree,
            "branch": self.branch,
            "role": self.role,
            "prd_digest": self.prd_digest,
            "chain_digest": self.chain_digest,
            "allowed_write_scopes": self.allowed_write_scopes,
            "state_vocabulary": self.state_vocabulary,
            "forbidden_transitions": self.forbidden_transitions,
            "pin_sha": self.pin_sha,
            "pinned_at": self.pinned_at,
        }

    def validate_product(self, expected_product: str) -> bool:
        return self.product == expected_product

    def validate_repo(self, actual_remote: str) -> bool:
        return self.remote_repo == actual_remote

    def validate_write_scope(self, target_path: str) -> bool:
        if not self.allowed_write_scopes:
            return False
        resolved_target = os.path.abspath(target_path)
        for scope in self.allowed_write_scopes:
            resolved_scope = os.path.abspath(scope.replace("**", "").rstrip("/"))
            if resolved_scope == os.sep:
                return True
            if resolved_target.startswith(resolved_scope + os.sep) or resolved_target == resolved_scope:
                return True
        return False

    def is_read_only_operation(self, action: str) -> bool:
        read_only_prefixes = ("get_", "list_", "read_", "search_", "diagnose_", "check_")
        # Mutating verbs always win over any read-looking prefix. In particular
        # ``analyze_and_delete`` (or any ``*_delete``/``*_write``/``*_mutate``)
        # must NEVER be released as read-only merely because it also matches a
        # benign prefix. The name does not decide authorization.
        mutating_markers = ("delete", "write", "mutate", "commit", "push", "merge", "release", "purge", "truncate")
        lowered = action.lower()
        if any(m in lowered for m in mutating_markers):
            return False
        return any(action.startswith(p) for p in read_only_prefixes)

    def mutation_requires_capability(self, action: str) -> bool:
        """Return True when ``action`` is a destructive/mutating operation that
        must fail closed unless an explicit capability grants it.

        ``analyze_and_delete`` is the canonical case: the ``analyze_`` prefix
        looks read-only, but the ``_delete`` suffix is destructive. It is never
        released by name; only an explicit ``allowed_actions`` grant passes.
        """
        lowered = action.lower()
        return "_delete" in lowered or lowered.endswith("delete") or lowered in ("purge", "truncate")



@dataclass
class PreflightResult:
    passed: bool
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return {
            "passed": self.passed,
            "mismatches": self.mismatches,
            "warnings": self.warnings,
            "checked_at": self.checked_at,
        }


def run_preflight(
    envelope: SessionEnvelope,
    actual_repo: str,
    actual_branch: str,
    actual_product: Optional[str] = None,
    actual_worktree: Optional[str] = None,
    actual_sha: Optional[str] = None,
    actual_role: Optional[str] = None,
    actual_scope: Optional[str] = None,
) -> PreflightResult:
    mismatches = []
    warnings = []

    required_string_fields = (
        "product",
        "remote_repo",
        "worktree",
        "branch",
        "role",
        "prd_digest",
        "chain_digest",
    )
    required_list_fields = ("allowed_write_scopes", "state_vocabulary", "forbidden_transitions")

    for field_name in required_string_fields:
        if not getattr(envelope, field_name, None):
            mismatches.append({
                "field": field_name,
                "expected": "non-empty",
                "actual": getattr(envelope, field_name, None),
            })

    for field_name in required_list_fields:
        if getattr(envelope, field_name, None) is None:
            mismatches.append({
                "field": field_name,
                "expected": "list",
                "actual": None,
            })

    if actual_product and not envelope.validate_product(actual_product):
        mismatches.append({
            "field": "product",
            "expected": envelope.product,
            "actual": actual_product,
        })

    if not envelope.validate_repo(actual_repo):
        mismatches.append({
            "field": "remote_repo",
            "expected": envelope.remote_repo,
            "actual": actual_repo,
        })

    if envelope.branch and actual_branch and envelope.branch != actual_branch:
        mismatches.append({
            "field": "branch",
            "expected": envelope.branch,
            "actual": actual_branch,
        })

    # Worktree / SHA / role are compared when the caller supplies the actual
    # value; a mismatch is release-blocking, exactly like repo and branch.
    if actual_worktree is not None and envelope.worktree and actual_worktree != envelope.worktree:
        mismatches.append({
            "field": "worktree",
            "expected": envelope.worktree,
            "actual": actual_worktree,
        })

    if actual_sha is not None and envelope.pin_sha and actual_sha != envelope.pin_sha:
        mismatches.append({
            "field": "sha",
            "expected": envelope.pin_sha,
            "actual": actual_sha,
        })

    if actual_role is not None and envelope.role and actual_role != envelope.role:
        mismatches.append({
            "field": "role",
            "expected": envelope.role,
            "actual": actual_role,
        })

    if actual_scope is not None and not envelope.validate_write_scope(actual_scope):
        mismatches.append({
            "field": "scope",
            "expected": "within allowed_write_scopes",
            "actual": actual_scope,
        })

    if mismatches:
        return PreflightResult(passed=False, mismatches=mismatches, warnings=warnings)

    return PreflightResult(passed=True, warnings=warnings)


InterceptedCallable = Any


class PreflightInterceptor:
    """
    Fail-closed interceptor. Wraps a mutating callable with a preflight
    gate. If preflight fails, the callable is never invoked and
    PreflightError is raised.
    """

    def __init__(self, envelope: SessionEnvelope, repo: str, branch: str, product: Optional[str] = None):
        self._envelope = envelope
        self._repo = repo
        self._branch = branch
        self._product = product
        self._passed = False
        self._result: Optional[PreflightResult] = None

    @property
    def passed(self) -> bool:
        if self._result is None:
            self._result = run_preflight(
                self._envelope,
                actual_repo=self._repo,
                actual_branch=self._branch,
                actual_product=self._product,
            )
            self._passed = self._result.passed
        return self._passed

    @property
    def result(self) -> PreflightResult:
        if self._result is None:
            _ = self.passed
        return self._result

    def guard(self, callable_fn: InterceptedCallable, *args: Any, **kwargs: Any) -> Any:
        if not self.passed:
            raise PreflightError(
                reason=f"Preflight failed: {len(self.result.mismatches)} mismatches",
                mismatches=self.result.mismatches,
                code="INTERCEPTOR_BLOCKED",
            )
        return callable_fn(*args, **kwargs)
