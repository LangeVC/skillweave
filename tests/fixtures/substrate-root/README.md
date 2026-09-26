# Test substrate root

A project root whose `.skillweave/` directory is checked in, for tests that need
a populated substrate.

## Why this exists

The repository's **own** `.skillweave/` is git-excluded — see
`docs/substrate-map.md`, invariant 5. What SkillWeave generates into a substrate
is IP, and this repository is publicly mirrored. No test may read the repository's
own substrate instance, because after the exclusion there is nothing there to read
in a fresh clone or CI checkout.

Everything under `.skillweave/` here was moved out of the repository's own
substrate for exactly that reason. It is fixture data now, not project state.

## What remains and why

This fixture only holds files that are genuinely fixture-only — either drift
snapshots that exist to be compared against a generator, or a representative
project config. It deliberately no longer copies the discovery assets.

| Path | Consumed by | What it is |
|---|---|---|
| `phases.yaml`, `bundles.yaml` | `test_lifecycle_system.py`, `unit/test_lifecycle_single_source.py` | A stored snapshot of what `skillweave.lifecycle.to_yaml()` generates. `skillweave.lifecycle` is the canonical source (SW-LC-001); this copy exists so the drift guard has something to compare against. **Regenerate it when the module changes** — a failing `test_checked_in_yaml_matches_the_generator` means this file is stale, not that the module is wrong. |
| `config.yaml` | `test_lifecycle_system.py`, `test_discovery.py` | A representative project config. Not a discovery asset (lens/prompt/template), so it stays here and is not shipped. |
| `lib/` | `test_discovery.py` | `ideation.py`, `assumptions.py`. Nothing under `src/` imports these and the packaged distribution deliberately excludes them (`tests/packaging/test_discovery_installed.py`). |
| `release/skill-boundaries.yaml` | `test_skill_boundaries.py` | The Release/Launch boundary policy |

## What is no longer here

The `lenses/`, `prompts/discovery/` and `templates/discovery/` directories that
were once checked in under this fixture were byte-identical copies of the
discovery assets shipped in the package (`src/skillweave/assets/`). They were a
second place for the same bytes and drifted. They are removed; `test_discovery.py`
resolves every discovery asset through `resolve_discovery_asset()`, which falls
through to the packaged default when the project has no `skillweave.config/` tier
(SW152-007 ships the defaults, SW152-009 adds the resolver chain, SW152-012 retires
the duplicate copies here).

## The `.gitignore` interaction

The root `.gitignore` entry is anchored (`/.skillweave/`), so it excludes the
repository's own substrate and leaves this one tracked. Keep the anchor: an
unanchored `.skillweave/` would swallow this fixture and the tests would fail in
CI while passing locally.
