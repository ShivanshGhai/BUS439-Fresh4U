"""
Fresh4U labour planning prototype (BUS 439, team GLW BC).

The loop: plan the whole year (Year plan) -> set per-task targets (Targets) -> check each week's numbers
before payroll (Weekly check), all from Priva's own exports after they pass the checks (Data trust).

Data sources: the bundled SYNTHETIC demo exports, exports in a folder on this computer (kept in a local
history so later runs only read new files), or uploaded exports (processed in memory, not stored).
Styling and charts live in app_ui.py; plain-language interpretations in fresh4u/insights.py.
"""
import glob
import hashlib
import os

import pandas as pd
import streamlit as st

import app_ui as ui
from fresh4u import insights as ins
from fresh4u import planner
from fresh4u import season_plan as sp
from fresh4u import targets as tg
from fresh4u import weekly_check as wc
from fresh4u.app_data import folder_fingerprint, process, process_folder
from fresh4u.coaching import best_task

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.join(HERE, "demo_data")
LOCAL_DATA = os.path.join(HERE, "data")            # git-ignored; the local history of real exports
LOGO = os.path.join(HERE, "assets", "fresh4u_group_logo.png")

st.set_page_config(page_title=f"Fresh4U Labour Planner · {ui.TEAM}", page_icon=LOGO, layout="wide",
                   initial_sidebar_state="expanded")
ui.inject_css()


@st.cache_data(show_spinner="Reading and checking the exports...")
def load(key: tuple, files: list):
    return process(files)


@st.cache_data(show_spinner="Reading and checking the exports in the folder (the first time takes a minute)...")
def load_folder(folder: str, fingerprint: tuple):
    return process_folder(folder, LOCAL_DATA)


def demo_files():
    out = []
    for p in sorted(glob.glob(os.path.join(DEMO_DIR, "*.xlsx"))):
        with open(p, "rb") as fh:
            out.append((os.path.basename(p), fh.read()))
    return out


def table(df, **kw):
    ui.full_width(st.dataframe, df, hide_index=True, **kw)


SOURCES = ["Synthetic demo data", "Exports on this computer", "Upload Priva exports"]

# ---- sidebar: brand + data source -----------------------------------------------------------
with st.sidebar:
    st.image(LOGO, width=150)
    st.markdown(f'<div class="f4-side-team">Labour Planner prototype by <b>{ui.TEAM}</b><br>'
                'BUS 439 &middot; Simon Fraser University</div>', unsafe_allow_html=True)
    st.divider()
    source = st.radio("Data source", SOURCES)
    demo = source == SOURCES[0]
    res = None
    if demo:
        files = demo_files()
        st.caption("No Fresh4U records are in this app. One demo file was edited by hand on purpose, "
                   "to show that the checks catch it.")
    elif source == SOURCES[1]:
        folder = st.text_input("Folder with the Priva exports", value=os.environ.get("FRESH4U_EXPORTS", ""),
                               help="Every .xlsx in this folder and its sub-folders is read. The originals are "
                                    "never changed. A history is kept in this app's data folder, so later runs "
                                    "only read new exports.")
        st.caption("For running on your own computer. Client data stays on this computer.")
        files = []
        if folder and os.path.isdir(folder):
            res = load_folder(folder, folder_fingerprint(folder))
        elif folder:
            st.error("That folder does not exist on this computer.")
    else:
        st.caption("Files are processed for this session only and are not saved. Do not upload client data "
                   "to a public deployment; run the app locally instead.")
        up = st.file_uploader("Priva exports (.xlsx)", type=["xlsx"], accept_multiple_files=True)
        files = [(f.name, f.getvalue()) for f in (up or [])]

ui.hero(demo, source)

if res is None and not files:
    msg = ("Enter the folder that holds the Priva exports in the sidebar (for example the 'Main project' folder). "
           if source == SOURCES[1] else "Upload one or more Priva exports (.xlsx) in the sidebar to begin. ")
    ui.callout(msg + "Each file is checked against Priva's own totals before anything is shown.",
               tag="Waiting for files", tone="note")
    ui.footer(demo)
    st.stop()

if res is None:
    key = tuple((n, hashlib.sha256(b).hexdigest()) for n, b in files)
    res = load(key, files)
log, rec, pace, recon = res["log"], res["records"], res["pace"], res["recon"]
trust = ins.trust_counts(log, recon)
not_used = log[log["status"] == "not used"] if len(log) else log

