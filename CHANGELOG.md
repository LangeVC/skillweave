# Changelog

## 1.3.13 — Dynamic Routing and Anti-Masking

- **Dynamic Routing Policy Engine:** Added support for capability-based routing and scoring (DR-002, DR-004).
- **Anti-Masking:** Faigate adapter now parses `served_by` headers to detect and flag silent fallbacks (DR-003).
- **Council Deduplication:** The council engine drops duplicated models and triggers the Routing Policy Engine for dynamic replacement (DR-005, DR-006).

## 1.3.12 — Forgejo-first release provenance

1.3.11 shipped with an ambiguity at the release seam: the visible GitHub release
object was created by a GitHub-side workflow, not delivered by the mirror from
the Forgejo canonical. This release resolves that ambiguity before the release
line is cut again.

### Release artifact policy

The release line follows one artifact policy across three surfaces, and every
future release is verified against it by the Forgejo-first release contract:

- **Runtime** — `pyproject.toml` carries the one runtime version; it is the
  declared `source_of_truth` and the version a release tag derives from.
- **Bundle** — `capability.yaml` carries the same version as the runtime; its
  member `capabilities[]` pins are a manifest, not a separate version line.
- **Skill capabilities** — each `skills/skillweave-*/capability.yaml` carries
  the same version as the runtime under the lockstep policy.

A release is one immutable commit: the Forgejo release object, the canonical tag
target, the GitHub mirror tag and the distribution receipt must all refer to the
same commit. Zero Forgejo release objects, or more than one, fail the contract.

### Release path reconciled with the org model

- A single release-object producer remains: the ops-engine `ReleaseHandler` on
  Forgejo `tag_push`. No SkillWeave GitHub workflow creates a release object.
- GitHub-side workflows are distribution-only after mirror input. They cannot
  create or move the canonical tag, alter Forgejo release truth, or publish from
  an unverified branch.
- Capacium publication is triggered by the verified immutable release/tag path.
- The dormant PyPI job is removed; there is no PyPI distribution claim.

### Changelog history restored

The 1.3.8, 1.3.9 and 1.3.10 entries were reconstructed from the immutable tags,
not backfilled from memory, and are listed below.

## 1.3.11 — Dispatch operations, and a gate that can fail

1.3.10 closed the Council namespace. This release closes the operational gap
underneath it: structured jobs, strict review, harness adherence, model
allocation, observation, and a transfer catalogue, proven by a gate that
holds itself to the same standard it applies to the code.

### Dispatch operations

- **Append-only receipts and typed terminals.** Multi-round receipts preserve
  prior bytes and keep process, task, evidence and gate outcomes separate. A
  zero exit code no longer implies a passing gate.
- **Collision-safe topology and integration eligibility.** Missing commits,
  detached HEAD, dirty non-allowlisted state, a stale base, an omitted sibling
  and a SHA changed after review each fail integration closed.
- **Strict review loop.** A REVIEW_FAIL produces finding dispositions, a bounded
  correction, controller verification and a fresh cold REVIEW_PASS before any
  dependent work starts.
- **Four-harness adherence profiles** with strict digest, bypass and
  role-authority checks. Real proof status stays per harness and per machine;
  no stable transport-parity claim is made before 1.4.
- **Provider-neutral model policy** covering complexity, risk, cost and
  escalation without a hardcoded dispatch-provider default.
- **Semantic observation** with deterministic live and replay projections and
  read-only observer authority.
- **Transfer catalogue.** Dispatch learnings are stored with resolvable
  provenance, observed scope and contradictions. Retrieval is advisory and
  changes no policy, profile, topology, state or gate.

### Routing

- **Minimal adapter mapping for Faigate and OpenRouter.** Council profiles keep
  provider-agnostic names; `translate_model_id` remains the single translation
  point and the alias tables are its provider backend, applied exactly once
  after the namespace is resolved. The dynamic registry that replaces this
  mapping is planned for 1.3.13.

### Release hygiene

- `jsonschema` is declared in the `dev` extra, so a clean environment collects
  the contract tests instead of failing on import.
- The discovery tracking-log tests read tracked fixtures instead of relative
  git-ignored paths, so the full suite is green in every worktree rather than
  carrying two standing failures.

### The gate

`SW-GATE-1311` proves `DISPATCH_OPERATIONS_PASS` across thirteen criteria, with
two independent reviewers of different model classes inspecting one immutable
subject. Criteria that a test process cannot observe are controller-attested,
and the attestation now binds the candidate SHA: a dual pass recorded against
any other subject fails closed inside the repository, not only in tooling.

