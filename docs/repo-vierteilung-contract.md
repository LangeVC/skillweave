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

### Was „SDK besitzt Taxonomie" präzise heißt

PRD §2.2 sagt „SDK besitzt Schemas UND Taxonomie". Wer das wörtlich liest,
liest „jede Codezeile, die das Vokabular berührt, liegt im SDK" — und stößt
beim Schnitt auf `RunStateModel`, das zweierlei trägt:

- **Wertemenge** (welche Zustände existieren) — das ist Vokabular und gehört
  ins SDK. Das Schema (`run-state.schema.json` → `properties.state.enum`)
  trägt sie.
- **Ausführungssemantik** (`legal_transitions` — welcher Zustand darf auf
  welchen folgen) — das ist Kernel-Logik und gehört zum Core, nicht zum
  Vertrag.

„SDK besitzt Taxonomie" heißt daher: das SDK besitzt die **autoritative
Wertemenge**, nicht jede Codezeile, die sie berührt. Der Core besitzt Struktur
(`RunStateModel` mit Member-Namen) und Semantik (`legal_transitions`). Wäre
`RunStateModel` vollständig ins SDK gewandert, trüge das SDK entweder
Ausführungslogik oder die Klasse müsste aufgespalten werden, sodass Member und
Übergänge in verschiedenen Repos liegen — beides schlechter als die Trennung
entlang der Bedeutung.

**GLE-005 bleibt erfüllt:** Ein externer Pack-Autor braucht keinen
Core-Zugriff. Der Validator muss eine Kategoriereferenz auflösen können, und
dafür genügt die Wertemenge, die das Schema im SDK trägt. Er braucht weder
`RunStateModel` noch `legal_transitions`. Das ist das eigentliche Argument:
der Vertrag ist die Wertemenge, nicht ihre Implementierung.

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

### B.1 Erstversion 0.1.0 — Versionierung vor dem Schnitt (entschieden)

Die SDK-Version ist **0.1.0, nicht 1.0.0**. Begründung, die nicht aus dem
PRD-Text, sondern aus dem Umfang dieses Schnitts folgt (§D):

Ein angelegtes, eben befülltes Repo ist **Struktur, kein vollzogener Schnitt**.
Der Inhalt, der `1.0.0` rechtfertigen würde, fehlt noch:

- Die fünf GLE-001-Schemas sind nicht enthalten.
- `profiles` und `packs-pro` sind leer (füllen GLE-007/008).
- Der Core trägt die Schema-Kopie noch nicht ab (Dateivorzug steht aus).

`1.0.0` behauptet Stabilität, die der Vertrag nicht hat. Er kommt, wenn die
Vierteilung **inhaltlich** vollzogen ist — dasselbe Kriterium, das das PRD
für „Schnitt" gegenüber „angelegtem leeren Repo" anlegt.

Konsequenz fürs Pinning: Consumer pinnen auf den **echten** Tag `v0.1.0`.
Kein Pin darf eine Versionsnummer referenzieren, für die kein Tag existiert
(das wäre ein unauflösbarer Verweis und der Wächter liefe ins Leere).

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

Nicht zulässig ist die doppelte Wahrheit, die C.1 beim Referenzmuster als
Fehlerquelle dokumentiert: eine **eingecheckte `sdk/`-Kopie im Consumer**, die
der Wächter der gepinnten Fassung vorzieht. Das wäre `check-contract-drift.sh`
über Repo-Grenzen hinweg neu aufgebaut — die Kopie läge neben dem Code, der
sie nutzt, und meldete grün, während das echte SDK auseinanderläuft. Das ist
dieselbe Drift-Lage wie SW-SCOPE-005 (Schema und Enum doppelt), nur über
Repo-Grenzen. Eine eingecheckte Kopie wird gegen nichts verifiziert.

Erlaubt ist nur der **Cache**: ein lokales Verzeichnis, das gegen die
Pin-Prüfsumme verifiziert und bei Abweichung neu geholt wird. Der Cache ist
Ergonomie (lokaler Build ohne Netz), nie die Wahrheitsquelle; er ist Opt-in
über eine Umgebungsvariable und niemals eingecheckt.

