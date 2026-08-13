# GLE-004 — Repo-Vierteilung: Cross-Repo-Contract

**Status:** Draft (Vertragsskizze, abgeleitet aus §2.2 des PRD)
**PRD:** `generic-lifecycle-extension/prd.md` §2.2 (Forgejo-only, `skillweave-planning`)
**Ratification:** SW-SCOPE-004 (Schemas UND Taxonomie gehören in `skillweave-sdk`)
**Basis:** `feature/GLE-004-repo-vierteilung` auf `eb79726` (= GLE-020-Head, nicht dev)

Dieses Dokument legt fest, was jedes der vier Repos **besitzt** und was es
**nur konsumiert**. Es ist die Vertragsautorität für den Schnitt. Es ist
**abgeleitet**, nicht erfunden: Ownership und Trennlinie stammen aus §2.2;
neu dazu kommt nur die CI-Strategie (§C), die §2.2 ausdrücklich nicht
enthält.

Wir schneiden **erst nach** diesem Vertrag. Ein Schnitt ohne festen Vertrag
erzeugt vier Repos, die sich gegenseitig blockieren — und das merkt man erst,
wenn das Zurückdrehen teuer ist.

---

## A. Ownership-Matrix (abgeleitet aus §2.2)

| Repo | Besitzt (Autorität) | Konsumiert (nur lesend) | Lizenz | Sichtbarkeit | GH-Mirror |
|---|---|---|---|---|---|
| `skillweave-sdk` | die 5 Kernschemas, Category Taxonomy Registry (IDs, Versionierung, Aliase, Deprecation), Validator, Test Harness, Doku-Generator | nichts — das SDK ist die Wurzel, hat keine Laufzeitabhängigkeit auf `skillweave` | Apache-2.0 | public | **ja** |
| `skillweave` | Runtime, 13 Skills, Kernel State Machine, Engine | SDK-Schemas + Taxonomie (gepinnt); Profile/Category-Packs nur als externer Inhalt, nie als Quellwahrheit | Apache-2.0 | public | **ja** |
| `skillweave-profiles` | die 9 Lifecycle Profiles, die 11 Category Packs (Defaults, Gates, Metrics), Golden Scenarios | SDK-Schemas + Taxonomie (gepinnt); `skillweave` Runtime (gepinnt, nur zum Testen der Profile) | Apache-2.0 | public | **ja** |
| `skillweave-packs-pro` | CMS Ops Pack und künftige providergebundene Packs | SDK-Schemas + Taxonomie (gepinnt); Runtime (gepinnt) | **proprietär** | **Forgejo-only** | **nein** |

### Trennlinie (begründet die Aufteilung)

- **`skillweave-sdk` besitzt den VERTRAG** — Schema und Vokabular, gegen das validiert wird.
- **`skillweave` besitzt die AUSFÜHRUNG** — Runtime, Engine, Kernel State Machine.
- **`skillweave-profiles` besitzt die MEINUNG** — was eine Kategorie standardmäßig impliziert. Das ist exakt die Ebene, die ein Whitelabel-Kunde ersetzen können muss.
- **`skillweave-packs-pro` besitzt COMMERCIAL OPINION** — providergebundene Packs, die einen unabhängig versionierten Provider für ihren Kernwert benötigen.

### Warum die Taxonomie ins SDK gehört (nicht in den Core) — SW-SCOPE-004

GLE-005 verlangt, dass ein externer Pack-Autor **ohne Core-Zugriff** ein
gültiges Pack bauen kann. Ein Validator, der `category:build` nicht auflösen
kann, validiert Struktur ohne Semantik — ein Pack mit erfundener Kategorie
ginge durch. Schema und Vokabular an getrennten Orten wären zwei Wahrheiten
mit Driftrisiko.

Konsequenz für den Schnitt (bereits beobachtet, hier benannt):

> Die Taxonomie liegt heute **doppelt** — als Code in
> `src/skillweave/runtime/schema/vocabulary.py` (`RunStateModel`-Enum als
> Vokabular-Quelle) und als `enum`-Literal in `schemas/run-state.schema.json`.
> Im Schnitt wandert beides ins SDK. Bis dahin bleibt die Doppelung eine
> bewusste Bruchlinie, nicht ein Fehler; sie darf nicht heimlich an **einem**
> Ort angeglichen werden, weil das die Drift in die andere Richtung zementiert.

