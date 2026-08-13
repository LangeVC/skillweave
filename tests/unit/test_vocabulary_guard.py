"""
SW-SCOPE-005: Das Statusvokabular liegt doppelt (Enum in store.py, enum-Liste
im Schema) und darf nicht auseinanderlaufen. Dieser Waechter vergleicht die
Wertemengen und wird rot, sobald eine Seite einen Wert hat, den die andere
nicht kennt.

Richtung (siehe docs/repo-vierteilung-contract.md §F.3): Das Schema ist die
kanonische Quelle der Wertemenge, das Enum bleibt die Code-Struktur. Der
Waechter nagelt keine Richtung fest, er erzwingt Gleichheit: er liest
properties.state.enum aus run-state.schema.json und vergleicht es mit
{s.value for s in RunStateModel}.

Nach dem Schnitt (GLE-004) wird aus diesem Unit-Test eine Contract-CI: das
Schema liegt dann im SDK, das Enum im Consumer. Der Mengenvergleich bleibt
derselbe, nur die Quelle des Schemas wechselt von "Datei im eigenen Repo" auf
"gepinntes SDK-Artefakt".

Zwei Ebenen, verschiedene Aufgaben (GLE-004):
- Dieser Unit-Test ist der SCHNELLE LOKALE VORFILTER: er liest die lokale
  schemas/-Datei und faengt eine Vokabular-Abweichung frueh im Arbeitsbaum,
  ohne auf CI zu warten. Er ist NICHT der Vertragsnachweis.
- Der VERTRAGSNACHWEIS ist scripts/contract/contract_ci.py (Cross-Repo):
  er liest die gepinnte SDK-Wertemenge per Klon UND erzwingt Byte-Gleichheit
  der Core-schemas/*.json gegen das SDK-Artefakt (§C.9). Der Bruch-Beweis
  (Repository A bricht, Repository B rot) steht dort, nicht hier.
- Die Wahrheitsquelle der Wertemenge ist das SDK-Schema; die Core-lokale
  schemas/-Datei ist ein ABGELEITETES Artefakt der gepinnten SDK-Version.
"""
from pathlib import Path
import json

import pytest

from skillweave.runtime.store import RunStateModel


def _repo_root() -> Path:
    # tests/unit/test_vocabulary_guard.py -> repo root (drei Ebenen hoch).
    # Bewusst pfad-unabhaengig: der Waechter darf nicht auf einem Rechner mit
    # hart verdrahteten Worktree-Pfaden gruen laufen und ueberall sonst nie
    # ausloesen (vgl. check-contract-drift.sh in elementeer-specs).
    return Path(__file__).resolve().parent.parent.parent


def _schema_state_enum() -> set:
    schema_path = _repo_root() / "schemas" / "run-state.schema.json"
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    return set(data["properties"]["state"]["enum"])


def _enum_state_values() -> set:
    return {s.value for s in RunStateModel}


class TestVocabularyGuard:
    def test_enum_and_schema_value_sets_are_identical(self):
        from_schema = _schema_state_enum()
        from_enum = _enum_state_values()
        missing_in_schema = from_enum - from_schema
        missing_in_enum = from_schema - from_enum
        assert missing_in_schema == set(), (
            f"Wer im Enum, aber nicht im Schema (Runtime schreibt Zustand, "
            f"den das Schema abweist): {sorted(missing_in_schema)}"
        )
        assert missing_in_enum == set(), (
            f"Wer im Schema, aber nicht im Enum (Schema akzeptiert Zustand, "
            f"den die Runtime nie schreibt): {sorted(missing_in_enum)}"
        )

    def test_stopped_before_b06_present_on_both_sides(self):
        # SW-SCOPE-005 Wertentscheidung: STOPPED_BEFORE_B06 ist legitim.
        assert "STOPPED_BEFORE_B06" in _schema_state_enum()
        assert RunStateModel.STOPPED_BEFORE_B06.value in _enum_state_values()

    def test_schema_is_not_empty(self):
        # Guard: ein leerer/fehlender enum-Block darf nicht still durchgehen.
        values = _schema_state_enum()
        assert len(values) >= 1