## 1.3.10 — Council profiles revert the provider prefix

Reconstructed from the immutable `v1.3.10` tag. A version-only release: the
`faigate/` model-id prefix introduced in 1.3.9 was reverted, because the council
provider talks to Faigate natively and must not carry the prefix. Runtime,
bundle and all thirteen skill capabilities move to 1.3.10 in step.

## 1.3.9 — Council profiles carry the Faigate prefix

Reconstructed from the immutable `v1.3.9` tag. Council profile model ids were
prefixed with `faigate/` (`faigate/gpt-4o`, `faigate/deepseek-v4-pro`, and the
chairman ids likewise) across the four council tiers. Runtime, bundle and all
thirteen skill capabilities move to 1.3.9 in step.

## 1.3.8 — Lazy runtime imports and capability sync

Reconstructed from the immutable `v1.3.8` tag. Top-level runtime imports in the
routing and fanout layers were made lazy so the engine core imports without
`runtime/` present: `ProcessResult`, `ArtifactReceipt`, `EvidenceType` and
`ObserverRuntime` resolve on first use rather than at module import. Runtime,
bundle and all thirteen skill capabilities move to 1.3.8 in step.

## 1.3.7 — Self-hosting comes home, and the gate holds it to its word

1.3.6 closed the dispatch seam and taught the council to verify who answered.
This release closes a different gap: the pipeline that ships SkillWeave could
not ship itself. The multi-lane self-hosting work makes the release line
reproducible inside its own machinery, and the ready-to-release amendment ties
the version and CI net together so a declared release is what the gate checks.

### Self-hosting multi-lane

- **The release line runs its own lanes.** The self-hosting gate fixture
  (`tests/gate_b06/test_self_hosting_multilane_gate.py`) drives parallel,
  conflict, SHA, review, and coordinator-kill fixtures under `bash -eo
  pipefail`, with the five W3-L1 hermetic unit suites, and emits
  `SELF_HOSTING_MULTI_LANE_PASS` only when every fixture holds.

### Ready-to-release amendment

- **GLE-020 lazy-surface restoration.** Optional runtime surfaces resolve on
  first access rather than eager import, so the engine's core imports without
  `runtime/` present.
- **Frameworks anchor derivation.** The capability frameworks list derives
  from the installer's declared agent targets, never re-typed in
  `capability_sync.py`.
- **Version and CI net.** `.version.yaml` declares the version locations; the
  release readiness gate enforces every declared manifest carries the release
  version, and the changelog is written by hand, not rewritten by a bump.

### Notes

All fourteen manifests (root plus thirteen skills) move to 1.3.7 in step. The
prose changelog remains a hand-written history and is not an auto-bumped
location.

## 1.3.6 — The seam closes, and the council learns who answered

1.3.5 shipped every part of a dispatch except the seam that joins them: a
profile could name a target tool and its launch command, and nothing started
it. This release closes that seam, and a second one nobody had looked for —
whether the model that answered is the model you asked for.

### The seam

- **`launch_command` is read and the tool is started.** A role with a
  `ToolSpec` is launched, the work is handed over on standard input, and the
  result comes back as an `ArtifactReceipt` rather than as free text. The
  adapter branches on no tool name.
- **A role without a `ToolSpec` runs in place and is recorded as such.**
  Staying in the current harness is a declared configuration, distinguishable
  afterwards from a dispatch that silently did not happen.
- **A profile ships as data**, `profiles/example-standard.yaml`, as a worked
  example to copy and adapt rather than a default that loads itself.
- **A timeout can be set and is reported as itself.** `dispatch()` and
  `launch_from_role()` take one, defaulting to `DEFAULT_DISPATCH_TIMEOUT`
  (900s). The record keeps *declared* apart from *terminated*.
- **The executing harness is declared, never guessed.** `determine_harness`
  reads `SKILLWEAVE_HARNESS`; absent data never reads as a caller's statement.
  Harness and profile stay separate.

### The council

Faigate substitutes silently: an unknown model id returns HTTP 200, a
well-formed completion and no error field, answered by a different model. All
nine ids in `ROUTER_PROFILES` were substituted when measured — `gemini-pro`
included, which *is* in `/v1/models`. A four-seat run had three seats answered
by one model, the chairman among them, and stage 2 had that model rank its own
three anonymised answers.

- The answering model is read from the response envelope, never inferred.
- `min_models_required` counts **distinct** answering models.
- A substitution is surfaced per seat; a self-ranked stage 2 is visible in the
  record; the chairman's own substitution is recorded.

