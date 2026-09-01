# SW-ROUTE-001 — Close the routing dispatch seam

## 1. Executive summary

SkillWeave 1.3.5 shipped a routing layer with every part of a dispatch except
the seam that joins them. A profile can name a target tool and its launch
command; nothing starts it. A profile can pin a model; the check that admits it
consults the wrong table. A profile can be one of several; nothing knows which
harness is asking.

This closes all three. It is the first work that makes 1.3.5's headline claim
true rather than declared.

## 2. Problem statement

Measured 2026-08-17 against the released tree (`v1.3.5`, `478211f`):

```
launch_command             required by ToolSpec, ZERO readers outside
                           profile.py            -> nothing dispatches

_check_unavailable_models  gates on known_model_ids(), derived from
                           ROUTER_PROFILES — the council's casting
                                                 -> refuses deepseek-v4-pro
                                                    with a false message

harness                    ZERO references in routing/ AND runtime/
                                                 -> no per-harness selection
```

`role.tool` says where a role is dispatched **to**. Nothing says where **from**.
The adapter needs both, which is why this is one piece of work and not three.

The failure mode is the one this organisation keeps paying for: a declaration
that reads as a capability. The release note states that a role with a target
tool is dispatched there. A reader would not learn otherwise without grepping
for the field.

## 3. Users

The operator running five to fifteen parallel agent sessions across four
harnesses (Claude Code, OpenCode, Codex, Antigravity), who wants the routing
decision to be data rather than whichever tool the session happens to sit in.

Second, any consumer of the open core: the adapter is the general one, so a
fifth harness costs a declaration rather than a branch.

## 4. Solution overview

Three lanes on disjoint files, then a gate that runs the real case.

| Lane | Adds | Closes |
|------|------|--------|
| `SW-RT-001` | `routing/dispatch.py` | launch_command has no reader |
| `SW-RT-002` | fixes `routing/faigate_adapter.py` | availability consults the roster |
| `SW-RT-003` | `routing/harness.py` | no notion of the executing harness |
| `SW-RT-R` | — | the standard case runs end to end |

## 5. Key design decision: harness and profile stay separate

A profile carries no harness. A harness maps to one or more profile names.

The alternative — a `harness:` field inside each profile — makes the
cross-product the maintenance surface. Four harnesses and three profiles become
twelve declarations that must be kept in step, and "how I work" has to be
changed in four places. Separated, it stays three profiles plus a mapping, and
the operator's standard case is one line rather than the only possible case.

```yaml
harnesses:
  claude:       [langevc-standard]
  codex:        [elementeer-standard]
  antigravity:  [capacium-standard, capacium-deep]

profiles:
  langevc-standard:
    roles:
      ops:      { model: deepseek-v4-pro, tool: { name: opencode, ... } }
      reviewer: { model: deepseek-v4-pro, tool: { name: opencode, ... } }
```

## 6. Success metrics

Binary, each with a red proof that fails against `478211f`:

- A stub tool named only in a profile produces an artifact bound to the run.
- A profile pinning `deepseek-v4-pro` loads.
- A profile declaring a harness is refused, naming the field.
- No specific tool name appears anywhere under `src/skillweave/routing/`.
- Unit suite at or above the measured 1.3.5 baseline, both numbers reported.

## 7. Out of scope

- Relinking Antigravity off `~/.skillweave/skills/` onto the Capacium package.
  It is an April copy, 4890 bytes smaller than canonical, and it blocks using
  Antigravity as a test harness — but it is capacium `FEAT-003`, not this.
- Any Codex, Antigravity or Cursor integration. Criterion 2 of `SW-RT-001`
  exists so those cost a declaration later, not a change here.
- Wizard or recommendation for choosing a profile.

## 8. Constraints

- Every proof runs under `bash -eo pipefail`. Checked in the login shell does
  not count as checked (`LVC-214`).
- Lanes touch disjoint files. `faigate_adapter.py` belongs to `SW-RT-002`
  alone, `profile.py` to `SW-RT-003` alone.
- Everything landing in the repository is English (`LVC-217`).
- Reviewer does not repair. A wrong lane goes back to that lane.
