"""
Fresh4U labour planning prototype (BUS 439, team GLW BC).

Runs the same verified pipeline as the command line on either the bundled SYNTHETIC
demo exports or Priva exports the viewer uploads (processed in memory, not stored).
Styling and charts live in app_ui.py; the plain-language interpretations in fresh4u/insights.py.
"""
import glob
import hashlib
import os

import pandas as pd
import streamlit as st

import app_ui as ui
from fresh4u import insights as ins
from fresh4u import planner
from fresh4u.app_data import process
from fresh4u.coaching import best_task

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.join(HERE, "demo_data")
LOGO = os.path.join(HERE, "assets", "fresh4u_group_logo.png")

st.set_page_config(page_title=f"Fresh4U Labour Planner · {ui.TEAM}", page_icon=LOGO, layout="wide",
                   initial_sidebar_state="expanded")
ui.inject_css()


@st.cache_data(show_spinner="Reading and checking the exports...")
def load(key: tuple, files: list):
    return process(files)


def demo_files():
    out = []
    for p in sorted(glob.glob(os.path.join(DEMO_DIR, "*.xlsx"))):
        with open(p, "rb") as fh:
            out.append((os.path.basename(p), fh.read()))
    return out


def table(df, **kw):
    ui.full_width(st.dataframe, df, hide_index=True, **kw)


# ---- sidebar: brand + data source -----------------------------------------------------------
with st.sidebar:
    st.image(LOGO, width=150)
    st.markdown(f'<div class="f4-side-team">Labour Planner prototype by <b>{ui.TEAM}</b><br>'
                'BUS 439 &middot; Simon Fraser University</div>', unsafe_allow_html=True)
    st.divider()
    source = st.radio("Data source", ["Synthetic demo data", "Upload Priva exports"])
    demo = source == "Synthetic demo data"
    if demo:
        files = demo_files()
        st.caption("No Fresh4U records are in this app. One demo file was edited by hand on purpose, "
                   "to show that the checks catch it.")
    else:
        st.caption("Files are processed for this session only and are not saved. Do not upload client data "
                   "to a public deployment; run the app locally instead.")
        up = st.file_uploader("Priva Operational Report exports (.xlsx)", type=["xlsx"], accept_multiple_files=True)
        files = [(f.name, f.getvalue()) for f in (up or [])]

ui.hero(demo)

if not files:
    ui.callout("Upload one or more Priva Operational Report exports (.xlsx) in the sidebar to begin. "
               "Each file is checked against Priva's own totals before anything is shown.",
               tag="Waiting for files", tone="note")
    ui.footer(demo)
    st.stop()

key = tuple((n, hashlib.sha256(b).hexdigest()) for n, b in files)
res = load(key, files)
log, rec, pace, recon = res["log"], res["records"], res["pace"], res["recon"]
trust = ins.trust_counts(log, recon)

with st.sidebar:
    st.divider()
    st.markdown("**Data in use**")
    if rec.empty:
        ui.sidebar_summary([("Files loaded", f"{trust['loaded']} of {trust['files']}")])
    else:
        ui.sidebar_summary([
            ("Period", f"{rec['date'].min():%b %d} – {rec['date'].max():%b %d, %Y}"),
            ("Registrations", ins.n(len(rec))),
            ("Hours", ins.n(rec["hours"].sum())),
            ("Files loaded", f"{trust['loaded']} of {trust['files']}"),
            ("Totals reconciled", f"{trust['checks'] - trust['checks_failed']} of {trust['checks']}"),
        ])
    st.divider()
    with st.expander("About this prototype"):
        st.markdown(
            f"Built by **{ui.TEAM}** for The Fresh4U Group (BUS 439, SFU, Fall 2026).\n\n"
            "It reads Priva Performance exports by their column names, checks every record against Priva's "
            "own daily and grand totals, and only then plans labour, shows crew strengths and lists records "
            "to fix. Files that fail are held back with a plain reason, and the original files are never changed.")

