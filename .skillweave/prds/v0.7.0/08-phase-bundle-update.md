# v0.7.0: Phases & Bundles Update — Sequence-Type-konforme Integration

## Problem

`phases.yaml` und `bundles.yaml` sind veraltet: Launch und Post-Release haben `skills: []`, keine Phase hat sequence-type-Informationen für promptchain-generate.

## Lösung

### phases.yaml Update — mit Sequence-Types

Jede Phase bekommt ihren Skill + sequence-type:

```yaml
phases:
  - id: discovery
    order: 1
    skills:
      - skillweave-discovery      # NEU
      - skillweave-blueprint
      - last30days
    promptchain_types:
      - plan                      # discovery + blueprint = plan
    phase_type: optional

  - id: blueprint
    order: 2
    skills:
      - skillweave-blueprint
      - skillweave-promptchain-generate
      - skillweave-promptchain-validate
    promptchain_types:
      - plan                      # blueprint/generate/validate
    phase_type: recommended

  - id: design
    order: 3
    skills:
      - skillweave-design         # NEU
      - frontend-design
    promptchain_types:
      - mixed                     # design = analyse + generieren
    phase_type: optional

  - id: build
    order: 4
    skills:
      - skillweave-promptchain-execute
      - skillweave-releasechain
      - skillweave-observe        # NEU
    promptchain_types:
      - build                     # execute + releasechain
      - plan                      # observe
    phase_type: core

  - id: release
    order: 5
    skills:
      - skillweave-releasechain
      - skillweave-observe        # NEU
    promptchain_types:
      - build                     # releasechain
      - plan                      # observe
    phase_type: core

  - id: launch
    order: 6
    skills:
      - skillweave-launch         # NEU (vorher leer)
    promptchain_types:
      - build                     # deployment
    phase_type: optional

  - id: post-release
    order: 7
    skills:
      - skillweave-post-release   # NEU (vorher leer)
      - skillweave-repo-health    # NEU
      - skillweave-observe        # NEU
      - skillweave-discovery      # NEU (für nächste Iteration)
    promptchain_types:
      - mixed                     # post-release
      - plan                      # repo-health + observe + discovery
    phase_type: optional
```

### Phase-agnostische Skills (immer verfügbar)

```yaml
global_skills:
  - id: skillweave-lifecycle
    type: plan
    description: Navigation, Bundle-Auswahl, Phasen-Status
  - id: skillweave-repo-health
    type: plan
    description: Repo-Hygiene jederzeit ausführbar
  - id: skillweave-observe
    type: plan
    description: Reports, Metriken, Memory — nur Lesezugriff
```

### bundles.yaml Update — mit navigator_command + sequence_types

```yaml
bundles:
  - id: full-lifecycle
    name: "Full Lifecycle"
    phases: [discovery, blueprint, design, build, release, launch, post-release]
    entry_requires: ["Project idea or problem statement"]
    sequence_types_used: [plan, mixed, build]
    estimated_effort: "Full project duration"

  - id: discovery-to-blueprint
    name: "Discovery to Blueprint"
    phases: [discovery, blueprint]
    entry_requires: ["Problem or opportunity to explore"]
    sequence_types_used: [plan]
    estimated_effort: "1-3 days"

  - id: design-and-build
    name: "Design and Build"
    phases: [design, build]
    entry_requires: ["Valid PRD or clear requirements"]
    sequence_types_used: [mixed, build]
    estimated_effort: "2-5 days"

  - id: release-and-launch
    name: "Release and Launch"
    phases: [release, launch]
    entry_requires: ["Working code in releasable state"]
    sequence_types_used: [build]
    estimated_effort: "1-2 days"

  - id: post-release-improvement
    name: "Post-Release Improvement"
    phases: [post-release, blueprint, build]
    entry_requires: ["System is live in production"]
    sequence_types_used: [mixed, plan, build]
    estimated_effort: "2-5 days"
```

### Installer-Update auf 12 Skills

| # | Skill | Status | Sequence-Type | Install-Pfad |
|--:|-------|--------|---------------|-------------|
| 1 | skillweave-lifecycle | **NEU** | plan | `skills/skillweave-lifecycle/` |
| 2 | skillweave-discovery | **NEU** | plan | `skills/skillweave-discovery/` |
| 3 | skillweave-blueprint | bestehend | plan | unverändert |
| 4 | skillweave-design | **NEU** | mixed | `skills/skillweave-design/` |
| 5 | skillweave-promptchain-generate | bestehend | plan | unverändert |
| 6 | skillweave-promptchain-validate | bestehend | plan | unverändert |
| 7 | skillweave-promptchain-execute | bestehend | build | unverändert |
| 8 | skillweave-releasechain | bestehend | build | unverändert |
| 9 | skillweave-launch | **ERWEITERT** | build | `skills/skillweave-launch/` |
| 10 | skillweave-post-release | **NEU** | mixed | `skills/skillweave-post-release/` |
| 11 | skillweave-repo-health | **NEU** | plan | `skills/skillweave-repo-health/` |
| 12 | skillweave-observe | **NEU** | plan | `skills/skillweave-observe/` |

### Tests

| Test | Beschreibung |
|------|-------------|
| `test_phase_skill_assignment.py` | Prüft: Jede Phase hat ≥ 1 Skill + promptchain_types |
| `test_bundle_coverage.py` | Prüft: Jedes Bundle referenziert gültige Phasen |
| `test_global_skills.py` | Prüft: global_skills sind nicht in phases dupliziert |
| `test_installer_coverage.py` | Prüft: Installer findet alle 12 Skills |
| `test_sequence_type_consistency.py` | Prüft: Jeder Skill hat konsistenten sequence_type in phases.yaml + capability.yaml |
