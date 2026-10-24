"""
Look and feel for the Streamlit app: brand colours, page styling, small HTML components
and the Altair charts. Kept out of streamlit_app.py so the page reads as a story.

Brand colours are taken from The Fresh4U Group logo (assets/fresh4u_group_logo.png):
slate #565963 (greenhouse and wordmark), green #00972D (swoosh), tomato #F91C1C (the "O").
"""
from __future__ import annotations

import html
import zlib
import re

import altair as alt
import pandas as pd
import streamlit as st

TEAM = "GLW BC"

# ---- colour tokens ------------------------------------------------------------------------
SLATE = "#565963"        # logo greenhouse + wordmark
SLATE_DARK = "#43464F"
INK = "#2E3138"          # body text
MUTED = "#6B6F78"        # secondary text
GREEN = "#00972D"        # logo swoosh
GREEN_DARK = "#0A7D2C"   # buttons / text on white (contrast)
GREEN_TINT = "#EAF5EC"
TOMATO = "#D7261E"       # logo tomato, darkened for text contrast; used only for "needs attention"
TOMATO_TINT = "#FDEDEC"
SURFACE_ALT = "#F5F7F4"
BORDER = "#E2E7E0"
GRID = "#EDF0EB"

# Categorical palette for tasks (validated for colour-blind separation and 3:1 contrast on white).
# Assigned to tasks in order of total hours, so a task keeps its colour on every chart and filter.
TASK_PALETTE = ["#1E8A3C", "#2F67B1", "#C98500", "#8E5AA8", "#2A9D8F"]
OTHER = "#9AA0A6"

BAND_COLORS = {"Strong": "#1E8A3C", "Typical": "#8A8F99", "Developing": "#C98500",
               "Ramping up": "#2F67B1", "Not enough data": "#C5C9CF"}

FONT = "'Source Sans Pro', 'Source Sans 3', sans-serif"


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
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap');

.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1240px; }}
h1, h2, h3, .f4-serif {{ font-family: 'Source Serif 4', Georgia, serif !important; color: {INK}; letter-spacing: -0.01em; }}
[data-testid="stSidebar"] {{ background: {SURFACE_ALT}; border-right: 1px solid {BORDER}; }}
[data-testid="stSidebar"] hr {{ margin: 0.8rem 0; }}

/* tabs */
.stTabs [data-baseweb="tab-list"] {{ gap: 0.25rem; border-bottom: 1px solid {BORDER}; }}
.stTabs [data-baseweb="tab"] {{ padding: 0.55rem 0.9rem; font-weight: 600; color: {MUTED}; }}
.stTabs [aria-selected="true"] {{ color: {GREEN_DARK}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {GREEN_DARK}; }}

/* header band */
.f4-hero {{ background: linear-gradient(120deg, {SLATE} 0%, {SLATE_DARK} 100%); color: #fff;
  border-radius: 14px; padding: 1.4rem 1.6rem 1.25rem; margin-bottom: 1.1rem; position: relative;
  border-bottom: 5px solid {GREEN}; display: flex; justify-content: space-between; align-items: flex-end;
  gap: 1rem; flex-wrap: wrap; }}