if rec.empty:
    ui.callout("None of the files passed the checks, so there is nothing to plan from yet. "
               "The reasons are listed below.", tag="No usable data", tone="alert")
    for name, text in res["quarantine"].items():
        ui.quarantine_card(name, ins.quarantine_headline(text))
        with st.expander("Full details"):
            st.code(text, language=None)
    ui.footer(demo)
    st.stop()

colors = ui.task_colors(rec)
tasks = sorted(pace["activity_name"].dropna().unique())
focus = next(iter(colors))  # the task with the most hours
next_week = pace["week_start"].max() + pd.Timedelta(weeks=1)

tab_over, tab_plan, tab_crew, tab_review, tab_trends, tab_trust = st.tabs(
    ["Overview", "Weekly planner", "Crew strengths", "Review list", "Trends", "Data trust"])

# ---- overview -------------------------------------------------------------------------------------
with tab_over:
    rv = res["review"]
    ui.section("At a glance", f"{ins.day(rec['date'].min())} to {ins.day(rec['date'].max())}, "
                              f"{ins.plural(rec['activity_name'].nunique(), 'task')}, "
                              f"{ins.plural(rec['employee_id'].nunique(), 'person', 'people')}.")
    ui.kpis([
        ui.kpi_html("Registrations verified", ins.n(len(rec)), f"{ins.n(rec['hours'].sum())} hours of work"),
        ui.kpi_html("Priva totals reconciled", f"{trust['checks'] - trust['checks_failed']} / {trust['checks']}",
                    "every total matches its records" if not trust["checks_failed"] else "some totals differ",
                    tone="good" if not trust["checks_failed"] else "bad"),
        ui.kpi_html("Files held back", ins.n(trust["quarantined"]),
                    "did not add up, so not used" if trust["quarantined"] else "every file passed",
                    tone="bad" if trust["quarantined"] else "good"),
        ui.kpi_html("Registrations to review", ins.n(len(rv)),
                    f"{ins.pct(100 * rv['hours'].sum() / rec['hours'].sum(), 1)} of all hours" if len(rv) else "none",
                    tone="bad" if len(rv) else "good"),
    ])
    ui.callout(ins.overview_takeaways(res, focus), tag="Key takeaways")
    ui.section("How to use it", "Four steps a supervisor would follow each week.")
    ui.steps([
        ("Trust the data", "Every export is checked against Priva's own totals before it is used.", "Data trust"),
        ("Plan next week", "Rows to do × recent minutes per row gives the hours and people needed.", "Weekly planner"),
        ("Place the crew", "See who is strong at which task, shown as bands, never as a ranking.", "Crew strengths"),
        ("Fix odd records", "A short weekly list of registrations to correct in Priva.", "Review list"),
    ])

