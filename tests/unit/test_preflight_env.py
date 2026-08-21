"""SW-PREFLIGHT-001: compare the real environment against the envelope;
technical dispatch-abort on any mismatch; no action released by name prefix.

Wrong repo, worktree, branch, SHA, digest, role, or scope must never start a
process, and ``analyze_and_delete`` (or any destructive verb wearing a benign
``analyze_`` prefix) must fail closed without an explicit capability.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.preflight import SessionEnvelope, run_preflight


def _envelope(**overrides):
    base = dict(
        product="SkillWeave",
        remote_repo="git@canonical",
        worktree="/w",
        branch="feature/x",
        role="ops",
        prd_digest="prd-d",
        chain_digest="chain-d",
        allowed_write_scopes=["src/**"],
        state_vocabulary=["idle"],
        forbidden_transitions=["merge"],
        pin_sha="abc123",
    )
    base.update(overrides)
    return SessionEnvelope(**base)


def _passing(**actual):
    defaults = dict(
        actual_repo="git@canonical",
        actual_branch="feature/x",
        actual_product="SkillWeave",
        actual_worktree="/w",
        actual_sha="abc123",
        actual_role="ops",
        actual_scope="src/skillweave/runtime/x.py",
    )
    defaults.update(actual)
    return run_preflight(_envelope(), **defaults)


def test_complete_match_passes():
    assert _passing().passed is True


def test_wrong_repo_fails():
    assert _passing(actual_repo="git@evil").passed is False


def test_wrong_worktree_fails():
    assert _passing(actual_worktree="/elsewhere").passed is False


def test_wrong_branch_fails():
    assert _passing(actual_branch="main").passed is False


def test_wrong_sha_fails():
    assert _passing(actual_sha="deadbeef").passed is False


def test_wrong_role_fails():
    assert _passing(actual_role="reviewer").passed is False


def test_scope_outside_write_scope_fails():
    assert _passing(actual_scope="/etc/passwd").passed is False


def test_analyze_and_delete_fails_closed():
    env = _envelope()
    # A destructive verb carrying a benign prefix is NOT read-only.
    assert env.is_read_only_operation("analyze_and_delete") is False
    assert env.mutation_requires_capability("analyze_and_delete") is True
    # A truly read-only verb still passes.
    assert env.is_read_only_operation("read_file") is True
    # ``delete_*`` is never read-only regardless of a read-looking prefix.
    assert env.is_read_only_operation("get_and_delete") is False


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in _tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
