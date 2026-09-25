# Item 001 — Neutral wording describing the work in general terms

## 1. Executive summary

A recent release shipped a routing layer with every part of a dispatch except
the seam that joins them. A profile can name a target tool and its launch
command; nothing starts it. A profile can pin a model; the check that admits it
consults the wrong table. A profile can be one of several; nothing knows which
harness is asking.

This closes all three. It is the first work that makes the release's headline
claim true rather than declared.

## 2. Problem statement

Measured on a stated date against the released tree (a version and a
short commit identifier):

```
field_a                     required by one record type, ZERO readers outside
                            a single module              -> nothing dispatches

field_b                     gates on a derived identifier, drawn from the
                            central register             -> refuses a model
                                                            with a false message

field_c                     ZERO references in the routing and runtime areas
                                                         -> no per-harness selection
```

A role record says where a role is dispatched **to**. Nothing says where
**from**. The adapter needs both, which is why this is one piece of work and
not three.

The failure mode is the one this organisation keeps paying for: a declaration
that reads as a capability. The release note states that a role with a target
tool is dispatched there. A reader would not learn otherwise without grepping
for the field.

## 3. Users

The operator running five to fifteen parallel agent sessions across four
harnesses, who wants the routing decision to be data rather than whichever
tool the session happens to sit in.

Second, any consumer of the open core: the adapter is the general one, so a
fifth harness costs a declaration rather than a branch.

## 4. Solution overview

Three lanes on disjoint files, then a gate that runs the real case.

| Lane | Adds | Closes |
|------|------|--------|
| `LANE-A0` | `area/one/file.py` | field_a has no reader |
| `LANE-A1` | fixes `area/two/file.py` | the gate consults the roster |
| `LANE-A2` | `area/three/file.py` | no notion of the executing harness |
| `LANE-A3` | — | the standard case runs end to end |

## 5. Key design decision: harness and profile stay separate

A profile carries no harness. A harness maps to one or more profile names.

The alternative — a `harness:` field inside each profile — makes the
cross-product the maintenance surface. Four harnesses and three profiles become
twelve declarations that must be kept in step, and "how I work" has to be
changed in four places. Separated, it stays three profiles plus a mapping, and
the operator's standard case is one line rather than the only possible case.

```yaml
harnesses:
  alpha:        [profile-one]
  beta:         [profile-two]
  gamma:        [profile-three, profile-four]

profiles:
  profile-one:
    roles:
      ops:      { model: model-1, tool: { name: tool-1, ... } }
      reviewer: { model: model-1, tool: { name: tool-1, ... } }
```

## 6. Success metrics

Binary, each with a red proof that fails against the baseline:

- A stub tool named only in a profile produces an artifact bound to the run.
- A profile pinning a specific model loads.
- A profile declaring a harness is refused, naming the field.
- No specific tool name appears anywhere under the routing area.
- Unit suite at or above the measured baseline, both numbers reported.

## 7. Out of scope

- Relinking one harness off its local skills directory onto the packaged form.
  It is an older copy, slightly smaller than canonical, and it blocks using
  that harness as a test harness — but it is a separate feature, not this.
- Any further harness integration. Criterion 2 of `LANE-A0` exists so those
  cost a declaration later, not a change here.
- Wizard or recommendation for choosing a profile.

## 8. Constraints

- Every proof runs under `bash -eo pipefail`. Checked in the login shell does
  not count as checked (policy reference one).
- Lanes touch disjoint files. `area/two/file.py` belongs to `LANE-A1` alone,
  `area/one/file.py` to `LANE-A2` alone.
- Everything landing in the repository is a single language (policy
  reference two).
- Reviewer does not repair. A wrong lane goes back to that lane.