.f4-hero .eyebrow {{ font-size: 0.78rem; letter-spacing: 0.14em; text-transform: uppercase; opacity: 0.8; }}
.f4-hero .title {{ color: #fff !important; font-size: 2.1rem; font-weight: 700; line-height: 1.2; margin: 0.15rem 0 0.3rem; }}
.f4-hero p {{ margin: 0; opacity: 0.88; max-width: 46rem; font-size: 1rem; }}
.f4-pills {{ display: flex; gap: 0.45rem; flex-wrap: wrap; }}
.f4-pill {{ font-size: 0.8rem; font-weight: 600; padding: 0.28rem 0.7rem; border-radius: 999px;
  background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.3); color: #fff; white-space: nowrap; }}
.f4-pill.team {{ background: {GREEN}; border-color: {GREEN}; }}
.f4-pill.warn {{ background: #fff; color: {SLATE_DARK}; }}

/* section heading */
.f4-section {{ margin: 0.6rem 0 0.6rem; }}
.f4-section .title {{ margin: 0 0 0.15rem; font-size: 1.4rem; font-weight: 700; line-height: 1.3; }}
.f4-section p {{ margin: 0; color: {MUTED}; }}

/* KPI cards */
.f4-kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.75rem; margin: 0.4rem 0 0.9rem; }}
.f4-kpi {{ background: #fff; border: 1px solid {BORDER}; border-radius: 12px; padding: 0.85rem 1rem; }}
.f4-kpi .label {{ font-size: 0.82rem; color: {MUTED}; font-weight: 600; }}
.f4-kpi .value {{ font-size: 1.9rem; font-weight: 700; color: {INK}; line-height: 1.15; margin-top: 0.15rem; }}
.f4-kpi .sub {{ font-size: 0.82rem; color: {MUTED}; margin-top: 0.15rem; }}
.f4-kpi.good {{ border-top: 4px solid {GREEN}; }}
.f4-kpi.bad {{ border-top: 4px solid {TOMATO}; }}
.f4-kpi.neutral {{ border-top: 4px solid {SLATE}; }}
.f4-kpi.good .value {{ color: {GREEN_DARK}; }}
.f4-kpi.bad .value {{ color: {TOMATO}; }}
.f4-kpi.hero {{ background: {GREEN_TINT}; border-color: #CFE7D4; }}

/* equation row (planner) */
.f4-eq {{ display: flex; align-items: stretch; gap: 0.5rem; flex-wrap: wrap; margin: 0.4rem 0 0.9rem; }}
.f4-eq .f4-kpi {{ flex: 1 1 140px; }}
.f4-eq .op {{ display: flex; align-items: center; font-size: 1.5rem; color: {MUTED}; font-weight: 600; padding: 0 0.1rem; }}

/* callouts */
.f4-callout {{ border-left: 4px solid {GREEN}; background: {GREEN_TINT}; border-radius: 0 10px 10px 0;
  padding: 0.75rem 1rem; margin: 0.3rem 0 1.1rem; color: {INK}; }}
.f4-callout .tag {{ font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
  color: {GREEN_DARK}; display: block; margin-bottom: 0.2rem; }}
.f4-callout.alert {{ border-left-color: {TOMATO}; background: {TOMATO_TINT}; }}
.f4-callout.alert .tag {{ color: {TOMATO}; }}
.f4-callout.note {{ border-left-color: {SLATE}; background: {SURFACE_ALT}; }}
.f4-callout.note .tag {{ color: {SLATE}; }}
.f4-callout ul {{ margin: 0.2rem 0 0 1.1rem; padding: 0; }}
.f4-callout li {{ margin: 0.3rem 0; }}

/* chart caption */
.f4-chart-title {{ font-weight: 700; color: {INK}; margin: 0.4rem 0 0; font-size: 1.02rem; }}
.f4-chart-sub {{ color: {MUTED}; font-size: 0.9rem; margin: 0 0 0.2rem; }}

/* workflow steps (overview) */
.f4-steps {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; margin: 0.3rem 0 1rem; }}
.f4-step {{ border: 1px solid {BORDER}; border-radius: 12px; padding: 0.85rem 1rem; background: #fff; }}
.f4-step .num {{ display: inline-flex; width: 1.6rem; height: 1.6rem; border-radius: 50%; background: {SLATE};
  color: #fff; font-weight: 700; align-items: center; justify-content: center; font-size: 0.85rem; }}
.f4-step .name {{ font-weight: 700; margin: 0.45rem 0 0.15rem; color: {INK}; }}
.f4-step .desc {{ color: {MUTED}; font-size: 0.9rem; }}
.f4-step .tab {{ font-size: 0.78rem; font-weight: 600; color: {GREEN_DARK}; margin-top: 0.35rem; }}

/* band chips (crew) */
.f4-chip {{ display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 3px; margin-right: 0.35rem; vertical-align: baseline; }}

/* quarantine card */
.f4-q {{ border: 1px solid #F3C4C1; background: {TOMATO_TINT}; border-radius: 12px; padding: 0.85rem 1rem; margin: 0.4rem 0; }}
.f4-q .file {{ font-weight: 700; color: {INK}; }}
.f4-q .why {{ color: {TOMATO}; font-weight: 600; margin-top: 0.15rem; }}

/* footer */
.f4-footer {{ margin-top: 2.2rem; padding-top: 0.9rem; border-top: 1px solid {BORDER}; color: {MUTED};
  font-size: 0.85rem; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }}
.f4-footer b {{ color: {INK}; }}

/* sidebar summary */
.f4-side-dl {{ font-size: 0.88rem; margin: 0.2rem 0; }}
.f4-side-dl div {{ display: flex; justify-content: space-between; padding: 0.22rem 0; border-bottom: 1px dashed {BORDER}; }}
.f4-side-dl span:first-child {{ color: {MUTED}; }}
.f4-side-dl span:last-child {{ font-weight: 600; color: {INK}; }}
.f4-side-team {{ font-size: 0.82rem; color: {MUTED}; margin-top: 0.2rem; }}
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


# ---- components -------------------------------------------------------------------------------
def hero(demo: bool, source: str = ""):
    label = "Synthetic demo data" if demo else ("Exports on this computer" if "computer" in source else "Your uploaded exports")
    data_pill = f'<span class="f4-pill warn">{html.escape(label)}</span>'
    _html(f"""
<div class="f4-hero">
  <div>
    <div class="eyebrow">The Fresh4U Group &middot; Labour planning</div>
    <div class="title f4-serif">Labour Planner</div>
    <p>Plans the whole year's labour from Fresh4U's own Priva data, checks each week against per-task
    targets, and lists what to fix before payroll.</p>
  </div>
  <div class="f4-pills"><span class="f4-pill team">Built by {TEAM}</span>{data_pill}</div>
</div>""")


def section(title: str, subtitle: str = ""):
    sub = f"<p>{md(subtitle)}</p>" if subtitle else ""
    _html(f'<div class="f4-section"><div class="title f4-serif">{md(title)}</div>{sub}</div>')


def kpi_html(label: str, value: str, sub: str = "", tone: str = "neutral", hero_card: bool = False) -> str:
    cls = f"f4-kpi {tone}" + (" hero" if hero_card else "")
    sub_html = f'<div class="sub">{md(sub)}</div>' if sub else ""
    return f'<div class="{cls}"><div class="label">{md(label)}</div><div class="value">{md(value)}</div>{sub_html}</div>'


def kpis(cards: list[str]):
    _html(f'<div class="f4-kpis">{"".join(cards)}</div>')


def equation(parts: list[str]):
    """parts alternates cards and operators, e.g. [card, '×', card, '=', card]."""
    out = []
    for p in parts:
        out.append(p if p.startswith("<div") else f'<div class="op">{html.escape(p)}</div>')
    _html(f'<div class="f4-eq">{"".join(out)}</div>')


def callout(text: str | list[str], tag: str = "What this means", tone: str = ""):
    body = ("<ul>" + "".join(f"<li>{md(t)}</li>" for t in text) + "</ul>") if isinstance(text, list) else md(text)
    _html(f'<div class="f4-callout {tone}"><span class="tag">{html.escape(tag)}</span>{body}</div>')


def chart_title(title: str, subtitle: str = ""):
    sub = f'<div class="f4-chart-sub">{md(subtitle)}</div>' if subtitle else ""
    _html(f'<div class="f4-chart-title">{md(title)}</div>{sub}')


def steps(items: list[tuple[str, str, str]]):
    cards = "".join(
        f'<div class="f4-step"><span class="num">{i}</span><div class="name">{md(name)}</div>'
        f'<div class="desc">{md(desc)}</div>'
        + (f'<div class="tab">&rarr; {md(tab)} tab</div>' if tab else "") + "</div>"
        for i, (name, desc, tab) in enumerate(items, 1))
    _html(f'<div class="f4-steps">{cards}</div>')


def quarantine_card(name: str, why: str):
    _html(f'<div class="f4-q"><div class="file">&#9888; {md(name)}</div><div class="why">{md(why)}</div></div>')


def band_legend():
    chips = " &nbsp; ".join(f'<span class="f4-chip" style="background:{c}"></span>{b}' for b, c in BAND_COLORS.items())
    _html(f'<div style="font-size:0.88rem;color:{MUTED};margin:0.2rem 0 0.4rem">{chips}</div>')


def sidebar_summary(rows: list[tuple[str, str]]):
    body = "".join(f"<div><span>{md(k)}</span><span>{md(v)}</span></div>" for k, v in rows)
    st.sidebar.markdown(f'<div class="f4-side-dl">{body}</div>', unsafe_allow_html=True)


def footer(demo: bool):
    data = "Synthetic demo data: no Fresh4U records are included." if demo else \
        "Client data stays on this computer; names are never stored."
    _html(f'<div class="f4-footer"><span>Built by <b>{TEAM}</b> for The Fresh4U Group &middot; '
          f'BUS 439, Simon Fraser University, Fall 2026</span><span>{html.escape(data)}</span></div>')


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
            .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=GRID, domainColor=BORDER,
                            tickColor=BORDER, labelFontSize=12, titleFontSize=12, titleFontWeight=600,
                            labelPadding=6)
            .configure_legend(orient="top", title=None, labelColor=INK, labelFontSize=12, symbolSize=110,
                              columnPadding=14, labelLimit=220)
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
                                                   range=[SLATE, GREEN_DARK]))
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
    lines = base.mark_line(strokeWidth=2.5).encode(strokeDash=dash)
    pts = base.mark_point(filled=True, size=70, opacity=1).encode(tooltip=tip)
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
    band_zone = alt.Chart(pd.DataFrame({"lo": [90], "hi": [110]})).mark_rect(color=SURFACE_ALT, opacity=1).encode(
        x="lo:Q", x2="hi:Q")
    ref = alt.Chart(pd.DataFrame({"x": [100]})).mark_rule(color=SLATE, strokeDash=[4, 3]).encode(x="x:Q")
    jitter = ({"yOffset": alt.YOffset("jitter:Q", scale=alt.Scale(domain=[-0.5, 0.5]))}
              if hasattr(alt, "YOffset") else {})  # Altair 5+; older versions just overlap the dots
    dots = alt.Chart(d).mark_circle(size=150, opacity=0.9, stroke="#fff", strokeWidth=1.5).encode(
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
    return (base.mark_line(strokeWidth=2) + base.mark_point(filled=True, size=45, opacity=1).encode(tooltip=tip)
            + base.mark_point(size=400, opacity=0).encode(tooltip=tip))


def rows_chart(pace: pd.DataFrame, colors: dict, greenhouse_rows: int):
    lines = _task_lines(pace, "rows_done", "Rows completed", colors, ",.0f")
    rule = alt.Chart(pd.DataFrame({"y": [greenhouse_rows]}))
    ref = rule.mark_rule(color=SLATE, strokeDash=[5, 4]).encode(y="y:Q")
    lab = rule.mark_text(align="left", dx=6, dy=12, color=MUTED, fontSize=11).encode(
        y="y:Q", x=alt.value(0), text=alt.value(f"Whole greenhouse ({greenhouse_rows} rows)"))
    return lines + ref + lab


def pace_chart(pace: pd.DataFrame, colors: dict):
    return _task_lines(pace.dropna(subset=["min_per_row"]), "min_per_row", "Minutes per row", colors, ".1f")


def review_by_task_chart(sel: pd.DataFrame):
    d = sel.groupby("activity_name").agg(count=("hours", "size"), hours=("hours", "sum")).reset_index()
    d["hours"] = d["hours"].astype(float).round(1)
    return alt.Chart(d).mark_bar(color=SLATE, cornerRadiusEnd=4, size=18).encode(
        y=alt.Y("activity_name:N", title=None, sort="-x"),
        x=alt.X("count:Q", title="Registrations to check", axis=alt.Axis(tickMinStep=1)),
        tooltip=[alt.Tooltip("activity_name:N", title="Task"), alt.Tooltip("count:Q", title="Registrations"),
                 alt.Tooltip("hours:Q", title="Hours")])


# ---- year plan, targets and weekly check ------------------------------------------------------------
CAT_COLORS = {
    "Tomato harvest": "#1E8A3C", "Tomato crop work": "#2F67B1", "Packing & grading": "#C98500",
    "Strawberry harvest": "#8E5AA8", "Strawberry crop work": "#2A9D8F", "Clean-out & planting": "#8A6A45",
    "Pest control & general": "#9AA0A6", "Breaks (unpaid)": "#CDD1D6",
}
STATUS_COLORS = {"Slower than target": TOMATO, "On track": GREEN_DARK, "Faster than target": "#2F67B1",
                 "No target yet": "#C5C9CF"}


def plan_chart(plan: pd.DataFrame, unit: str, crew_people: float, hours_per_person: float, year: int):
    import datetime as _d
    cats = list(CAT_COLORS)
    k = 1 / hours_per_person if unit == "People" else 1.0
    long = plan.melt(id_vars=["iso_week"], value_vars=cats, var_name="activity", value_name="v")
    long["v"] = (long["v"] * k).round(1 if unit == "People" else 0)
    long["rank"] = long["activity"].map({c: i for i, c in enumerate(cats)})
    long["week_of"] = long["iso_week"].map(lambda w: f"{_d.date.fromisocalendar(int(year), int(w), 1):%b %d}")
    tot = plan.assign(total=(plan["Total hours"] * k).round(1 if unit == "People" else 0))
    tot["week_of"] = tot["iso_week"].map(lambda w: f"{_d.date.fromisocalendar(int(year), int(w), 1):%b %d}")
    x = alt.X("iso_week:O", title="Week of the year", axis=alt.Axis(labelAngle=0, values=list(range(1, 53, 4))))
    bars = alt.Chart(long).mark_bar(stroke="#fff", strokeWidth=0.4).encode(
        x=x, y=alt.Y("sum(v):Q", title=unit, stack="zero"),
        color=alt.Color("activity:N", scale=alt.Scale(domain=cats, range=[CAT_COLORS[c] for c in cats])),
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
    rule = rule_d.mark_rule(color=SLATE, strokeDash=[5, 4], strokeWidth=1.5).encode(y="y:Q")
    lab = rule_d.mark_text(align="left", dx=4, dy=-7, color=SLATE, fontSize=11, fontWeight=600).encode(
        y="y:Q", x=alt.value(4), text="lab:N")
    return bars + hit + rule + lab


def split_chart(cats: pd.Series):
    d = cats.rename("hours").reset_index().rename(columns={"index": "activity"})
    d.columns = ["activity", "hours"]
    d["share"] = d["hours"] / d["hours"].sum()
    d["label"] = d["share"].map(lambda s: f"{100 * s:.0f}%")
    order = d.sort_values("hours", ascending=False)["activity"].tolist()
    base = alt.Chart(d).encode(y=alt.Y("activity:N", title=None, sort=order))
    bars = base.mark_bar(cornerRadiusEnd=4, size=18).encode(
        x=alt.X("hours:Q", title="Hours in the year"),
        color=alt.Color("activity:N", scale=alt.Scale(domain=list(CAT_COLORS), range=list(CAT_COLORS.values())), legend=None),
        tooltip=[alt.Tooltip("activity:N", title="Activity"), alt.Tooltip("hours:Q", title="Hours", format=",.0f"),
                 alt.Tooltip("share:Q", title="Share", format=".1%")])
    text = base.mark_text(align="left", dx=4, color=MUTED, fontSize=11).encode(x="hours:Q", text="label:N")
    return bars + text


def on_track_chart(ot: pd.DataFrame, band_pct: float = 10.0):
    d = ot[ot["status"] != "No target yet"].copy()
    d["vs"] = d["vs_target_pct"].astype(float).round(1)
    zone = alt.Chart(pd.DataFrame({"lo": [-band_pct], "hi": [band_pct]})).mark_rect(color=GREEN_TINT).encode(
        x="lo:Q", x2="hi:Q")
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=SLATE).encode(x="x:Q")
    bars = alt.Chart(d).mark_bar(cornerRadiusEnd=4, size=18).encode(
        y=alt.Y("task:N", title=None, sort="-x"),
        x=alt.X("vs:Q", title="Minutes per row vs target (%; right = slower)"),
        color=alt.Color("status:N", scale=alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values())),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("task:N", title="Task"),
                 alt.Tooltip("actual_min_per_row:Q", title="This week (min/row)", format=".1f"),
                 alt.Tooltip("target_min_per_row:Q", title="Target (min/row)", format=".1f"),
                 alt.Tooltip("vs:Q", title="vs target (%)"), alt.Tooltip("hours_over:Q", title="Hours over", format=",.0f")])
    return zone + zero + bars


def untagged_chart(u: pd.DataFrame, flag_hours: float):
    d = u.copy()
    d["untagged"] = d["untagged"].astype(float).round(1)
    d["state"] = d["flag"].map({True: "To check", False: "Within normal range"})
    return alt.Chart(d).mark_bar(cornerRadiusEnd=2).encode(
        x=alt.X("untagged:Q", bin=alt.Bin(step=1), title="Hours present with no task, over the period"),
        y=alt.Y("count():Q", title="People"),
        color=alt.Color("state:N", scale=alt.Scale(domain=["Within normal range", "To check"], range=["#B8BEC6", TOMATO]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("count():Q", title="People"), alt.Tooltip("state:N", title="")])