### Repairs

- **Availability was checked against the council's casting**, so a profile
  pinning a served model was refused with a false claim.
- **A hardcoded ten-second socket timeout** made `timeout_per_model` inert.
- **A degraded council named who, never why.**
- **An empty completion counted as an answer**; one guard now covers all four
  providers.
- **`dispatch` was both a module and a re-exported function.** The module keeps
  its name; the function is `dispatch_role`.

### Compatibility

The thirteen bundled skills stay at 1.3.0 — none changed. Two behaviours move
toward the documented contract: an empty completion raises, and a collapsed
council fails its minimum. Code importing `dispatch` from the package root must
use `dispatch_role`.

## 1.3.5 — Contracts worth trusting, and a dispatcher on top

Ten runtime contracts existed since 1.3.0 but did not hold what they promised.
Each defect below was proven by a test that fails against 1.3.0 and passes
here; where no such test was constructible, the criterion says so instead of
inventing one.

### Repairs

- **Compare-and-swap detects conflicts again.** The guard read
  `connection.total_changes`, which is cumulative per connection and therefore
  never differs — every stale write reported success. Now `rowcount`.
- **Journal sequences no longer collide.** Allocation and INSERT are one
  `BEGIN IMMEDIATE` transaction. Eight writers appending 200 entries persisted
  33 before; all of them now.
- **AuthorityGuard fails closed.** An unknown action returned True. It returns
  False, and an undeclared role holds no capability at all.
- **Preflight validates the whole envelope** against resolved paths, not a
  prefix of the string.
- **Checkpoint, handoff and evidence survive the process.** They lived in
  memory; they live in the same store as runs and transitions.
- **The state vocabulary has one truth.** `STOPPED_BEFORE_B06` was in the enum
  and not in the schema.
- **`busy_timeout` is set explicitly**, with a stated reason. The value does not
  change behaviour — `sqlite3.connect` already defaults to 5000. It stops a
  concurrency-critical property from depending on a library default nobody chose.
- **`executor` says what it is.** `execute_step` never executed anything;
  it is `simulate_step`.

### Arbitration and dispatch

- **Write scopes are claimed and released**, not merely checked, and the claim
  is persistent. Overlap is decided on resolved absolute paths.
- **DagScheduler** turns a dependency graph into batches, rejects cycles by
  name, enforces `max_parallel`, and refuses to release the dependents of a
  failed gate. It starts no process and knows no runner.
- **RunnerAdapter** starts real processes, binds their output to the run as
  `ArtifactReceipt` evidence rather than free text, distinguishes exit code
  from signal, kills the whole process group on cancel, and treats a worker
  that dies without a result as a failure with a message.
- **A batch bounds a session.** Both emit that boundary explicitly and refuse a
  sequence that does not declare one.

### Routing — leaving the model behind

This is the part that makes SkillWeave usable from a model-bound harness. A run
can be orchestrated from Codex, Claude Desktop, Claude Code or Antigravity and
executed elsewhere — primarily OpenCode — with the model resolved through
Faigate rather than inherited from wherever the operator happened to sit.

- **RoutingProfile** is declarable data: a model per role, a tier Faigate
  resolves, limits, and an optional target tool. Roles are data too, with
  `observer` wired to the existing runtime observer. A role holding both
  `can_mutate_run_state` and `can_approve_gate` is refused at load — that
  combination is self-approval.
- **The Faigate adapter left `council/`** for a shared routing surface; the
  council consumes it through a re-export shim. `ROUTER_PROFILES` is subsumed,
  not duplicated.
- **Three tier vocabularies were reconciled** with the mapping written down.
  `expert` deliberately stays a router profile and not a tier: it varies which
  models run, not how much work is done.
- **Three routing modes**: `pin` decides nothing, `auto` derives the tier from
  the complexity promptchain-generate already computes, and `hybrid` lets auto
  decide within declared bounds. A bound that moved the decision is recorded as
  an adjustment, never as the original decision.
- **The record separates requested from resolved** — tier, mode, the input that
  drove it, every adjustment, and what Faigate actually returned.
- **Dispatch is optional and per role.** A role without a target tool runs where
  it is. Staying inside the current harness is a first-class configuration.

### Notes

The thirteen member versions in `capability.yaml` stay at 1.3.0. No skill
changed in this release; only the runtime and the new routing layer did, and the
bundle version moves because its composition did.

## Unveroeffentlicht

### Der Kern laesst sich ohne `runtime` importieren