with st.sidebar:
    st.divider()
    st.markdown("**Data in use**")
    summary_rows = [("Files loaded", f"{trust['loaded']} of {trust['files']}"),
                    ("Totals reconciled", f"{trust['checks'] - trust['checks_failed']} of {trust['checks']}")]
    if not rec.empty:
        summary_rows = [("Registrations", f"{rec['date'].min():%b %d} – {rec['date'].max():%b %d, %Y}")] + summary_rows
    if not res["yield"].empty:
        y = res["yield"]
        summary_rows.insert(0, ("Yield", f"{int(y['year'].min())} – {int(y['year'].max())} wk {int(y[y['year'] == y['year'].max()]['iso_week'].max())}"))
    ui.sidebar_summary(summary_rows)
    st.divider()
    with st.expander("About this prototype"):
        st.markdown(
            f"Built by **{ui.TEAM}** for The Fresh4U Group (BUS 439, SFU, Fall 2026).\n\n"
            "It reads Priva exports by their column names, checks every record against Priva's own totals, "
            "and only then plans the year's labour, sets per-task targets and lists what to fix before "
            "payroll. Files that fail are held back with a plain reason, the original files are never changed, "
            "and employee names are replaced by employee numbers before anything is stored.")

if trust["loaded"] == 0:
    ui.callout("None of the files passed the checks, so there is nothing to plan from yet. "
               "The reasons are listed below.", tag="No usable data", tone="alert")
    for name, text in res["quarantine"].items():
        ui.quarantine_card(name, ins.quarantine_headline(text))
        with st.expander("Full details"):
            st.code(text, language=None)
    ui.footer(demo)
    st.stop()

R = res["rates"]
has_plan = bool(R) and bool(sp.basis_years(res["yield"]))
T = res["targets"]
hours_periods = wc.periods(res["hours"])

tab_over, tab_plan, tab_targets, tab_check, tab_trust, tab_more = st.tabs(
    ["Overview", "Year plan", "Targets", "Weekly check", "Data trust", "More"])

