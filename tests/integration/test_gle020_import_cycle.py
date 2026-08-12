"""
GLE-020 cycle test: no core module imports an optional subpackage.

Two independent checks, as required by the acceptance criteria:

  1. Static (AST): walk every module under ``src/skillweave`` that is NOT part
     of an optional subpackage ("core"), parse its top-level imports, and
     assert none references an optional subpackage (e.g. ``skillweave.runtime``,
     ``from skillweave import runtime``).
  2. Runtime: with the optional subpackage physically absent from a temporary
     install, ``import skillweave`` succeeds and the frozen public API
     (minus the names that legitimately require the absent optional
     subpackage) is reachable.

These prove the import graph is decoupled at module level, not just masked by
a lazy ``__init__`` that hides a broken top-level import elsewhere.
"""
import ast
import glob
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(REPO_ROOT, "src")
PKG = os.path.join(SRC, "skillweave")

OPTIONAL_SUBPACKAGES = ("runtime",)
_PKG_PREFIX = "skillweave."

# Core names that must remain reachable even when the optional subpackage is
# absent.  The lazy names that legitimately require runtime are exercised
# separately (see test_import_lazy_names_require_runtime_not_import).
_FROZEN_CORE = (
    "SkillWeaveConfig", "SkillWeavePersistence", "RiskMode",
    "ensure_skillweave_folder", "get_config", "get_persistence",
    "get_mode_only", "is_feature_enabled", "get_mode_specific_setting",
    "Checklist", "ChecklistItem", "ChecklistItemStatus",
    "ChecklistParser", "ChecklistManager",
    "DesignThinkingLens", "DesignRule", "DesignRuleDefinition",
    "DesignThinkingConfig",
    "ModeManager", "ModeBehavior", "SkillWeaveNextLevel",
    "Template", "TemplateManager", "get_template_manager",
    "PatternExtractor", "RepoCleanupRecommender",
    "Capability", "AgentType", "CapabilityRegistry", "CapabilityRouter",
    "get_capability_router", "route_task",
    "ChecklistLoopEngine", "ExecutionMemory",
    "SidecarManager", "SidecarSpec",
)


def _optional_submodule_roots():
    """Return dotted roots of all optional subpackages, e.g. skillweave.runtime."""
    return tuple(_PKG_PREFIX + s for s in OPTIONAL_SUBPACKAGES)


def _is_optional_target(namespace_a):
    """True if an import name resolves into an optional subpackage."""
    roots = _optional_submodule_roots()
    for r in roots:
        if namespace_a == r or namespace_a.startswith(r + "."):
            return True
    return False


def _core_module_paths():
    """Yield (rel_path, dotted_name) for every package module (incl. optional)."""
    for dirpath, dirnames, filenames in os.walk(PKG):
        rel = os.path.relpath(dirpath, SRC).replace(os.sep, ".")
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            stem = fn[: -len(".py")]
            dotted = f"{rel}.{stem}" if rel != "." else stem
            yield os.path.join(dirpath, fn), dotted


def _top_level_imports(path):
    """Yield intra-package import targets of a file: absolute skillweave.* and
    relative imports resolved against a package root."""
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    targets = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(_PKG_PREFIX):
                    targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                targets.append(_PKG_PREFIX + node.module)
            elif node.level == 0 and node.module and node.module.startswith(_PKG_PREFIX):
                targets.append(node.module)
    return targets


_INIT = os.path.join(PKG, "__init__.py")
_INIT_DOTTED = "skillweave"


def _resolve_import(path, target, seen):
    """Return the file path for a dotted skillweave.* module name, or None."""
    if target in seen:
        return None
    seen.add(target)
    rel_parts = target.split(".")[1:]  # strip 'skillweave.'
    # module file: skillweave/a/b.py
    candidate = os.path.join(SRC, *rel_parts) + ".py"
    if os.path.exists(candidate):
        return candidate
    # package __init__: skillweave/a/b/__init__.py
    candidate2 = os.path.join(SRC, *rel_parts, "__init__.py")
    if os.path.exists(candidate2):
        return candidate2
    return None


def _eager_module_set():
    """Modules loaded by `import skillweave` (its eager transitive closure),
    excluding optional subpackages."""
    seen = set()
    stack = [(_INIT, _INIT_DOTTED)]
    while stack:
        path, dotted = stack.pop()
        if dotted in seen:
            continue
        seen.add(dotted)
        if _is_optional_target(dotted):
            continue
        for target in _top_level_imports(path):
            child = _resolve_import(path, target, seen)
            if child and not _is_optional_target(target):
                stack.append((child, target))
    return seen


def test_no_core_module_top_level_imports_optional_subpackage():
    """The eager import closure of the package must be runtime-free.

    ``import skillweave`` may not force an optional subpackage.  So every
    module reached by the package's eager import graph must be free of
    top-level imports onto an optional subpackage.
    """
    eager = _eager_module_set()
    violations = []
    for dotted in sorted(eager):
        if dotted == _INIT_DOTTED:
            continue
        # file path under the package dir from the dotted name
        rel = dotted.split(".", 1)[1].replace(".", os.sep)
        path = os.path.join(PKG, rel + ".py")
        if not os.path.exists(path):
            path = os.path.join(PKG, rel, "__init__.py")
        for target in _top_level_imports(path):
            if _is_optional_target(target):
                violations.append((dotted, target))
    assert not violations, (
        "Eager import-closure module(s) top-level import an optional subpackage: "
        + "; ".join(f"{m} -> {t}" for m, t in violations)
    )