`import skillweave` scheiterte bisher mit `ModuleNotFoundError`, sobald
`runtime/` physisch fehlte — `__init__.py` importierte `.execution` und
`.observation` eager und zog `runtime` ueber `state_machine.py`,
`gate_policy.py` und `event_logger.py` nach. Ein Consumer, der die Engine
einbettet, konnte damit nicht weniger als alles einbetten.

Aufgeloest ueber PEP 562: 14 runtime-erreichbare Namen werden erst beim
ersten Zugriff aufgeloest. `OPTIONAL_SUBPACKAGES = ("runtime",)` ist
ausdruecklich deklariert statt implizit.

**Verhaltensaenderung, die Konsumenten betreffen kann.** Die oeffentliche
API ist zeichengleich — `__all__` unveraendert bei 50 Namen, `from
skillweave import *` liefert dasselbe. Aber die Eager-Bindungen der
Submodulnamen entfallen:

```python
hasattr(skillweave, "execution")              # True  -> False
hasattr(skillweave, "observation")            # True  -> False
hasattr(skillweave, "execution_integration")  # True  -> False
dir(skillweave)                               # 16 Eintraege weniger

import skillweave.execution                   # unveraendert
from skillweave.execution.batch_planner import BatchPlanner   # unveraendert
```

Das liegt ausserhalb des `__all__`-Vertrags und wird im Repo nirgends
attributverkettet genutzt. Wer `hasattr` zur Feature-Erkennung einsetzt,
muss auf `importlib.util.find_spec("skillweave.execution")` wechseln.

## 1.3.0 — Runtime Foundation

Der dokumentierte Lifecycle war bis hierher nicht durchsetzbar: `executor.py`
war laut eigenem Kommentar eine Simulation, die State Machine lag im
Arbeitsspeicher, der Event Logger verschluckte I/O-Fehler, die Gate Policy
kannte keine Rollen. Diese Version schliesst genau diese Luecke.

- Autoritative Run State Machine mit Persistenz
- Schreibvalidierung des Statusvokabulars; ein Wert ausserhalb des Enums wird
  abgewiesen statt geschrieben
- Append-only Event Journal mit Persist-before-Ack
- Rollen- und Transition-Autoritaet; Selbstfreigabe wird strukturell verhindert
- Session Envelope und Preflight gegen produktfremde Prompts
- Immutable Artifact und Evidence Registry
- Typed Handoff Broker mit `cold_start_bundle`
- Checkpoint und Resume mit Revalidierung der Umgebung
- Observer Runtime mit Offset und Lease
- Cross-Run Gate Reconciliation
- Verifizierbare Kontextbeschaffung; Prosa wird als Kontextquelle abgewiesen
- Conformance-Readiness des Kerndatenmodells
- Neun Golden Negative Fixtures, jede aus einem real aufgetretenen Fehler der
  Welle CP-OPT-2026-08-05-W1 abgeleitet

Der Degradationsdetektor liegt als eigenstaendiges Modul `skillweave_degraded`
neben dem Package, damit er erreichbar bleibt, wenn `skillweave.runtime` fehlt.
Sein `fallback_version` bleibt bewusst auf `v1.2.0` — das ist die letzte
Version ohne Runtime.

Bekannte Einschraenkung: Der GNF-Gegenbeweis dokumentiert die Abwesenheit des
Schutzes auf `v1.2.0`, demonstriert aber nicht, dass die Fixtures den Defekt
fangen. Verfolgt als `SW-SCOPE-003`.

## 1.2.0 — Branch Topology Consolidation

Consolidates three previously unintegrated development lines onto a single baseline.
Wave `CP-OPT-2026-08-05-W1`, session S02, iteration I00. Independently reviewed and
reproduced by the cross-product review authority (`SKILLWEAVE_TOPOLOGY: AUTHORIZED`,
`S02_RELEASECHAIN_AUTHORIZED: true`).

Merge order: `EN-FIRST 50c3012` → `G0C bc1bd41` → `G2A 3c24cb1`, zero pairwise conflicts.

