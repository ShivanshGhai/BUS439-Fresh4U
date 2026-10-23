"""
Plain-language interpretations for every view in the app.

Each function takes the same tables the app shows and returns short sentences
(Markdown with **bold**) written from the live numbers, so the explanation always
matches the chart above it. No Streamlit here, so it can be tested on its own.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import planner


# ---- formatting --------------------------------------------------------------------

def n(x, digits: int = 0) -> str:
    """Thousands separators; never prints 'nan'."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x:,.{digits}f}"


def pct(x, digits: int = 0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x:.{digits}f}%"


def day(d) -> str:
    return f"{pd.Timestamp(d):%b %d, %Y}"


def short_day(d) -> str:
    return f"{pd.Timestamp(d):%b %d}"


def plural(k: int, word: str, many: str | None = None) -> str:
    return f"{n(k)} {word if k == 1 else (many or word + 's')}"


# ---- data trust ----------------------------------------------------------------------

def trust_counts(log: pd.DataFrame, recon: pd.DataFrame) -> dict:
    loaded = log[log["status"] == "loaded"] if len(log) else log
    quarantined = log[log["status"] == "quarantined"] if len(log) else log
    failed = int((~recon["match"].astype(bool)).sum()) if len(recon) else 0
    return dict(files=len(log), loaded=len(loaded), quarantined=len(quarantined),
                checks=len(recon), checks_failed=failed)


def trust_takeaway(c: dict) -> str:
    if c["files"] == 0:
        return "No files were read yet."
    s = (f"**{c['loaded']} of {c['files']} files** passed every check, and all "
         f"**{n(c['checks'])} Priva totals** they contain match the records underneath them exactly.")
    if c["quarantined"]:
        s += (f" **{plural(c['quarantined'], 'file')}** did not add up and {'was' if c['quarantined'] == 1 else 'were'} "
              "held back, so none of {0} numbers reached the planner or any chart.".format(
                  "its" if c["quarantined"] == 1 else "their"))
    else:
        s += " No file had to be held back."
    return s


def quarantine_headline(reason_text: str) -> str:
    """The one plain sentence under 'Why this file was not loaded:' in a quarantine note."""
    lines = [l.strip() for l in reason_text.splitlines()]
    for i, l in enumerate(lines):
        if l.lower().startswith("why this file was not loaded"):
            for nxt in lines[i + 1:]:
                if nxt:
                    return nxt
    return next((l for l in lines if l), "This file did not pass the checks.")


# ---- planner ---------------------------------------------------------------------------

def recent_pace(pace: pd.DataFrame, task: str, before_week, lookback: int) -> pd.DataFrame:
    """The weeks planner.pace_for() takes its median from."""
    p = pace[(pace["activity_name"] == task) & (pace["week_start"] < pd.Timestamp(before_week))]
    return p.dropna(subset=["min_per_row"]).tail(lookback)


def planner_takeaway(task: str, next_week, rows: float, mpr: float, hpp: float, plan: dict,
                     pf: dict, recent: pd.DataFrame) -> str:
    people = plan["people_rounded"]
    if not isinstance(people, (int, np.integer)) and (people is None or math.isnan(people)):
        return "Enter rows, minutes per row and hours per person above to get a plan."
    s = (f"Plan **{plural(int(people), 'person', 'people')} on {task}** for the week of {short_day(next_week)} "
         f"to cover {n(rows)} rows.")
    hist = pf["min_per_row"]
    if len(recent) >= 2:
        lo, hi = recent["min_per_row"].min(), recent["min_per_row"].max()
        p_lo = planner.plan(rows, lo, hpp)["people_rounded"]
        p_hi = planner.plan(rows, hi, hpp)["people_rounded"]
        if p_lo == p_hi:
            s += (f" Over the last {plural(len(recent), 'week')} the pace stayed between {n(lo, 1)} and "
                  f"{n(hi, 1)} min per row, which gives the same answer, so this plan is **robust**.")
        else:
            s += (f" Over the last {plural(len(recent), 'week')} the pace ranged from {n(lo, 1)} to {n(hi, 1)} min "
                  f"per row; that alone would move the plan between **{p_lo} and {p_hi} people**.")
    if hist and not math.isnan(hist) and abs(mpr - hist) / hist > 0.005:
        diff = 100 * (mpr - hist) / hist
        word = "faster" if diff < 0 else "slower"
        s += (f" You have set {n(mpr, 1)} min per row, **{pct(abs(diff))} {word}** than the recent pace "
              f"of {n(hist, 1)}; treat the result as a target, not a forecast.")
    return s


