"""Regression tests for SW-135 preflight hardening.

Bug 1 (validate_write_scope): the scope check used a plain string-prefix
    comparison, so an unauthorized path could slip through either as a
    substring/partial-path component (scope "src" matching "src_evil/...")
    or via parent traversal ("src/../secret.txt" starting with "src/" but
    resolving outside the boundary). The check must run against resolved,
    normalized path boundaries.

Bug 2 (run_preflight): only product/repo/branch were cross-checked; every
    other envelope field was silently skipped. A missing field must be a
    failure, not a skip.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from skillweave.runtime.preflight import SessionEnvelope, run_preflight


def _envelope(**overrides):
    base = dict(
        product="SkillWeave",
        remote_repo="git@canonical",
        worktree="/w",
        branch="feature/x",
        role="OPS",
        prd_digest="d",
        chain_digest="c",
        allowed_write_scopes=["src/**"],
        state_vocabulary=["idle"],
        forbidden_transitions=["merge"],
    )
    base.update(overrides)
    return SessionEnvelope(**base)


# --- Bug 1: write-scope path resolution ------------------------------------

def test_scope_rejects_parent_traversal():
    env = _envelope(allowed_write_scopes=["src/"])
    assert env.validate_write_scope("src/../secret.txt") is False, (
        "parent traversal must not be authorized by a string prefix"
    )


def test_scope_rejects_partial_path_component():
    env = _envelope(allowed_write_scopes=["src"])
    assert env.validate_write_scope("src_evil/foo.py") is False, (
        "partial-path component (src vs src_evil) must not match"
    )


def test_scope_rejects_sibling_with_slash_scope():
    env = _envelope(allowed_write_scopes=["src/**"])
    assert env.validate_write_scope("src2/other.py") is False


def test_scope_allows_legitimate_nested_path():
    env = _envelope(allowed_write_scopes=["src/**"])
    assert env.validate_write_scope("src/skillweave/runtime/preflight.py") is True


def test_scope_allows_exact_boundary():
    env = _envelope(allowed_write_scopes=["src/"])
    assert env.validate_write_scope("src/preflight.py") is True


# --- Bug 2: whole-envelope field presence -----------------------------------

def test_missing_string_field_fails():
    env = _envelope(product=None)
    result = run_preflight(env, actual_repo="git@canonical", actual_branch="feature/x")
    assert result.passed is False, "missing product field must fail preflight"
    assert any(m.get("field") == "product" for m in result.mismatches)


def test_missing_worktree_field_fails():
    env = _envelope(worktree="")
    result = run_preflight(env, actual_repo="git@canonical", actual_branch="feature/x")
    assert result.passed is False, "empty worktree field must fail preflight"
    assert any(m.get("field") == "worktree" for m in result.mismatches)


def test_missing_list_field_fails():
    env = _envelope(allowed_write_scopes=None)
    result = run_preflight(env, actual_repo="git@canonical", actual_branch="feature/x")
    assert result.passed is False, "missing allowed_write_scopes must fail preflight"
    assert any(m.get("field") == "allowed_write_scopes" for m in result.mismatches)


def test_complete_envelope_passes():
    env = _envelope()
    result = run_preflight(env, actual_repo="git@canonical", actual_branch="feature/x")
    assert result.passed is True


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in _tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(_tests) - failures}/{len(_tests)} passed")
    sys.exit(1 if failures else 0)
