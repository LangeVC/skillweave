# GLE-004 — Repo-Vierteilung: Cross-Repo-Contract

**Status:** Draft (Vertragsskizze, abgeleitet aus §2.2 des PRD)
**PRD:** `generic-lifecycle-extension/prd.md` §2.2 (Forgejo-only, `skillweave-planning`)
**Ratification:** SW-SCOPE-004 (Schemas UND Taxonomie gehören in `skillweave-sdk`) — `done`, in PRD §2.2 eingearbeitet
**Basis:** `feature/GLE-004-repo-vierteilung` auf `738a1f2` (= `origin/dev`, GLE-020 gemergt)
**Vorbedingungen:** GLE-020 (gemergt) · SW-SCOPE-005 (offen, siehe §E)

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

Die vier Repos existieren bereits auf Forgejo und GitHub (durch SW-SCOPE-004
angelegt), sind aber inhaltlich leer. Der Schnitt füllt sie, er erzeugt sie
nicht.

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

SW-SCOPE-004 ist **nicht** eine plausible Vorsichtsmaßnahme, sondern die
Reaktion auf einen bereits eingetretenen Fall. Das Driftrisiko, das §2.2 als
Begründung anführt, war beim Entwurf des PRD keine Prophezeiung mehr — es war
real, innerhalb eines Repos, vor jeder Teilung. Nachgemessen (SW-SCOPE-005):

> Das Statusvokabular liegt doppelt — `store.py:12` (`RunStateModel`, 16
> Werte) und `schemas/run-state.schema.json` (`properties.state.enum`, 15
> Werte). Sie sind **auseinandergelaufen**: `STOPPED_BEFORE_B06` existiert nur
> im Code, hat eine Übergangsregel (`store.py:48`) und einen Test
> (`test_review_fixes.py:247`), fehlt aber im Schema. Die Runtime kann einen
> Zustand schreiben, den das Schema abweist; `vocabulary.py` leitet die
> Schreib-Validierung aus dem Enum ab, nicht aus dem Schema — die beiden sind
> strukturell entkoppelt.

Dieser Befund schützt SW-SCOPE-004 gegen spätere Relativierung: Wer die
Taxonomie wieder in den Core ziehen will, argumentiert gegen einen belegten,
nicht nur behaupteten, Driftfall.

Der Befund selbst ist **SW-SCOPE-005** und kein Teil dieses Schnitt-Tasks.
Welcher Wert gilt (`STOPPED_BEFORE_B06` legitim oder Überbleibsel),
entscheidet nicht, wer schneidet — siehe §E.

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

### C.5 Open-Core-Grenze

Die technische Grenze steht hier: `skillweave-packs-pro` bekommt **keinen**
GitHub-Mirror. Sie ist kein Versehen und bleibt Teil des public-Vertrags,
weil sie der Spiegel-Mechanik eine harte Regel gibt.

Die **Begründung** — welche Packs proprietär sind und warum der CMS-Ops-Pack
kein OSS-Profil ist — gehört nicht hierher. Sie ist Planungsinhalt und liegt
im Planning-Repo (Forgejo-only, nicht gespiegelt): PRD §2.3 „Open-Core-Grenze".
Dieser Vertrag verweist darauf, statt die proprietäre Begründung in ein
public Repo zu duplizieren.

Vorkehrung (technisch, hier beheimatet):

- Das Mirror-Workflow in `skillweave`/`sdk`/`profiles` spricht **nur** das
  jeweilige eigene Repo an und hat keine Pflicht auf ein `packs-pro`-Remote.
- `packs-pro` besitzt einen eigenständigen CI-Job, der **fehlschlägt**, wenn
  sein Inhalt gegen die SDK-Schemas **plus** einen erfundenen Provider-Pin
  validiert, der in einem public Repo landen würde. Konkret: ein
  provider-gebundener Pack darf nur gegen eine gepinnte Provider-Fassung
  validieren, die es im public SDK gar nicht gibt; taucht ein solcher Pack in
  einem public Repo auf, ist das bereits strukturell ein Drift.

### C.6 Veröffentlichungs-Mechanik (explizit entschieden)

Ownership-Matrix und Contract-CI-Strategie sind technische Dokumentation und
dürfen public. Sie liegen in diesem Repo, das nach GitHub gespiegelt wird. Die
Open-Core-Begründung dagegen bleibt im Planning-Repo. Die Trennung ist
**verweisend, nicht duplizierend**: dieser Vertrag nennt die Grenze und
referenziert PRD §2.3 für das Warum. Ein Duplikat der Begründung im
public-Vertrag wäre eine zweite Wahrheit mit demselben Driftrisiko, gegen das
SW-SCOPE-004 die Taxonomie schützt.

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

## E. Vorbedingungen (benannt, nicht verschwiegen)

### E.1 GLE-020 — Importgraph-Entkopplung (erfüllt, gemergt)

GLE-020 ist in `dev` gemergt. Der Kern ist ohne `runtime/` importierbar;
`OPTIONAL_SUBPACKAGES = ("runtime",)` steht ausdrücklich in
`src/skillweave/__init__.py`. Die Vorbedingung des Schnitts ist echt, nicht
mehr Kandidat. `hasattr(skillweave, "execution")` ist jetzt `False` — die
Eager-Bindungen der Submodulnamen sind entfallen. Dieser Vertrag nimmt **keine**
Attributketten auf Submodul-Ebene an; er bewegt sich auf Repo-/Paket- und
Schema-/Taxonomie-Ebene und ist davon nicht betroffen.

### E.2 SW-SCOPE-005 — Taxonomie-Drift (offen, VOR dem Schnitt)

`SW-SCOPE-005` (Status backlog, P1, Forgejo-only) hält fest: Das
Statusvokabular liegt doppelt und ist bereits auseinandergelaufen (§A). Es
ist **Vorbedingung**, kein Teil von GLE-004. Handel:

- Solange beides in **einem** Repo liegt, ist die Angleichung ein Commit und
  der Wächter ein Unit-Test. Nach der Vierteilung wird daraus eine
  Cross-Repo-CI zwischen `skillweave-sdk` und `skillweave` — dieselbe Arbeit,
  mit erheblich mehr Aufwand.
- **Es ist nicht mein Task.** Welcher Wert gilt (`STOPPED_BEFORE_B06` legitim
  oder Überbleibsel), entscheidet nicht, wer schneidet. Der Befund ist
  benannt, dokumentiert, nicht eigenmächtig angeglichen.
- Falls ich den Wächter mit vorbereite, gilt derselbe Nachweismaßstab wie für
  die Contract-CI: einen Wert auf einer Seite hinzufügen, der Test wird rot —
  nicht „der Test läuft grün".

### E.3 Rebase-Verpflichtung

Dieser Branch ist auf `origin/dev` (`738a1f2`) rebased. Weitere Rebase-Punkte
folgen, sobald sich `dev` gegenüber der aktuellen Basis bewegt — sofort, nicht
am Ende. Solange SW-SCOPE-005 offen bleibt, steht dieser Vertrag, aber der
Schnitt beginnt erst nach seiner Entscheidung.