# ---- weekly planner ----------------------------------------------------------------------------------
with tab_plan:
    ui.section("How many people does a task need next week?",
               "Pick a task. The planner uses its recent pace; change any number to test a scenario.")
    c1, c2 = st.columns([2, 1])
    task = c1.selectbox("Task", tasks, index=tasks.index(focus) if focus in tasks else 0)
    lookback = c2.slider("Weeks of history to use", 2, 8, 4,
                         help="The pace is the median of these weeks, so one unusual week does not swing the plan.")
    pf = planner.pace_for(pace, task, next_week, lookback)
    if pf["weeks_used"] == 0:
        ui.callout("Not enough history for this task yet. At least one week with 50 or more rows is needed.",
                   tag="Not enough data", tone="note")
    else:
        c1, c2, c3 = st.columns(3)
        rows = c1.number_input("Rows to do", min_value=0, max_value=5000, value=planner.GREENHOUSE_ROWS, step=10,
                               help=f"The greenhouse has {planner.GREENHOUSE_ROWS} rows.")
        mpr = c2.number_input("Minutes per row", min_value=1.0, max_value=300.0,
                              value=round(pf["min_per_row"], 1), step=0.5,
                              help=f"Median of the {pf['weeks_used']} weeks from {pf['from_week']:%b %d} to "
                                   f"{pf['to_week']:%b %d}. Change it to test a target.")
        hpp = c3.number_input("Hours per person on this task", min_value=1.0, max_value=60.0, value=40.0, step=1.0,
                              help="How many hours one person spends on this task in the week.")
        p = planner.plan(rows, mpr, hpp)
        if pd.isna(p["hours_needed"]):
            ui.callout("Enter rows, minutes per row and hours per person above to get a plan.", tone="note",
                       tag="Waiting for inputs")
        else:
            ui.equation([
                ui.kpi_html("Rows to do", ins.n(rows)), "×",
                ui.kpi_html("Minutes per row", ins.n(mpr, 1), f"recent pace {ins.n(pf['min_per_row'], 1)}"), "÷ 60 =",
                ui.kpi_html("Hours needed", ins.n(p["hours_needed"])), f"÷ {ins.n(hpp)} h =",
                ui.kpi_html("People needed", ins.n(p["people_rounded"]),
                            f"{ins.n(p['people_exact'], 1)} rounded up", tone="good", hero_card=True),
            ])
            recent = ins.recent_pace(pace, task, next_week, lookback)
            ui.callout(ins.planner_takeaway(task, next_week, rows, mpr, hpp, p, pf, recent))

        pva = planner.plan_vs_actual(pace, task, lookback)
        ui.chart_title("Would this method have worked?",
                       "The same method applied to past weeks, given the rows that were actually done.")
        if len(pva):
            ui.show(ui.backtest_chart(pva), height=290)
            ui.callout(ins.backtest_takeaway(pva))
        else:
            ui.callout("Not enough past weeks to test the method on this task yet.", tone="note", tag="Note")
        with st.expander("How the plan is worked out"):
            st.markdown(
                "1. **Minutes per row** is the median of the chosen weeks for this task, counting only weeks "
                "with at least 50 rows done.\n"
                "2. **Hours needed** = rows to do × minutes per row ÷ 60.\n"
                "3. **People needed** = hours needed ÷ hours one person works on the task, rounded up.\n\n"
                "One row is 144.5 m², as Priva records it. Every number can be traced back to `weekly_by_task.csv`.")

# ---- crew strengths ----------------------------------------------------------------------------------
with tab_crew:
    ui.section("Who is strong at which task",
               "For supervisors only. Bands, not ranks. Speed only; it says nothing about quality.")
    s = res["strengths"]
    crew_tasks = sorted(s["activity_name"].unique())
    t2 = st.selectbox("Task", crew_tasks, index=crew_tasks.index(focus) if focus in crew_tasks else 0, key="crew_task")
    view = s[s["activity_name"] == t2]
    counts = view["band"].value_counts()
    tone = {"Strong": "good", "Developing": "neutral", "Ramping up": "neutral"}
    ui.kpis([ui.kpi_html(b, ins.n(int(counts.get(b, 0))), tone=tone.get(b, "neutral")) for b in ins.BAND_ORDER])
    ui.chart_title(f"Speed on {t2}, one dot per person",
                   "The shaded zone is within 10% of typical. Hover a dot for details.")
    ui.band_legend()
    ui.show(ui.strengths_chart(view), height=260)
    ui.callout(ins.crew_takeaway(view, t2))
    with st.expander("How to read this"):
        st.markdown(
            "- **Speed 100** is the typical (median) pace of everyone on that task in the same week, so a slow "
            "week for everyone does not count against anyone. **120** means 20% faster than typical.\n"
            "- **Strong** is 10% or more faster on average; **Developing** is 10% or more slower.\n"
            "- Nobody is banded on fewer than **4 weeks and 8 hours** on a task (*Not enough data*).\n"
            "- People in their first 6 weeks show as **Ramping up** instead of Developing.")
    order = {b: i for i, b in enumerate(ins.BAND_ORDER)}
    tbl = view.assign(_o=view["band"].map(order)).sort_values(["_o", "employee_id"])
    table(tbl[["employee_id", "employee_group", "band", "speed_index", "weeks", "hours"]],
          column_config={
              "employee_id": "Person",
              "employee_group": "Group",
              "band": "Band",
              "speed_index": st.column_config.NumberColumn("Speed (100 = typical)", format="%d"),
              "weeks": st.column_config.NumberColumn("Weeks on task"),
              "hours": st.column_config.NumberColumn("Hours on task", format="%.1f")})

    ui.chart_title("Each person's relatively strongest task")
    bt = best_task(s)
    ui.callout(ins.best_task_takeaway(bt))
    table(bt, column_config={
        "employee_id": "Person",
        "best_task": "Strongest task",
        "speed_index": st.column_config.NumberColumn("Speed (100 = typical)", format="%d"),
        "band": "Band"})