# ---- year plan (computed first: the overview quotes it) -------------------------------------------
plan = None
year = crew = None
with tab_plan:
    strip_slot = st.container()
    ui.section("How many people will we need each week of the year?",
               "Harvest from the yield curve, crop work from Priva's weekly pattern, plus packing, clean-out, "
               "pest control and breaks.")
    answer_slot = st.container()
    if not has_plan:
        ui.callout("The year plan needs a full year of weekly yield (Priva's Production (tactical) report) and at "
                   "least one whole-site week (a Production export or a Management Report).",
                   tag="Not enough data yet", tone="note")
    else:
        years = sp.basis_years(res["yield"])
        c1, c2, c3, c4 = st.columns(4)
        year = c1.selectbox("Yield to plan from", years, index=len(years) - 1,
                            help="A year with all 52 weeks of yield. Change the forecast with the sliders.")
        tom_pct = c2.slider("Tomato yield vs that year (%)", 50, 150, 100, step=5,
                            help="Your forecast for next season, as a share of the chosen year.")
        str_pct = c3.slider("Strawberry yield vs that year (%)", 50, 200, 100, step=5)
        co_weeks = c4.slider("Weeks to change over a house", 2, 10, sp.DEFAULTS["changeover_weeks"],
                             help="Clean-out and replanting. No data yet: confirm with the grower.")
        c1, c2, c3 = st.columns([1, 1, 2])
        hpp = c1.number_input("Hours per person per week", min_value=20.0, max_value=70.0,
                              value=float(round(R["hours_per_person"].value, 1)), step=0.5,
                              help=f"Measured: {R['hours_per_person'].based_on}.")
        crew = c2.number_input("TFW + local crew (people)", min_value=0, max_value=400,
                               value=int(round(R["crew"].value)), step=1,
                               help="The year-round crew. Everything above it is contractor work.")
        unit = c3.radio("Show", ["People", "Hours"], horizontal=True)
        settings = dict(changeover_weeks=co_weeks, hours_per_person=hpp)
        plan = sp.build_plan(sp.weekly_kg(res["yield"], year, tom_pct, str_pct), R, res["cw_points"], settings)
        s = sp.summary(plan, crew)
        cats = plan[sp.CATEGORIES].sum()
        with strip_slot:
            ui.season_strip(plan, year, crew, mark=[s["peak_week"]],
                            mark_label=f"Busiest week, {ins.n(s['peak_people'])} people")
        with answer_slot:
            ui.answer(f"Labour peaks at **{ins.n(s['peak_people'])} people** in {ins.week_label(s['peak_week'], year)}. "
                      f"The crew of {ins.n(crew)} covers **{52 - s['weeks_over_crew']} of 52** weeks; the rest needs "
                      "contractors.")
        ui.kpis([
            ui.kpi_html("Hours in the year", ins.n(s["total_hours"]), "registered, breaks included"),
            ui.kpi_html("Busiest week", f"{ins.n(s['peak_people'])} people", ins.week_label(s["peak_week"], year), tone="neutral"),
            ui.kpi_html("Quietest week", f"{ins.n(s['low_people'])} people", ins.week_label(s["low_week"], year)),
            ui.kpi_html("Weeks above the crew", f"{s['weeks_over_crew']} of 52", f"crew of {ins.n(crew)} people"),
            ui.kpi_html("Contractor person-weeks", ins.n(s["contractor_person_weeks"]), "above the TFW + local crew",
                        tone="neutral"),
        ])
        ui.chart_title(f"{unit} needed each week, by activity",
                       f"Yield of {year} × {tom_pct}% (tomato) and {str_pct}% (strawberry). Hover a bar for the week.")
        ui.show(ui.plan_chart(plan, unit, crew, hpp, year), height=340)
        ui.callout(ins.plan_takeaways(s, crew, year, cats)[1:], tag="What this means")

        c1, c2 = st.columns(2)
        with c1:
            ui.chart_title("Where the year's hours go")
            ui.show(ui.split_chart(cats), height=260)
        with c2:
            chk = sp.check_against_anchors(res["anchors"], R, res["cw_points"], res["yield"], settings)
            ui.chart_title("Check against the weeks Priva recorded", "Hours per week.")
            wide = chk.pivot_table(index="category", columns="week", values=["recorded", "plan"], sort=False)
            wide.columns = [f"{w}: {'recorded' if m == 'recorded' else 'plan'}" for m, w in wide.columns]
            wide = wide[sorted(wide.columns, key=lambda c: (c.split(":")[0], c.endswith("plan")))].reset_index()
            table(wide.round(0), column_config={"category": "Activity"})
        ui.callout(ins.check_takeaway(chk), tone="note", tag="How far to trust it")

        ui.chart_title("What each number rests on",
                       "'Assumed' rows are the questions for the grower. The rest come from the loaded exports.")
        rt = sp.rates_table(R, settings)
        rt["range"] = [f"{ins.n(lo, 1)} – {ins.n(hi, 1)}" if pd.notna(lo) and pd.notna(hi) and lo != hi else ""
                       for lo, hi in zip(rt["low"], rt["high"])]
        table(rt[["item", "value", "unit", "range", "based_on", "evidence"]], column_config={
            "item": "Item", "value": st.column_config.NumberColumn("Rate used", format="%.2f"), "unit": "Unit",
            "range": "Range seen", "based_on": st.column_config.TextColumn("Based on", width="large"),
            "evidence": "Evidence"})
        with st.expander("Week by week"):
            wk_tbl = plan[["iso_week", "Tomato t", "Strawberry t"] + sp.CATEGORIES +
                          ["Total hours", "People", "Changeover", "Tomato crop work from"]].round(1)
            table(wk_tbl, column_config={"iso_week": "Week"})
            st.download_button("Download the year plan (CSV)", wk_tbl.to_csv(index=False).encode(),
                               file_name=f"labour_plan_{year}_basis.csv", mime="text/csv")
        with st.expander("How the plan is worked out"):
            st.markdown(
                "- **Harvest hours** = forecast kg ÷ kg picked per hour (tomato; strawberry per house).\n"
                "- **Packing** = tonnes × hours per tonne for tomatoes, plus a fixed amount per strawberry house picking.\n"
                "- **Tomato crop work** follows the weekly hours Priva recorded for the seven crop-work tasks; weeks "
                "with no record are drawn as a straight line between recorded weeks.\n"
                "- **Clean-out & planting** is added for each house in the weeks after its last pick.\n"
                "- **Breaks** are a share of worked hours; **people** = hours ÷ registered hours per person per week.\n\n"
                "Each rate is pooled over every whole-site week loaded (a Production export or a Management Report), "
                "so each new export of that kind sharpens the plan.")

