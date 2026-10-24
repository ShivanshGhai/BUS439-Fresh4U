---
name: Fresh4U Labour Planner
description: A grower's season wall planner, as a working app.
colors:
  ink: "#16191D"
  ink-2: "#3F444C"
  muted: "#5F656E"
  house: "#0D4B2A"
  brand-green: "#00972D"
  green-dark: "#0A7D2C"
  green-tint: "#E3F2E6"
  highlight: "#C6EBCF"
  tomato: "#D7261E"
  tomato-text: "#B3211A"
  tomato-tint: "#FCEBEA"
  amber: "#C98500"
  amber-text: "#8A5A00"
  amber-tint: "#FBF3E2"
  paper: "#F3F5F2"
  rule: "#D5DBD3"
  grid: "#E9ECE7"
  white: "#FFFFFF"
  cat-tomato-harvest: "#1E8A3C"
  cat-tomato-crop-work: "#2F67B1"
  cat-packing: "#C98500"
  cat-strawberry-harvest: "#8E5AA8"
  cat-strawberry-crop-work: "#2A9D8F"
  cat-clean-out: "#B4475E"
  cat-pest-general: "#9AA0A6"
  cat-breaks: "#CDD1D6"
typography:
  app-title:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "2.3rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.01em"
  section:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.65rem"
    fontWeight: 750
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  answer:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.45rem"
    fontWeight: 500
    lineHeight: 1.35
  figure:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "2.3rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.84rem"
    fontWeight: 600
    lineHeight: 1.3
rounded:
  sm: "2px"
  md: "6px"
  lg: "8px"
  xl: "10px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  header-band:
    backgroundColor: "{colors.house}"
    textColor: "{colors.white}"
    rounded: "{rounded.xl}"
    padding: "16px 22px"
  tab-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    rounded: "{rounded.md}"
  note:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "14px 18px"
  note-check:
    backgroundColor: "{colors.amber-tint}"
  note-failed:
    backgroundColor: "{colors.tomato-tint}"
  answer-equals:
    backgroundColor: "{colors.house}"
    textColor: "{colors.white}"
    rounded: "{rounded.lg}"
---

# Fresh4U Labour Planner: design system

## Overview
The app is drawn as a grower's season wall planner: white paper, an ink-black week grid, crop phases as flat colour
bands and condensed figures. It is an Operate surface, so navigation and controls stay standard Streamlit. The
planner supplies four things: the typeface, the palette, the density, and one signature, the **Season strip**.

Every tab follows the same order: Season strip (the tab's weeks marked) → question as heading → **answer sentence**
with its number set big → ruled row of figures → chart or table → short numbered notes. Method notes live in expanders.

## Colors
- **House green** fills the header band. **Ink** is the text colour, the heavy rules, the selected tab and the
  Season-strip marker.
- State colours mean one thing each: **amber** = something to check, **tomato red** = a check failed (never
  decoration, never a data series), **green** = passed.
- Activity colours (`cat-*`) are fixed per activity on every chart and in the strip. They were validated for
  colour-blind separation; tomato harvest is green (the vine), so red stays reserved for failures.
- Body text ≥ 4.5:1 everywhere. Red text on the red tint uses `tomato-text`.

## Typography
One family: **Archivo** (variable weight 100–900, width 62–125), served from `static/Archivo.woff` (latin subset,
OFL) so it works offline. Figures, the app title and the answer numbers use width 78% (condensed) at weight 800,
with tabular lining numerals. Headings run 700–750 at normal width. Never use small caps or a tracked uppercase label above a heading.

## Layout
Max width 1280px. Rows of figures are a grid ruled by a 2px ink line on top and 1px hairlines between figures,
one row up to 5 figures (6 → 3 + 3). Below 900px they wrap with a hairline over each figure. Steps run 4 across,
2 × 2 under 900px and 1 under 520px. On phones the strip hides its SVG labels and names the marked weeks in text.

## Elevation & Depth
Flat, like print. No shadows; depth comes from ink rules, hairlines and the paper tint.

## Shapes
Small radii: 2px on colour keys and bars, 6px on tabs and controls, 8px on notes, 10px on the header band.
Number markers on notes and steps are ink circles.

## Components
- **Season strip** (`app_ui.season_strip`): 52 week columns, height = people needed, colour = the activity with
  most hours that week, dashed ink crew line, heavy baseline, month names. `mark=` takes the weeks the tab is about;
  they get ink brackets above and below and everything else drops to 32% opacity. Hovering a week shows its tooltip.
- **Answer** (`app_ui.answer`): one sentence. The first `**bold**` is the headline number with a marker-pen
  highlight (green, amber with `tone="warn"`, red with `tone="bad"`).
- **Figures** (`app_ui.kpis` + `kpi_html`): a coloured key square before the label carries the tone. Values do not wrap.
- **Notes** (`app_ui.callout`): paper-tint block, a bold heading with a key square, numbered items.
- **Equation** (planner): bordered cells with the result as a solid house-green cell.
- Motion: button press scales to 0.97 over 140ms, `cubic-bezier(0.23, 1, 0.32, 1)`. Tabs and strip fade colour over 150ms.
  Nothing animates on entrance: Streamlit reruns on every control change. Reduced motion removes the press scale.

## Do's and Don'ts
- Do lead every tab with its answer sentence and mark the tab's weeks on the strip.
- Do keep red for failed checks only.
- Don't add same-size cards, a coloured side stripe on notes, gradient text, or an uppercase label above a heading.
- Don't add a second typeface; use Archivo's width axis for contrast.
