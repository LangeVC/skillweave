from typing import Any


class WireframeError(Exception):
    def __init__(self, reason: str, code: str = "WIREFRAME", context: dict[str, Any] | None = None):
        self.reason = reason
        self.code = code
        self.context = context or {}
        super().__init__(f"[{code}] {reason}")


def assert_gate_discipline(
    self_approved: bool = False,
    merge_invoked: bool = False,
    release_invoked: bool = False,
) -> list[str]:
    violations = []
    if self_approved:
        violations.append("Self-approval attempted — forbidden by I00 authority policy")
    if merge_invoked:
        violations.append("Merge invoked — out of scope for Runtime Foundation")
    if release_invoked:
        violations.append("Release invoked — out of scope for Runtime Foundation")
    return violations


def assert_write_scope(
    target_paths: list[str],
    allowed_scopes: list[str],
) -> tuple[bool, list[str]]:
    violations = []
    for target in target_paths:
        allowed = False
        for scope in allowed_scopes:
            normalized_scope = scope.replace("**", "")
            if target.startswith(normalized_scope):
                allowed = True
                break
        if not allowed:
            violations.append(target)
    return len(violations) == 0, violations


def assert_non_polling(poll_count: int) -> bool:
    """Fail when ``poll_count`` indicates a polling loop, not a single check.

    ``poll_count`` is the number of identical repeated calls a consumer made to
    wait on a result. Zero or one is a single check (allowed); two or more is a
    polling loop and fails the guard. This replaces the former constant-PASS
    stub: the guard now inspects evidence instead of always returning True.
    """
    return poll_count <= 1


def assert_no_foreign_repos(remote_url: str, canonical_url: str) -> bool:
    return remote_url == canonical_url


def validate_summary(required_keys: list[str], actual: dict[str, Any]) -> list[str]:
    missing = [k for k in required_keys if k not in actual]
    return missing
