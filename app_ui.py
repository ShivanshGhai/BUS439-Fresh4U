"""
Look and feel for the Streamlit app: the season-planner visual system, small HTML components
and the Altair charts. Kept out of streamlit_app.py so the page reads as a story.

The world is a grower's season wall planner: white paper, an ink-black week grid, crop phases as
flat colour bands, condensed figures. Its signature is the Season strip (season_strip), drawn at the
top of every tab with the weeks that tab is about marked.

Brand colours from The Fresh4U Group logo (assets/fresh4u_group_logo.png): green #00972D (swoosh),
tomato #F91C1C (the "O"). Red is used only for checks that failed.
"""
from __future__ import annotations

import base64
import datetime as _dt
import html
import os
import re
import zlib

import altair as alt
import pandas as pd
import streamlit as st

TEAM = "GLW BC"
_HERE = os.path.dirname(os.path.abspath(__file__))

# ---- colour tokens ------------------------------------------------------------------------
INK = "#16191D"          # planner ink: text, heavy rules, the week marker
INK_2 = "#3F444C"        # secondary text that still has to read on a projector
MUTED = "#5F656E"        # captions (4.5:1 on white and on PAPER)
HOUSE = "#0D4B2A"        # greenhouse green: the header band
GREEN = "#00972D"        # logo swoosh
GREEN_DARK = "#0A7D2C"   # buttons and green text on white (contrast)
GREEN_TINT = "#E3F2E6"
HIGHLIGHT = "#C6EBCF"    # marker-pen highlight behind the lead number
TOMATO = "#D7261E"       # logo tomato, darkened for text; only for checks that failed
TOMATO_TINT = "#FCEBEA"
TOMATO_TEXT = "#B3211A"   # red text on the red tint (4.5:1+)
AMBER = "#C98500"        # things a supervisor should look at (not failures)
AMBER_TEXT = "#8A5A00"
AMBER_TINT = "#FBF3E2"
PAPER = "#F3F5F2"        # second neutral layer: sidebar, notes
RULE = "#D5DBD3"         # hairlines
GRID = "#E9ECE7"
SLATE = "#565963"        # logo slate, for reference lines
SLATE_DARK = "#43464F"
SURFACE_ALT = PAPER
BORDER = RULE

# Categorical palette for tasks (validated for colour-blind separation and 3:1 contrast on white).
# Assigned to tasks in order of total hours, so a task keeps its colour on every chart and filter.
TASK_PALETTE = ["#1E8A3C", "#2F67B1", "#C98500", "#8E5AA8", "#2A9D8F", "#B4475E", "#7C8A2A"]
OTHER = "#9AA0A6"

BAND_COLORS = {"Strong": "#1E8A3C", "Typical": "#8A8F99", "Developing": "#C98500",
               "Ramping up": "#2F67B1", "Not enough data": "#C5C9CF"}

FONT = "'Archivo', 'Archivo F4', 'Helvetica Neue', Arial, sans-serif"


# ---- version-safe width ---------------------------------------------------------------------
def _ver():
    try:
        return tuple(int(x) for x in st.__version__.split(".")[:2])
    except Exception:
        return (1, 32)


def stretch() -> dict:
    """Full-width keyword for st.dataframe / st.altair_chart across Streamlit versions."""
    return {"width": "stretch"} if _ver() >= (1, 46) else {"use_container_width": True}


