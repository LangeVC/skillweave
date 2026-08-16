"""
GLE-020 Import-Decoupling — Nachweis im installierten Wheel (venv)

Bedingung wird HERGESTELLT, nicht simuliert (§3.8 PRD): ``runtime/`` wird
physisch aus dem site-packages des venv entfernt, DANN importiert. Kein
Monkeypatch auf ``builtins.__import__``, kein Mock der Importkette. Das Rad
wird aus einer git-archive-Kopie (HEAD) gebaut und per ``pip install`` in ein
frisches venv eingespielt — nicht über PYTHONPATH=src, nicht editable.

Zustände:

  Z0: skillweave_degraded.py ist im Wheel — Auslieferbarkeit (fängt eine
      Packaging-Regression).
  Z1: runtime/ vorhanden → `import skillweave` gelingt UND skillweave.runtime
      ist NICHT eager geladen (lazy).
  Z2: runtime/ physisch umbenannt (nur im venv) → `import skillweave` gelingt
      weiterhin, der eingefrorene Kern-API resolved, detect_degraded() meldet
      active=True.
  Z3: eingefrorene OEFENTLICHE API (alle 50 Namen) ist im Wheel als
      skillweave.<Name> aufloesbar — Vergleich gegen die Namensliste, nicht
      gegen Erinnerung (GLE020_API).
  Z4: runtime/ umbenannt + Zugriff auf einen runtime-gebundenen lazy Namen
      wirft ModuleNotFoundError (nicht beim Import, erst beim Zugriff),
      Package und Kern bleiben nutzbar.
  Z5: Die Liste optionaler Subpakete ist deklariert und lautet ('runtime',).

Alle os.rename-Operationen operieren ausschliesslich im site-packages des
venv. Der Quellbaum wird nicht veraendert (git archive). Temp-Verzeichnis
wird je Lauf geloescht.

Wiederholbarkeit wird durch zwei aufeinanderfolgende Laeufe mit identischen
Ergebnissen belegt.

Reproduzierbar: python3 tests/gate_b06/gle020_import_decoupling_proof.py
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gle020_api import FROZEN_API, FROZEN_CORE  # noqa: E402

OPTIONAL_SUBPACKAGES = ("runtime",)


def prove_decoupling():
    TMP = tempfile.mkdtemp(prefix="sw-gle020-")
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

    # ── git archive → $SRC (unveraenderte HEAD-Kopie) ──
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

    # ── Build wheel aus der archivierten Kopie ──
    os.makedirs(DIST, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", DIST, SRC],
        check=True, capture_output=True, cwd=SRC, timeout=120,
    )

    # ── Z0: Detektor ist im Wheel (Packaging-Regression absichern) ──
    whl_files = sorted(glob.glob(os.path.join(DIST, "*.whl")))
    assert whl_files, "No wheel built"
    names = zipfile.ZipFile(whl_files[-1]).namelist()
    present = "skillweave_degraded.py" in names
    check("Z0: skillweave_degraded in wheel", present)
    print(f"    Z0: wheel={os.path.basename(whl_files[-1])} detector_present={present}")

    # ── Frisches venv + pip install des Rades ──
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

    # runtime/ im site-packages des venv lokalisieren (nicht im Quellbaum)
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

    # ── Z1: runtime vorhanden → Import gelingt UND lazy ──
    rc, stdout, stderr = run_in_venv("""
import sys
import skillweave
lazy = 'skillweave.runtime' not in sys.modules
core = """ + repr(FROZEN_CORE) + """
for n in core:
    getattr(skillweave, n)
print(f'lazy={lazy}')
assert lazy, 'runtime was loaded eagerly'
print('Z1 OK')
""")
    check("Z1: import-lazy (runtime not eager)", "Z1 OK" in stdout)
    print(f"    Z1: {stdout}")

    # ── Z3: eingefrorene OEFENTLICHE API voll aufloesbar (runtime present) ──
    rc, stdout, stderr = run_in_venv("""
import skillweave
frozen = """ + repr(FROZEN_API) + """
missing = [n for n in frozen if not hasattr(skillweave, n)]
for n in frozen:
    getattr(skillweave, n)
print(f'api={len(frozen)} missing={len(missing)}')
assert not missing, missing
print('Z3 OK')
""")
    check("Z3: frozen public API reachable", "Z3 OK" in stdout)
    print(f"    Z3: {stdout}")

    # ── Z2: runtime/ umbenannt (nur im venv) → Import + Kern + Detector ──
    runtime_hidden = runtime_path + "_hidden"
    os.rename(runtime_path, runtime_hidden)
    rc, stdout, stderr = run_in_venv("""
import importlib, sys
for k in list(sys.modules):
    if k.startswith('skillweave.runtime'):
        del sys.modules[k]
importlib.invalidate_caches()

import skillweave
core = """ + repr(FROZEN_CORE) + """
for n in core:
    getattr(skillweave, n)
from skillweave_degraded import detect_degraded
s = detect_degraded()
print(f'active={s.active} fallback={s.fallback_version}')
assert s.active is True
print('Z2 OK')
""")
    check("Z2: absent-runtime import + core + detector", "Z2 OK" in stdout)
    print(f"    Z2: {stdout}")

    # ── Z4: runtime weg + Zugriff auf runtime-gebundenen Namen → ModuleNotFoundError ──
    rc, stdout, stderr = run_in_venv("""
import importlib, sys
for k in list(sys.modules):
    if k.startswith('skillweave.runtime'):
        del sys.modules[k]
importlib.invalidate_caches()

import skillweave
getattr(skillweave, 'SkillWeaveConfig')  # Kern bleibt nutzbar
try:
    skillweave.EventLogger
    print('FAIL: no error')
except ModuleNotFoundError:
    print('Z4 OK')
""")
    check("Z4: lazy access fails only on touch", "Z4 OK" in stdout)
    print(f"    Z4: {stdout}")
    os.rename(runtime_hidden, runtime_path)

    # ── Z5: listete optionale Subpakete deklariert ──
    rc, stdout, stderr = run_in_venv("""
import skillweave
decl = tuple(getattr(skillweave, 'OPTIONAL_SUBPACKAGES', ()))
print(f'decl={decl!r}')
assert decl == """ + repr(OPTIONAL_SUBPACKAGES) + """, decl
print('Z5 OK')
""")
    check("Z5: optional subpackages declared", "Z5 OK" in stdout)
    print(f"    Z5: {stdout}")

    shutil.rmtree(TMP, ignore_errors=True)

    for label, verdict in results.items():
        print(f"    {label}: {verdict}")
    print(f"  => {passed} passed, {failed} failed\n")
    return passed, failed


print("=== Lauf 1 ===")
p1, f1 = prove_decoupling()

print("=== Lauf 2 (Wiederholbarkeit) ===")
p2, f2 = prove_decoupling()

assert (p1, f1) == (p2, f2), (
    f"Wiederholbarkeit gebrochen: Lauf1 ({p1}/{f1}), Lauf2 ({p2}/{f2})"
)

print(f"Wiederholbarkeit: Lauf1=({p1}/{f1}) == Lauf2=({p2}/{f2})")
print(f"OVERALL: {'PASS' if p1 == 6 else 'FAIL'}  ({p1} passed, {f1} failed)")
sys.exit(0 if p1 == 6 and f1 == 0 else 1)