# ---- review list --------------------------------------------------------------------------------------
with tab_review:
    ui.section("Registrations to check in Priva",
               "Registrations that look wrong, week by week. Fix them in Priva, re-export and run again.")
    rv = res["review"]
    weeks = sorted(rec["week_start"].unique())
    wk = st.selectbox("Week starting", weeks, index=len(weeks) - 1, format_func=lambda d: ins.day(d))
    wk = pd.Timestamp(wk)
    sel = rv[(pd.to_datetime(rv["date"]) >= wk) & (pd.to_datetime(rv["date"]) < wk + pd.Timedelta(days=7))]
    hrs = rec.loc[rec["week_start"] == wk, "hours"].sum()
    ui.kpis([
        ui.kpi_html("Registrations to check", ins.n(len(sel)), f"week of {ins.short_day(wk)}",
                    tone="bad" if len(sel) else "good"),
        ui.kpi_html("Hours affected", ins.n(sel["hours"].sum(), 1), f"of {ins.n(hrs)} hours that week"),
        ui.kpi_html("Share of the week", ins.pct(100 * sel["hours"].sum() / hrs if hrs else 0, 1),
                    "of registered hours"),
    ])
    ui.callout(ins.review_takeaway(sel, hrs, wk), tone="alert" if len(sel) else "")
    if len(sel):
        ui.chart_title("Where they are", "Registrations to check, by task.")
        ui.show(ui.review_by_task_chart(sel), height=max(120, 42 * sel["activity_name"].nunique()))
        ui.chart_title("The list", "Excel row and file show exactly where each one came from.")
        table(sel, column_config={
            "date": st.column_config.DateColumn("Date", format="MMM D"),
            "activity_name": "Task",
            "location": "Location",
            "employee_group": "Group",
            "employee_id": "Person",
            "end_time": "Ended",
            "hours": st.column_config.NumberColumn("Hours", format="%.2f"),
            "min_per_row": st.column_config.NumberColumn("Min per row", format="%.0f"),
            "review_reason": st.column_config.TextColumn("Why it was flagged", width="large"),
            "source_file": "File",
            "excel_row": st.column_config.NumberColumn("Excel row", format="%d")})
        st.download_button("Download this week's list (CSV)", sel.to_csv(index=False).encode(),
                           file_name=f"review_{wk:%Y%m%d}.csv", mime="text/csv")
    with st.expander("How to fix a flagged registration"):
        st.markdown(
            "1. Open Priva's **Validation & Correction** screen and find the registration by person, date and time.\n"
            "2. Correct the end time or split the registration.\n"
            "3. Re-export that period and run the app again. The corrected file **replaces** the old one; "
            "nothing is counted twice.")

