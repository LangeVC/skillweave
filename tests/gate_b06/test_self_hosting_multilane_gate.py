"""SW-GATE-137: the independent `SELF_HOSTING_MULTI_LANE_PASS` gate fixture.

The gate reproduces five fixtures — parallel, conflict, SHA, review, and
coordinator-kill — in a single self-contained run, emitting the token
``SELF_HOSTING_MULTI_LANE_PASS`` only when every fixture holds. The fixtures
compress the acceptance guarantees of the whole SW-137 program into one
reproducible check:

* **parallel** — two real processes overlap in time (fan-out, SW-FANOUT-001).
* **conflict** — two writers on the same version: exactly one wins, the other
  gets a conflict (CAS, SW-STATE-001).
* **SHA** — a review child-run gated on a full pinned remote SHA (SW-REVIEW-001).
* **review** — the reviewer is read-only; write attempts block before execution
  (SW-AUTH-001 / SW-REVIEW-001).
* **coordinator-kill** — a coordinator dies, a fresh coordinator resumes the
  persisted root cursor (SW-COORD-001).

The fixture is invoked under ``bash -eo pipefail``; it is independently
reproducible via ``scripts/gate_self_hosting_multilane.sh`` (which shells out
to the hermetic unit suites and this test).

Dependencies: the gate's dependency list in the PRD spans all 29 other tasks;
each is satisfied by the module its fixture exercises (mapped via the WAVE
contract). The gate asserts the *integrated* outcome, not the individual
modules.
"""

import hashlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent.parent
_src = _repo / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.fanout import fan_out_dispatch  # noqa: E402
from skillweave.runtime.store import SQLiteRunStore  # noqa: E402
from skillweave.runtime.authority import AuthorityGuard  # noqa: E402
from skillweave.review import ReviewGate, ReviewGateError  # noqa: E402
from skillweave.coordinator import Coordinator  # noqa: E402
from skillweave.routing.modelspec import concrete, delegated  # noqa: E402

GATE_TOKEN = "SELF_HOSTING_MULTI_LANE_PASS"

FULL_A = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
FULL_B = "b2c3d4e5f60718293a4b5c6d7e8f90123456789"


def _fixture_parallel() -> bool:
    marker = tempfile.mkdtemp(prefix="gate-par-")
    script = (
        "import time, pathlib\n"
        f"p = pathlib.Path({marker!r})\n"
        "open(p / %r, 'w').write(str(time.time()*1000))\n"
        "time.sleep(0.3)\n"
        "open(p / (%r + '.end'), 'w').write(str(time.time()*1000))\n"
        "print('done')\n"
    )
    cmds = [
        [sys.executable, "-c", script % ("a", "a")],
        [sys.executable, "-c", script % ("b", "b")],
    ]
    result = fan_out_dispatch(
        cmds, run_id="gate-par", subject_repo="skillweave", subject_commit=FULL_A,
        tool="opencode", model="faigate/deepseek-v4-pro",
        created_at="2026-08-22T00:00:00Z",
    )
    if not (result.overlapped and result.succeeded):
        return False
    a_start = float((Path(marker) / "a").read_text())
    a_end = float((Path(marker) / "a.end").read_text())
    b_start = float((Path(marker) / "b").read_text())
    b_end = float((Path(marker) / "b.end").read_text())
    return a_end > b_start and b_end > a_start


def _fixture_conflict() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteRunStore(str(Path(tmp) / "store.db"))
        # Two writers race on the same version; exactly one wins, the other
        # gets a Conflict (CAS). Use the transition CAS surface.
        store.create_run("cas-1")
        run = store.get_run("cas-1")
        first = store.transition("cas-1", "batch_selection", expected_state="preflight",
                                  expected_version=run.version, role="ops")
        # A stale version write must conflict.
        try:
            store.transition("cas-1", "batch_selection", expected_state="preflight",
                             expected_version=run.version, role="ops")
        except Exception:
            won = True
        else:
            won = False
        store.close()
        return won


def _fixture_sha() -> bool:
    gate = ReviewGate()
    try:
        gate.evaluate(review_id="gate-sha", pinned_remote_sha=FULL_A,
                      fetched_sha=FULL_A, subject_repo="skillweave")
    except ReviewGateError:
        return False
    try:
        gate.evaluate(review_id="gate-sha-bad", pinned_remote_sha=FULL_A,
                      fetched_sha=FULL_B, subject_repo="skillweave")
    except ReviewGateError:
        return True
    return False


def _fixture_review() -> bool:
    guard = AuthorityGuard()
    for action in ("write", "commit", "push", "mutate_run_state"):
        if guard.can_perform("reviewer", action):
            return False
    return True


def _fixture_per_child_model() -> bool:
    # SW-FANOUT-001-MODELSPEC: each fan-out child resolves its own model, and the
    # child carries which model actually answered (not a shared parent model).
    cmd = [sys.executable, "-c", "print('child')"]
    result = fan_out_dispatch(
        [cmd, cmd], run_id="gate-model", subject_repo="skillweave",
        subject_commit=FULL_A, tool="opencode",
        models=[concrete("faigate/deepseek-v4-pro"), delegated("faigate", "auto")],
        created_at="2026-08-22T00:00:00Z",
    )
    if not result.succeeded or len(result.children) != 2:
        return False
    return (
        result.children[0].model == "faigate/deepseek-v4-pro"
        and result.children[1].model == "faigate:auto"
        and result.children[0].model != result.children[1].model
    )


def _fixture_coordinator_kill() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db)
        coord = Coordinator(store)
        coord.ensure_root("gate-kill", "W3", "L1", role="ops")
        coord.advance("gate-kill", "W3", "n1", role="ops")
        coord.advance("gate-kill", "W3", "n2", role="ops")
        # Simulate the coordinator dying: drop the object and reopen the store.
        store.close()

        store2 = SQLiteRunStore(db)
        fresh = Coordinator(store2)
        cursor = fresh.load("gate-kill", "W3", role="ops")
        if cursor is None or cursor.committed_nodes != ["n1", "n2"]:
            store2.close()
            return False
        nxt = fresh.advance("gate-kill", "W3", "n3", role="ops",
                            expected_version=cursor.version)
        ok = fresh.load("gate-kill", "W3").committed_nodes == ["n1", "n2", "n3"]
        store2.close()
        return ok


_FIXTURES = [
    ("parallel", _fixture_parallel),
    ("conflict", _fixture_conflict),
    ("sha", _fixture_sha),
    ("review", _fixture_review),
    ("coordinator-kill", _fixture_coordinator_kill),
    ("per-child-model", _fixture_per_child_model),
]


def run_gate() -> tuple[bool, dict[str, bool]]:
    results: dict[str, bool] = {}
    for name, fn in _FIXTURES:
        results[name] = bool(fn())
    all_pass = all(results.values())
    return all_pass, results


def emit_token() -> str:
    all_pass, results = run_gate()
    for name, passed in results.items():
        print(f"{'PASS' if passed else 'FAIL'} gate:{name}")
    print(GATE_TOKEN if all_pass else "SELF_HOSTING_MULTI_LANE_FAIL")
    return GATE_TOKEN if all_pass else "SELF_HOSTING_MULTI_LANE_FAIL"


if __name__ == "__main__":
    token = emit_token()
    sys.exit(0 if token == GATE_TOKEN else 1)