# ---- targets ------------------------------------------------------------------------------------
with tab_targets:
    t_strip = st.container()
    ui.section("Is each task on track?",
               "A target per task and season from Fresh4U's own history, for the grower to confirm and enter in Priva.")
    if T.empty:
        with t_strip:
            ui.season_strip(plan, year, crew)
        ui.callout("Targets need registrations with area (R&D Analytics) or a Production export.", tone="note",
                   tag="Not enough data yet")
    else:
        if len(res["priva_norm"]):
            nr = res["priva_norm"].iloc[-1]
            ui.answer(f"Priva grades every task against one norm, **{ins.n(nr.as_min_per_row, 1)} min/row**. "
                      f"Real paces run from {ins.n(T['target_min_per_row'].min(), 1)} to "
                      f"{ins.n(T['target_min_per_row'].max(), 0)} min/row, so {ins.n(T['task'].nunique())} tasks "
                      "get their own target below.", tone="warn")
            ui.callout("Entered in Priva as a norm per activity, these targets make Priva's own % performance and "
                       "phone app meaningful. The grower's numbers win: type them in the last column.",
                       tag="What to do", tone="warn")
        else:
            ui.answer(f"**{ins.n(T['task'].nunique())} tasks** now have their own target per season, from "
                      f"{ins.n(T['target_min_per_row'].min(), 1)} to {ins.n(T['target_min_per_row'].max(), 0)} min/row.")
            ui.callout(ins.priva_norm_takeaway(res["priva_norm"], T), tag="Priva's norm today", tone="note")
        c1, c2 = st.columns(2)
        crops = sorted(T["crop"].unique())
        crop = c1.selectbox("Crop", ["All"] + crops)
        seasons = [s for s in tg.SEASON_ORDER if s in set(T["season"].astype(str))]
        season = c2.selectbox("Season", ["All"] + seasons)
        view = T.copy()
        if crop != "All":
            view = view[view["crop"] == crop]
        if season != "All":
            view = view[view["season"].astype(str) == season]
        view = view.assign(season=view["season"].astype(str), grower_min_per_row=float("nan"))
        ui.chart_title("Targets", "Minutes per row (lower is faster). 'Good week' is the fastest quarter of weeks. "
                                  "Type the grower's own number in the last column to replace ours.")
        cols = ["task", "crop", "season", "target_min_per_row", "good_week", "slow_week", "weeks", "kg_per_hour",
                "evidence", "priva_norm_m2_per_hour", "grower_min_per_row"]
        cfg = {"task": "Task", "crop": "Crop", "season": "Season",
               "target_min_per_row": st.column_config.NumberColumn("Target (min/row)", format="%.1f"),
               "good_week": st.column_config.NumberColumn("Good week", format="%.1f"),
               "slow_week": st.column_config.NumberColumn("Slow week", format="%.1f"),
               "weeks": st.column_config.NumberColumn("Weeks of data", format="%d"),
               "kg_per_hour": st.column_config.NumberColumn("kg per hour", format="%.0f"),
               "evidence": "Evidence",
               "priva_norm_m2_per_hour": st.column_config.NumberColumn("As a Priva norm (m²/h)", format="%.0f"),
               "grower_min_per_row": st.column_config.NumberColumn("Grower's target (min/row)", format="%.1f")}
        # Display copy: optional numbers show "—" when there is no value, never "None" (the CSV uses `view`).
        disp = view[cols].copy()
        for c, fmt in (("good_week", "{:.1f}"), ("slow_week", "{:.1f}"), ("kg_per_hour", "{:,.0f}"),
                       ("priva_norm_m2_per_hour", "{:,.0f}")):
            disp[c] = disp[c].map(lambda v, f=fmt: f.format(v) if pd.notna(v) else "—")
        for c, label in (("good_week", "Good week"), ("slow_week", "Slow week"), ("kg_per_hour", "kg per hour"),
                         ("priva_norm_m2_per_hour", "As a Priva norm (m²/h)")):
            cfg[c] = label
        edited = ui.full_width(st.data_editor, disp, hide_index=True, column_config=cfg,
                               disabled=cols[:-1], key="targets_editor")
        edited = view[cols] if edited is None else edited
        agreed = tg.for_priva(view, pd.Series(edited["grower_min_per_row"].to_numpy(), index=view.index))
        st.download_button("Download targets to enter in Priva (CSV)", agreed.round(2).to_csv(index=False).encode(),
                           file_name="targets_for_priva.csv", mime="text/csv")
        with st.expander("How targets are set"):
            st.markdown(
                "- **Target** = the median weekly minutes per row for that task in that season, from the weeks Priva "
                "recorded (R&D Analytics registrations). Tasks seen only in a Production export use that fortnight.\n"
                "- **Good week / slow week** = the fastest and slowest quarter of weeks.\n"
                "- **As a Priva norm** = 60 × 144.5 ÷ minutes per row, the m² per hour Priva's '% performance' divides by.\n"
                "- The grower's numbers win. In the interview the grower mentioned **43 minutes per row**, close to "
                "the picking pace here (about 40); which task it was for is a question for the visit.")

        ui.section("Was a week on track?", "Each task's pace that week against its target for the season. "
                                           "The target leaves the week itself out.")
        weeks = sorted(pace["week_start"].unique()) if len(pace) else []
        if not weeks:
            with t_strip:
                ui.season_strip(plan, year, crew)
        if weeks:
            comparable = [i for i, w in enumerate(weeks)
                          if (tg.week_on_track(pace, T, w)["status"] != "No target yet").any()]
            wk = pd.Timestamp(st.selectbox("Week starting", weeks, index=comparable[-1] if comparable else len(weeks) - 1,
                                           format_func=ins.day, key="ot_week",
                                           help="Opens on the latest week that has other weeks of its season to compare with."))
            ot = tg.week_on_track(pace, T, wk)
            with t_strip:
                ui.season_strip(plan, year, crew, mark=ui.iso_weeks_between(wk, wk + pd.Timedelta(days=6)),
                                mark_label="Week checked")
            ui.callout(ins.on_track_takeaway(ot, wk))
            if len(ot[ot["status"] != "No target yet"]):
                ui.show(ui.on_track_chart(ot, 100 * tg.ON_TRACK_BAND), height=max(140, 40 * len(ot)))
            table(ot, column_config={
                "task": "Task",
                "actual_min_per_row": st.column_config.NumberColumn("This week (min/row)", format="%.1f"),
                "target_min_per_row": st.column_config.NumberColumn("Target (min/row)", format="%.1f"),
                "vs_target_pct": st.column_config.NumberColumn("vs target (%)", format="%+.0f"),
                "status": "Status", "rows_done": st.column_config.NumberColumn("Rows done", format="%.0f"),
                "hours": st.column_config.NumberColumn("Hours", format="%.0f"),
                "hours_at_target": st.column_config.NumberColumn("Hours at target", format="%.0f"),
                "hours_over": st.column_config.NumberColumn("Hours over", format="%+.0f"),
                "target_weeks": st.column_config.NumberColumn("Target from (weeks)", format="%d")})