- **FEATURE**: SW-N-G2A neutrality adapters — ProcessDefinition, EventGrammar, EVR and compiler contracts, executable and test-covered, with no Capacium or Elementeer imports.
- **CHANGED**: Canonical skill catalog is now EN-first. All 13 skill descriptions rewritten in English; boundary declarations corrected.
- **CHANGED**: Skill count 14 → 13. The legacy `skills/launch/SKILL.md` relic is removed; `skills/skillweave-launch/` remains the canonical launch skill.
- **CHANGED**: Domain corrected from `skillweave.dev` to `skillweave.xyz` across licensing and endpoint configuration.
- **FIXED**: SW-G0C release dead code removed from `launch/deployment.py`.
- **FIXED**: SW-N-G2A R2 process-pack handoff — both schema entries carried an empty `""` key instead of `"$id"`. Repaired to canonical URIs, digests recomputed, non-recursive manifest and receipt reissued, independently verified (`4ef1cf67`).
- **ADDED**: `tests/test_skill_catalog.py` and `tests/test_skill_boundaries.py`.

### Known issues

`BACKLOG-ENV-001` — pre-existing environmental test failures in `test_backlog_sync`,
`test_council` and `test_integration`. Fail-set is identical before and after this
consolidation; no regressions were introduced. Not addressed in this release.

### Not in this release

The runtime remains a planning and contract surface. `executor.py` is still a
simulation; the state machine is in-memory and the event logger writes local files
best-effort. Runtime integrity (authoritative run state, event journal, role
authority, typed handoffs, checkpoints, evidence registry, observer cursor) is the
subject of the next PRD, not of this consolidation.

## 1.1.0 — Studio Hook Binding Engine

- **FEATURE**: Hook binding engine with 4 execution types (Python HookAdapter, shell, SKILL.md injection, Capacium capability)
- **FEATURE**: YAML binding config with 3-source resolution (project > user > auto-discovered), dedup by capability+phase+position, priority sorting
- **FEATURE**: Execution chain with 4 failure modes (block, warn, ignore, retry), safe condition evaluator, timeout enforcement
- **FEATURE**: Auto-discovery of hook bindings from Capacium capability triggers (CloudEvents mapping)
- **FEATURE**: JWT license validation — HMAC-SHA256, offline-first, 7-day grace period, 14-day trial support
- **FEATURE**: Tier gate enforcement — Free tier bypass for `pre_discovery` (mentoring hooks), Studio required for all other hook points
- **FEATURE**: CLI with 6 commands: `hooks list`, `bind`, `unbind`, `test`, `discover`, `help`
- **FEATURE**: 2 reference capabilities — `ci-gate` (post_test HookAdapter) + `lean-startup` SKILL.md (pre_discovery)
- **TESTS**: 195 tests across hooks, binding, engine, discovery, licensing, CLI, and reference modules

## 1.0.2

- **FIX**: Capacium manifests now stay synchronized across the root bundle and all individual SkillWeave skill manifests.
- **FEATURE**: Release gates now block releases when the requested release/tag version differs from any `capability.yaml` version.
- **FEATURE**: Published GitHub releases trigger the Capacium Exchange publish workflow.

## 1.0.1

- **FEATURE**: Git Flow Convention — skills enforce minimum branching discipline (feature/fix/chore branches, dev → main merge path, preflight detection)
- **FEATURE**: Forgejo → GitHub mirror workflow (`.forgejo/workflows/mirror.yml`) — auto-push to GitHub on main push
- **IMPROVEMENT**: promptchain-execute Preflight Phase 1 now includes git flow state evaluation (Step 7)
- **IMPROVEMENT**: releasechain Pipeline Stage 5 expanded with branch model, merge flow enforcement, and config schema
- **IMPROVEMENT**: launch Pre-Launch-Checklist includes git flow check (dev → main merge path verified)
- **IMPROVEMENT**: Skill SKILL.md files synced between user-level and repo-level copies

## 1.0.0 — Forever Free
- **RELEASE**: SkillWeave v1.0.0 "Forever Free" — production-stable AI skill orchestration
- **FEATURE**: 5-level test pyramid (Lint → Unit → E2E Smoke → Acceptance → Evidence/Groundedness) with 3-state gate (PROMOTE/HOLD/ROLLBACK)
- **FEATURE**: File-based planning system (beans-pattern) — directory-as-state Kanban with YAML frontmatter tickets in `.skillweave/planning/{backlog,doing,done}/`
- **FEATURE**: Lifecycle Navigator with automatic phase detection from `.skillweave/` artifacts and intelligent next-step recommendations
- **FEATURE**: Progressive Disclosure architecture — Layer 0 (Wizard, 5 questions), Layer 1 (7 Meta-Commands), Layer 2 (13 Direct Skills)
- **FEATURE**: Handover signal validation with JSON schemas for skill-to-skill phase transitions
- **FEATURE**: Release report generation with date-stamped markdown templates
- **FEATURE**: Free/Studio tier boundary enforcement via `.skillweave/config.yaml`
- **IMPROVEMENT**: Council stability — structured JSON peer review, CouncilDegradedError, 60s/180s timeouts, graceful degradation with partial results
- **FIX**: Council Faigate port mismatch (8092 → 8090) causing OpenCode instability
- **FIX**: `normalize_manifest` always uses `pyproject.toml` version for skill manifests
- **IMPROVEMENT**: SerpApi and Perplexity MCP search provider support
- **IMPROVEMENT**: Google CSE provider removed (API deprecated by Google)
- **DOCS**: Unified getting-started guide for 3 personas (Power User, Indie Hacker, Non-Technical)
- **DOCS**: Complete reference docs for plan commands, testing flow, navigator detection, meta-commands, wizard flow
- **LICENSE**: Copyright updated to LangeVC.com, Apache 2.0 confirmed

