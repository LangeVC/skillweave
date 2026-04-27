# Design Commands Reference

Functional specifications for all design commands — signatures, parameters, return formats, and examples.

---

## apply_lens

Wendet die 6 Workshop-Regeln und 5 UX-Prinzipien auf einen Design-Input an.

### Function Signature
```
apply_lens(design_brief: str) -> LensReport
```

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `design_brief` | `str` | yes | Design-Beschreibung, Spezifikation oder Pfad zu einer Datei |

### Return Format
```yaml
lens_report:
  workshop_rules:
    value_ge_noise:
      score: <int 0-10>
      evidence: "<concrete observation>"
    scan_before_read:
      score: <int 0-10>
      evidence: "<concrete observation>"
    hierarchy_of_needs:
      score: <int 0-10>
      evidence: "<concrete observation>"
    progressive_disclosure:
      score: <int 0-10>
      evidence: "<concrete observation>"
    recognition_over_recall:
      score: <int 0-10>
      evidence: "<concrete observation>"
    error_tolerance:
      score: <int 0-10>
      evidence: "<concrete observation>"
  ux_principles:
    clarity_over_creativity:
      score: <int 0-10>
      evidence: "<concrete observation>"
    consistency_over_break:
      score: <int 0-10>
      evidence: "<concrete observation>"
    feedback_over_silence:
      score: <int 0-10>
      evidence: "<concrete observation>"
    proximity_alignment:
      score: <int 0-10>
      evidence: "<concrete observation>"
    less_is_more:
      score: <int 0-10>
      evidence: "<concrete observation>"
  improvements:
    - priority: "<high|medium|low>"
      finding: "<description>"
      suggestion: "<concrete improvement>"
```

### Example
**Input:**
```yaml
design_brief: "Modern SaaS Dashboard with dark mode, real-time charts, collapsible sidebar, and notification center"
```

**Output (compact):**
```yaml
lens_report:
  workshop_rules:
    hierarchy_of_needs:
      score: 7
      evidence: "Navigation and data visibility addressed first"
    scan_before_read:
      score: 6
      evidence: "Dashboard layout suggests scanning hierarchy but sidebar collapse state unclear"
  ux_principles:
    less_is_more:
      score: 5
      evidence: "Notification center risks feature creep — scope missing"
  improvements:
    - priority: high
      finding: "No loading/empty/error states defined"
      suggestion: "Specify skeleton screens for chart loading, empty states for zero data"
```

---

## evaluate_design

Evaluiert ein Design gegen die 5 UX-Prinzipien und gibt eine priorisierte Scorecard zurück.

### Function Signature
```
evaluate_design(design: str, criteria: list[str] | None = None) -> EvaluationReport
```

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `design` | `str` | yes | Design-Beschreibung, Komponenten-Spezifikation oder Dateipfad |
| `criteria` | `list[str]` | no | Zu prüfende Prinzipien (default: alle 5) |

### Return Format
```yaml
evaluation_report:
  scores:
    clarity_over_creativity: <int 0-10>
    consistency_over_break: <int 0-10>
    feedback_over_silence: <int 0-10>
    proximity_alignment: <int 0-10>
    less_is_more: <int 0-10>
  total_score: <float 0-50>
  percentage: <float 0-100>
  priority_items:
    - priority: "<critical|high|medium|low>"
      principle: "<principle name>"
      issue: "<specific finding>"
      fix: "<actionable recommendation>"
```

### Example
**Input:**
```yaml
design: "Button component: blue background, white text, 8px radius, hover darkens"
criteria: ["consistency_over_break", "feedback_over_silence", "less_is_more"]
```

**Output:**
```yaml
evaluation_report:
  scores:
    consistency_over_break: 8
    feedback_over_silence: 9
    less_is_more: 7
  total_score: 24.0
  percentage: 80.0
  priority_items:
    - priority: medium
      principle: less_is_more
      issue: "No disabled/loading state defined"
      fix: "Add opacity-50 + cursor-not-allowed for disabled, spinner for loading"
```

---

## extract_tokens

Extrahiert Farben, Typografie und Spacing aus einem Design-Input als strukturiertes Token-Set.

### Function Signature
```
extract_tokens(design: str) -> DesignTokenSet
```

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `design` | `str` | yes | Design-Spezifikation, Style-Guide, Figma-Export oder Pfad |

### Return Format
```yaml
design_tokens:
  colors:
    primary:
      hex: "<#hex>"
      usage: "<description>"
    secondary:
      hex: "<#hex>"
      usage: "<description>"
    text:
      hex: "<#hex>"
      usage: "<description>"
    accent:
      hex: "<#hex>"
      usage: "<description>"
    surfaces:
      - name: "<name>"
        hex: "<#hex>"
        usage: "<description>"
  typography:
    font_family_primary: "<family>"
    font_family_secondary: "<family>"
    scale:
      - name: "<h1|h2|h3|h4|body|small>"
        size: "<px>"
        weight: "<weight>"
        line_height: "<ratio>"
  spacing:
    unit: "<px>"
    scale: [<values>]
```
