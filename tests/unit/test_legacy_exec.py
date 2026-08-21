"""Tests for legacy executor quarantine (SW-LEGACY-EXEC-001).

Two guarantees, both machine-checked:

1. **Zero ``simulate_*`` on the canonical path.** An import/callgraph scan over
   the Run Application Service and the self-hosting entry modules finds no
   ``simulate_step``/``simulate_step_parallel``/``simulate_subagent_execution``
   reference — neither an import of ``skillweave.executor`` nor a direct call.

2. **Direct legacy call warns visibly.** Routing through the quarantine's
   ``call_legacy_simulator`` emits the ``LegacyExecutorWarning`` and returns the
   visible warning banner, so a direct legacy invocation cannot be mistaken for
   a real run.

Self-contained sys.path handling and hermetic scanning (reads the module source
bytes on disk, no import of the canonical path's references), following the
sibling-test convention.
"""

import ast
import sys
import warnings
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.legacy import (  # noqa: E402
    quarantine_warning,
    LegacyExecutorWarning,
    call_legacy_simulator,
    simulate_functions,
)

#: The modules that MUST be free of any simulated executor reference.
_CANONICAL_MODULES = [
    "skillweave/runsvc/service.py",
    "skillweave/selfhost/runner.py",
]

#: Source names that would indicate a reference to the simulating executor.
_LEGACY_TOKENS = [
    "skillweave.executor",
    "from .executor",
    "from ..executor",
    "import executor",
    "simulate_step_parallel",
    "simulate_subagent_execution",
    "simulate_step",
]


def _callgraph_names_used(source: str) -> set[str]:
    """Return every loaded/attribute name referenced in *source*, via AST."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # 'skillweave.executor' -> 'executor'; 'x.simulate_step' -> 'simulate_step'
            names.add(node.attr)
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("simulate_"):
            names.add(node.name)
    return names


def test_zero_simulate_references_in_canonical_path():
    for rel in _CANONICAL_MODULES:
        mod_path = _src / rel
        assert mod_path.exists(), f"canonical module missing: {rel}"
        source = mod_path.read_text()
        names = _callgraph_names_used(source)
        for token in _LEGACY_TOKENS:
            assert token not in source, f"{rel} references legacy token {token!r}"
        for sim_name in simulate_functions:
            assert sim_name not in names, (
                f"{rel} references simulated executor symbol {sim_name!r}; "
                "the canonical self-hosting path must be simulator-free"
            )


def test_direct_legacy_call_warns_visibly():
    # Route a legacy simulate via the quarantine: it must warn, visibly.
    import skillweave.executor as legacy_exec  # noqa: E402

    class _Step:
        id = "s1"
        name = "legacy"

    class _Ctx:
        current_step_id = None
        step_outputs = {}
        completed_steps = []
        metadata = {}
        errors = []

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call_legacy_simulator(legacy_exec.simulate_step, _Step(), _Ctx())

    legacy_warnings = [w for w in caught if issubclass(w.category, LegacyExecutorWarning)]
    assert legacy_warnings, "direct legacy call must emit LegacyExecutorWarning"
    banner = str(legacy_warnings[0].message)
    assert "SW-LEGACY-EXEC-001" in banner
    assert "simulat" in banner.lower()


def test_quarantine_warning_banner_is_stable():
    banner = quarantine_warning()
    assert "SW-LEGACY-EXEC-001" in banner
    assert "not" in banner.lower()


def _run_all() -> int:
    tests = [
        test_zero_simulate_references_in_canonical_path,
        test_direct_legacy_call_warns_visibly,
        test_quarantine_warning_banner_is_stable,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