## 0.7.0
- **FEATURE**: 6 new agent-facing skills after promptchain pattern (SKILL.md + capability.yaml + sequence_type)
  - `skillweave-lifecycle` (plan): Bundle-Navigator, Phasen-Status, Entry-Point-Detection
  - `skillweave-discovery` (plan): Problemdefinition, User Research, Empathy Mapping, 11 Prompts
  - `skillweave-design` (mixed): Design-Thinking-Lens, Briefanalyse, Token-Extraktion, Evaluation
  - `skillweave-launch` (build): Pre-Launch-Check, Deployment-Koordination, Announce, Metrics-Vergleich
  - `skillweave-post-release` (mixed): Retrospektive, Feedback-Sammlung, Iterationsplanung
  - `skillweave-repo-health` (plan): Inventory-Scan, 5-Class-Klassifikation, Archive, Dedup, Hygiene-Report
  - `skillweave-observe` (plan): Execution Reports, Timing, Events, Memory — Read-Only Observability
- **FEATURE**: Launch infrastructure (src/skillweave/launch/)
  - `deployment.py`: GitHub Actions workflow_dispatch-Trigger, Health-Check, Rollback-Plan
  - `announce.py`: Release Notes Generator aus CHANGELOG.md, Multi-Channel-Formatting
  - `metrics.py`: Pre/Post-Launch-Metriken, Snapshot-Vergleich mit Delta-Report
- **FEATURE**: Post-Release infrastructure (src/skillweave/post_release/)
  - `retrospective.py`: Strukturierte Retro-Vorlage (Went Well / To Improve / Action Items P1-P3)
  - `feedback.py`: GitHub Issues-Feedback-Sammlung, Kategorisierung (bug/feature/improvement/question)
  - `iteration.py`: Backlog-Generator aus Retro + Feedback, Prioritäts-Scoring
- **FEATURE**: Repo-Health infrastructure (src/skillweave/repo_health/)
  - `scanner.py`: Inventory-Scan mit Typ, Größe, last_modified
  - `classifier.py`: 5-category rules-based classification (Active Core / Consolidation / Legacy / Deprecated / Needs Review)
  - `dedup.py`: MD5-Exact + Fuzzy-Content-Duplikatserkennung
  - `archive.py`: Move + Restore mit JSON-Manifest, dry_run-Pflicht
  - `report.py`: Hygiene-Score (A-F) mit konkreten Empfehlungen
- **FEATURE**: phases.yaml — alle 7 Phasen mit Skills + promptchain_types + global_skills-Sektion
- **FEATURE**: bundles.yaml — 5 Bundles mit sequence_types_used + entry_requires + estimated_effort
- **FEATURE**: Installer auf 13 Skills aktualisiert (12 SkillWeave + frontend-design)
- **FEATURE**: Design-Skill references: 5 UX-Prinzipien, 6 Workshop-Regeln, Token-Format, Elementify-Integration
- **FEATURE**: Lifecycle-Skill references: 7 Phasen mit Entry/Exit-Conditions, 5 Bundles mit Recommendation-Matrix
- **IMPROVEMENT**: Alle neuen Skills haben sequence_type (plan/mixed/build) für promptchain-generate-Kompatibilität
- **IMPROVEMENT**: Discovery-Skill mit 11 Prompts in 4 Gruppen (Empathy, Research, Framing, Output)
- **IMPROVEMENT**: Legacy prompt-chain aus Installer-Tabelle entfernt (nie existiert, kein Effekt)
- **IMPROVEMENT**: Release-Naming-Convention in auto-tag-release.yml enforced (SkillWeave vX.Y.Z)