def backtest_takeaway(pva: pd.DataFrame) -> str:
    if pva.empty:
        return "Not enough past weeks to test the method on this task yet."
    miss = pva["variance_pct"].abs()
    worst = pva.loc[miss.idxmax()]
    over = int((pva["planned_hours"] > pva["actual_hours"]).sum())
    k = len(pva)
    s = (f"Tested on {plural(k, 'past week')}, the plan landed within **{pct(miss.median(), 1)}** of the hours "
         f"actually worked in a typical week (worst: {pct(abs(worst['variance_pct']), 1)}, week of "
         f"{short_day(worst['week_start'])}).")
    if over in (0, k):
        s += f" It {'over' if over else 'under'}-planned every week, so adjust the pace slightly when planning."
    else:
        s += f" It planned too many hours in {over} weeks and too few in {k - over}, so there is no built-in bias."
    return s


# ---- crew ------------------------------------------------------------------------------------

BAND_ORDER = ["Strong", "Typical", "Developing", "Ramping up", "Not enough data"]


def crew_takeaway(view: pd.DataFrame, task: str) -> str:
    counts = view["band"].value_counts()
    c = {b: int(counts.get(b, 0)) for b in BAND_ORDER}
    banded = c["Strong"] + c["Typical"] + c["Developing"]
    if banded == 0:
        return f"Nobody has enough weeks on {task} to be banded yet."
    s = (f"On **{task}**, {plural(c['Strong'], 'person', 'people')} {'is' if c['Strong'] == 1 else 'are'} "
         f"**Strong** (10%+ faster than that week's typical pace), {n(c['Typical'])} Typical and "
         f"{n(c['Developing'])} Developing.")
    if c["Strong"]:
        s += " Strong people are natural buddies for anyone learning this task."
    if c["Ramping up"]:
        s += (f" {plural(c['Ramping up'], 'person', 'people')} {'is' if c['Ramping up'] == 1 else 'are'} still "
              "**ramping up** (under 6 weeks in) and should not be judged on speed yet.")
    return s


def best_task_takeaway(best: pd.DataFrame) -> str:
    if best.empty:
        return "Not enough data yet to say where each person is strongest."
    top = best["best_task"].value_counts()
    t, k = top.index[0], int(top.iloc[0])
    return (f"For **{plural(len(best), 'person', 'people')}**, this is the task where they compare best with "
            f"their peers. The most common is **{t}** ({n(k)}). Use it when deciding who goes where, "
            "alongside what supervisors know about quality.")


# ---- review list ----------------------------------------------------------------------------

def review_takeaway(sel: pd.DataFrame, week_hours: float, wk) -> str:
    if sel.empty:
        return f"Nothing to check for the week of {short_day(wk)}. Every registration looks normal."
    share = 100 * sel["hours"].sum() / week_hours if week_hours else float("nan")
    by_task = sel["activity_name"].value_counts()
    s = (f"**{plural(len(sel), 'registration')}** in the week of {short_day(wk)} look wrong, covering "
         f"{n(sel['hours'].sum(), 1)} hours ({pct(share, 1)} of the week).")
    if len(by_task):
        s += f" The most are on **{by_task.index[0]}** ({n(int(by_task.iloc[0]))})."
    if sel["review_reason"].str.contains("tagged out", case=False).any():
        s += (" The usual cause is a worker not tagging out for a break or a task change, so the clock keeps "
              "running and the row looks far slower than it was.")
    return s


# ---- trends ---------------------------------------------------------------------------------------

def hours_takeaway(weekly: pd.DataFrame) -> str:
    """weekly: week_start, activity_name, hours."""
    if weekly.empty:
        return "No hours in the selected tasks."
    tot = weekly.groupby("week_start")["hours"].sum().sort_index()
    share = weekly.groupby("activity_name")["hours"].sum().sort_values(ascending=False)
    s = (f"The selected tasks took **{n(tot.mean())} hours a week** on average "
         f"({n(tot.min())} to {n(tot.max())}).")
    if len(tot) >= 2 and tot.iloc[0]:
        ch = 100 * (tot.iloc[-1] - tot.iloc[0]) / tot.iloc[0]
        if abs(ch) < 3:
            s += " Weekly hours have been **steady**."
        else:
            s += (f" The last week was **{pct(abs(ch))} {'higher' if ch > 0 else 'lower'}** than the first "
                  f"({short_day(tot.index[0])}).")
    if len(share) > 1:
        s += f" **{share.index[0]}** is the biggest, at {pct(100 * share.iloc[0] / share.sum())} of these hours."
    return s


