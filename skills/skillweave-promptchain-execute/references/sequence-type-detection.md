# Sequence Type Detection

Detect whether a prompt sequence is **plan mode**, **build mode**, or **mixed** to adapt validation and execution appropriately.

## Detection Heuristics

### 1. Metadata Analysis
- Check `metadata.domain`: 
  - Plan domains: `strategy`, `business`, `research`, `wellness`, `marketing`, `consulting`, `analysis`, `planning`
  - Build domains: `development`, `coding`, `software`, `web`, `mobile`, `api`, `infrastructure`, `devops`, `automation`
- Check `metadata.intent`:
  - Plan intents: `generate`, `analyze`, `evaluate`, `plan`, `strategize`, `research`
  - Build intents: `implement`, `develop`, `code`, `build`, `deploy`, `test`, `debug`
- Check `metadata.mode` if present (optional field):
  - `plan`: explicitly plan mode
  - `build`: explicitly build mode  
  - `mixed`: explicitly mixed mode

### 2. Step Purpose Analysis
- Scan `purpose` fields in sequence steps for keywords:
  - **Plan keywords**: `analyze`, `evaluate`, `research`, `plan`, `strategize`, `assess`, `recommend`, `design` (conceptual), `model`, `forecast`, `estimate`, `brainstorm`
  - **Build keywords**: `implement`, `code`, `develop`, `build`, `create` (tangible), `deploy`, `test`, `debug`, `integrate`, `configure`, `automate`, `script`, `generate` (code/files), `refactor`, `optimize`
- Count plan vs build steps; majority determines primary mode

### 3. Output Analysis  
- Check `outputs_required` and `final_deliverable_format`:
  - Plan outputs: `report`, `document`, `strategy`, `plan`, `analysis`, `summary`, `presentation`, `slide deck`, `business model`, `framework`
  - Build outputs: `code`, `script`, `file`, `module`, `library`, `API`, `configuration`, `package`, `docker`, `database`, `schema`, `test`, `documentation` (technical)

### 4. Usage Notes Analysis
- Check `usage_notes.execution_mode`:
  - `strict_sequential`, `iterative`, `exploratory` → often plan
  - `parallel`, `automated`, `ci_cd` → often build
- Check `usage_notes.web_research`, `citations` → more common in plan
- Check `usage_notes.intermediate_validation` → both

## Decision Logic

1. **Explicit mode** in metadata → use that mode
2. **Domain/intent strongly indicates** → use indicated mode  
3. **Step purpose majority** (>66% one type) → use that mode
4. **Mixed signals** (40-60% split) → classify as `mixed`
5. **Equal signals** → classify as `mixed`

## Output Adaptation

### Plan Mode
- Structure outputs as human-readable documents
- Use sections: Executive Summary, Analysis, Recommendations, Next Steps
- Focus on clarity, narrative, business value
- Format as `.md` with clear headings and bullet points

### Build Mode  
- Structure outputs as machine-readable artifacts + technical documentation
- Generate actual code/files with appropriate extensions
- Include technical specifications, API docs, deployment guides
- Format as separate files with accompanying README

### Mixed Mode
- Separate plan and build components clearly
- Create plan documents AND build artifacts
- Indicate which outputs correspond to which mode
- Consider initiating development pipeline for build components

## Examples

### Plan Example
```
metadata:
  domain: wellness
  intent: evaluate
  title: Wellness Business Evaluation
step purposes: analyze, evaluate, recommend, plan
outputs: business plan, recommendations
→ PLAN MODE
```

### Build Example  
```
metadata:
  domain: web development
  intent: implement
  title: Website Prototype
step purposes: implement, code, test, deploy
outputs: React components, API endpoints, deployment config
→ BUILD MODE
```

### Mixed Example
```
metadata:
  domain: product development
  intent: generate
  title: MVP Planning + Implementation
step purposes: analyze, plan, design, implement, test
outputs: product spec, wireframes, React components, test suite
→ MIXED MODE
```