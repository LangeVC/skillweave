"""
Degraded-Kennzeichnung — Nachweis im installierten Wheel (venv)

Drei Zustände werden durch physikalisches Verschieben der runtime/
im site-packages-Verzeichnis hergestellt, nicht durch monkeypatching:

  Z1: runtime/ vorhanden → active=False
  Z2: runtime/ umbenannt  → active=True, reason + fallback_version
  Z3: runtime/ kaputt     → ModuleNotFoundError durchgereicht

Reproduzierbar: python3 tests/gate_b06/degraded_proof.py
Repo-Root aus eigener Position abgeleitet, kein fester Pfad.
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

results = {}
passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        results[label] = "PASS"
        passed += 1
    else:
        results[label] = "FAIL"
        failed += 1


def run_in_venv(venv_python, code):
    """Run a Python snippet in the given venv and return (rc, stdout, stderr)."""
    result = subprocess.run(
        [venv_python, "-c", code],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=60,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


# ── Build and install wheel into temp venv ──
venv_dir = tempfile.mkdtemp(prefix="sw-venv-")
print(f"Creating venv: {venv_dir}")
subprocess.run([sys.executable, "-m", "venv", venv_dir],
               check=True, capture_output=True)
venv_python = os.path.join(venv_dir, "bin", "python3")

subprocess.run([venv_python, "-m", "pip", "install", "-e", REPO_ROOT],
               check=True, capture_output=True, cwd=REPO_ROOT, timeout=120)

# Finde das installierte skillweave/runtime/ im venv
rc, stdout, stderr = run_in_venv(venv_python, """
import importlib.util, os
spec = importlib.util.find_spec('skillweave')
runtime = os.path.join(os.path.dirname(spec.origin), 'runtime')
print(runtime)
""")
runtime_path = stdout
print(f"runtime/ in venv: {runtime_path}")

# ── Z1: runtime vorhanden ──
rc, stdout, stderr = run_in_venv(venv_python, """
from skillweave_degraded import detect_degraded
s = detect_degraded()
print(f'active={s.active} reason={s.reason!r} fallback={s.fallback_version}')
assert s.active is False
print('Z1 OK')
""")
check("Z1: runtime-present", "Z1 OK" in stdout)
print(f"  Z1 stdout: {stdout}")

# ── Z2: runtime/ umbenannt ──
runtime_hidden = runtime_path + "_hidden"
os.rename(runtime_path, runtime_hidden)
rc, stdout, stderr = run_in_venv(venv_python, """
import importlib, sys
for k in list(sys.modules):
    if k.startswith('skillweave.runtime'):
        del sys.modules[k]
importlib.invalidate_caches()

from skillweave_degraded import detect_degraded
s = detect_degraded()
print(f'active={s.active} reason={s.reason!r} fallback={s.fallback_version}')
assert s.active is True
assert s.fallback_version == 'v1.2.0'
print('Z2 OK')
""")
check("Z2: runtime-absent", "Z2 OK" in stdout)
print(f"  Z2 stdout: {stdout}")
os.rename(runtime_hidden, runtime_path)

# ── Z3: runtime/ kaputt (schema/ fehlt) ──
schema_path = os.path.join(runtime_path, "schema")
schema_hidden = schema_path + "_hidden"
os.rename(schema_path, schema_hidden)
rc, stdout, stderr = run_in_venv(venv_python, """
import importlib, sys
for k in list(sys.modules):
    if k.startswith('skillweave.runtime'):
        del sys.modules[k]
importlib.invalidate_caches()

from skillweave_degraded import detect_degraded
try:
    detect_degraded()
except ModuleNotFoundError as e:
    print(f'ModuleNotFoundError durchgereicht: {e}')
    print('Z3 OK')
else:
    print('FAIL: kein Fehler geworfen')
""")
check("Z3: runtime-broken", "Z3 OK" in stdout)
print(f"  Z3 stdout: {stdout}")
os.rename(schema_hidden, schema_path)

# ── Cleanup ──
shutil.rmtree(venv_dir, ignore_errors=True)

# ── Report ──
print("=" * 60)
for label, status in results.items():
    print(f"  [{status}] {label}")
print("=" * 60)
print(f"  {passed} passed, {failed} failed")
print(f"  OVERALL: {'PASS' if failed == 0 else 'FAIL'}")
sys.exit(0 if failed == 0 else 1)
