"""
Minimal Whitelabel-Consumer — importiert skillweave.runtime plus
skillweave.runtime.schema ohne .skillweave/-Profile.

Erwartung: Import gelingt ohne ImportError, Module sind importierbar,
keine Seiteneffekte aus phases.yaml/bundles.yaml/skills/.

Ausgeführt von einem Verzeichnis ausserhalb des SkillWeave-Repos;
das Skript ermittelt den Repo-Root aus seiner eigenen Position
(tests/gate_b06/ → zwei Ebenen hoch).
"""
import sys
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

results = {}

print("--- 1. Core runtime modules ---")
for mod_name in (
    "skillweave.runtime",
    "skillweave.runtime.store",
    "skillweave.runtime.journal",
    "skillweave.runtime.authority",
    "skillweave.runtime.preflight",
    "skillweave.runtime.observer",
    "skillweave.runtime.registry",
    "skillweave.runtime.gate_reconciliation",
    "skillweave.runtime.checkpoint",
    "skillweave.runtime.context",
    "skillweave.runtime.handoff",
    "skillweave.runtime.errors",
    "skillweave.runtime.wireframe",
):
    try:
        __import__(mod_name)
        results[mod_name] = "OK"
    except ImportError as e:
        results[mod_name] = f"FAIL: {e}"

print("--- 2. Schema modules ---")
for mod_name in (
    "skillweave.runtime.schema",
    "skillweave.runtime.schema.vocabulary",
):
    try:
        __import__(mod_name)
        results[mod_name] = "OK"
    except ImportError as e:
        results[mod_name] = f"FAIL: {e}"

print("--- 3. Profile absence ---")
cwd = os.getcwd()
profile_files = (".skillweave", "phases.yaml", "bundles.yaml", "skills")
for name in profile_files:
    path = os.path.join(cwd, name)
    exists = os.path.exists(path)
    results[f"profile:{name}"] = "ABSENT" if not exists else "PRESENT"

print("--- 4. Functional smoke test ---")
from skillweave.runtime.store import SQLiteRunStore, RunStateModel
from skillweave.runtime.journal import EventJournal
from skillweave.runtime.observer import ObserverRuntime
from skillweave.runtime.schema.vocabulary import validate_status

store = SQLiteRunStore()
store.ensure_storage()
journal = EventJournal(store)
r = store.create_run("whitelabel-smoke")
assert r.run_id, "No run_id"
results["smoke:create_run"] = f"OK ({r.run_id})"

journal.append(r.run_id, "smoke-event",
               {"state": RunStateModel.IN_PROGRESS.value},
               event_type="state")
events = journal.get_events(r.run_id)
assert len(events) >= 1, "No events retrieved"
results["smoke:event_journal"] = f"OK ({len(events)} event(s))"

obs = ObserverRuntime(journal, r.run_id)
assert obs._state.offset == 0
results["smoke:observer"] = "OK"

validate_status(RunStateModel.IN_PROGRESS.value)
results["smoke:validate_status"] = "OK"

print("\n===== RESULTS =====")
all_ok = True
for key, value in sorted(results.items()):
    status = "PASS" if ("OK" in value or "ABSENT" in value) else "FAIL"
    if status != "PASS":
        all_ok = False
    print(f"  [{status}] {key}: {value}")

print(f"\nOVERALL: {'PASS' if all_ok else 'FAIL'}")
sys.exit(0 if all_ok else 1)
