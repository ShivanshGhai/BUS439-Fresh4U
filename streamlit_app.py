"""
Fresh4U labour planning prototype (BUS 439, Team BCGLW).

Runs the same verified pipeline as the command line on either the bundled SYNTHETIC
demo exports or Priva exports the viewer uploads (processed in memory, not stored).
"""
import glob
import hashlib
import os

import pandas as pd
import streamlit as st

from fresh4u import planner
from fresh4u.app_data import process
from fresh4u.coaching import best_task

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.join(HERE, "demo_data")

st.set_page_config(page_title="Fresh4U labour planner", layout="wide")


@st.cache_data(show_spinner="Reading and checking the exports...")
def load(key: tuple, files: list):
    return process(files)


def demo_files():
    out = []
    for p in sorted(glob.glob(os.path.join(DEMO_DIR, "*.xlsx"))):
        with open(p, "rb") as fh:
            out.append((os.path.basename(p), fh.read()))
    return out


# ---- source -------------------------------------------------------------------
st.title("Fresh4U labour planner")
st.caption("Prototype by Team BCGLW, BUS 439. Built on Priva Performance exports.")

source = st.radio("Data", ["Synthetic demo data", "Upload Priva exports"], horizontal=True)
if source == "Synthetic demo data":
    files = demo_files()
    st.info("Showing SYNTHETIC demo data. No Fresh4U records are in this app. "
            "One demo file was edited by hand on purpose, to show that the checks catch it.")
else:
    st.warning("Uploaded files are processed for this session only and are not saved. "
               "Do not upload client data to a public deployment; run the app locally instead.")
    up = st.file_uploader("Priva Operational Report exports (.xlsx)", type=["xlsx"], accept_multiple_files=True)
    files = [(f.name, f.getvalue()) for f in (up or [])]
    if not files:
        st.stop()

key = tuple((n, hashlib.sha256(b).hexdigest()) for n, b in files)
res = load(key, files)
log, rec, pace = res["log"], res["records"], res["pace"]

tab_checks, tab_plan, tab_crew, tab_review, tab_trends = st.tabs(
    ["Data checks", "Weekly planner", "Crew strengths", "Review list", "Trends"])

