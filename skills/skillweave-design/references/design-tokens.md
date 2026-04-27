# Design Tokens Reference

Standardisiertes Token-Format für Farben, Typografie und Abstände. Ausgabe von `command="tokens"`.

---

## Token Format

### Colors (System Slot)

Vier Hauptfarben-Slots — angelehnt an das Elementor Global Colors System:

| Slot | Purpose | Example |
|------|---------|---------|
| `primary` | Brand-Hauptfarbe, CTAs, aktive Elemente | `#2563EB` |
| `secondary` | Brand-Sekundärfarbe, Highlights | `#7C3AED` |
| `text` | Lesefarbe für Fließtext | `#1F2937` |
| `accent` | Akzentfarbe für Hover, Fokus, Status | `#F59E0B` |

### Colors (Custom Slots)

Zusätzliche benannte Farben — für Surfaces, Borders, States:

```yaml
surfaces:
  - name: background
    hex: "#F9FAFB"
    usage: "Page background"
  - name: card
    hex: "#FFFFFF"
    usage: "Card/surface background"
  - name: border
    hex: "#E5E7EB"
    usage: "Divider and border lines"

states:
  hover: "#1D4ED8"
  error: "#EF4444"
  success: "#10B981"
  warning: "#F59E0B"
```

### Typography

| Token | Type | Example |
|-------|------|---------|
| `font_family_primary` | string | `"Inter, system-ui, sans-serif"` |
| `font_family_secondary` | string | `"Georgia, serif"` |

Type Scale (modular scale, ratio 1.25):

| Name | Size | Weight | Line Height | Usage |
|------|------|--------|-------------|-------|
| `h1` | 48px | 700 | 1.2 | Page title |
| `h2` | 38px | 700 | 1.25 | Section heading |
| `h3` | 30px | 600 | 1.3 | Subsection heading |
| `h4` | 24px | 600 | 1.35 | Card heading |
| `body` | 16px | 400 | 1.6 | Paragraph text |
| `small` | 14px | 400 | 1.5 | Captions, meta |

### Spacing

Spacing Scale (4px base unit):

```yaml
unit: 4px
scale: [4px, 8px, 12px, 16px, 20px, 24px, 32px, 40px, 48px, 64px, 80px, 96px]
aliases:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
```

---

## Elementify Integration

Die extrahierten Tokens können direkt in Elementify-Global-Styles geschrieben werden:

```yaml
# Mapping: skillweave-design tokens → elementify_set_global_colors
elementify_colors:
  - title: Primary
    color: "#2563EB"
  - title: Secondary
    color: "#7C3AED"
  - title: Text
    color: "#1F2937"
  - title: Accent
    color: "#F59E0B"

# Mapping: skillweave-design typography → elementify_set_global_typography
elementify_typography:
  - title: Primary
    font_family: "Inter"
    font_size: 16
    font_weight: "400"
    line_height: 1.6
```

Siehe `elementify_set_global_colors` und `elementify_set_global_typography` in der Elementify-Tool-Dokumentation.

---

## Example: Complete Token Set

```yaml
design_tokens:
  project: "SaaS Dashboard"
  version: "0.1.0"

  colors:
    primary:
      hex: "#2563EB"
      usage: "Buttons, links, active nav items"
    secondary:
      hex: "#7C3AED"
      usage: "Secondary CTAs, feature badges"
    text:
      hex: "#1F2937"
      usage: "Body text, headings"
    accent:
      hex: "#F59E0B"
      usage: "Warnings, ratings, highlights"
    surfaces:
      - name: background
        hex: "#F9FAFB"
      - name: card
        hex: "#FFFFFF"
      - name: sidebar
        hex: "#111827"
      - name: input
        hex: "#FFFFFF"

  typography:
    font_family_primary: "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    font_family_secondary: "Georgia, Cambria, Times New Roman, serif"
    scale:
      - name: h1
        size: 48px
        weight: "700"
        line_height: 1.2
      - name: h2
        size: 38px
        weight: "700"
        line_height: 1.25
      - name: h3
        size: 30px
        weight: "600"
        line_height: 1.3
      - name: h4
        size: 24px
        weight: "600"
        line_height: 1.35
      - name: body
        size: 16px
        weight: "400"
        line_height: 1.6
      - name: small
        size: 14px
        weight: "400"
        line_height: 1.5
      - name: mono
        size: 14px
        weight: "400"
        line_height: 1.6
        family: "JetBrains Mono, monospace"

  spacing:
    unit: 4px
    scale: [4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96]
    aliases:
      xs: 4px
      sm: 8px
      md: 16px
      lg: 24px
      xl: 32px
      xxl: 48px
```