# ---- weekly check ----------------------------------------------------------------------------------
with tab_check:
    c_strip = st.container()
    ui.section("Can this period's numbers be trusted?",
               "A list for supervisors to fix in Priva before payroll. People are shown by employee number only.")
    if not hours_periods:
        with c_strip:
            ui.season_strip(plan, year, crew)
        ui.callout("The weekly check needs Priva's Hours report (present, registered and paid hours per person) "
                   "for the period.", tone="note", tag="Not enough data yet")
    else:
        per = st.selectbox("Pay period", hours_periods, format_func=lambda p: f"{ins.day(p[0])} – {ins.day(p[1])}")
        unt = wc.untagged(res["hours"], per)
        slow = wc.slow_registrations(res["review"], per)
        locs = wc.location_problems(res["production"], per)
        sm = wc.summary(unt, slow, locs)
        with c_strip:
            ui.season_strip(plan, year, crew, mark=ui.iso_weeks_between(*per), mark_label="Pay period")
        ui.answer(f"**{ins.n(sm['untagged'])} h** of present time had no task booked. "
                  f"{ins.plural(sm['people_flagged'], 'person', 'people')} to check before Tuesday's payroll.",
                  tone="warn" if sm["untagged"] else "")
        ui.kpis([
            ui.kpi_html("Present but untagged", f"{ins.n(sm['untagged'])} h",
                        f"{ins.pct(100 * sm['untagged'] / sm['present'], 1)} of present time", tone="warn"),
            ui.kpi_html("People to check", ins.n(sm["people_flagged"]), f"of {ins.n(sm['people'])} present",
                        tone="warn" if sm["people_flagged"] else "good"),
            ui.kpi_html("Registrations 3x+ usual", ins.n(sm["slow"]), f"{ins.n(sm['slow_hours'], 1)} h",
                        tone="warn" if sm["slow"] else "good"),
            ui.kpi_html("Locations that can't be right", ins.n(sm["loc_items"]), f"{ins.n(sm['loc_hours'])} h",
                        tone="warn" if sm["loc_items"] else "good"),
        ])
        ui.callout(ins.weekly_check_takeaway(sm, per))
        lst = wc.supervisor_list(unt, slow, locs)
        ui.chart_title("The list, most hours first", "Work down it in Priva's Validation & Correction screen.")
        table(lst, column_config={
            "check": "Check", "employee": "Employee no.", "group": "Group", "where": "Where", "task": "Task",
            "hours": st.column_config.NumberColumn("Hours", format="%.1f"),
            "what_to_do": st.column_config.TextColumn("What to do", width="large")})
        st.download_button("Download the list (CSV)", lst.to_csv(index=False).encode(),
                           file_name=f"weekly_check_{per[0]}_{per[1]}.csv", mime="text/csv")
        c1, c2 = st.columns(2)
        with c1:
            ui.chart_title("Untagged time per person",
                           f"Flagged at {ins.n(wc.UNTAGGED_MIN_HOURS)} h or more and at least "
                           f"{ins.pct(100 * wc.UNTAGGED_MIN_SHARE)} of present time.")
            ui.show(ui.untagged_chart(unt, wc.UNTAGGED_MIN_HOURS), height=240)
        with c2:
            ui.chart_title("Where the registrations to check are")
            if len(slow):
                ui.show(ui.review_by_task_chart(slow), height=max(120, 42 * slow["activity_name"].nunique()))
            else:
                ui.callout("No registration in this period took 3x the usual time.", tone="note", tag="None")
        with st.expander("Everyone's present, registered and paid hours"):
            table(unt, column_config={
                "employee_id": "Employee no.", "employee_group": "Group",
                "present": st.column_config.NumberColumn("Present h", format="%.1f"),
                "registered": st.column_config.NumberColumn("Registered h", format="%.1f"),
                "paid": st.column_config.NumberColumn("Paid h", format="%.1f"),
                "days_present": st.column_config.NumberColumn("Days present", format="%d"),
                "untagged": st.column_config.NumberColumn("Untagged h", format="%.1f"),
                "untagged_min_per_day": st.column_config.NumberColumn("Untagged min/day", format="%.0f"),
                "flag": "To check"})
        with st.expander("What each check means"):
            st.markdown(
                "- **Present but untagged**: present hours (Hours report) minus registered hours. Time at work with no task "
                "booked is usually a missed tag-in after a break, or a task never started on the phone.\n"
                "- **3x+ usual time**: one registration took three times the task's median minutes per row. Covers the "
                "tasks in the R&D Analytics exports (tomato crop work).\n"
                "- **Location can't be right**: a strawberry task on a tomato row (or the reverse), or a row task with no row.\n\n"
                "After fixing in Priva, re-export the period and run again: the corrected file replaces the old one.")

