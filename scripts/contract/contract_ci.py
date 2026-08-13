#!/usr/bin/env python3
"""
Cross-Repo-Contract-CI — Wächter für den skillweave-Kern.

Vergleicht die Wertemenge, die dieser Consumer (RunStateModel im Kern) kennt,
gegen die autoritative Wertemenge des gepinnten SDK
(skillweave-sdk → contract/run-state.enum.json).

Pull, nicht Push (docs/repo-vierteilung-contract.md §C.2): der Consumer liest
die gepinnte SDK-Version aus .contract/consumer.toml und validiert gegen genau
diese Fassung. Kein Repo kennt die Pfadlage eines anderen.

Quellen der SDK-Wertemenge, in dieser Reihenfolge:
  1. SKILLWEAVE_SDK_DIR (Umgebungsvariable) — ein bereits ausgechecktes SDK,
     z. B. vom CI-Job nach "git clone sdk@<pin>".
  2. ./sdk — das lokale SDK-Verzeichnis im Entwicklungs-Checkout (vor dem
     Subtree-Push), damit der Wächter auch lokal rot/grün beweisbar ist.
  3. Keine — der Wächter scheitert laut, statt still durchzugehen.

Der Nachweis (Nachweispflicht §C.4/GLE-004): ein absichtlich gebrochener
Contract im SDK (ein Wert aus run-state.enum.json entfernt) macht DIESEN Lauf
rot. Nicht "Pipeline grün".
"""
import json
import os
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    tomllib = None


def _repo_root() -> Path:
    # scripts/contract/contract_ci.py -> Repo-Root (drei Ebenen hoch).
    return Path(__file__).resolve().parent.parent.parent


def _read_pin() -> str:
    pin_path = _repo_root() / ".contract" / "consumer.toml"
    text = pin_path.read_text(encoding="utf-8")
    if tomllib is not None:
        data = tomllib.loads(text)
    else:
        data = {"sdk": {}}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data["sdk"][key.strip()] = value.strip().strip('"')
    return data["sdk"]["version"]


def _sdk_dir() -> Path:
    env = os.environ.get("SKILLWEAVE_SDK_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
        raise SystemExit(f"SKILLWEAVE_SDK_DIR gesetzt, aber kein Verzeichnis: {env}")
    local = _repo_root() / "sdk"
    if local.is_dir():
        return local
    raise SystemExit(
        "SDK nicht auffindbar: weder SKILLWEAVE_SDK_DIR gesetzt noch ./sdk "
        "vorhanden. Der Contract-CI-Job muss das gepinnte SDK auschecken."
    )


def _load_sdk_enum(sdk_dir: Path) -> set:
    enum_path = sdk_dir / "contract" / "run-state.enum.json"
    if not enum_path.is_file():
        raise SystemExit(f"SDK fehlt Contract-Datei: {enum_path}")
    data = json.loads(enum_path.read_text(encoding="utf-8"))
    values = data.get("values")
    if values is None:
        raise SystemExit(f"SDK-Contract {enum_path} hat kein 'values'-Feld")
    return set(values)


def _load_core_enum() -> set:
    sys.path.insert(0, str(_repo_root() / "src"))
    from skillweave.runtime.store import RunStateModel

    return {s.value for s in RunStateModel}


def main() -> int:
    pin = _read_pin()
    sdk_dir = _sdk_dir()
    sdk_values = _load_sdk_enum(sdk_dir)
    core_values = _load_core_enum()

    missing_in_sdk = core_values - sdk_values
    missing_in_core = sdk_values - core_values

    print(f"Contract-CI run-state: pin sdk={pin}")
    print(f"  SDK-Werte : {len(sdk_values)}")
    print(f"  Core-Werte: {len(core_values)}")

    failures = []
    if missing_in_sdk:
        failures.append(
            "Core kennt Zustände, die das SDK nicht deklariert "
            f"(Runtime schreibt, was der Vertrag abweist): {sorted(missing_in_sdk)}"
        )
    if missing_in_core:
        failures.append(
            "SDK deklariert Zustände, die der Core nicht kennt "
            f"(Vertrag akzeptiert, was die Runtime nie schreibt): {sorted(missing_in_core)}"
        )

    if failures:
        for f in failures:
            print(f"  [DRIFT] {f}", file=sys.stderr)
        print("CONTRACT DRIFT DETECTED", file=sys.stderr)
        return 1

    print(f"PASS: Wertemengen identisch ({len(core_values)} Zustände).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
