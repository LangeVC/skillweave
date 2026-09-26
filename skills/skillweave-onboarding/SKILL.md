---
name: skillweave-onboarding
description: "Run operator onboarding — collect role, purpose, autonomy, and risk boundary; persist durable profile and generated state."
argument-hint: 'role="[operator|developer|reviewer|researcher]" purpose="[build|review|research|operate]" autonomy="[guided|supervised|autonomous]" risk_boundary="[conservative|medium|unicorn]"'
---

# /skillweave-onboarding

> Canonical metadata is English. User-facing artifacts follow the output language setting.

**Operator onboarding for the SkillWeave lifecycle.**  
This skill collects an operator's role, purpose, desired autonomy and risk
boundary through closed-choice questions with usable defaults. It persists
durable authored input to ``skillweave.config/`` and generated state to
``.skillweave/``, and is idempotent: re-running with the same profile
produces the same result.

## Responsibilities

| Activity | Description |
|----------|-------------|
| Profile collection | Collect role, purpose, autonomy, risk boundary |
| Phase detection | Detect the project's current lifecycle phase |
| Goal setting | Capture the operator's stated goal |
| Preview | Show what would be persisted without writing |
| Durable persistence | Store profile in ``skillweave.config/`` |
| Generated state | Store onboarding result in ``.skillweave/`` |
| Idempotence | Re-running with the same profile is a no-op |
| Reprofiling | Changing profile fields produces a structured diff |

## Usage

```
skillweave-onboarding                                               # Interactive (all defaults)
skillweave-onboarding role="developer" purpose="build"              # Partial overrides
skillweave-onboarding autonomy="autonomous" risk_boundary="unicorn" # Risk-on profile
```

## Parameters

- `role` (optional): Operator role — `operator`, `developer`, `reviewer`, `researcher`. Default: `developer`.
- `purpose` (optional): Onboarding purpose — `build`, `review`, `research`, `operate`. Default: `build`.
- `autonomy` (optional): Desired autonomy — `guided`, `supervised`, `autonomous`. Default: `guided`.
- `risk_boundary` (optional): Risk boundary — `conservative`, `medium`, `unicorn`. Default: `conservative`.

Any omitted parameter takes its documented default. All parameters are
closed-choice; an undeclared value falls back to the default.

## Preview Mode

Prefix the invocation with `preview=true` to see the onboarding result
without persisting anything:

```
skillweave-onboarding preview=true role="reviewer" purpose="review"
```

## Testing

```bash
python -m pytest tests/integration/test_onboarding_facades.py -v --tb=short
```