# ---- trends ---------------------------------------------------------------------------------------------
with tab_trends:
    ui.section("Hours, rows and pace over time", "Filter the tasks to compare. Each task keeps its colour throughout.")
    picked = st.multiselect("Tasks", list(colors), default=list(colors)[:len(ui.TASK_PALETTE)])
    if not picked:
        ui.callout("Pick at least one task above.", tone="note", tag="Nothing selected")
    else:
        wkly = (rec[rec["activity_name"].isin(picked)]
                .groupby(["week_start", "activity_name"])["hours"].sum().reset_index())
        pc = pace[pace["activity_name"].isin(picked)]
        ui.chart_title("Registered hours by task", "Total hours per week, stacked by task.")
        ui.show(ui.hours_chart(wkly, colors), height=300)
        ui.callout(ins.hours_takeaway(wkly))
        ui.chart_title("Rows completed by task",
                       f"Area done ÷ 144.5 m² per row. The dashed line is the whole greenhouse "
                       f"({planner.GREENHOUSE_ROWS} rows).")
        ui.show(ui.rows_chart(pc, colors, planner.GREENHOUSE_ROWS), height=300)
        ui.callout(ins.rows_takeaway(pc))
        ui.chart_title("Pace: minutes per row", "Lower is faster. Weeks with fewer than 50 rows are left out.")
        ui.show(ui.pace_chart(pc, colors), height=300)
        ui.callout(ins.pace_takeaway(pc))

# ---- data trust -------------------------------------------------------------------------------------------
with tab_trust:
    ui.section("Can we trust these numbers?",
               "Nothing is used until it adds up to Priva's own totals.")
    ui.kpis([
        ui.kpi_html("Files loaded", ins.n(trust["loaded"]), f"of {trust['files']} read", tone="good"),
        ui.kpi_html("Files held back", ins.n(trust["quarantined"]), "changed nothing",
                    tone="bad" if trust["quarantined"] else "good"),
        ui.kpi_html("Priva totals checked", ins.n(trust["checks"]), "daily subtotals and grand totals"),
        ui.kpi_html("Totals that failed", ins.n(trust["checks_failed"]), "in loaded files",
                    tone="bad" if trust["checks_failed"] else "good"),
    ])
    ui.callout(ins.trust_takeaway(trust))
    ui.steps([
        ("Read by column name", "Each file is read by its headers, never by position, so moved or extra "
                                "columns are handled.", ""),
        ("Check against Priva", "Every daily subtotal and the grand total must equal the sum of the records "
                                "underneath, for hours, result and area.", ""),
        ("Load or hold back", "Files that pass are added to the history; files that fail change nothing and "
                              "get a plain reason.", ""),
    ])
    loaded = log[log["status"] == "loaded"]
    if len(loaded):
        ui.chart_title("Files loaded")
        files_tbl = loaded[["file", "report_type", "period_start", "period_end", "records", "hours", "checks",
                            "checks_failed"]].copy()
        for c in ("period_start", "period_end"):
            files_tbl[c] = pd.to_datetime(files_tbl[c], errors="coerce")
        table(files_tbl, column_config={
            "file": st.column_config.TextColumn("File", width="large"),
            "report_type": "Report",
            "period_start": st.column_config.DateColumn("From", format="MMM D, YYYY"),
            "period_end": st.column_config.DateColumn("To", format="MMM D, YYYY"),
            "records": st.column_config.NumberColumn("Records", format="%d"),
            "hours": st.column_config.NumberColumn("Hours", format="%.0f"),
            "checks": st.column_config.NumberColumn("Totals checked", format="%d"),
            "checks_failed": st.column_config.NumberColumn("Failed", format="%d")})
    if res["quarantine"]:
        ui.chart_title("Files held back", "Fix the export (or the column mapping) and run again.")
        for name, text in res["quarantine"].items():
            ui.quarantine_card(name, ins.quarantine_headline(text))
            with st.expander("Full details"):
                st.code(text, language=None)

ui.footer(demo)