Der Contract-Wächter liest die Core-Wertemenge **importfrei** (statisch aus
dem Quelltext, nicht per `import skillweave`). Begründung: er prüft eine
**Deklaration**, kein lauffähiges System, und darf nicht an dessen
Installierbarkeit hängen. Ein Wächter, der ausfällt, weil eine Engine-
Abhängigkeit fehlt, meldet etwas über die Installation, nicht über den
Vertrag — das ist nach dem Schnitt für jeden Consumer die falsche
Fehlerklasse (und arbeitet gegen die GLE-020-Entkopplung des Kerns).

### C.3 Die Versionsmatrix (maschinenlesbar)

Jedes Repo führt eine Maschinenkennung seines Vertrags als Datei:

```
skillweave-sdk:               sdk/schema_version.toml   ->  version = "0.1.0"
skillweave:                   .contract/consumer.toml   ->  sdk = "0.1.0"
skillweave-profiles:          .contract/consumer.toml   ->  sdk = "0.1.0"; runtime = "..."
skillweave-packs-pro:         .contract/consumer.toml   ->  sdk = "0.1.0"; runtime = "..."
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

### C.7 Konkrete Implementierung — erster Contract (run-state)

Der erste echte Contract, den §C mechanisch trägt, ist gemessen, nicht
konstruiert: `run-state.schema.json` (Wertemenge, SDK) gegen `RunStateModel`
(Core). Der SW-SCOPE-005-Wächter (`tests/unit/test_vocabulary_guard.py`)
vergleicht die Mengen und wird in beide Richtungen rot. Beim Schnitt ändert
sich genau eine Sache: die Quelle der Schema-Datei.

- **Heute (ein Repo):** der Wächter lädt `schemas/run-state.schema.json` aus
  dem eigenen Repo.
- **Nach dem Schnitt:** der Wächter im Core lädt dieselbe Datei als gepinntes
  SDK-Artefakt (§B), nicht aus dem eigenen Baum. Der Mengenvergleich bleibt
  identisch.

Mechanik (Pull, §C.2), konkret:

1. `skillweave-sdk` trägt `schemas/` (4 Kernschemas) + `schema_version.toml`
   (Wurzel des Releasegraphen, maschinenlesbar) + eine `contract/`-Darstellung
   der `enum`-Wertemengen, gegen die ein Consumer ohne Python-Kontext
   validieren kann.
2. `skillweave` trägt `.contract/consumer.toml` mit `sdk = <gepinnt>`. Der
   Contract-CI-Job im Core liest die Pin, lädt das SDK-Artefakt, und führt den
   Wächter aus — jetzt gegen die SDK-`enum`, nicht gegen die lokale Datei.
3. **Bruch-Beweis (§C.4):** im SDK wird `STOPPED_BEFORE_B06` aus
   `run-state.schema.json` entfernt (vertragswidrige Verkürzung) → der
   Contract-CI-Lauf im Core wird rot. Das ist der Nachweis „absichtlich
   gebrochener Contract in Repo A macht Build in Repo B rot", nicht „Pipeline
   grün".

`profiles` und `packs-pro` erhalten **noch keine** Contract-CI-Logik: sie
haben keinen Inhalt, gegen den sie validieren könnten (§D). Ihre Struktur
(schema_version/consumer.toml) wird erst beim Füllen über GLE-007 registriert.
Ein leeres Repo kann keinen Contract brechen.

### C.8 SDK-Dispatcher — wann der Consumer-Build überhaupt läuft

Eine Contract-CI, die nur auf den Consumer-Push triggert, ist im Cross-Repo-
Sinn **nicht vorhanden**: ändert sich das SDK, ändert sich der Consumer nicht,
also läuft kein Job, also wird nichts rot. Das ist der Unterschied zwischen
„ungeprüft" und „nicht vorhanden" (siehe C.1 und die zweite Wahrheit aus
SW-SCOPE-005).

Der Consumer kann nicht wissen, wann der SDK-Besitzer etwas ändert. Also pollt
er **deterministisch**: der Contract-CI-Job läuft zusätzlich periodisch
(Schedule) und bei Bedarf manuell (workflow_dispatch). Damit ist der Lauf
garantiert, nicht von einem Ereignis abhängig, das jemand anstoßen muss.

Bewusst kein `repository_dispatch`/Cross-Repo-Webhook: Forgejo ist kanonisch
und der Consumer-Build läuft auf GitHub. Ein Forgejo→GitHub-Ereignisbrückenbau
wäre eine eigene Fehlerquelle (Token, Secrets, unsichtbarer Ausfall) — genau
die Klasse, die §C.1 beim Referenzmuster dokumentiert. Der Schedule ist der
ehrliche Poll: begrenzte Erkennungsverzögerung, dafür keinen neuen Ausfallpfad.

Konsequenz für den Bruch-Beweis: der Nachweis wird über `workflow_dispatch`
sofort demonstriert (nicht auf den Cron gewartet), der automatisierte Dauer-
Wächter ist der Schedule. Beides läuft gegen das gepinnte Artefakt, nie gegen
eine eingecheckte Kopie.

### C.9 Übergangszustand — Core-lokale `schemas/` ist abgeleitet, nicht Quelle

Während GLE-004 existiert im Core noch ein `schemas/`-Verzeichnis. Ab jetzt
ist dessen Status festgelegt: **abgeleitetes Artefakt, nicht Quelle.** Der
Unterschied in einem Satz: eine geprüfte Kopie ist ein Spiegel, eine nur
dokumentierte Kopie ist eine zweite Wahrheit.

Die Wahrheit ist ausschließlich das SDK-Artefakt (§B, §C.2). Die Core-lokale
`schemas/*.json` bleibt, weil die Engine sie zur Laufzeit lädt und deren Umzug
auf das SDK-Artefakt GLE-001-Territorium ist (Scope-Grenze, PRD legt für diesen
Schnitt nur die vier Kernschemas + Taxonomie-Wertemenge fest). Aber sie wird
durchgesetzt:

- Der Contract-Wächter prüft **Byte-Gleichheit** zwischen jeder
  Core-`schemas/*.json` und derselben Datei im gepinnten SDK-Artefakt. Das ist
  **blockierend**, nicht ein lokaler Vorfilter. Weicht ein Byte ab, wird der
  Build rot.
- Bevorzugt wäre **erzeugen statt einchecken** (beim Build aus dem gepinnten
  SDK kopieren, wie beim `enum`-Extrakt in C.7) — dann bräuchte es gar keinen
  Gleichheits-Wächter. Solange das nicht steht, gilt der Byte-Gleichheits-Test
  als Durchsetzung.

Der Übergang ist **befristet** und endet mit GLE-001 (Schema-Import in den
Core). Danach lädt die Runtime aus dem SDK-Artefakt, und die lokale Kopie
entfällt. Ein „vorläufig" ohne Frist wäre dauerhaft und ist deshalb hier
ausgeschlossen.

---

## D. Umfang dieses Schnitts (ehrlich bemessen)

Dieser Schnitt trennt nur, was heute **existiert**: die vier bestehenden
Kernschemas und die Taxonomie-Wertemenge. Er erfindet keinen Inhalt für Dinge,
die noch nicht gebaut sind.

**Faktische Folge: Es entstehen zwei befüllte Repos, nicht vier.**

| Repo | Zustand nach diesem Schnitt |
|---|---|
| `skillweave-sdk` | **befüllt** — die 4 Kernschemas + `schema_version.toml` + Contract-CI-Skelett |
| `skillweave` | **befüllt** (bleibt Kern) — Runtime, Skills, Kernel; konsumiert SDK-Wertemenge über den Wächter |
| `skillweave-profiles` | **leer, deklariert** — bis GLE-007 (11 Packs) und GLE-008/009 (Profil) Inhalt liefern |
| `skillweave-packs-pro` | **leer, deklariert** — bis der CMS-Ops-Pack gebaut wird |

Das ist **kein** „Vierteilung vollzogen". Es ist der Schnitt **erst auf der
Achse, die heute Inhalt hat** (Vertrag ↔ Ausführung). Die „Meinung"- und
„Commercial"-Repos sind angelegt und deklariert, aber leer. Ein angelegtes
leeres Repo ist Struktur, kein Schnitt — hier ausdrücklich, damit niemand
später zwei leere Hüllen für vollzogene Teilung hält.

Die Contract-CI (Nachweispflicht) braucht echten Inhalt, um beweisbar zu sein:
Der Nachweis „gebrochener Contract in Repo A macht Build in Repo B rot" ist
mit leeren Repos nicht herstellbar. Der erste echte Contract ist bereits
gemessen (nicht konstruiert): `run-state.schema.json` (SDK) gegen
`RunStateModel` (Core), mit dem Wächter aus SW-SCOPE-005, der in beide
Richtungen rot wird. Genau dieser Fall wird die erste Cross-Repo-CI tragen.

**Reihenfolge bleibt:** Vertrag (§A–§F) → Vorbedingungen (erfüllt) →
CI-Mechanik (§C-Implementierung, inkl. Bruch-Beweis) → **zuletzt** der erste
SDK-Push. Der Push ist der Schlusspunkt, nicht der Anfang: Läge der erste
SDK-Commit vor der Contract-CI, gäbe es einen Zeitraum ohne Wächter — und
genau in dem entsteht die Drift, gegen die all das gebaut wird.

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

### E.2 SW-SCOPE-005 — Taxonomie-Drift (Wert entschieden, Richtung siehe §F)

`SW-SCOPE-005` hält fest: Das Statusvokabular liegt doppelt und ist bereits
auseinandergelaufen (§A). Zwei Fragen trennen sich hier:

- **Wertfrage** (entschieden durch den Operator, nicht durch den Schneidenden):
  `STOPPED_BEFORE_B06` ist **legitim** und kommt ins Schema. Grund: Es hat eine
  Übergangsregel (`store.py:48`, nach `IN_PROGRESS`) und einen Test
  (`test_review_fixes.py:247`); ein Überbleibsel hat beides nicht.
- **Richtungsfrage** (gehört dem Schneidenden als Vertragsfrage): Welche Seite
  ist Quelle, und wie wandert eine Quelländerung zur anderen Seite? Sie wird in
  §F beantwortet — sie zwingt den Vertrag, seinen ersten echten Anwendungsfall
  zu tragen.

Solange beide Orte in **einem** Repo liegen, ist die Angleichung ein Commit und
der Wächter ein Unit-Test. Nach der Vierteilung wird daraus eine Cross-Repo-CI
zwischen `skillweave-sdk` und `skillweave`. Deshalb gehört SW-SCOPE-005 **vor**
den Schnitt — dieselbe Arbeit, in einem Repo billig, in vieren teuer.

### E.3 Rebase-Verpflichtung

Dieser Branch ist auf `origin/dev` (`738a1f2`) rebased. Weitere Rebase-Punkte
folgen, sobald sich `dev` gegenüber der aktuellen Basis bewegt — sofort, nicht
am Ende. Solange SW-SCOPE-005 offen bleibt, steht dieser Vertrag, aber der
Schnitt beginnt erst nach seiner Entscheidung.

---

## F. Richtungsentscheidung — erster Anwendungsfall des Vertrags

SW-SCOPE-005 wirft eine Vertragsfrage auf, die §B (Consumer-Pinning) und §C
(Pull statt Push) implizit beantworten, aber noch nie an einem konkreten
Datenpunkt. Dieser Abschnitt beantwortet sie und prüft dabei, ob §C trägt.

### F.1 Der Datenpunkt

```
src/skillweave/runtime/store.py                    class RunStateModel(str, Enum)   16 Werte
src/skillweave/execution/state_machine.py          class RalphLoopState(str, Enum)  9 Werte  (Teilmenge)
schemas/run-state.schema.json                      properties.state.enum            15 Werte
```

Drei Dinge, nicht zwei. `RalphLoopState` ist die Obermenge der neun
softwaretypischen Zustände; `RunStateModel` erweitert sie um Runtime- und
Sandbox-Zustände. `vocabulary.py` leitet das gültige Statusvokabular aus
`RunStateModel` ab (`{s.value for s in RunStateModel}`); das Schema liest
niemand.

### F.2 Die Feststellung, die §B/§C allein nicht tragen

§B/§C sagen: „SDK besitzt Schemas, Consumer pinnt eine Version und validiert
dagegen." Das trägt für **Wertemengen**: ein Pack referenziert `category:build`,
der Validator löst sie gegen die gepinnte Taxonomie auf. Trägt es auch für
**Code-Strukturen**, deren Member eine Semantik tragen?

`RunStateModel` ist ein `str, Enum`, dessen **Member-Namen** API sind:
`legal_transitions` referenziert `cls.PREFLIGHT`, `cls.IN_PROGRESS`;
hundert Aufrufstellen schreiben `RunStateModel.IN_PROGRESS.value`. Ein
JSON-Schema `enum` liefert nur Strings — keine Member-Namen, keine
Übergangsregeln. Ein Generator, der aus dem Schema ein Enum baut, verlöre die
Member-Namen oder müsste sie erfinden.

Befund am Vertrag: **§B/§C müssen präzisiert werden.** „Consumer generiert aus
dem Schema" gilt für Wertemengen und Datenträger, nicht für typisierte
Runtime-Strukturen mit Member-Semantik. Beide Formen existieren, und der
Vertrag muss sie unterscheiden:

- **Kanonische Vokabular-Werte** (Statusnamen, Kategorien): Das SDK besitzt die
  Wertemenge; der Consumer validiert gegen die gepinnte Fassung und hält sie
  durch einen Abweichungswächter deckungsgleich.
- **Typisierte Runtime-Strukturen** (Enum mit Member-Namen, Übergangsregeln):
  bleiben Code-Struktur im Consumer. Das SDK besitzt den **Vertrag über die
  Wertemenge**, nicht den Syntaxbaum der Member.

### F.3 Die gewählte Richtung (vor dem Schnitt, in einem Repo)

**Das Schema ist die kanonische Quelle der Wertemenge (`enum`). Das Enum bleibt
die Code-Struktur. Ein Wächter-Test erzwingt Gleichheit — und zwar in beide
Richtungen, indem er die Mengen vergleicht, nicht eine Richtung festnagelt.**

Begründung gegen „Enum aus Schema generieren zur Bauzeit":

- Der Generator müsste die Member-Namen ableiten, die im Schema nicht stehen.
  Member-Namen sind API, keine Daten; sie gehören zu `legal_transitions` und
  den Aufrufern, nicht zur Wertemenge.
- Ein Buildzeit-Generator verschiebt die Drift in das Generator-Skript selbst —
  dieselbe Art vermeintlicher Vollständigkeit wie `check-contract-drift.sh`
  (§C.1), nur lokal.
- Ein Mengenvergleich ist der kleinste Wächter, der die eingetretene Drift
  (16 vs. 15) fängt, ohne die Member-Semantik anzugreifen.

Konkret:

1. `schemas/run-state.schema.json` bekommt `STOPPED_BEFORE_B06` (Operator hat
   entschieden: legitim). Damit sind Schema und Enum wertgleich (16 = 16).
2. Ein Wächter-Test lädt `run-state.schema.json`, liest `properties.state.enum`,
   vergleicht mit `{s.value for s in RunStateModel}`. Rot bei Differenz.
3. Nachweis **hergestellt** (nicht simuliert): ein Wert wird auf einer Seite
   hinzugefügt, der Test wird rot — der Test wird für diesen Beweis einmal
   absichtlich gebrochen und die Rötung dokumentiert, dann zurückgedreht.

### F.4 Was daraus nach dem Schnitt wird

Nach §A wandert das Schema ins SDK, `RunStateModel` bleibt im Consumer
`skillweave`. Aus dem Unit-Test wird eine Contract-CI: der Consumer pinnt die
SDK-Schemaversion (§B) und hält sein Enum gegen die `enum`-Wertemenge der
gepinnten Fassung deckungsgleich. Der Mengenvergleich bleibt derselbe; nur die
Quelle des Schemas wechselt von „Datei im eigenen Repo" auf „gepinntes
Artefakt vom SDK".

Das ist der Übergang, vor dem SW-SCOPE-005 warnt: billig hier, teuer da. §C.2
(Pull statt Push) trägt ihn — der Consumer zieht die gepinnte SDK-Fassung und
vergleicht; kein Repo kennt die Pfadlage eines anderen.

### F.5 Was hier NICHT getan wird

- `RalphLoopState` (zweites Enum, Teilmenge) wird nicht angefasst. Es ist eine
  eigene, unabhängige Duplikation und ein eigener Befund, kein Teil von
  SW-SCOPE-005. Es wird benannt, nicht eigenmächtig vereinheitlicht.
- Die Member-Semantik (Übergangsregeln, Aufrufer) wird nicht aus dem Schema
  herauserzwungen. Das wäre ein Vorgriff auf GLE-002 (Kernel State Machine) und
  gehört in den Schnitt, nicht in die Vorbedingung.

### F.6 Bewertung: Scheitert §C am ersten Anwendungsfall?

Nein, aber §C musste präzisiert werden. Der Vertrag unterschied bisher nicht
zwischen „Wertemenge im SDK" und „typisierter Structure im Consumer". Der
Statusvokabular-Fall legt offen, dass §B/§C stillschweigend ersteres meinten.
Mit der Unterscheidung in F.2 trägt §C den Fall: Pull einer gepinnten
SDK-Version, Mengenvergleich als Wächter, Rot bei Drift. Der Vertrag ist am
ersten Anwendungsfall korrigiert, nicht widerlegt.