# ---- page styling ---------------------------------------------------------------------------
CSS = f"""
<style>
@font-face {{ font-family: 'Archivo F4'; src: url('/app/static/Archivo.woff') format('woff');
  font-weight: 100 900; font-stretch: 62% 125%; font-display: swap; }}
:root {{ --f4-ease-out: cubic-bezier(0.23, 1, 0.32, 1); --f4-press: 140ms; --f4-colour: 150ms;
  --f4-font: 'Archivo F4', 'Archivo', 'Helvetica Neue', Arial, sans-serif; }}
html {{ -webkit-tap-highlight-color: transparent; }}
::selection {{ background: {HIGHLIGHT}; color: {INK}; }}
input, textarea {{ caret-color: {GREEN_DARK}; }}
:focus-visible {{ outline: 2px solid {GREEN_DARK}; outline-offset: 2px; }}

.block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1280px; }}
.f4, .f4 * {{ font-family: var(--f4-font); }}
.f4 [data-testid="stHeaderActionElements"], .f4-section a[href^="#"], .f4-head a[href^="#"] {{ display: none !important; }}
h1, h2, h3 {{ letter-spacing: -0.015em; }}
[data-testid="stSidebar"] {{ border-right: 1px solid {RULE}; }}
[data-testid="stSidebar"] hr {{ margin: 0.8rem 0; }}

/* tabs: planner index tabs, ink when selected (role selectors cover old BaseWeb and new react-aria tabs) */
.stTabs [role="tablist"] {{ gap: 0.15rem; border-bottom: 2px solid {INK}; }}
.stTabs [role="tab"] {{ padding: 0.5rem 0.95rem !important; font-weight: 650; color: {MUTED}; border-radius: 6px 6px 0 0;
  transition: color var(--f4-colour) ease, background-color var(--f4-colour) ease; }}
.stTabs [role="tab"] p {{ font-size: 1rem; font-weight: 650; }}
@media (hover: hover) and (pointer: fine) {{ .stTabs [role="tab"]:hover {{ color: {INK}; background: {PAPER}; }} }}
.stTabs [role="tab"][aria-selected="true"] {{ color: #fff !important; background: {INK}; }}
.stTabs [role="tab"][aria-selected="true"] p {{ color: #fff !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"],
.stTabs .react-aria-SelectionIndicator {{ display: none !important; }}
/* tabs nested inside a tab (More) stay quiet: underline only */
.stTabs .stTabs [role="tablist"] {{ border-bottom: 1px solid {RULE}; }}
.stTabs .stTabs [role="tab"][aria-selected="true"] {{ color: {INK} !important; background: transparent;
  box-shadow: inset 0 -3px 0 {GREEN_DARK}; }}
.stTabs .stTabs [role="tab"][aria-selected="true"] p {{ color: {INK} !important; }}

/* press feedback on every button (download, upload, form) */
.stButton button, [data-testid="stDownloadButton"] button, [data-testid="stFormSubmitButton"] button,
[data-testid="stFileUploader"] button {{ font-weight: 650;
  transition: transform var(--f4-press) var(--f4-ease-out), background-color var(--f4-colour) ease,
              border-color var(--f4-colour) ease, color var(--f4-colour) ease; }}
.stButton button:active, [data-testid="stDownloadButton"] button:active,
[data-testid="stFormSubmitButton"] button:active, [data-testid="stFileUploader"] button:active {{
  transform: scale(0.97); }}

/* phones: inputs under 16px make iOS zoom the page and stay zoomed */
@media (pointer: coarse) {{
  input, textarea, [data-baseweb="select"] div, [data-baseweb="input"] input {{ font-size: 16px !important; }} }}
@media (prefers-reduced-motion: reduce) {{
  .stButton button, [data-testid="stDownloadButton"] button, [data-testid="stFormSubmitButton"] button,
  [data-testid="stFileUploader"] button {{ transition: background-color var(--f4-colour) ease; }}
  .stButton button:active, [data-testid="stDownloadButton"] button:active,
  [data-testid="stFormSubmitButton"] button:active, [data-testid="stFileUploader"] button:active {{ transform: none; }} }}

/* expanders read as the planner's back pages: quiet, ruled */
[data-testid="stExpander"] details {{ border-radius: 6px; border-color: {RULE}; }}
[data-testid="stExpander"] summary p {{ font-weight: 600; }}

/* ---- header band ---- */
.f4-head {{ background: {HOUSE}; color: #fff; border-radius: 10px; padding: 1rem 1.4rem;
  display: flex; align-items: center; justify-content: space-between; gap: 1rem 1.5rem; flex-wrap: wrap;
  margin-bottom: 1rem; }}
.f4-brand {{ display: flex; align-items: center; gap: 1.1rem; min-width: 0; }}
.f4-plate {{ background: #fff; border-radius: 8px; padding: 0.45rem 0.6rem; display: flex; flex: none; }}
.f4-plate img {{ width: 92px; height: auto; display: block; }}
.f4-head .title {{ font-size: 2.3rem; line-height: 1; font-weight: 800; font-stretch: 78%; letter-spacing: -0.01em;
  color: #fff; margin: 0; }}
.f4-head .sub {{ margin: 0.35rem 0 0; font-size: 0.98rem; color: #D4E8DA; max-width: 44rem; line-height: 1.4; }}
.f4-meta {{ display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }}
.f4-chip {{ font-size: 0.82rem; font-weight: 650; padding: 0.3rem 0.7rem; border-radius: 999px; white-space: nowrap;
  border: 1px solid rgba(255,255,255,0.35); color: #fff; }}
.f4-chip.data {{ background: #fff; color: {HOUSE}; border-color: #fff; }}
.f4-chip.data::before {{ content: ""; display: inline-block; width: 0.5rem; height: 0.5rem; border-radius: 50%;
  background: {AMBER}; margin-right: 0.4rem; vertical-align: 0.05em; }}
.f4-chip.data.real::before {{ background: {GREEN}; }}
@media (max-width: 640px) {{ .f4-head .title {{ font-size: 1.8rem; }} .f4-plate img {{ width: 72px; }} }}

/* ---- season strip (signature) ---- */
.f4-strip {{ margin: 0.9rem 0 0.4rem; }}
.f4-strip-top {{ display: flex; justify-content: space-between; align-items: baseline; gap: 0.4rem 1rem; flex-wrap: wrap;
  margin-bottom: 0.25rem; }}
.f4-strip-title {{ font-weight: 700; font-size: 0.92rem; color: {INK}; }}
.f4-strip-title span {{ color: {MUTED}; font-weight: 500; }}
.f4-legend {{ display: flex; gap: 0.25rem 0.9rem; flex-wrap: wrap; font-size: 0.8rem; color: {INK_2}; }}
.f4-legend i {{ display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 2px; margin-right: 0.3rem;
  vertical-align: -0.05em; }}
.f4-strip svg {{ width: 100%; height: auto; display: block; overflow: visible; }}
.f4-strip svg text {{ font-family: var(--f4-font); }}
.f4-strip .wk {{ transition: opacity var(--f4-colour) ease; }}
@media (hover: hover) and (pointer: fine) {{ .f4-strip .wk:hover {{ opacity: 1 !important; }} }}
.f4-strip-mark {{ display: none; font-weight: 800; font-size: 0.85rem; color: {INK}; }}
@media (max-width: 640px) {{ .f4-legend, .f4-strip svg text {{ display: none; }} .f4-strip-mark {{ display: block; }} }}

/* ---- section heading ---- */
.f4-section {{ margin: 1.1rem 0 0.5rem; }}
.f4-section .title {{ margin: 0; font-size: 1.65rem; font-weight: 750; line-height: 1.2; color: {INK};
  letter-spacing: -0.015em; text-wrap: balance; }}
.f4-section p {{ margin: 0.3rem 0 0; color: {MUTED}; font-size: 0.98rem; max-width: 62rem; }}

/* ---- the answer: one sentence, the number set big ---- */
.f4-answer {{ font-size: 1.45rem; line-height: 1.35; font-weight: 500; color: {INK}; margin: 0.5rem 0 1rem;
  max-width: 60rem; text-wrap: pretty; }}
.f4-answer b {{ font-weight: 800; font-stretch: 78%; font-size: 1.75em; line-height: 1; letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums lining-nums; white-space: nowrap; }}
.f4-answer b:first-of-type {{ background: linear-gradient(transparent 58%, {HIGHLIGHT} 58%, {HIGHLIGHT} 92%, transparent 92%);
  padding: 0 0.08em; }}
.f4-answer.warn b:first-of-type {{ background: linear-gradient(transparent 58%, #F6DFAE 58%, #F6DFAE 92%, transparent 92%); }}
.f4-answer.bad b:first-of-type {{ background: linear-gradient(transparent 58%, #F6C9C6 58%, #F6C9C6 92%, transparent 92%); }}
@media (max-width: 640px) {{ .f4-answer {{ font-size: 1.15rem; }} }}

/* ---- ledger of figures (the planner's legend row, not cards) ---- */
.f4-kpis {{ display: grid; grid-template-columns: repeat(var(--f4-cols, 4), minmax(0, 1fr));
  border-top: 2px solid {INK}; border-bottom: 1px solid {RULE}; margin: 0.4rem 0 1.1rem; }}
@media (max-width: 900px) {{ .f4-kpis {{ display: flex; flex-wrap: wrap; }}
  .f4-kpis > .f4-kpi {{ flex: 1 1 150px; box-shadow: none !important; border-top: 1px solid {RULE}; }} }}
.f4-kpi {{ padding: 0.7rem 1rem 0.75rem; min-width: 0; box-shadow: inset 1px 0 0 {RULE}; }}
.f4-kpis.c1 > .f4-kpi, .f4-kpis.c2 > .f4-kpi:nth-child(2n+1), .f4-kpis.c3 > .f4-kpi:nth-child(3n+1),
.f4-kpis.c4 > .f4-kpi:nth-child(4n+1), .f4-kpis.c5 > .f4-kpi:nth-child(5n+1) {{ box-shadow: none; }}
.f4-kpis.c3 > .f4-kpi:nth-child(n+4), .f4-kpis.c4 > .f4-kpi:nth-child(n+5) {{ border-top: 1px solid {RULE}; }}
.f4-kpi {{ display: flex; flex-direction: column; }}
.f4-kpi .label {{ font-size: 0.84rem; color: {INK_2}; font-weight: 600; display: flex; align-items: flex-start; gap: 0.4rem;
  line-height: 1.3; min-height: 2.6em; }}
@media (min-width: 1100px) {{ .f4-kpis .f4-kpi .label {{ min-height: 0; }} }}
.f4-kpi .label::before {{ content: ""; width: 0.55rem; height: 0.55rem; border-radius: 2px; flex: none; margin-top: 0.3em;
  background: var(--f4-tone, {RULE}); }}
.f4-kpi .value {{ font-size: 2.3rem; font-weight: 800; font-stretch: 78%; color: {INK}; line-height: 1.05;
  margin-top: 0.3rem; font-variant-numeric: tabular-nums lining-nums; letter-spacing: -0.01em;
  white-space: nowrap; }}
.f4-kpi .sub {{ font-size: 0.84rem; color: {MUTED}; margin-top: 0.15rem; font-variant-numeric: tabular-nums; }}
.f4-kpi.good {{ --f4-tone: {GREEN}; }}
.f4-kpi.bad {{ --f4-tone: {TOMATO}; }}
.f4-kpi.warn {{ --f4-tone: {AMBER}; }}
.f4-kpi.neutral {{ --f4-tone: {INK}; }}
.f4-kpi.good .value {{ color: {GREEN_DARK}; }}
.f4-kpi.bad .value {{ color: {TOMATO}; }}
.f4-kpi.warn .value {{ color: {AMBER_TEXT}; }}

/* ---- equation row (planner) ---- */
.f4-eq {{ display: flex; align-items: stretch; gap: 0.5rem; flex-wrap: wrap; margin: 0.4rem 0 1rem; }}
.f4-eq .f4-kpi {{ flex: 1 1 140px; border: 1px solid {RULE}; border-radius: 8px; box-shadow: none; background: #fff; }}
.f4-eq .f4-kpi.hero {{ background: {HOUSE}; border-color: {HOUSE}; }}
.f4-eq .f4-kpi.hero .label, .f4-eq .f4-kpi.hero .sub {{ color: #D4E8DA; }}
.f4-eq .f4-kpi.hero .value {{ color: #fff; font-size: 2.9rem; }}
.f4-eq .f4-kpi.hero .label::before {{ background: {GREEN}; }}
.f4-eq .op {{ display: flex; align-items: center; font-size: 1.5rem; color: {MUTED}; font-weight: 600; padding: 0 0.1rem;
  white-space: nowrap; font-variant-numeric: tabular-nums; }}
@media (max-width: 640px) {{
  .f4-eq {{ flex-direction: column; gap: 0.25rem; }}
  .f4-eq .f4-kpi {{ flex: none; }}
  .f4-eq .op {{ justify-content: center; font-size: 1.1rem; padding: 0; }} }}

/* ---- notes (takeaways): the planner's margin notes ---- */
.f4-callout {{ background: {PAPER}; border-radius: 8px; padding: 0.85rem 1.1rem 0.9rem; margin: 0.3rem 0 1.2rem;
  color: {INK}; overflow-wrap: anywhere; font-size: 0.98rem; line-height: 1.5; max-width: 72rem; }}
.f4-callout .tag {{ display: block; font-weight: 750; font-size: 0.95rem; margin-bottom: 0.3rem; color: {INK}; }}
.f4-callout .tag::before {{ content: ""; display: inline-block; width: 0.55rem; height: 0.55rem; border-radius: 2px;
  background: {GREEN}; margin-right: 0.45rem; vertical-align: 0.05em; }}
.f4-callout.alert {{ background: {TOMATO_TINT}; }}
.f4-callout.alert .tag {{ color: {TOMATO_TEXT}; }}
.f4-callout.alert .tag::before {{ background: {TOMATO}; }}
.f4-callout.warn {{ background: {AMBER_TINT}; }}
.f4-callout.warn .tag::before {{ background: {AMBER}; }}
.f4-callout.note .tag::before {{ background: {SLATE}; }}
.f4-callout ul {{ margin: 0.1rem 0 0; padding: 0; list-style: none; counter-reset: f4n; }}
.f4-callout li {{ margin: 0.35rem 0; padding-left: 1.6rem; position: relative; counter-increment: f4n; }}
.f4-callout li::before {{ content: counter(f4n); position: absolute; left: 0; top: 0.12rem; width: 1.15rem; height: 1.15rem;
  border-radius: 50%; background: {INK}; color: #fff; font-size: 0.7rem; font-weight: 700; display: flex;
  align-items: center; justify-content: center; }}

/* ---- chart caption ---- */
.f4-chart-title {{ font-weight: 750; color: {INK}; margin: 0.9rem 0 0; font-size: 1.1rem; letter-spacing: -0.005em; }}
.f4-chart-sub {{ color: {MUTED}; font-size: 0.9rem; margin: 0.1rem 0 0.3rem; }}

/* ---- the loop (overview, data trust) ---- */
.f4-steps {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0.4rem 0 1.2rem;
  border-top: 2px solid {INK}; }}
.f4-step {{ padding: 0.8rem 1rem 0.9rem; box-shadow: inset 1px 0 0 {RULE}; position: relative; }}
.f4-step:first-child {{ box-shadow: none; }}
.f4-step .num {{ display: inline-flex; width: 1.7rem; height: 1.7rem; border-radius: 50%; background: {INK};
  color: #fff; font-weight: 800; align-items: center; justify-content: center; font-size: 0.85rem; }}
.f4-step .name {{ font-weight: 750; margin: 0.5rem 0 0.15rem; color: {INK}; font-size: 1.05rem; }}
.f4-step .desc {{ color: {INK_2}; font-size: 0.92rem; line-height: 1.45; }}
.f4-step .tab {{ font-size: 0.82rem; color: {GREEN_DARK}; margin-top: 0.5rem; font-weight: 650; }}
@media (max-width: 900px) {{ .f4-steps {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .f4-step:nth-child(2n+1) {{ box-shadow: none; }} .f4-step:nth-child(n+3) {{ border-top: 1px solid {RULE}; }} }}
@media (max-width: 520px) {{ .f4-steps {{ grid-template-columns: 1fr; }} .f4-step {{ box-shadow: none; }}
  .f4-step:nth-child(n+2) {{ border-top: 1px solid {RULE}; }} }}

/* band chips (crew) */
.f4-dot {{ display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 2px; margin-right: 0.35rem; vertical-align: -0.05em; }}

/* quarantine card */
.f4-q {{ border: 1px solid #F0C2BF; background: {TOMATO_TINT}; border-radius: 8px; padding: 0.85rem 1rem; margin: 0.4rem 0; }}
.f4-q .file {{ font-weight: 750; color: {INK}; overflow-wrap: anywhere; }}
.f4-q .why {{ color: {TOMATO_TEXT}; font-weight: 600; margin-top: 0.15rem; }}

/* footer */
.f4-footer {{ margin-top: 2.4rem; padding-top: 0.9rem; border-top: 2px solid {INK}; color: {MUTED};
  font-size: 0.85rem; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }}
.f4-footer b {{ color: {INK}; }}

/* sidebar summary */
.f4-side-dl {{ font-size: 0.88rem; margin: 0.2rem 0; }}
.f4-side-dl div {{ display: flex; justify-content: space-between; gap: 0.75rem; padding: 0.3rem 0; border-bottom: 1px solid {RULE}; }}
.f4-side-dl span:first-child {{ color: {MUTED}; }}
.f4-side-dl span:last-child {{ font-weight: 650; color: {INK}; font-variant-numeric: tabular-nums; text-align: right; }}
.f4-side-team {{ font-size: 0.84rem; color: {MUTED}; margin-top: 0.2rem; }}
.f4-side-team b {{ color: {GREEN_DARK}; }}
</style>
"""