# ---- data checks --------------------------------------------------------------
with tab_checks:
    loaded = log[log["status"] == "loaded"] if len(log) else log
    quarantined = log[log["status"] == "quarantined"] if len(log) else log
    recon = res["recon"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Files loaded", len(loaded))
    c2.metric("Files quarantined", len(quarantined))
    c3.metric("Priva totals checked", len(recon))
    c4.metric("Totals that failed", int((~recon["match"].astype(bool)).sum()) if len(recon) else 0)
    st.markdown("Every file is read by its headers, and its records must add up to Priva's own daily "
                "and grand totals before anything is loaded. Files that fail change nothing and are listed below.")
    if len(loaded):
        show = loaded[["file", "report_type", "period_start", "period_end", "records", "hours", "checks", "checks_failed"]]
        st.dataframe(show, hide_index=True, use_container_width=True)
    for name, text in res["quarantine"].items():
        with st.expander(f"Quarantined: {name}"):
            st.code(text, language=None)
    if rec.empty:
        st.error("No Performance data loaded, so the other tabs are empty.")
        st.stop()
    st.caption(f"{len(rec):,} registrations, {rec['hours'].sum():,.1f} hours, "
               f"{rec['date'].min():%b %d, %Y} to {rec['date'].max():%b %d, %Y}.")

# ---- planner --------------------------------------------------------------------
with tab_plan:
    st.subheader("How many people does a task need next week?")
    tasks = sorted(pace["activity_name"].dropna().unique())
    default_task = tasks.index("Clipping") if "Clipping" in tasks else 0
    c1, c2 = st.columns(2)
    task = c1.selectbox("Task", tasks, index=default_task)
    next_week = pace["week_start"].max() + pd.Timedelta(weeks=1)
    lookback = c2.slider("Weeks of history to use", 2, 8, 4)
    pf = planner.pace_for(pace, task, next_week, lookback)
    if pf["weeks_used"] == 0:
        st.warning("Not enough history for this task yet.")
    else:
        c1, c2, c3 = st.columns(3)
        rows = c1.number_input("Rows to do", min_value=0, max_value=5000, value=planner.GREENHOUSE_ROWS, step=10)
        mpr = c2.number_input("Minutes per row", min_value=1.0, max_value=300.0,
                              value=round(pf["min_per_row"], 1), step=0.5,
                              help=f"Median of the {pf['weeks_used']} weeks from "
                                   f"{pf['from_week']:%b %d} to {pf['to_week']:%b %d}. Change it to test a target.")
        hpp = c3.number_input("Hours per person on this task per week", min_value=1.0, max_value=60.0,
                              value=40.0, step=1.0)
        p = planner.plan(rows, mpr, hpp)
        m1, m2, m3 = st.columns(3)
        m1.metric("Hours needed", f"{p['hours_needed']:,.0f}")
        m2.metric("People needed", f"{p['people_rounded']}")
        m3.metric("History pace", f"{pf['min_per_row']:.1f} min/row")
        st.markdown(f"**Method:** {rows:,} rows × {mpr:.1f} min ÷ 60 = **{p['hours_needed']:,.0f} hours**; "
                    f"÷ {hpp:.0f} h per person = {p['people_exact']:.1f}, rounded up to **{p['people_rounded']} people**.")
        pva = planner.plan_vs_actual(pace, task, lookback)
        if len(pva):
            st.markdown("**Would this have worked?** The same method applied to past weeks, knowing the rows done:")
            chart = pva.melt(id_vars="week_start", value_vars=["actual_hours", "planned_hours"],
                             var_name="series", value_name="hours")
            chart["series"] = chart["series"].map({"actual_hours": "Actual", "planned_hours": "Planned"})
            st.line_chart(chart, x="week_start", y="hours", color="series")
            st.caption(f"Typical miss: {pva['variance_pct'].abs().median():.1f}% of actual hours.")

# ---- crew strengths ---------------------------------------------------------------
with tab_crew:
    st.subheader("Who is strong at which task")
    st.caption("For supervisors only. Bands, not ranks. Speed is compared with the same task in the same week. "
               "Nobody is banded on fewer than 4 weeks and 8 hours. New starters show as 'Ramping up'. "
               "Speed says nothing about quality.")
    s = res["strengths"]
    t2 = st.selectbox("Task", sorted(s["activity_name"].unique()), key="crew_task")
    view = s[s["activity_name"] == t2]
    order = ["Strong", "Typical", "Developing", "Ramping up", "Not enough data"]
    cols = st.columns(len(order))
    for c, b in zip(cols, order):
        c.metric(b, int((view["band"] == b).sum()))
    view = view.assign(_o=view["band"].map({b: i for i, b in enumerate(order)})).sort_values(["_o", "employee_id"])
    st.dataframe(view[["employee_id", "employee_group", "band", "speed_index", "weeks", "hours"]]
                 .rename(columns={"speed_index": "speed (100 = typical)", "employee_id": "person"}),
                 hide_index=True, use_container_width=True)
    st.markdown("**Each person's relatively strongest task**")
    st.dataframe(best_task(s).rename(columns={"employee_id": "person", "speed_index": "speed (100 = typical)"}),
                 hide_index=True, use_container_width=True)

# ---- review list ---------------------------------------------------------------------
with tab_review:
    st.subheader("Registrations to check in Priva")
    rv = res["review"]
    st.caption("Fix these in Priva's Validation & Correction screen, re-export the period and run again; "
               "the corrected file replaces the old one.")
    weeks = sorted(rec["week_start"].unique())
    wk = st.selectbox("Week starting", weeks, index=len(weeks) - 1, format_func=lambda d: f"{pd.Timestamp(d):%b %d, %Y}")
    wk = pd.Timestamp(wk)
    sel = rv[(pd.to_datetime(rv["date"]) >= wk) & (pd.to_datetime(rv["date"]) < wk + pd.Timedelta(days=7))]
    hrs = rec.loc[rec["week_start"] == wk, "hours"].sum()
    st.metric("Registrations to check this week", len(sel),
              help=f"{sel['hours'].sum():,.1f} of {hrs:,.1f} hours")
    st.dataframe(sel, hide_index=True, use_container_width=True)
    st.download_button("Download this week's list (CSV)", sel.to_csv(index=False).encode(),
                       file_name=f"review_{wk:%Y%m%d}.csv", mime="text/csv")

# ---- trends ----------------------------------------------------------------------------
with tab_trends:
    st.subheader("Hours and rows per week")
    wkly = (rec.groupby(["week_start", "activity_name"])["hours"].sum().reset_index())
    st.markdown("**Registered hours by task**")
    st.bar_chart(wkly, x="week_start", y="hours", color="activity_name")
    st.markdown("**Rows completed by task** (area ÷ 144.5 m²; the greenhouse has 560)")
    st.line_chart(pace, x="week_start", y="rows_done", color="activity_name")