## 0.6.0
- **FEATURE**: 7-phase lifecycle model with entry/exit conditions and bundle system (Initiative 01)
- **FEATURE**: Discovery prompt library (11 prompts) and Design Thinking Lens (Initiative 02)
- **FEATURE**: Release readiness assessment, premature invocation detection, Launch skill separation (Initiative 03)
- **FEATURE**: Repo cleanup, dead code removal, archive with restore manifest (Initiative 04)
- **FEATURE**: Execution system with Ralph Loop state machine, batch planner, retry, gate policy, observation layer, execution memory, sidecar manager (Initiative 05)
- **FEATURE**: GitHub Action workflows (11 workflows), GitHub integration layer, auto-tag, auto-changelog, auto-issue, auto-PR, auto-docs-sync, release readiness gate (Initiative 06)
- **FEATURE**: Phase-aware onboarding flow with state persistence
- **FEATURE**: Phase boundary enforcement (soft) with violation logging
- **FEATURE**: Ideation module (quantity-first, wild ideas, separate evaluation)
- **FEATURE**: Assumption tracking with risk scoring and validation status
- **FEATURE**: Iteration quality framework with evidence-driven revision
- **FEATURE**: Release workflow with 5 gated sequential steps
- **FEATURE**: Launch skill placeholder with separate lifecycle phase
- **FEATURE**: Capability-based GitHub Actions (workflow-inventory, auto-tag, auto-release, auto-changelog, auto-issue, auto-PR, auto-docs-sync, release-readiness-gate, integration-test, auto-release-notes)
- **IMPROVEMENT**: promptchain-execute redefined as orchestration substrate (release logic moved to releasechain)
- **IMPROVEMENT**: All 510 tests passing across full system

## 0.5.6
- **FEATURE**: Capacium badge and install section in README
- **FEATURE**: Content boundary enforcement for release artifacts (AGENTS.md + prerelease.yml)
- **IMPROVEMENT**: Version bump to 0.5.6 with updated documentation

## 0.5.0
- **RELEASE**: SkillWeave Next Level Features v0.5.0
- **FEATURE**: Three risk modes (conservative, medium, unicorn) across all skills
- **FEATURE**: .skillweave folder structure with config, tracking, manifesto
- **FEATURE**: Persistent state manager with session recovery
- **FEATURE**: Configuration manager with mode interpretation
- **FEATURE**: GitHub Issues integration with Planning Poker estimation
- **FEATURE**: Backlog synchronization with .skillweave tracking
- **FEATURE**: Optional checklist execution with markdown checkbox tracking
- **FEATURE**: Optional Design-Thinking Lens for UI/UX decisions
- **FEATURE**: Enhanced capability-based routing with dynamic agent detection
- **FEATURE**: Modular templates foundation with example templates
- **FEATURE**: Community know-how prototype for pattern extraction
- **FEATURE**: Comprehensive testing suite with 100+ tests
- **FEATURE**: Updated documentation with configuration guide and examples
- **FEATURE**: Capacium packaging for all skills - each skill ships as a self-contained capability.yaml for cap install
- **IMPROVEMENT**: All Next Level features fully tested and integrated

## 0.4.4
- **FEATURE**: Execute Skill v2 – Ralph Loop state machine with binary gates, batch planning, and safe parallelization
- **FEATURE**: Two-axis model for generate – separates `sequence_type` (plan/build/mixed) from `execution_mode` (rex/ralph_attended/ralph_overnight)
- **FEATURE**: Enhanced validate – checks parallelization readiness and separation of critical path vs sidecar lanes
- **NEW**: Three reference files for execute – `ralph-loop-state-machine.md`, `build-step-normalization.md`, `gate-policy.md`
- **IMPROVEMENT**: Execute now enforces write-scope ownership, safe parallel lanes, and binary completion signals
- **IMPROVEMENT**: Generate includes mode mapping table with 9 combinations (plan/build/mixed × rex/ralph_attended/ralph_overnight)
- **IMPROVEMENT**: Validate now identifies single-owner surfaces and integration gate requirements

## 0.4.3
- **FIX**: Installed `skillweave-blueprint` for supported agents so Codex and related tools see the full five-skill SkillWeave set
- **FIX**: Cleaned up legacy SkillWeave duplicates under `~/.agents/skills` to prevent duplicate promptchain entries with stale descriptions
- **FIX**: Source/Target directory separation – installer now copies skills from development repo to `~/.skillweave` installation directory
- **FIX**: Removed duplicate git repository from `~/.skillweave` (target directory should be plain folder, not a git repo)
- **FIX**: Added warning when target directory is a git repository with cleanup instructions
- **NEW**: `update-local-skills.sh` script for developers to sync changes from development repo to installation
- **IMPROVEMENT**: Installer automatically copies skills from source to target when run from development repository
- **IMPROVEMENT**: Better logging and dry-run output for copying operations