# ---- overview -------------------------------------------------------------------------------------
with tab_over:
    latest = ui.iso_weeks_between(*hours_periods[0]) if hours_periods else []
    ui.season_strip(plan, year, crew, mark=latest, mark_label="Latest pay period" if latest else "")
    ui.section("The season at a glance")
    if plan is not None:
        s_over = sp.summary(plan, crew)
        ui.answer(f"Next season peaks at **{ins.n(s_over['peak_people'])} people** in week {s_over['peak_week']}. "
                  f"The crew of {ins.n(crew)} covers {52 - s_over['weeks_over_crew']} of 52 weeks, and every Priva "
                  f"total checked adds up ({trust['checks'] - trust['checks_failed']} of {trust['checks']}).")
    else:
        ui.answer(f"**{trust['checks'] - trust['checks_failed']} of {trust['checks']}** Priva totals add up to their "
                  "records.", tone="" if not trust["checks_failed"] else "bad")
    cards = []
    if plan is not None:
        s0 = s_over
        cards.append(ui.kpi_html("Weeks above the TFW crew", f"{s0['weeks_over_crew']} of 52",
                                 "contractors needed", tone="neutral"))
    if not T.empty:
        cards.append(ui.kpi_html("Tasks with a target", ins.n(T["task"].nunique()),
                                 f"Priva uses one norm for all" if len(res["priva_norm"]) else "from history"))
    if hours_periods:
        u0 = wc.untagged(res["hours"], hours_periods[0])
        cards.append(ui.kpi_html("Untagged time, latest period", f"{ins.n(u0['untagged'].sum())} h",
                                 f"{ins.n(int(u0['flag'].sum()))} people to check", tone="warn"))
    cards.append(ui.kpi_html("Priva totals reconciled", f"{trust['checks'] - trust['checks_failed']} / {trust['checks']}",
                             "every total matches its records" if not trust["checks_failed"] else "some totals differ",
                             tone="good" if not trust["checks_failed"] else "bad"))
    cards.append(ui.kpi_html("Files held back", ins.n(trust["quarantined"]),
                             "caught by the checks, so not used" if trust["quarantined"] else "every file passed",
                             tone="warn" if trust["quarantined"] else "good"))
    ui.kpis(cards)
    take = [ins.trust_takeaway(trust)]
    if plan is not None:
        take += ins.plan_takeaways(s0, crew, year, plan[sp.CATEGORIES].sum())[1:3]
    if hours_periods:
        take.append(ins.weekly_check_takeaway(wc.summary(u0, wc.slow_registrations(res["review"], hours_periods[0]),
                                                         wc.location_problems(res["production"], hours_periods[0])),
                                              hours_periods[0])[0])
    ui.callout(take, tag="Key takeaways")
    ui.section("How it works", "A loop: each week's fixes make the next plan and targets better.")
    ui.steps([
        ("Plan the year", "Hours and people per week for every house and activity, from yield and Priva's rates.",
         "Year plan"),
        ("Set targets", "A pace per task and season from history, confirmed by the grower and entered in Priva.",
         "Targets"),
        ("Check the week", "Before payroll: untagged time, slow registrations and impossible locations.", "Weekly check"),
        ("Trust the data", "Every export is checked against Priva's own totals before it is used.", "Data trust"),
    ])

