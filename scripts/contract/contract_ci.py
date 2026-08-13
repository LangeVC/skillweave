#!/usr/bin/env python3
"""
Cross-Repo-Contract-CI — Wächter für den skillweave-Kern.

Prüft zwei Dinge gegen das gepinnte SDK-Artefakt (v<pin>):

  1. Wertemenge: die Zustände, die RunStateModel im Kern kennt, müssen
     deckungsgleich sein mit der autoritativen Schema-Wertemenge des SDK
     (schemas/run-state.schema.json#/properties/state/enum).
  2. Byte-Gleichheit (§C.9): jede Core-lokale schemas/*.json muss byte-gleich
     zur selben Datei im gepinnten SDK sein. Die Core-Kopie ist ein
     ABGELEITETES Artefakt, keine Quelle — weicht ein Byte ab, wird der Build
     rot, auch wenn die Wertemengen zufällig gleich sind.

Pull, nicht Push (docs/repo-vierteilung-contract.md §C.2): der Consumer liest
die gepinnte SDK-Version aus .contract/consumer.toml und validiert gegen genau
diese Fassung. Kein Repo kennt die Pfadlage eines anderen.

Wahrheitsquelle ist AUSSCHLIESSLICH das gepinnte SDK-Artefakt, nie eine
eingecheckte Kopie (Signatur der zweiten Wahrheit, §C.2). Zwei zulaessige
Bezugswege:

  1. SKILLWEAVE_SDK_DIR (Umgebungsvariable) — ein lokaler CACHE. Er ist
     Ergonomie (lokaler Build ohne Netz), wird aber gegen den Pin verifiziert
     (schema_version.toml muss zum Pin passen); weicht er ab, scheitert der
     Waechter, statt eine falsche Quelle zu lesen.
  2. Sonst klont der Waechter das gepinnte SDK-Artefakt selbst (Tag v<pin>).

Es gibt bewusst KEINEN ./sdk-Fallback. Eine eingecheckte sdk/-Kopie ist keine
Wahrheitsquelle und darf vom Waechter nicht gelesen werden.

Der Nachweis (Nachweispflicht §C.4/GLE-004): ein absichtlich gebrochener
Contract im SDK (ein Wert aus run-state.schema.json entfernt) macht DIESEN
Lauf rot. Nicht "Pipeline grün". Der Bruch muss im Remote-Artefakt existieren,
nicht im Arbeitsbaum; erst dann prueft der Waechter das Richtige.

Zwei Leser auf dieselbe Core-Wertemenge — MERKMAL, keine Redundanz (siehe auch
tests/unit/test_vocabulary_guard.py): dieser Waechter liest RunStateModel
AST-basiert importfrei; der Unit-Test importiert es normal. Laufen beide
auseinander, ist das ein Befund (das Enum wurde dynamisch).
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    tomllib = None

# Woher das gepinnte SDK-Artefakt geklont wird, falls kein Cache gesetzt ist.
SOURCE_REMOTES = (
    "https://github.com/LangeVC/skillweave-sdk.git",
    "https://git.langevc.com/skillweave/skillweave-sdk.git",
)


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


def _tag_for_pin(pin: str) -> str:
    # Pin "0.1.0" -> Tag "v0.1.0". Der Pin ist die Versionsnummer; der Tag
    # ist die Git-Ref, die sie referenziert.
    return f"v{pin}"


def _clone_sdk(pin: str) -> Path:
    tag = _tag_for_pin(pin)
    dest = Path(tempfile.mkdtemp(prefix="skillweave-sdk-"))
    last_err = None
    for remote in SOURCE_REMOTES:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", tag, remote, str(dest)],
                check=True,
                capture_output=True,
                text=True,
            )
            return dest
        except subprocess.CalledProcessError as exc:
            last_err = exc
    raise SystemExit(
        f"SDK-Artefakt {tag} nicht klonbar. Geproeft:\n"
        + "\n".join(f"  - {r}" for r in SOURCE_REMOTES)
        + f"\nLetzter Fehler: {getattr(last_err, 'stderr', last_err)!r}"
    )


def _verify_cache(sdk_dir: Path, pin: str) -> None:
    # Der Cache ist nur gueltig, wenn seine schema_version.toml zum Pin passt.
    version_path = sdk_dir / "schema_version.toml"
    if not version_path.is_file():
        raise SystemExit(
            "SKILLWEAVE_SDK_DIR zeigt auf kein SDK (schema_version.toml fehlt). "
            "Cache verwerfen und neu holen."
        )
    text = version_path.read_text(encoding="utf-8")
    loaded = tomllib.loads(text) if tomllib is not None else None
    if loaded is None:
        # Ohne tomllib ist ein sauberer Abgleich nicht moeglich; scheitern statt raten.
        raise SystemExit("tomllib fehlt; Cache kann nicht verifiziert werden.")
    cached = loaded["schema"]["version"]
    if cached != pin:
        raise SystemExit(
            f"Cache-Version {cached} passt nicht zum Pin {pin}. "
            "Cache verwerfen und neu holen."
        )


def _sdk_dir(pin: str) -> Path:
    env = os.environ.get("SKILLWEAVE_SDK_DIR")
    if env:
        p = Path(env)
        if not p.is_dir():
            raise SystemExit(f"SKILLWEAVE_SDK_DIR gesetzt, aber kein Verzeichnis: {env}")
        _verify_cache(p, pin)
        return p
    # Kein Cache: gepinntes Artefakt klonen. Bewusst KEIN ./sdk-Fallback.
    return _clone_sdk(pin)


def _load_sdk_enum(sdk_dir: Path) -> set:
    # Autoritativ ist die Schema-Wertemenge (§F.3), nicht der contract/*.json-
    # Extrakt. Der Extrakt ist nur ein erzeugtes Bequemlichkeits-Artefakt und
    # darf vom Waechter nicht als Wahrheitsquelle gelesen werden.
    schema_path = sdk_dir / "schemas" / "run-state.schema.json"
    if not schema_path.is_file():
        raise SystemExit(f"SDK fehlt Schema: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    enum = schema["properties"]["state"]["enum"]
    if not isinstance(enum, list) or not enum:
        raise SystemExit(f"{schema_path}: properties.state.enum leer oder fehlt")
    return set(enum)


def _load_core_enum() -> set:
    # Importfrei (§C.2): die Wertemenge wird statisch aus store.py gelesen,
    # nicht per "import skillweave". Der Waechter prueft eine DEKLARATION und
    # darf nicht an der Installierbarkeit des Cores haengen (kein pyyaml, keine
    # GLE-020-Importkette). Scheitert LAUT, wenn ein Member nicht statisch als
    # String-Literal aufloesbar ist — still weniger Werte zu finden waere der
    # Drift-Fehler in neuer Form.
    store_path = _repo_root() / "src" / "skillweave" / "runtime" / "store.py"
    tree = ast.parse(store_path.read_text(encoding="utf-8"), filename=str(store_path))
    values = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "RunStateModel":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            if isinstance(stmt.value, ast.Constant) and isinstance(
                                stmt.value.value, str
                            ):
                                values.add(stmt.value.value)
                            else:
                                raise SystemExit(
                                    f"RunStateModel.{target.id} (Zeile {stmt.lineno}) "
                                    "ist kein statisch aufloesbares String-Literal. "
                                    "Contract-Waechter kann die Core-Wertemenge nicht "
                                    "importfrei lesen."
                                )
            break
    else:
        raise SystemExit("RunStateModel nicht in store.py gefunden.")
    if not values:
        raise SystemExit("RunStateModel lieferte eine leere Wertemenge.")
    return values


def _check_schema_bytes(sdk_dir: Path) -> list:
    # Uebergangszustand (§C.9): die Core-lokale schemas/*.json ist ein
    # ABGELEITETES Artefakt der gepinnten SDK-Version. Dieser Check erzwingt
    # Byte-Gleichheit — blockierend, nicht als Vorfilter. Weicht ein Byte ab,
    # ist der Build rot, auch wenn die Wertemengen zufaellig gleich sind.
    core_schemas = sorted((_repo_root() / "schemas").glob("*.schema.json"))
    failures = []
    for core_schema in core_schemas:
        rel = core_schema.name
        sdk_schema = sdk_dir / "schemas" / rel
        if not sdk_schema.is_file():
            failures.append(
                f"Core-Schema {rel} fehlt im gepinnten SDK-Artefakt."
            )
            continue
        if core_schema.read_bytes() != sdk_schema.read_bytes():
            failures.append(
                f"Byte-Drift in {rel}: Core-Kopie weicht vom gepinnten "
                "SDK-Artefakt ab (abgeleitet, nicht Quelle)."
            )
    return failures


def main() -> int:
    pin = _read_pin()
    sdk_dir = _sdk_dir(pin)
    sdk_values = _load_sdk_enum(sdk_dir)
    core_values = _load_core_enum()

    missing_in_sdk = core_values - sdk_values
    missing_in_core = sdk_values - core_values

    print(f"Contract-CI run-state: pin sdk={pin}")
    print(f"  SDK-Werte : {len(sdk_values)}")
    print(f"  Core-Werte: {len(core_values)}")

    failures = []
    failures.extend(_check_schema_bytes(sdk_dir))
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

    print(f"PASS: Wertemengen identisch ({len(core_values)} Zustände), "
          "Schemas byte-gleich zum gepinnten SDK-Artefakt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