## 0.4.2
- **FEATURE**: Interactive installer with agent selection modes (`--interactive`, `--uninstall`, `--update`, `--troubleshoot`)
- **FIX**: Correct agent paths for Gemini CLI (`~/.gemini/skills`) and Qwen Code (`~/.qwen/skills`)
- **FIX**: Prevent creating directories for non-existent agents (no "file-leichen")
- **IMPROVEMENT**: Smart agent detection with numeric selection, `all`, or `none` options
- **DOCS**: Updated README with interactive installation section and corrected agent paths

## 0.4.1
- **DOCS**: Complete README overhaul with "Product development flow on steroids" branding
- **DOCS**: Added DEVELOPMENT_WORKFLOW.md with standardized release process
- **DOCS**: Release conventions and "SkillWeave vX.Y.Z" naming standardization
- **IMPROVEMENT**: ASCII workflow diagram and enhanced architecture documentation
- **IMPROVEMENT**: Repository structure updates and clearer onboarding guidance

## 0.4.0
- **FEATURE**: Blueprint Skill (`/skillweave-blueprint`) for structured PRD creation
- **FEATURE**: Enhanced Execute Skill with parallel execution and dependency analysis
- **FEATURE**: Enhanced ReleaseChain Skill with dual-mode (REX/Ralph Loop) execution
- **ARCHITECTURE**: Parallel execution core with dependency graph analysis
- **ARCHITECTURE**: Capability-based agent-agnostic design for any AI coding agent
- **DOCS**: Full workflow example and comprehensive testing suite
- **PERFORMANCE**: Optimizations for large projects (50+ tasks)

## 0.3.5
- **FEATURE**: Intelligent `skillweave-promptchain-execute` with plan/build/mixed mode detection
- **NEW**: `skillweave-releasechain` development pipeline skill
- Execute skill now detects sequence type and adapts outputs accordingly
- Post-execution options: target audience (humanize/machinize/mixed)
- Build components can trigger automated development pipeline
- Releasechain handles: review, testing, iteration, commit, push, PR, release, changelog
- Better integration between execute and releasechain skills

## 0.3.4
- **IMPROVEMENT**: Enhanced `skillweave-promptchain-validate` with better output handling
- Added user prompts for output format: Validation Report, Improved sequence only, Both separate files
- Added sequence type detection: plan mode, build mode, mixed
- Improved sequence must be complete (no placeholder references)
- Output format adaptation based on sequence type
- Better documentation of validation interaction process

## 0.3.3
- **FEATURE**: Attachment detection for `skillweave-promptchain-execute` and `skillweave-promptchain-validate`
- Skills now accept prompt sequences as .md/.txt file attachments
- Updated descriptions, usage examples, and parameters
- Added attachment detection logic description
- Clarified that generate uses parameters only (no attachments)

## 0.3.2
- **FIX**: YAML parsing in `skillweave-promptchain-execute` argument-hint
- Changed `inputs='{\"key\": \"value\"}'` to `inputs=\"[JSON]\"` to avoid YAML parser errors
- Fixes Codex and other agent compatibility issues

## 0.3.1
- **FIX**: Multi-agent installer with correct paths and formats for all agents
- **FIX**: Opencode installation as single `.md` files to `~/.config/opencode/commands/`
- **FIX**: Claude Code/Codex/Antigravity paths to correct locations (`~/.claude/skills/`, `~/.codex/skills/`, `~/.antigravity/skills/`)
- **FIX**: Different installation formats per agent type (single files vs directories)
- **FIX**: Updated README with correct manual installation instructions
- **IMPROVEMENT**: Better error handling and logging in installer script

## 0.3.0
- separate skill directories for each command: `skillweave-promptchain-generate`, `-validate`, `-execute`
- initial multi-agent installer script (had incorrect paths for some agents)
- license changed from MIT to Apache 2.0
- initial README updates for multi-agent installation

## 0.2.0
- new `skillweave-promptchain` skill with direct `/skillweave-*` commands
- `/skillweave-promptchain-generate`, `-validate`, `-execute` commands
- improved README with new installation instructions
- updated multi-agent quickstart section

## 0.1.0
- initial repository structure
- first `prompt-chain` skill
- initial docs
- initial schemas
- initial parser, validator, orchestrator, executor
- first examples and templates
