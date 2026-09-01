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

## Layout

| Path | Consumed by | What it is |
|---|---|---|
| `phases.yaml`, `bundles.yaml` | `test_lifecycle_system.py`, `unit/test_lifecycle_single_source.py` | A stored snapshot of what `skillweave.lifecycle.to_yaml()` generates. `skillweave.lifecycle` is the canonical source (SW-LC-001); this copy exists so the drift guard has something to compare against. **Regenerate it when the module changes** — a failing `test_checked_in_yaml_matches_the_generator` means this file is stale, not that the module is wrong. |
| `config.yaml` | `test_lifecycle_system.py`, `test_discovery.py` | A representative project config |
| `lenses/`, `prompts/discovery/`, `templates/discovery/` | `test_discovery.py` | Discovery assets, resolved through `resolve_discovery_asset(root, kind, name)`, which expects a project root containing `.skillweave/`. That is why this fixture is a *root* and not a flat directory. |
| `lib/` | `test_discovery.py` | `ideation.py`, `assumptions.py`. Nothing under `src/` imports these and the packaged distribution deliberately excludes them (`tests/packaging/test_discovery_installed.py`). |
| `release/skill-boundaries.yaml` | `test_skill_boundaries.py` | The Release/Launch boundary policy |

## The `.gitignore` interaction

The root `.gitignore` entry is anchored (`/.skillweave/`), so it excludes the
repository's own substrate and leaves this one tracked. Keep the anchor: an
unanchored `.skillweave/` would swallow this fixture and the tests would fail in
CI while passing locally.

## Open question, not settled here

`lenses/`, `prompts/discovery/`, `templates/discovery/` and `lib/` may want to be
*shipped* assets rather than fixtures. `resolve_discovery_asset()` looks for them
under the consuming project's `.skillweave/`, but nothing ships them and the
preflight does not create them — `SkillWeavePersistence.ensure_folder_structure()`
makes four empty directories, a config and some READMEs. So a consumer that
installs SkillWeave has no discovery assets and gets `DiscoveryAssetNotFound`.
Moving them here makes the tests hermetic; it does not answer where a real
consumer is supposed to get them.