def _flat(s: str) -> str:
    """No indentation or blank lines, so Markdown never mistakes the HTML for a code block."""
    return "\n".join(line.strip() for line in s.splitlines() if line.strip())


def inject_css():
    st.markdown(_flat(CSS), unsafe_allow_html=True)


def _html(s: str):
    st.markdown(_flat(s), unsafe_allow_html=True)


def md(text: str) -> str:
    """Escape text for HTML, then turn **bold** into <b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(str(text)))


def _logo_uri() -> str:
    try:
        with open(os.path.join(_HERE, "assets", "fresh4u_group_logo.png"), "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    except OSError:
        return ""


# ---- components -------------------------------------------------------------------------------
def hero(demo: bool, source: str = ""):
    label = "Synthetic demo data" if demo else ("Exports on this computer" if "computer" in source else "Your uploaded exports")
    logo = _logo_uri()
    plate = f'<span class="f4-plate"><img src="{logo}" alt="The Fresh4U Group"></span>' if logo else ""
    _html(f"""
<header class="f4 f4-head">
  <div class="f4-brand">{plate}
    <div><div class="title" role="heading" aria-level="1">Labour Planner</div>
    <p class="sub">The year's crews, a target for every task and a check before payroll, from Fresh4U's own Priva data.</p></div>
  </div>
  <div class="f4-meta"><span class="f4-chip data{'' if demo else ' real'}">{html.escape(label)}</span>
  <span class="f4-chip">Built by {TEAM}</span></div>
