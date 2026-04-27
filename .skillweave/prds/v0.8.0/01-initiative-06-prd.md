# Initiative 06 — GitHub Action & Integration Layer (PRD)

## Overview

Initiative 06 baut GitHub-native Surfaces für SkillWeave: eine publikumsfähige GitHub Action (Marktplatz-ready), bidirektionale Issues↔Tracking-Log Sync, und eine GitHub App als optionale Deep-Integration (v0.9.0+).

## Architektur

```
GitHub Marketplace              SkillWeave Repo
┌──────────────────┐           ┌──────────────────────────┐
│ skillweave-      │           │ .github/workflows/       │
│ validate-action  │◄──────────│   skillweave-validate.yml│
│                  │           │   release-gate.yml       │
│ (action.yml)     │           │   (alle 11 bestehenden)  │
└──────────────────┘           └──────────────────────────┘
                                        │
GitHub Issues              ┌────────────┴────────────┐
┌──────────────────┐       │ src/skillweave/          │
│ Issue erstellt   │──────►│   github_integration/   │
│ Label: backlog   │       │   release/readiness.py  │
│ Assign: phase    │       │   post_release/         │
└──────────────────┘       │   tracking-log/         │
        ▲                  └──────────────────────────┘
        │ sync.py
┌──────────────────┐
│ .skillweave/     │
│   tracking-log/  │
│   backlog/       │
└──────────────────┘
```

## Layer 1: Validation Action (v0.8.0)

### action.yml

```yaml
name: "SkillWeave Validate"
description: "Validate SkillWeave bundle structure, skill metadata, manifest consistency, and release readiness"
author: "SkillWeave"
branding:
  icon: "check-circle"
  color: "blue"

inputs:
  check:
    description: "What to validate: bundles, skills, manifest, release, all"
    default: "all"
  fail_on_warning:
    description: "Whether to fail on warnings or only errors"
    default: "false"

runs:
  using: "composite"
  steps:
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - run: pip install pyyaml
      shell: bash
    - run: python ${{ github.action_path }}/validate.py
      shell: bash
      env:
        CHECK: ${{ inputs.check }}
        FAIL_ON_WARNING: ${{ inputs.fail_on_warning }}
```

### Python-Module

Neue Datei `action/validate.py` (im Repo-Root, da GitHub Action das erfordert):

```python
# Validator: Wrapper um github_integration/ + release/readiness.py
# Checks:
# 1. Alle skills/ Ordner haben SKILL.md + capability.yaml
# 2. phases.yaml: keine leeren skills-Listen
# 3. bundles.yaml: alle Phasen-Referenzen gültig
# 4. CHANGELOG.md hat Eintrag für aktuelle Version
# 5. capability.yaml version stimmt mit pyproject.toml
# Output: Structured Validation Report (JSON + Annotations)
```

### Exporter: bestehende Workflows

- `release-readiness-gate.yml` bleibt, bekommt optionalen `validate`-Step
- `auto-changelog.yml` bleibt
- `auto-tag-release.yml` bleibt
- `auto-issue.yml` bekommt Erweiterung für tracking-log

## Layer 2: Issues ↔ Tracking-Log Sync (v0.8.0)

### Neue Module

`src/skillweave/github_integration/sync.py`:
```python
class IssueSync:
    def sync_to_tracking_log(issue: Issue) -> None
        # Neue Issue → Eintrag in .skillweave/tracking-log/
        # Label → Phase-Mapping (skillweave/phase:build → task in build.json)
    
    def sync_to_github(backlog_item: BacklogItem) -> Issue
        # Backlog-Eintrag ohne Issue → GitHub Issue erstellen
        # Status-Änderung → Issue updaten
```

`src/skillweave/github_integration/labels.py`:
```python
SKILLWEAVE_LABELS = {
    "skillweave/backlog": "000000",
    "skillweave/phase:discovery": "bfd4f2",
    "skillweave/phase:blueprint": "c5def5",
    "skillweave/phase:design": "d4c5f9",
    "skillweave/phase:build": "c5e0b4",
    "skillweave/phase:release": "f9e79f",
    "skillweave/phase:launch": "f5b7b1",
    "skillweave/phase:post-release": "d5f5e3",
    "skillweave/bundle:full-lifecycle": "f0f3f4",
    "skillweave/bundle:discovery-to-blueprint": "e8f6ef",
    "skillweave/bundle:design-and-build": "fef9e7",
    "skillweave/bundle:release-and-launch": "fdedec",
    "skillweave/bundle:post-release-improvement": "eaf2f8",
}

def ensure_skillweave_labels(repo: str) -> list
def classify_issue(issue: Issue) -> str  # → phase-id
```

### auto-issue.yml Erweiterung

Bestehenden Workflow erweitern: nach Issue-Erstellung → tracking-log-Eintrag + Label-Set.

## Layer 3: GitHub App (v0.9.0+ — nur architektur)

### Nicht implementiert — nur dokumentiert

```yaml
app:
  permissions:
    contents: write
    issues: write
    pull_requests: write
    metadata: read
  events:
    - issues
    - pull_request
    - push
    - release
  features:
    - repo-sync: SkillWeave-Templates in Ziel-Repo deployen
    - release-signal: Metriken aus Release-Events capturen
    - trust-enrichment: Provenance-Informationen an Releases anhängen
```

## Tasks

### Layer 1: Validation Action

| ID | Titel | Typ | Aufwand |
|----|-------|-----|---------|
| GHA-001 | `action.yml` erstellen | config | 0.5 |
| GHA-002 | `action/validate.py` — Bundle-Struktur + Skill-Metadaten-Check | build | 2 |
| GHA-003 | `action/validate.py` — Release-Readiness + Version-Konsistenz | build | 1.5 |
| GHA-004 | GitHub Action im Marketplace publizieren | ops | 1 |
| GHA-005 | Tests: Validierung aller Check-Typen, Fehlerfälle, Exit-Codes | test | 2 |

### Layer 2: Issues ↔ Tracking-Log Sync

| ID | Titel | Typ | Aufwand |
|----|-------|-----|---------|
| GHA-006 | `github_integration/sync.py` — Issue-to-Tracking-Log | build | 2 |
| GHA-007 | `github_integration/sync.py` — Tracking-Log-to-Issue | build | 1.5 |
| GHA-008 | `github_integration/labels.py` — Label-Management | build | 1 |
| GHA-009 | auto-issue.yml Erweiterung + Label-Set | config | 1 |
| GHA-010 | Tests: bidirektionaler Sync, Label-Erstellung, Edge Cases | test | 2 |

### Layer 3: App-Konzept (optional)

| ID | Titel | Typ | Aufwand |
|----|-------|-----|---------|
| GHA-011 | GitHub App Architektur-Dokument + Entscheidungsmatrix | doc | 1 |

## phasen.yaml Integration

Initiative 06 gehört zu **keiner bestehenden Phase**. Sie ist ein neuer Skill:

```yaml
- id: github-integration
  order: 0  # phase-agnostisch, immer verfügbar
  skills:
    - skillweave-github-validate   # NEU
    - skillweave-github-sync       # NEU
  promptchain_types:
    - plan
    - build
  phase_type: tooling
```

## Erfolgskriterien

1. `skillweave-validate` GitHub Action ist auf dem Marketplace: `typelicious/skillweave-validate`
2. Issue-Erstellung → automatischer Eintrag in `.skillweave/tracking-log/`
3. Backlog-Änderung → automatisches Issue-Update
4. Bundle-Validierung läuft bei jedem PR (optionaler Check)
5. GitHub App ist dokumentiert, aber nicht implementiert