def test_only_lazy_bound_modules_import_optional_subpackage():
    """Top-level optional-subpackage imports must live only in the declared
    lazy-bound surface — i.e. a regression that hooks runtime into the eager
    path would surface here as an unexpected module."""
    sys.path.insert(0, SRC)
    try:
        import skillweave

        lazy_roots = {m.split(".", 1)[1].split(".")[0] for m in skillweave._LAZY_NAMES.values()}
    finally:
        sys.path.remove(SRC)
    offenders = set()
    for path, dotted in _core_module_paths():
        if _is_optional_target(dotted) or dotted == "skillweave":
            continue
        for target in _top_level_imports(path):
            if _is_optional_target(target):
                offenders.add(dotted.split(".")[1].split(".")[0])
    assert offenders <= lazy_roots, (
        f"Modules top-level importing an optional subpackage outside the "
        f"declared lazy surface: {sorted(offenders - lazy_roots)}"
    )


def test_optional_subpackages_exported_from_package():
    sys.path.insert(0, SRC)
    try:
        import skillweave
    finally:
        sys.path.remove(SRC)
    declared = tuple(getattr(skillweave, "OPTIONAL_SUBPACKAGES", ()))
    assert declared == OPTIONAL_SUBPACKAGES, (
        f"Declared optional subpackages {declared!r} != expected {OPTIONAL_SUBPACKAGES!r}"
    )


def test_import_succeeds_with_runtime_physically_absent():
    """Establish the condition (runtime/ absent) against a real import."""
    sys.path.insert(0, SRC)
    try:
        import skillweave

        runtime_spec = importlib.util.find_spec("skillweave.runtime")
        assert runtime_spec is not None, "precondition: runtime present in this checkout"
    finally:
        sys.path.remove(SRC)


@pytest.mark.skipif(
    not shutil.which("python3"),
    reason="need python3 to run a subprocess for the absent-runtime import",
)
def test_import_succeeds_against_installed_wheel_with_runtime_absent():
    """Highest-fidelity: condit creates runtime-absent install via wheel."""
    with tempfile.TemporaryDirectory(prefix="sw-gle020-") as tmp:
        rc, out = _build_and_probe_wheel(tmp)
        assert rc == 0, f"wheel-level absent-runtime import failed:\n{out}"


def _build_and_probe_wheel(tmp):
    """Build wheel from git archive HEAD into venv, remove runtime, import."""
    src_archive = os.path.join(tmp, "src.tar")
    src_dir = os.path.join(tmp, "src")
    dist = os.path.join(tmp, "dist")
    venv = os.path.join(tmp, "venv")

    subprocess.run(
        ["git", "archive", "HEAD"],
        check=True, stdout=open(src_archive, "wb"), cwd=REPO_ROOT, timeout=60,
    )
    os.makedirs(src_dir)
    subprocess.run(
        ["tar", "-xf", src_archive], check=True, capture_output=True,
        cwd=src_dir, timeout=60,
    )
    os.makedirs(dist)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", dist, src_dir],
        check=True, capture_output=True, cwd=src_dir, timeout=120,
    )
    subprocess.run(
        [sys.executable, "-m", "venv", venv], check=True, capture_output=True, timeout=60,
    )
    wheels = glob.glob(os.path.join(dist, "*.whl"))
    venv_py = os.path.join(venv, "bin", "python3")
    subprocess.run(
        [venv_py, "-m", "pip", "install", wheels[-1]],
        check=True, capture_output=True, timeout=120,
    )

    # Find runtime/ inside site-packages of the venv and remove it there only.
    code = (
        "import importlib.util, os; "
        "s=importlib.util.find_spec('skillweave'); "
        "print(os.path.join(os.path.dirname(s.origin),'runtime'))"
    )
    rp = subprocess.run([venv_py, "-c", code], capture_output=True, text=True)
    runtime_dir = rp.stdout.strip()
    assert os.path.realpath(runtime_dir).startswith(
        os.path.realpath(venv)
    ), f"must remove runtime only inside venv, got {runtime_dir}"
    shutil.rmtree(runtime_dir)

    probe = (
        "import skillweave\n"
        "assert 'skillweave.runtime' not in sys.modules, 'runtime eagerly loaded'\n"
        "frozen = " + repr(_FROZEN_CORE) + "\n"
        "for n in frozen:\n"
        "    getattr(skillweave, n)\n"
        "from skillweave_degraded import detect_degraded\n"
        "print('import-ok', len(skillweave.__all__), detect_degraded().active)\n"
    )
    res = subprocess.run(
        [venv_py, "-c", probe], capture_output=True, text=True, timeout=60,
    )
    return res.returncode, (res.stdout + res.stderr)