</header>""")


def section(title: str, subtitle: str = ""):
    sub = f"<p>{md(subtitle)}</p>" if subtitle else ""
    _html(f'<div class="f4 f4-section"><div class="title" role="heading" aria-level="2">{md(title)}</div>{sub}</div>')


def answer(text: str, tone: str = ""):
    """The tab's answer in one sentence; the first **number** is set big with a marker highlight."""
    _html(f'<p class="f4 f4-answer {tone}">{md(text)}</p>')


def kpi_html(label: str, value: str, sub: str = "", tone: str = "neutral", hero_card: bool = False) -> str:
    cls = f"f4-kpi {tone}" + (" hero" if hero_card else "")
    sub_html = f'<div class="sub">{md(sub)}</div>' if sub else ""
    return f'<div class="{cls}"><div class="label">{md(label)}</div><div class="value">{md(value)}</div>{sub_html}</div>'


def kpis(cards: list[str]):
    n = len(cards)
    cols = max(n if n <= 5 else (n + 1) // 2, 1)     # one row up to 5 figures; 6 -> 3 + 3
    _html(f'<div class="f4 f4-kpis c{cols}" style="--f4-cols:{cols}">{"".join(cards)}</div>')


def equation(parts: list[str]):
    """parts alternates cards and operators, e.g. [card, '×', card, '=', card]."""
    out = []
    for p in parts:
        out.append(p if p.startswith("<div") else f'<div class="op">{html.escape(p)}</div>')
    _html(f'<div class="f4 f4-eq">{"".join(out)}</div>')


def callout(text: str | list[str], tag: str = "What this means", tone: str = ""):
    body = ("<ul>" + "".join(f"<li>{md(t)}</li>" for t in text) + "</ul>") if isinstance(text, list) else md(text)
    _html(f'<div class="f4 f4-callout {tone}"><span class="tag">{html.escape(tag)}</span>{body}</div>')


def chart_title(title: str, subtitle: str = ""):
    sub = f'<div class="f4-chart-sub">{md(subtitle)}</div>' if subtitle else ""
    _html(f'<div class="f4"><div class="f4-chart-title">{md(title)}</div>{sub}</div>')


def steps(items: list[tuple[str, str, str]]):
    cards = "".join(
        f'<div class="f4-step"><span class="num">{i}</span><div class="name">{md(name)}</div>'
        f'<div class="desc">{md(desc)}</div>'
        + (f'<div class="tab">In the {md(tab)} tab</div>' if tab else "") + "</div>"
        for i, (name, desc, tab) in enumerate(items, 1))
    _html(f'<div class="f4 f4-steps">{cards}</div>')


def quarantine_card(name: str, why: str):
    _html(f'<div class="f4 f4-q"><div class="file">Held back: {md(name)}</div><div class="why">{md(why)}</div></div>')


def band_legend():
    chips = " &nbsp; ".join(f'<span class="f4-dot" style="background:{c}"></span>{b}' for b, c in BAND_COLORS.items())
    _html(f'<div class="f4" style="font-size:0.88rem;color:{INK_2};margin:0.2rem 0 0.4rem">{chips}</div>')


def sidebar_summary(rows: list[tuple[str, str]]):
    body = "".join(f"<div><span>{md(k)}</span><span>{md(v)}</span></div>" for k, v in rows)
    st.sidebar.markdown(f'<div class="f4 f4-side-dl">{body}</div>', unsafe_allow_html=True)


def footer(demo: bool):
    data = "Synthetic demo data: no Fresh4U records are included." if demo else \
        "Client data stays on this computer; names are never stored."
    _html(f'<div class="f4 f4-footer"><span>Built by <b>{TEAM}</b> for The Fresh4U Group &middot; '
          f'BUS 439, Simon Fraser University, Fall 2026</span><span>{html.escape(data)}</span></div>')


# ---- season strip (the signature) ------------------------------------------------------------------
CAT_COLORS = {
    "Tomato harvest": "#1E8A3C", "Tomato crop work": "#2F67B1", "Packing & grading": "#C98500",
    "Strawberry harvest": "#8E5AA8", "Strawberry crop work": "#2A9D8F", "Clean-out & planting": "#B4475E",
    "Pest control & general": "#9AA0A6", "Breaks (unpaid)": "#CDD1D6",
}
STATUS_COLORS = {"Slower than target": AMBER, "On track": GREEN_DARK, "Faster than target": "#2F67B1",
                 "No target yet": "#C5C9CF"}


def iso_weeks_between(start, end) -> list[int]:
    """ISO week numbers touched by a date range (inclusive)."""
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    if pd.isna(a) or pd.isna(b) or b < a:
        return []
    days = pd.date_range(a, b, freq="D")
    return sorted({int(d.isocalendar()[1]) for d in days})


def season_strip(plan: pd.DataFrame | None, year: int | None, crew_people: float | None = None,
                 mark: list[int] | tuple = (), mark_label: str = "", title: str = ""):
    """
    The whole season on one line, like the crop calendar on a grower's wall: one column per ISO week,
    its height the people needed and its colour the activity that takes the most hours that week.
    `mark` lists the weeks the open tab is about; they get the ink bracket and everything else fades.
    """
    W, top, base, H = 1040.0, 26.0, 108.0, 136.0
    col = W / 52
    bar_w = col - 4
    mark = sorted({int(w) for w in mark if 1 <= int(w) <= 53})
    yr = int(year) if year else _dt.date.today().year
    parts = []

    people = lead = None
    if plan is not None and len(plan):
        p = plan.set_index("iso_week")
        people = p["People"].astype(float)
        work_cats = [c for c in CAT_COLORS if c in p.columns and c != "Breaks (unpaid)"]
        lead = p[work_cats].astype(float).idxmax(axis=1)
    peak = float(people.max()) if people is not None else 1.0
    scale_max = max(peak, float(crew_people or 0)) * 1.06 or 1.0

    # faint week grid, like the ruled columns of a wall planner
    for i in range(53):
        x = i * col
        heavy = i % 4 == 0
        parts.append(f'<line x1="{x:.1f}" y1="{top - 4}" x2="{x:.1f}" y2="{base}" stroke="{GRID if not heavy else RULE}" '
                     'stroke-width="1"/>')

    for w in range(1, 53):
        x = (w - 1) * col + 2
        faded = bool(mark) and w not in mark
        op = "0.32" if faded else "1"
        try:
            monday = _dt.date.fromisocalendar(yr, w, 1)
        except ValueError:
            monday = None
        when = f" ({monday:%b %d})" if monday else ""
        if people is not None and w in people.index:
            v = float(people.loc[w])
            h = max(2.0, (base - top) * v / scale_max)
            c = CAT_COLORS.get(str(lead.loc[w]), OTHER)
            tip = f"Week {w}{when}: {v:,.0f} people; most hours go to {str(lead.loc[w]).lower()}"
            parts.append(f'<g class="wk" opacity="{op}"><title>{html.escape(tip)}</title>'
                         f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="1.5" fill="{c}"/>'
                         f'<rect x="{x - 2:.1f}" y="{top - 4}" width="{col:.1f}" height="{base - top + 4}" fill="transparent"/></g>')
        else:
            parts.append(f'<g class="wk" opacity="{op}"><title>Week {w}{html.escape(when)}</title>'
                         f'<rect x="{x:.1f}" y="{base - 3}" width="{bar_w:.1f}" height="3" fill="{RULE}"/></g>')

    # crew line: everything above it is contractor work
    if crew_people and people is not None:
        cy = base - (base - top) * float(crew_people) / scale_max
        parts.append(f'<line x1="0" y1="{cy:.1f}" x2="{W}" y2="{cy:.1f}" stroke="{INK}" stroke-width="1.25" '
                     'stroke-dasharray="5 4"/>')
        lab = f"Crew {crew_people:,.0f}"
        parts.append(f'<text x="{W - 4}" y="{cy - 5:.1f}" text-anchor="end" font-size="11" font-weight="700" fill="{INK}" '
                     f'stroke="#fff" stroke-width="4" paint-order="stroke" stroke-linejoin="round">{lab}</text>')

    # heavy baseline and month names
    parts.append(f'<line x1="0" y1="{base + 1}" x2="{W}" y2="{base + 1}" stroke="{INK}" stroke-width="2"/>')
    seen = set()
    for w in range(1, 53):
        try:
            m = _dt.date.fromisocalendar(yr, w, 1)
        except ValueError:
            continue
        if m.month not in seen and m.day <= 7:
            seen.add(m.month)
            parts.append(f'<text x="{(w - 1) * col + 2:.1f}" y="{base + 18}" font-size="11" fill="{MUTED}" '
                         f'font-weight="600">{m:%b}</text>')

    # the bracket over the weeks this tab is about
    if mark:
        runs, start, prev = [], mark[0], mark[0]
        for w in mark[1:] + [None]:
            if w is not None and w == prev + 1:
                prev = w
                continue
            runs.append((start, prev))
            if w is not None:
                start = prev = w
        for a, b in runs:
            x0, x1 = (a - 1) * col + 1, b * col - 1
            parts.append(f'<rect x="{x0:.1f}" y="{top - 8}" width="{x1 - x0:.1f}" height="4" fill="{INK}"/>')
            parts.append(f'<rect x="{x0:.1f}" y="{base + 4}" width="{x1 - x0:.1f}" height="4" fill="{INK}"/>')
        a = runs[0][0]
        span = f"wk {runs[0][0]}" + (f"–{runs[-1][1]}" if runs[-1][1] != runs[0][0] else "")
        text = f"{mark_label} · {span}" if mark_label else span
        x = (a - 1) * col + 1
        anchor = "start"
        if x > W - 260:
            x, anchor = runs[-1][1] * col - 1, "end"
        parts.append(f'<text x="{x:.1f}" y="{top - 13}" text-anchor="{anchor}" font-size="12.5" font-weight="800" '
                     f'fill="{INK}">{html.escape(text)}</text>')

    label = (f"Season {yr}: people needed each week" if people is not None else f"Weeks of {yr}")
    aria = label + (f"; marked: {mark_label} weeks {mark[0]} to {mark[-1]}" if mark else "")
    svg = (f'<svg viewBox="0 -4 {W} {H}" role="img" aria-label="{html.escape(aria)}" '
           f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>')

    legend = ""
    if lead is not None:
        present = [c for c in CAT_COLORS if c in set(lead.astype(str))]
        legend = "".join(f'<span><i style="background:{CAT_COLORS[c]}"></i>{html.escape(c)}</span>' for c in present)
    head = title or (f"Season {yr} <span>· people needed each week, coloured by the main activity</span>"
                     if people is not None else f"{yr} <span>· by week</span>")
    phone = ""
    if mark:   # on a phone the SVG labels are too small to read, so the marked weeks are named in text
        phone = (f'<div class="f4-strip-mark">{html.escape(mark_label + " · " if mark_label else "")}'
                 f'weeks {mark[0]}{"–" + str(mark[-1]) if mark[-1] != mark[0] else ""}</div>')
    _html(f'<div class="f4 f4-strip"><div class="f4-strip-top"><div class="f4-strip-title">{head}</div>'
          f'<div class="f4-legend">{legend}</div>{phone}</div>{svg}</div>')


# ---- charts --------------------------------------------------------------------------------------
def task_colors(records: pd.DataFrame) -> dict:
    """Fixed colour per task, by total hours (largest first). Tasks past the palette share 'Other' grey."""
    order = records.groupby("activity_name")["hours"].sum().sort_values(ascending=False).index.tolist()
    return {t: (TASK_PALETTE[i] if i < len(TASK_PALETTE) else OTHER) for i, t in enumerate(order)}


def _scale(colors: dict, present) -> alt.Scale:
    dom = [t for t in colors if t in set(present)]
    return alt.Scale(domain=dom, range=[colors[t] for t in dom])


def _style(chart, height: int = 300):
    return (chart.properties(height=height)
            .configure(font=FONT)
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor=INK_2, titleColor=MUTED, gridColor=GRID, domainColor=INK, domainWidth=1.5,
                            tickColor=RULE, ticks=False, labelFontSize=12, titleFontSize=12, titleFontWeight=600,
                            labelPadding=6)
            .configure_axisY(domain=False)
            .configure_legend(orient="top", title=None, labelColor=INK, labelFontSize=12.5, symbolSize=130,
                              symbolType="square", columnPadding=16, labelLimit=240)
            .configure_axisX(grid=False))


def full_width(fn, *args, **kwargs):
    """Call a Streamlit element full-width, whichever width keyword this Streamlit version accepts."""
    try:
        return fn(*args, **stretch(), **kwargs)
    except TypeError:
        alt_kw = {"use_container_width": True} if "width" in stretch() else {"width": "stretch"}
        return fn(*args, **alt_kw, **kwargs)


def show(chart, height: int = 300):
    full_width(st.altair_chart, _style(chart, height), theme=None)


def _weeks(df: pd.DataFrame, col: str = "week_start") -> pd.DataFrame:
    df = df.copy()
    df[col] = pd.to_datetime(df[col])
    df["week"] = df[col].dt.strftime("%b %d")
    return df


def _week_x(d: pd.DataFrame) -> alt.X:
    """One label per week, on the Monday each week starts (a time axis would label Sundays)."""
    labels = [pd.Timestamp(w).strftime("%b %d") for w in sorted(d["week_start"].unique())]
    return alt.X("week:O", title=None, sort=labels, axis=alt.Axis(labelAngle=0, labelPadding=8),
                 scale=alt.Scale(paddingOuter=0.25))


def backtest_chart(pva: pd.DataFrame):
    d = _weeks(pva)
    d["miss"] = d["variance_pct"].abs().round(1)
    long = d.melt(id_vars=["week_start", "week", "miss", "rows_done"], value_vars=["actual_hours", "planned_hours"],
                  var_name="series", value_name="hours")
    long["series"] = long["series"].map({"actual_hours": "Actual hours", "planned_hours": "Planned by the method"})
    long["hours"] = long["hours"].astype(float).round(0)
    x = _week_x(long)
    color = alt.Color("series:N", scale=alt.Scale(domain=["Actual hours", "Planned by the method"],
                                                   range=[INK, GREEN_DARK]))
    dash = alt.StrokeDash("series:N", scale=alt.Scale(domain=["Actual hours", "Planned by the method"],
                                                       range=[[1, 0], [6, 4]]))
    # Keep about ±10% of context so a 1-2% miss looks like the small miss it is.
    lo, hi = long["hours"].min(), long["hours"].max()
    mid = (lo + hi) / 2
    span = max(hi - lo, 0.2 * mid)
    domain = [max(0, mid - span / 2 - 0.05 * span), mid + span / 2 + 0.05 * span]
    tip = [alt.Tooltip("week_start:T", title="Week of", format="%b %d, %Y"),
           alt.Tooltip("series:N", title="Series"), alt.Tooltip("hours:Q", title="Hours", format=",.0f"),
           alt.Tooltip("miss:Q", title="Plan missed by (%)")]
    base = alt.Chart(long).encode(x=x, y=alt.Y("hours:Q", title="Hours", scale=alt.Scale(domain=domain, nice=False)),
                                  color=color)
    lines = base.mark_line(strokeWidth=3).encode(strokeDash=dash)
    pts = base.mark_point(filled=True, size=80, opacity=1).encode(tooltip=tip)
    hit = base.mark_point(size=500, opacity=0).encode(tooltip=tip)
    return lines + pts + hit


def strengths_chart(view: pd.DataFrame):
    d = view.copy()
    d["speed"] = d["speed_index"].astype(float)
    d["weeks"] = d["weeks"].astype(int)
    d["hours"] = d["hours"].astype(float).round(1)
    # spread dots vertically inside their band so people with similar speed do not hide each other
    d["jitter"] = [((zlib.crc32(str(e).encode()) % 1000) / 1000 - 0.5) * 0.7 for e in d["employee_id"]]
    present = [b for b in BAND_COLORS if b in set(d["band"])]
    band_zone = alt.Chart(pd.DataFrame({"lo": [90], "hi": [110]})).mark_rect(color=PAPER, opacity=1).encode(
        x="lo:Q", x2="hi:Q")
    ref = alt.Chart(pd.DataFrame({"x": [100]})).mark_rule(color=INK, strokeDash=[4, 3]).encode(x="x:Q")
    jitter = ({"yOffset": alt.YOffset("jitter:Q", scale=alt.Scale(domain=[-0.5, 0.5]))}
              if hasattr(alt, "YOffset") else {})  # Altair 5+; older versions just overlap the dots
    dots = alt.Chart(d).mark_circle(size=160, opacity=0.92, stroke="#fff", strokeWidth=1.5).encode(
        x=alt.X("speed:Q", title="Speed (100 = that week's typical pace; higher is faster)",
                scale=alt.Scale(zero=False, padding=12), axis=alt.Axis(tickCount=8)),
        y=alt.Y("band:N", title=None, sort=present),
        **jitter,
        color=alt.Color("band:N", scale=alt.Scale(domain=present, range=[BAND_COLORS[b] for b in present]),
                        legend=None),
        tooltip=[alt.Tooltip("employee_id:N", title="Person"), alt.Tooltip("employee_group:N", title="Group"),
                 alt.Tooltip("band:N", title="Band"), alt.Tooltip("speed:Q", title="Speed", format=".0f"),
                 alt.Tooltip("weeks:Q", title="Weeks on task"), alt.Tooltip("hours:Q", title="Hours on task")])
    return band_zone + ref + dots


def hours_chart(weekly: pd.DataFrame, colors: dict):
    d = _weeks(weekly)
    d["hours"] = d["hours"].astype(float).round(0)
    order = sorted(d["week_start"].unique())
    labels = [pd.Timestamp(w).strftime("%b %d") for w in order]
    present = d["activity_name"].unique()
    rank = {t: i for i, t in enumerate(colors)}
    d["rank"] = d["activity_name"].map(rank)
    return alt.Chart(d).mark_bar(stroke="#fff", strokeWidth=1.5).encode(
        x=alt.X("week:O", title=None, sort=labels, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("sum(hours):Q", title="Hours", stack="zero"),
        color=alt.Color("activity_name:N", scale=_scale(colors, present)),
        order=alt.Order("rank:Q", sort="ascending"),
        tooltip=[alt.Tooltip("week:O", title="Week of"), alt.Tooltip("activity_name:N", title="Task"),
                 alt.Tooltip("sum(hours):Q", title="Hours", format=",.0f")])


def _task_lines(d: pd.DataFrame, y: str, title: str, colors: dict, fmt: str):
    d = _weeks(d)
    d[y] = d[y].astype(float)
    x = _week_x(d)
    base = alt.Chart(d).encode(x=x, y=alt.Y(f"{y}:Q", title=title),
                               color=alt.Color("activity_name:N", scale=_scale(colors, d["activity_name"].unique())))
    tip = [alt.Tooltip("week_start:T", title="Week of", format="%b %d, %Y"),
           alt.Tooltip("activity_name:N", title="Task"), alt.Tooltip(f"{y}:Q", title=title, format=fmt)]
    return (base.mark_line(strokeWidth=2.5) + base.mark_point(filled=True, size=55, opacity=1).encode(tooltip=tip)
            + base.mark_point(size=400, opacity=0).encode(tooltip=tip))


def rows_chart(pace: pd.DataFrame, colors: dict, greenhouse_rows: int):
    lines = _task_lines(pace, "rows_done", "Rows completed", colors, ",.0f")
    rule = alt.Chart(pd.DataFrame({"y": [greenhouse_rows]}))
    ref = rule.mark_rule(color=INK, strokeDash=[5, 4]).encode(y="y:Q")
    lab = rule.mark_text(align="left", dx=6, dy=12, color=INK_2, fontSize=11, fontWeight=600).encode(
        y="y:Q", x=alt.value(0), text=alt.value(f"Whole greenhouse ({greenhouse_rows} rows)"))
    return lines + ref + lab


def pace_chart(pace: pd.DataFrame, colors: dict):
    return _task_lines(pace.dropna(subset=["min_per_row"]), "min_per_row", "Minutes per row", colors, ".1f")


def review_by_task_chart(sel: pd.DataFrame):
    d = sel.groupby("activity_name").agg(count=("hours", "size"), hours=("hours", "sum")).reset_index()
    d["hours"] = d["hours"].astype(float).round(1)
    base = alt.Chart(d).encode(y=alt.Y("activity_name:N", title=None, sort="-x"))
    bars = base.mark_bar(color=AMBER, cornerRadiusEnd=3, size=20).encode(
        x=alt.X("count:Q", title="Registrations to check", axis=alt.Axis(tickMinStep=1)),
        tooltip=[alt.Tooltip("activity_name:N", title="Task"), alt.Tooltip("count:Q", title="Registrations"),
                 alt.Tooltip("hours:Q", title="Hours")])
    text = base.mark_text(align="left", dx=5, color=INK, fontSize=12, fontWeight=700).encode(x="count:Q", text="count:Q")
    return bars + text


# ---- year plan, targets and weekly check ------------------------------------------------------------
def plan_chart(plan: pd.DataFrame, unit: str, crew_people: float, hours_per_person: float, year: int):
    cats = list(CAT_COLORS)
    k = 1 / hours_per_person if unit == "People" else 1.0
    long = plan.melt(id_vars=["iso_week"], value_vars=cats, var_name="activity", value_name="v")
    long["v"] = (long["v"] * k).round(1 if unit == "People" else 0)
    long["rank"] = long["activity"].map({c: i for i, c in enumerate(cats)})
    long["week_of"] = long["iso_week"].map(lambda w: f"{_dt.date.fromisocalendar(int(year), int(w), 1):%b %d}")
    tot = plan.assign(total=(plan["Total hours"] * k).round(1 if unit == "People" else 0))
    tot["week_of"] = tot["iso_week"].map(lambda w: f"{_dt.date.fromisocalendar(int(year), int(w), 1):%b %d}")
    x = alt.X("iso_week:O", title="Week of the year", axis=alt.Axis(labelAngle=0, values=list(range(1, 53, 4))))
    bars = alt.Chart(long).mark_bar(stroke="#fff", strokeWidth=0.4).encode(
        x=x, y=alt.Y("sum(v):Q", title=unit, stack="zero"),
        color=alt.Color("activity:N", scale=alt.Scale(domain=cats, range=[CAT_COLORS[c] for c in cats]),
                        legend=alt.Legend(orient="top", title=None, columns=4, symbolType="square")),
        order=alt.Order("rank:Q", sort="ascending"),
        tooltip=[alt.Tooltip("iso_week:O", title="Week"), alt.Tooltip("week_of:N", title="Starts"),
                 alt.Tooltip("activity:N", title="Activity"),
                 alt.Tooltip("sum(v):Q", title=unit, format=",.1f" if unit == "People" else ",.0f")])
    hit = alt.Chart(tot).mark_bar(opacity=0).encode(
        x=x, y=alt.Y("total:Q"),
        tooltip=[alt.Tooltip("iso_week:O", title="Week"), alt.Tooltip("week_of:N", title="Starts"),
                 alt.Tooltip("total:Q", title=f"Total {unit.lower()}", format=",.0f"),
                 alt.Tooltip("Changeover:N", title="Changeover")])
    crew_v = crew_people if unit == "People" else crew_people * hours_per_person
    rule_d = alt.Chart(pd.DataFrame({"y": [crew_v], "lab": [f"TFW + local crew ({crew_people:,.0f} people)"]}))
    rule = rule_d.mark_rule(color=INK, strokeDash=[5, 4], strokeWidth=1.5).encode(y="y:Q")
    # white halo underneath so the label stays readable where it crosses the bars
    halo = rule_d.mark_text(align="left", dx=4, dy=-8, color="#fff", stroke="#fff", strokeWidth=4,
                            strokeJoin="round", fontSize=11.5, fontWeight=700).encode(y="y:Q", x=alt.value(4), text="lab:N")
    lab = rule_d.mark_text(align="left", dx=4, dy=-8, color=INK, fontSize=11.5, fontWeight=700).encode(
        y="y:Q", x=alt.value(4), text="lab:N")
    # name the peak on the chart itself, so the headline number is visible where it happens
    pk = tot.loc[tot["total"].idxmax()]
    peak_d = pd.DataFrame({"iso_week": [pk["iso_week"]], "total": [pk["total"]],
                           "lab": [f"Peak: {pk['total']:,.0f} {'people' if unit == 'People' else 'h'}, wk {int(pk['iso_week'])}"]})
    peak = alt.Chart(peak_d).mark_text(dy=-10, fontSize=12, fontWeight=800, color=INK, stroke="#fff", strokeWidth=4,
                                       strokeJoin="round").encode(x=x, y="total:Q", text="lab:N")
    peak_ink = alt.Chart(peak_d).mark_text(dy=-10, fontSize=12, fontWeight=800, color=INK).encode(
        x=x, y="total:Q", text="lab:N")
    return bars + hit + rule + halo + lab + peak + peak_ink


def split_chart(cats: pd.Series):
    d = cats.rename("hours").reset_index().rename(columns={"index": "activity"})
    d.columns = ["activity", "hours"]
    d["share"] = d["hours"] / d["hours"].sum()
    d["label"] = d["share"].map(lambda s: f"{100 * s:.0f}%")
    order = d.sort_values("hours", ascending=False)["activity"].tolist()
    base = alt.Chart(d).encode(y=alt.Y("activity:N", title=None, sort=order))
    bars = base.mark_bar(cornerRadiusEnd=3, size=20).encode(
        x=alt.X("hours:Q", title="Hours in the year"),
        color=alt.Color("activity:N", scale=alt.Scale(domain=list(CAT_COLORS), range=list(CAT_COLORS.values())), legend=None),
        tooltip=[alt.Tooltip("activity:N", title="Activity"), alt.Tooltip("hours:Q", title="Hours", format=",.0f"),
                 alt.Tooltip("share:Q", title="Share", format=".1%")])
    text = base.mark_text(align="left", dx=5, color=INK, fontSize=12, fontWeight=700).encode(x="hours:Q", text="label:N")
    return bars + text


def on_track_chart(ot: pd.DataFrame, band_pct: float = 10.0):
    d = ot[ot["status"] != "No target yet"].copy()
    d["vs"] = d["vs_target_pct"].astype(float).round(1)
    d["lab"] = d["vs"].map(lambda v: f"{v:+.0f}%")
    zone = alt.Chart(pd.DataFrame({"lo": [-band_pct], "hi": [band_pct]})).mark_rect(color=GREEN_TINT).encode(
        x="lo:Q", x2="hi:Q")
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=INK, strokeWidth=1.5).encode(x="x:Q")
    y = alt.Y("task:N", title=None, sort="-x")
    present = [k for k in STATUS_COLORS if k in set(d["status"])]
    bars = alt.Chart(d).mark_bar(cornerRadiusEnd=3, size=20).encode(
        y=y, x=alt.X("vs:Q", title="Minutes per row vs target (%; right = slower)"),
        color=alt.Color("status:N", scale=alt.Scale(domain=present, range=[STATUS_COLORS[k] for k in present]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("task:N", title="Task"),
                 alt.Tooltip("actual_min_per_row:Q", title="This week (min/row)", format=".1f"),
                 alt.Tooltip("target_min_per_row:Q", title="Target (min/row)", format=".1f"),
                 alt.Tooltip("vs:Q", title="vs target (%)"), alt.Tooltip("hours_over:Q", title="Hours over", format=",.0f")])
    pos = alt.Chart(d[d["vs"] >= 0]).mark_text(align="left", dx=5, fontSize=12, fontWeight=700, color=INK).encode(
        y=y, x="vs:Q", text="lab:N")
    neg = alt.Chart(d[d["vs"] < 0]).mark_text(align="right", dx=-5, fontSize=12, fontWeight=700, color=INK).encode(
        y=y, x="vs:Q", text="lab:N")
    return zone + zero + bars + pos + neg


def untagged_chart(u: pd.DataFrame, flag_hours: float):
    d = u.copy()
    d["untagged"] = d["untagged"].astype(float).round(1)
    d["state"] = d["flag"].map({True: "To check", False: "Within normal range"})
    return alt.Chart(d).mark_bar(cornerRadiusEnd=2).encode(
        x=alt.X("untagged:Q", bin=alt.Bin(step=1), title="Hours present with no task, over the period",
                axis=alt.Axis(format="d")),
        y=alt.Y("count():Q", title="People"),
        color=alt.Color("state:N", scale=alt.Scale(domain=["Within normal range", "To check"], range=["#B8BEC6", AMBER]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("count():Q", title="People"), alt.Tooltip("state:N", title="")])