def rows_takeaway(pace: pd.DataFrame) -> str:
    if pace.empty:
        return "No rows recorded for the selected tasks."
    avg = pace.groupby("activity_name")["rows_done"].mean().sort_values(ascending=False)
    passes = avg / planner.GREENHOUSE_ROWS
    full = [t for t, v in passes.items() if v >= 0.9]
    if len(full) == len(avg):
        return (f"{'The selected task goes' if len(avg) == 1 else 'Every selected task goes'} through roughly the "
                f"**whole greenhouse ({planner.GREENHOUSE_ROWS} rows) every week**"
                + (f" (about {n(avg.mean())} rows on average)" if n(avg.min()) == n(avg.max())
                   else f" ({n(avg.min())} to {n(avg.max())} rows on average)")
                + ". The row count is predictable, so the plan mainly depends on pace.")
    s = f"**{avg.index[0]}** covers the most ground, about {n(avg.iloc[0])} rows a week."
    if full:
        s += (f" {', '.join(full)} {'goes' if len(full) == 1 else 'go'} through roughly the **whole greenhouse "
              f"({planner.GREENHOUSE_ROWS} rows) every week**, so for "
              f"{'that task' if len(full) == 1 else 'those'} the plan mainly depends on pace.")
    rest = [t for t in avg.index if t not in full]
    if rest:
        s += f" {', '.join(rest)} {'covers' if len(rest) == 1 else 'cover'} less, so check the rows to do before planning."
    return s


def pace_takeaway(pace: pd.DataFrame) -> str:
    p = pace.dropna(subset=["min_per_row"])
    if p.empty:
        return "Not enough rows recorded to work out a pace."
    cv = (p.groupby("activity_name")["min_per_row"].agg(lambda s: 100 * s.std(ddof=0) / s.mean())
            .sort_values(ascending=False))
    s = (f"Minutes per row is the number the planner runs on. The most variable task is **{cv.index[0]}** "
         f"(it moves about ±{pct(cv.iloc[0], 1)} week to week)")
    if len(cv) > 1:
        s += f"; the steadiest is **{cv.index[-1]}** (±{pct(cv.iloc[-1], 1)})."
    else:
        s += "."
    s += " A steadier pace means a more reliable plan."
    return s


# ---- overview -------------------------------------------------------------------------------------

def overview_takeaways(res: dict, focus_task: str, lookback: int = 4) -> list[str]:
    rec, pace = res["records"], res["pace"]
    out = [trust_takeaway(trust_counts(res["log"], res["recon"]))]
    next_week = pace["week_start"].max() + pd.Timedelta(weeks=1)
    pf = planner.pace_for(pace, focus_task, next_week, lookback)
    if pf["weeks_used"]:
        p = planner.plan(planner.GREENHOUSE_ROWS, pf["min_per_row"], 40.0)
        pva = planner.plan_vs_actual(pace, focus_task, lookback)
        s = (f"**{focus_task}**, the biggest task, needs about **{n(p['hours_needed'])} hours, or "
             f"{p['people_rounded']} people at 40 h each**, to cover the greenhouse next week.")
        if len(pva):
            s += f" On past weeks this method was within {pct(pva['variance_pct'].abs().median(), 1)} of actual hours."
        out.append(s)
    s = res["strengths"]
    if len(s):
        c = s["band"].value_counts()
        out.append(f"Across all tasks, **{n(int(c.get('Strong', 0)))} person-task pairs are Strong** and "
                   f"{n(int(c.get('Ramping up', 0)))} are still ramping up. The crew view shows who is best "
                   "placed where, without ranking anyone.")
    rv = res["review"]
    if len(rv):
        share = 100 * rv["hours"].sum() / rec["hours"].sum()
        out.append(f"**{n(len(rv))} registrations** ({pct(share, 1)} of all hours) look like missed tag-outs and "
                   "should be corrected in Priva so they do not distort the pace the planner uses.")
    return out
