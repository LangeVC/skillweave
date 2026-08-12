"""
Degraded-Kennzeichnung — Nachweis im installierten Wheel (venv)

Vier Zustände:

  Z0: skillweave_degraded.py ist im Wheel — Auslieferbarkeit.
  Z1: runtime/ vorhanden → active=False
  Z2: runtime/ umbenannt  → active=True, reason + fallback_version
  Z3: runtime/ kaputt     → ModuleNotFoundError durchgereicht

Der Nachweis verändert den Quellbaum nicht: das Rad wird aus einer
temporären git-archive-Kopie gebaut. Dadurch ist er beliebig oft
wiederholbar, und die Wiederholbarkeit wird selbst geprüft
(zweiter Lauf mit denselben Ergebnissen).

Alle os.rename-Operationen operieren ausschliesslich im site-packages
des venv.

Reproduzierbar: python3 tests/gate_b06/degraded_proof.py
Repo-Root aus eigener Position abgeleitet, kein fester Pfad.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def prove_detector():
    """
    Bau-Rad aus git-archive-Kopie → venv → vier Zustände prüfen.

    Keine Operationen im REPO_ROOT.  Temp-Verzeichnis wird am Ende
    gelöscht.  Gibt (passed, failed) zurück.
    """
    TMP = tempfile.mkdtemp(prefix="sw-gateb06-")
    SRC = os.path.join(TMP, "src")
    VENV = os.path.join(TMP, "venv")
    DIST = os.path.join(TMP, "dist")
    print(f"  TMP = {TMP}")

    results = {}
    passed = 0
    failed = 0

    def check(label, condition):
        nonlocal passed, failed
        if condition:
            results[label] = "PASS"
            passed += 1
        else:
            results[label] = "FAIL"
            failed += 1

    # ── git archive → $SRC ──
    subprocess.run(
        ["git", "archive", "HEAD"],
        check=True, stdout=open(os.path.join(TMP, "src.tar"), "wb"),
        cwd=REPO_ROOT, timeout=60,
    )
    os.makedirs(SRC, exist_ok=True)
    subprocess.run(
        ["tar", "-xf", os.path.join(TMP, "src.tar")],
        check=True, capture_output=True, cwd=SRC, timeout=60,
    )

    # ── Build wheel aus archivierter Kopie ──
    os.makedirs(DIST, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", DIST, SRC],
        check=True, capture_output=True, cwd=SRC, timeout=120,
    )

    # ── Z0: skillweave_degraded.py is in the wheel ──
    whl_files = sorted(glob.glob(os.path.join(DIST, "*.whl")))
    assert whl_files, "No wheel built"
    names = zipfile.ZipFile(whl_files[-1]).namelist()
    check("Z0: skillweave_degraded in wheel", "skillweave_degraded.py" in names)

    # ── Create venv and install wheel ──
    subprocess.run(
        [sys.executable, "-m", "venv", VENV],
        check=True, capture_output=True,
    )
    venv_python = os.path.join(VENV, "bin", "python3")
    subprocess.run(
        [venv_python, "-m", "pip", "install", whl_files[-1]],
        check=True, capture_output=True, timeout=120,
    )

    def run_in_venv(code):
        result = subprocess.run(
            [venv_python, "-c", code],
            capture_output=True, text=True, cwd=TMP, timeout=60,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    # Finde runtime/ im site-packages des venv (nicht im Quellbaum)
    rc, stdout, stderr = run_in_venv("""
import importlib.util, os
spec = importlib.util.find_spec('skillweave')
runtime = os.path.join(os.path.dirname(spec.origin), 'runtime')
print(runtime)
""")
    runtime_path = stdout
    assert os.path.realpath(runtime_path).startswith(os.path.realpath(VENV)), (
        f"runtime/ must be in venv site-packages, got {runtime_path}"
    )
    print(f"  runtime/ in venv: {runtime_path}")

    # ── Z1: runtime vorhanden ──
    rc, stdout, stderr = run_in_venv("""
from skillweave_degraded import detect_degraded
s = detect_degraded()
print(f'active={s.active} reason={s.reason!r} fallback={s.fallback_version}')
assert s.active is False
print('Z1 OK')
""")
    check("Z1: runtime-present", "Z1 OK" in stdout)
    print(f"    Z1: {stdout}")

    # ── Z2: runtime/ umbenannt (im venv, nicht im Repo) ──
    runtime_hidden = runtime_path + "_hidden"
    os.rename(runtime_path, runtime_hidden)
    rc, stdout, stderr = run_in_venv("""
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
    print(f"    Z2: {stdout}")
    os.rename(runtime_hidden, runtime_path)

    # ── Z3: runtime/ kaputt (schema/ fehlt, im venv) ──
    schema_path = os.path.join(runtime_path, "schema")
    schema_hidden = schema_path + "_hidden"
    os.rename(schema_path, schema_hidden)
    rc, stdout, stderr = run_in_venv("""
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
    print(f"    Z3: {stdout}")
    os.rename(schema_hidden, schema_path)

    shutil.rmtree(TMP, ignore_errors=True)

    print(f"  => {passed} passed, {failed} failed\n")
    return passed, failed


# ── Zwei aufeinanderfolgende Läufe — Wiederholbarkeit ──
print("=== Lauf 1 ===")
p1, f1 = prove_detector()

print("=== Lauf 2 (Wiederholbarkeit) ===")
p2, f2 = prove_detector()

assert (p1, f1) == (p2, f2), (
    f"Wiederholbarkeit gebrochen: Lauf1 ({p1}/{f1}), Lauf2 ({p2}/{f2})"
)

print(f"Wiederholbarkeit: Lauf1=({p1}/{f1}) == Lauf2=({p2}/{f2})")
print(f"OVERALL: {'PASS' if p1 == 4 else 'FAIL'}  ({p1} passed, {f1} failed)")
sys.exit(0 if p1 == 4 and f1 == 0 else 1)
