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
            "pinned_at": self.pinned_at,
        }

    def validate_product(self, expected_product: str) -> bool:
        return self.product == expected_product

    def validate_repo(self, actual_remote: str) -> bool:
        return self.remote_repo == actual_remote

    def validate_write_scope(self, target_path: str) -> bool:
        for scope in self.allowed_write_scopes:
            if target_path.startswith(scope.replace("**", "")):
                return True
        return False

    def is_read_only_operation(self, action: str) -> bool:
        read_only_prefixes = ("get_", "list_", "read_", "search_", "analyze_", "diagnose_", "check_")
        return any(action.startswith(p) for p in read_only_prefixes)


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
) -> PreflightResult:
    mismatches = []
    warnings = []

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

    if mismatches:
        return PreflightResult(passed=False, mismatches=mismatches, warnings=warnings)

    return PreflightResult(passed=True, warnings=warnings)