# ---- data trust -------------------------------------------------------------------------------------------
with tab_trust:
    covered = ui.iso_weeks_between(rec["date"].min(), rec["date"].max()) if not rec.empty else []
    ui.season_strip(plan, year, crew, mark=covered, mark_label="Registrations loaded" if covered else "")
    ui.section("Can we trust these numbers?",
               "Nothing is used until it adds up to Priva's own totals.")
    ui.answer(f"**{trust['checks'] - trust['checks_failed']} of {trust['checks']}** Priva totals match the records "
              f"underneath them. {ins.plural(trust['quarantined'], 'file')} held back.",
              tone="bad" if trust["checks_failed"] else "")
    ui.kpis([
        ui.kpi_html("Files loaded", ins.n(trust["loaded"]), f"of {trust['files']} read", tone="good"),
        ui.kpi_html("Files held back", ins.n(trust["quarantined"]),
                    "caught by the checks; changed nothing" if trust["quarantined"] else "every file passed",
                    tone="warn" if trust["quarantined"] else "good"),
        ui.kpi_html("Recognised, not used", ins.n(len(not_used)),
                    "reason listed below" if len(not_used) else "every file was used"),
        ui.kpi_html("Priva totals checked", ins.n(trust["checks"]), "subtotals and grand totals"),
        ui.kpi_html("Totals that failed", ins.n(trust["checks_failed"]), "in loaded files",
                    tone="bad" if trust["checks_failed"] else "good"),
    ])
    ui.steps([
        ("Read by column name", "Each file is read by its headers, never by position, so moved or extra "
                                "columns are handled.", ""),
        ("Check against Priva", "Every subtotal and grand total must equal the sum of the records underneath.", ""),
        ("No names kept", "Employee names are replaced by the employee number before anything is stored.", ""),
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
        for c in ("records", "hours", "checks", "checks_failed"):
            files_tbl[c] = pd.to_numeric(files_tbl[c], errors="coerce")
        table(files_tbl, column_config={
            "file": st.column_config.TextColumn("File", width="large"),
            "report_type": "Report",
            "period_start": st.column_config.DateColumn("From", format="MMM D, YYYY"),
            "period_end": st.column_config.DateColumn("To", format="MMM D, YYYY"),
            "records": st.column_config.NumberColumn("Records", format="%d"),
            "hours": st.column_config.NumberColumn("Hours", format="%.0f"),
            "checks": st.column_config.NumberColumn("Totals checked", format="%d"),
            "checks_failed": st.column_config.NumberColumn("Failed", format="%d")})
    if len(not_used):
        ui.chart_title("Recognised but not used yet")
        table(not_used[["file", "report_type", "message"]], column_config={
            "file": "File", "report_type": "Report", "message": st.column_config.TextColumn("Why", width="large")})
    if res["quarantine"]:
        ui.chart_title("Files held back", "Fix the export (or the column mapping) and run again.")
        for name, text in res["quarantine"].items():
            ui.quarantine_card(name, ins.quarantine_headline(text))
            with st.expander("Full details"):
                st.code(text, language=None)

# ---- more: last night's single-task views -------------------------------------------------------------------
with tab_more:
    if rec.empty:
        ui.season_strip(plan, year, crew)
        ui.callout("These views need registrations (R&D Analytics exports).", tone="note", tag="Not enough data")
    else:
        colors = ui.task_colors(rec)
        tasks = sorted(pace["activity_name"].dropna().unique())
        focus = next(iter(colors))
        next_week = pace["week_start"].max() + pd.Timedelta(weeks=1)
        ui.season_strip(plan, year, crew, mark=[int(pd.Timestamp(next_week).isocalendar()[1])],
                        mark_label="Next week")
        m_plan, m_crew, m_review, m_trends = st.tabs(["One task, next week", "Crew strengths", "Review list", "Trends"])
        with m_plan:
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
                                       help=f"Houses 1 and 2 have {planner.GREENHOUSE_ROWS} rows.")
                mpr = c2.number_input("Minutes per row", min_value=1.0, max_value=300.0,
                                      value=round(pf["min_per_row"], 1), step=0.5,
                                      help=f"Median of the {pf['weeks_used']} weeks from {pf['from_week']:%b %d} to "
                                           f"{pf['to_week']:%b %d}. Change it to test a target.")
                hpp1 = c3.number_input("Hours per person on this task", min_value=1.0, max_value=60.0, value=40.0, step=1.0)
                p = planner.plan(rows, mpr, hpp1)
                if not pd.isna(p["hours_needed"]):
                    ui.equation([
                        ui.kpi_html("Rows to do", ins.n(rows)), "×",
                        ui.kpi_html("Minutes per row", ins.n(mpr, 1), f"recent pace {ins.n(pf['min_per_row'], 1)}"), "÷ 60 =",
                        ui.kpi_html("Hours needed", ins.n(p["hours_needed"])), f"÷ {ins.n(hpp1)} h =",
                        ui.kpi_html("People needed", ins.n(p["people_rounded"]),
                                    f"{ins.n(p['people_exact'], 1)} rounded up", tone="good", hero_card=True),
                    ])
                    recent = ins.recent_pace(pace, task, next_week, lookback)
                    ui.callout(ins.planner_takeaway(task, next_week, rows, mpr, hpp1, p, pf, recent))
                pva = planner.plan_vs_actual(pace, task, lookback)
                ui.chart_title("Would this method have worked?",
                               "The same method applied to past weeks, given the rows that were actually done.")
                if len(pva):
                    ui.show(ui.backtest_chart(pva), height=290)
                    ui.callout(ins.backtest_takeaway(pva))
        with m_crew:
            ui.section("Who is strong at which task",
                       "For supervisors only. Bands, not ranks. Speed only; it says nothing about quality. "
                       "Parked until we know how 'Greenhouse Incentive' pay works.")
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
            bt = best_task(s)
            ui.chart_title("Each person's relatively strongest task")
            table(bt, column_config={
                "employee_id": "Person", "best_task": "Strongest task",
                "speed_index": st.column_config.NumberColumn("Speed (100 = typical)", format="%d"), "band": "Band"})
        with m_review:
            ui.section("Registrations to check in Priva", "Week by week, for the tasks in the R&D Analytics exports.")
            rv = res["review"]
            weeks = sorted(rec["week_start"].unique())
            wk2 = pd.Timestamp(st.selectbox("Week starting", weeks, index=len(weeks) - 1, format_func=ins.day,
                                            key="review_week"))
            sel = rv[(pd.to_datetime(rv["date"]) >= wk2) & (pd.to_datetime(rv["date"]) < wk2 + pd.Timedelta(days=7))]
            hrs = rec.loc[rec["week_start"] == wk2, "hours"].sum()
            ui.callout(ins.review_takeaway(sel, hrs, wk2), tone="warn" if len(sel) else "")
            if len(sel):
                table(sel, column_config={
                    "date": st.column_config.DateColumn("Date", format="MMM D"), "activity_name": "Task",
                    "location": "Location", "employee_group": "Group", "employee_id": "Person", "end_time": "Ended",
                    "hours": st.column_config.NumberColumn("Hours", format="%.2f"),
                    "min_per_row": st.column_config.NumberColumn("Min per row", format="%.0f"),
                    "review_reason": st.column_config.TextColumn("Why it was flagged", width="large"),
                    "source_file": "File", "excel_row": st.column_config.NumberColumn("Excel row", format="%d")})
        with m_trends:
            ui.section("Hours, rows and pace over time", "Tomato crop-work tasks in the R&D Analytics exports.")
            picked = st.multiselect("Tasks", list(colors), default=list(colors)[:len(ui.TASK_PALETTE)])
            if picked:
                wkly = (rec[rec["activity_name"].isin(picked)]
                        .groupby(["week_start", "activity_name"])["hours"].sum().reset_index())
                pc = pace[pace["activity_name"].isin(picked)]
                ui.chart_title("Registered hours by task", "Total hours per week, stacked by task.")
                ui.show(ui.hours_chart(wkly, colors), height=300)
                ui.callout(ins.hours_takeaway(wkly))
                ui.chart_title("Pace: minutes per row", "Lower is faster. Weeks with fewer than 50 rows are left out.")
                ui.show(ui.pace_chart(pc, colors), height=300)
                ui.callout(ins.pace_takeaway(pc))

ui.footer(demo)
