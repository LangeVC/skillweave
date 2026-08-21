"""SW-WIREFRAME-001: no exported guard returns a constant PASS or decides by
action name; every documented guard is really exercised with a negative case.

The former ``assert_non_polling() -> True`` stub is integrated: it now inspects
evidence (poll count) rather than returning a constant PASS.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.wireframe import (
    assert_gate_discipline,
    assert_write_scope,
    assert_non_polling,
    assert_no_foreign_repos,
    validate_summary,
)


def test_assert_non_polling_is_not_constant_pass():
    # A single check passes; a polling loop fails. No path is a constant PASS.
    assert assert_non_polling(0) is True
    assert assert_non_polling(1) is True
    assert assert_non_polling(2) is False
    assert assert_non_polling(100) is False


def test_assert_gate_discipline_negative_case_is_really_invoked():
    # No violation -> empty. Violations -> non-empty (guard actually fires).
    assert assert_gate_discipline() == []
    assert assert_gate_discipline(self_approved=True) != []
    assert assert_gate_discipline(merge_invoked=True) != []
    assert assert_gate_discipline(release_invoked=True) != []


def test_assert_write_scope_negative_case_is_really_invoked():
    ok, violations = assert_write_scope(["src/a.py"], ["src"])
    assert ok is True and violations == []
    ok2, violations2 = assert_write_scope(["src/a.py", "/etc/passwd"], ["src"])
    assert ok2 is False and "/etc/passwd" in violations2


def test_assert_no_foreign_repos_negative_case():
    assert assert_no_foreign_repos("git@canonical", "git@canonical") is True
    assert assert_no_foreign_repos("git@evil", "git@canonical") is False


def test_validate_summary_negative_case():
    assert validate_summary(["a", "b"], {"a": 1, "b": 2}) == []
    assert validate_summary(["a", "b", "c"], {"a": 1}) == ["b", "c"]


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