---

## B. Consumer-Pinning

`skillweave-sdk` ist die Wurzel des Releasegraphen. Die drei anderen Repos
pinnen eine **explizite, versionierte** SDK-Fassung. Mitgegeben:

```
skillweave-sdk                (Wurzel, keine Abhängigkeit)
    ├── skillweave            pinnt sdk == X.Y.Z
    ├── skillweave-profiles   pinnt sdk == X.Y.Z  UND  runtime == A.B.C
    └── skillweave-packs-pro  pinnt sdk == X.Y.Z  UND  runtime == A.B.C
```

Konsequenz:

- `profiles` und `packs-pro` dürfen eine eigene SDK-Pin und eine eigene
  Runtime-Pin tragen; sie dürfen **unterschiedlich** sein, aber beide müssen
  **sichtbar und explizit** sein (keine verdeckten Defaults, vgl. PRD §3.2).
- Die Versionierungsmatrix ist **vierfach** (§2.2: "vierfache Versionsmatrix
  in der CI"). Der Preis ist akzeptiert; er ist der Gegenwert für einen
  Vertrag, den einer besitzt statt ihn vorzugeben.

---

## C. Cross-Repo-Contract-CI-Strategie

Dieser Teil kommt **nicht** aus §2.2. Er ist die eigentliche Arbeit von
GLE-004.

### C.1 Das Referenzmuster und seine dokumentierte Fehlerquelle

Das Muster existiert bereits mit `elementeer-specs`. Seine Fehlerquelle ist
**dokumentiert und war der Grund, warum es unvollständig blieb**:

`elementeer-specs/scripts/check-contract-drift.sh` verdrahtet die
Consumer-Worktree-Pfade **hart** (absolute Pfade eines einzelnen Rechners)
und läuft mit lokalem `rg`. Es ist ein **Ein-Maschinen-Drift-Check**, kein
Cross-Repo-CI-Gate. Es kann nie in einem fremden Repo rot werden, weil es
dort gar nicht läuft und die Pfade dort gar nicht existieren.

Deshalb steht die Nachweispflicht in GLE-004 als Akzeptanzkriterium und
nicht als Fußnote:

> Cross-Repo-Contract-CI ist erst belegt, wenn ein **absichtlich gebrochener**
> Contract in Repo A den Build in Repo B **rot** macht. Nicht, wenn die
> Pipeline grün ist. Ein Gate, das nie ausgelöst hat, ist ungeprüft.

### C.2 Architektur: Pull, nicht Push

Der SDK-Besitzer kontrolliert **keinen** Consumer. Der Contract ist nur dann
ein Vertrag statt einer Vorgabe, wenn der Gebrochene ihn pufft (pull) und
nicht der Besitzer ihn hinstellt (push).

Jeder Consumer (skillweave, profiles, packs-pro) trägt einen CI-Job, der
gegen die **gepinnte** SDK-Version validiert:

- Der Job rechnet aus, welche SDK-Fassung der Consumer gepinnt hat.
- Er lädt **genau diese** Fassung als Artefakt (nicht `main`, nicht `latest`).
- Er validiert die eigenen Inhalte (Profile, Packs, Engine-Schemas) gegen
  die Schemas + Taxonomie dieser Fassung.

So bricht ein Contract in einem Repo **den Build des anderen**, ohne dass
irgendein Repo Kenntnis von der Pfadlage eines anderen Rechners braucht.

### C.3 Die Versionsmatrix (maschinenlesbar)

Jedes Repo führt eine Maschinenkennung seines Vertrags als Datei:

```
skillweave-sdk:               sdk/schema_version.toml   ->  version = "1.0.0"
skillweave:                   .contract/consumer.toml   ->  sdk = "1.0.0"
skillweave-profiles:          .contract/consumer.toml   ->  sdk = "1.0.0"; runtime = "..."
skillweave-packs-pro:         .contract/consumer.toml   ->  sdk = "1.0.0"; runtime = "..."
```

Der Releasegraph ist maschinenlesbar und weist das SDK als Wurzel aus
(Akzeptanzkriterium "Releasegraph ist maschinenlesbar und weist das SDK als
Wurzel aus"). Der CI-Job liest diese Datei — derselbe Mechanismus in allen
vier Repos.

### C.4 Trigger-Domäne: welcher Bruch macht wo rot

| Bruch in … | betrifft … | Rot wird … |
|---|---|---|
| `sdk` entfernt/umbenamt eine Kategorie | jeden Pack/Profil, der sie referenziert | `profiles`, `packs-pro` (und `skillweave`, sofern es die Taxonomie konsumiert) |
| `sdk` ändert ein Kernschema breaking | jeden Consumer, der es validiert | alle drei Consumer |
| `profiles` erfindet eine Kategorie, die nicht im SDK steht | semantische Validierung | eigene CI (Validator weist ab) + `packs-pro`/`skillweave`, falls sie das Profil ziehen |
| `packs-pro`-Inhalt gelangt in ein public Repo | Open-Core-Grenze | Vorkehrung in C.5 |

**Nachweispflicht (aus dem Ticket):** Der **eine** Beleg ist: eine Kategorie
oder ein Schema wird im SDK absichtlich gebrochen, und der Build in
`skillweave-profiles` wird rot. Der Gegenbeweis (grünes Gate ohne je
getriggert zu haben) zählt nicht.

### C.5 Open-Core-Grenze: kein Pro-Pack-Inhalt in public Repos

`skillweave-packs-pro` bekommt **keinen** GitHub-Mirror — das ist die
Open-Core-Grenze und kein Versehen. Steht ausdrücklich hier, nicht nur im
PRD. Vorkehrung:

- Das Mirror-Workflow in `skillweave`/`sdk`/`profiles` spricht **nur** das
  jeweilige eigene Repo an und hat keine Pflicht auf ein `packs-pro`-Remote.
- `packs-pro` besitzt einen eigenständigen CI-Job, der **fehlschlägt**, wenn
  sein Inhalt gegen die SDK-Schemas **plus** einen erfundenen Provider-Pin
  validiert, der in einem public Repo landen würde. Konkret: ein
  provider-gebundener Pack darf nur gegen eine gepinnte Provider-Fassung
  validieren, die es im public SDK gar nicht gibt; taucht ein solcher Pack in
  einem public Repo auf, ist das bereits strukturell ein Drift.

---

## D. Schnittfolge (was jetzt NICHT getan wird)

Dieser Vertrag etabliert die Grenzen. Er führt den Schnitt **nicht** aus.

1. Vertrag steht (dieses Dokument) → Review gegen §2.2.
2. SDK-Reposkelett mit Schemas + Taxonomie wandert (GLE-001 + GLE-003
   zusammen; GLE-004 hängt ausdrücklich an beiden).
3. Versionsmatrix CI in allen vier Repos; der **Bruch-Beweis** (C.4) wird
   als negativer Test angelegt, bevor irgendein Inhalt migriert.
4. Migration der Inhalte entlang der Ownership-Matrix.

**Was nie getan wird:** Merge nach `dev`/`main`, Self-Approval, direkter
Push auf den `github`-Remote. Das Planning-Repo `skillweave-planning` ist
Forgejo-only und wird nicht gespiegelt; dorthin gehören PRDs — dieses Repo
ist public und nach GitHub gespiegelt.

---

## E. Basis-Abhängigkeit (benannt, nicht verschwiegen)

GLE-020 ist die ausdrückliche Vorbedingung (§3.8). Dieser Branch steht auf
`eb79726` (= GLE-020-Head), nicht auf `dev`. Die Ownership-Matrix und die
CI-Strategie hängen an **keiner** bestimmten Fassung der Lazy-Import-Lösung;
sie gelten unabhängig davon, **wie** der Kern teilinstallierbar wird.

- Fällt der GLE-020-Review als BLOCKER aus, ändert sich die Grundlage; die
  Einbettbarkeit als solche („Consumer bettet Engine ohne Profile ein",
  DoD 11) steht und fällt mit GLE-020.
- Sobald GLE-020 in `dev` ist, rebased dieser Branch **sofort** auf `dev`
  — nicht am Ende.
