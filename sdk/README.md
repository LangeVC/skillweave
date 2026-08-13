# skillweave-sdk

Vertragsautorität für SkillWeave: die Kernschemas und die Taxonomie-Wertemenge,
gegen die jeder Consumer validiert.

**Kein Laufzeitcode. Keine Produktlogik.** Dieses Repo ist die Wurzel des
Releasegraphen und hat keine Laufzeitabhängigkeit auf `skillweave`.

Forgejo ist kanonisch; GitHub ist der read-only Mirror.

## Inhalt

| Pfad | Zweck |
|---|---|
| `schemas/` | Die Kernschemas (JSON Schema Draft 2020-12) |
| `contract/` | Maschinenlesbare Wertemengen-Auszüge, gegen die ein Consumer ohne Python-Kontext validieren kann |
| `schema_version.toml` | Wurzel des Releasegraphen; Consumer pinnen eine Version hieraus |

## Die Trennlinie

Dieses SDK besitzt den **Vertrag** — die autoritative **Wertemenge** von Schema
und Vokabular, nicht jede Codezeile, die sie berührt.

```
skillweave-sdk   besitzt den VERTRAG     (Schemas, Taxonomie-Wertemenge)
skillweave       besitzt die AUSFÜHRUNG  (Runtime, Kernel, Engine)
skillweave-profiles  besitzt die MEINUNG (Profile, Category Packs)
skillweave-packs-pro besitzt COMMERCIAL OPINION (providergebunden)
```

Konkret am Statusvokabular: `run-state.schema.json#/properties/state/enum`
trägt die Wertemenge. Der Core trägt `RunStateModel` (Member-Namen) und
`legal_transitions` (Ausführungssemantik). Ein Validator braucht nur die
Wertemenge — das ist das Argument dafür, dass ein externer Pack-Autor ohne
Core-Zugriff validieren kann (GLE-005).

## Versionierung

`schema_version.toml` → `schema.version`. Breaking-Change → Major, additiv →
Minor. Ein Consumer pinnt eine exakte Version und validiert dagegen; er
referenziert nie „latest".

## Cross-Repo-Contract-CI

Consumer halten einen Wächter, der ihre Wertemengen gegen die gepinnte
SDK-Fassung vergleicht. Wird ein Contract hier gebrochen, wird der Build des
Consumers rot. Der Nachweis ist erst erbracht, wenn ein absichtlich gebrochener
Contract den Build im anderen Repo rot macht — nicht wenn die Pipeline grün ist.
