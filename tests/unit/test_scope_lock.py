"""SW-SCOPE-LOCK-001: declared write-sets with a conflict matrix.

Overlapping write-sets block a worker BEFORE it starts, rather than being
discovered mid-flight. Disjoint write-sets may run concurrently.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.write_scope import WriteSetManager, WriteSetConflictError


def test_overlapping_scopes_block_before_worker_start():
    mgr = WriteSetManager()
    mgr.declare("worker-a", ["src/skillweave/runtime"])
    try:
        mgr.declare("worker-b", ["src/skillweave"])
        assert False, "overlapping write-set must block worker-b startup"
    except WriteSetConflictError as e:
        assert e.worker_id == "worker-b"
        assert e.conflicting_worker == "worker-a"


def test_disjoint_scopes_run_concurrently():
    mgr = WriteSetManager()
    mgr.declare("worker-a", ["src/skillweave/runtime"])
    mgr.declare("worker-b", ["src/skillweave/council"])
    assert mgr.conflicts_with("worker-c", ["src/skillweave/runtime"]) == ["worker-a"]


def test_conflicts_with_reports_overlap_without_mutating():
    mgr = WriteSetManager()
    mgr.declare("worker-a", ["src/a"])
    assert mgr.conflicts_with("worker-b", ["src/a/foo.py"]) == ["worker-a"]
    assert mgr.conflicts_with("worker-b", ["src/b"]) == []


def test_release_frees_scope_for_reclaim():
    mgr = WriteSetManager()
    mgr.declare("worker-a", ["src/a"])
    mgr.release("worker-a")
    # Now worker-b may declare the same scope without conflict.
    mgr.declare("worker-b", ["src/a"])


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
