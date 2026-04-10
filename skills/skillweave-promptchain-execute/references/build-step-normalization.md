# Build-Step Normalization

## Required Fields for Build-Oriented Execution

Each implementation step in a build sequence should define or be normalized into these fields:

### 1. `id`
- **Purpose**: Unique identifier for the step
- **Format**: String, e.g., `"ADV-006"`, `"ui-component-1"`
- **Normalization**: If missing, generate from title (slugified)

### 2. `title`
- **Purpose**: Human-readable description
- **Format**: String, e.g., `"Deepen advanced workflow differentiation"`
- **Normalization**: Required, cannot be empty

### 3. `depends_on`
- **Purpose**: Step dependencies for execution ordering
- **Format**: Array of step IDs, e.g., `["ADV-005", "UI-003"]`
- **Normalization**: Default to empty array `[]` if missing
- **Special values**:
  - `["*"]` = depends on all previous steps (conservative)
  - `[]` = independent, can run in parallel

### 4. `required_capabilities`
- **Purpose**: Agent capabilities needed for execution
- **Format**: Array of strings, e.g., `["code_generation", "testing", "review"]`
- **Normalization**: Infer from step type and content:
  - Code changes → `["code_generation"]`
  - Tests → `["testing"]`
  - Documentation → `["documentation"]`
  - Research → `["research"]`
  - Review → `["review"]`
- **Default**: `["general"]` if unclear

### 5. `write_scope`
- **Purpose**: Files, directories, or system surfaces this step will modify
- **Format**: Array of paths/identifiers, e.g., `["mcp-server/src/advanced-workflows.ts", "mcp-server/src/tools/advanced-workflows.ts"]`
- **Normalization**: Critical for parallelization safety:
  - If missing, analyze step description for file mentions
  - If unclear, assume conservative write scope (entire module)
  - Mark as `["unknown"]` if truly indeterminate
- **Special values**:
  - `["config"]` = configuration files
  - `["schema"]` = schema definitions
  - `["tests"]` = test files only
  - `["docs"]` = documentation only

### 6. `verification`
- **Purpose**: How to verify this step completed successfully
- **Format**: Array of verification criteria, e.g., `["targeted tests pass", "tier registration stays consistent"]`
- **Normalization**: Required for build steps:
  - Code steps: `["compiles", "tests pass", "no type errors"]`
  - Config steps: `["validates against schema", "applies without errors"]`
  - Test steps: `["tests run", "coverage maintained"]`
- **Default**: `["manual review required"]` if no automated verification possible

### 7. `integration_gate`
- **Purpose**: When to validate integration with other components
- **Format**: String, one of:
  - `"pre"` = validate before implementation
  - `"post"` = validate after implementation
  - `"both"` = validate before and after
  - `"none"` = no integration gate
- **Normalization**:
  - Steps with wide write scope → `"both"`
  - Isolated changes → `"post"`
  - Configuration changes → `"pre"`
- **Default**: `"post"`

### 8. `retry_budget`
- **Purpose**: How many retry attempts allowed before marking as blocked
- **Format**: Integer, e.g., `2`
- **Normalization**:
  - Simple steps: `1`
  - Complex steps: `2`
  - High-risk steps: `3`
- **Default**: `2`

### 9. `handoff_contract`
- **Purpose**: What to deliver when step completes
- **Format**: Array of deliverables, e.g., `["files_changed", "tests_run", "known_limitations", "next_best_slice"]`
- **Normalization**: Required for build steps:
  - Minimum: `["implementation_summary", "verification_status"]`
  - Recommended: `["files_changed", "tests_run", "known_limitations", "next_best_slice"]`
- **Default**: `["implementation_summary", "verification_status"]`

## Normalization Process

### Step 1: Classification
- Determine if step is `plan`, `build`, or `meta`
- Build steps require full normalization
- Plan steps require simplified normalization (focus on outputs)
- Meta steps (coordination, review) require minimal normalization

### Step 2: Field Inference
- Parse step description for implicit information
- Use context from previous steps
- Apply conservative defaults when uncertain
- Flag steps that cannot be normalized safely

### Step 3: Validation
- Check for contradictions (e.g., parallelizable but depends on many steps)
- Verify write scopes don't conflict with dependent steps
- Ensure verification criteria are achievable
- Validate retry budget is appropriate for complexity

### Step 4: Sequence Hardening
If normalization fails (missing critical information):
1. Stop execution
2. Emit sequence-hardening recommendation
3. List missing fields with examples
4. Suggest how to fix the sequence
5. Do not proceed with execution

## Examples

### Well-Normalized Step
```yaml
id: "ADV-006"
title: "Deepen advanced workflow differentiation"
depends_on: ["ADV-005"]
required_capabilities: ["code_generation", "testing", "review"]
write_scope: [
  "mcp-server/src/advanced-workflows.ts",
  "mcp-server/src/tools/advanced-workflows.ts",
  "mcp-server/src/__tests__/advanced-workflows.test.ts"
]
verification: [
  "targeted tests pass",
  "tier registration stays consistent"
]
integration_gate: "product-surface gate remains green"
retry_budget: 2
handoff_contract: [
  "files_changed",
  "tests_run",
  "known_limitations",
  "next_best_slice"
]
```

### Minimal Acceptable Step
```yaml
id: "config-001"
title: "Update configuration for new feature"
depends_on: []
required_capabilities: ["configuration"]
write_scope: ["config/feature.yaml"]
verification: ["config validates"]
integration_gate: "pre"
retry_budget: 1
handoff_contract: ["config_updated"]
```