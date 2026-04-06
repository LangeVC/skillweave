# Architecture

## Layers

### 1. Skill layer
Human-readable instructions for when and how to use a skill.

### 2. Sequence specification layer
Standardized structure for prompt chains.

### 3. Validation layer
Checks structure, completeness, and consistency.

### 4. Orchestration layer
Decides which step runs next and whether a step is complete.

### 5. Execution layer
Performs step work and records outputs.

## MVP boundary

The MVP is intentionally small:
- one skill
- one format
- sequential flow
- minimal schemas
