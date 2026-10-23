"""
Weekly labour planner.

The method, in the grower's terms:
    hours needed = rows to do x minutes per row / 60
    people needed = hours needed / hours one person works on that task per week
where "minutes per row" is the median of the last few weeks for that task
(so one unusual week does not swing the plan).

Every number the planner shows can be traced back to weekly_by_task.csv.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

ROW_M2 = 144.5
GREENHOUSE_ROWS = 560


def weekly_pace(records: pd.DataFrame) -> pd.DataFrame:
    """Hours, rows done and minutes per row per task per week, from enriched records."""
    e = records[records["productivity_eligible"]]
    w = (e.groupby(["week_start", "activity_name"])
           .agg(hours=("hours", "sum"), rows_done=("area_m2_clean", lambda s: s.sum() / ROW_M2),
                workers=("employee_id", "nunique"))
           .reset_index())
    w["min_per_row"] = np.where(w["rows_done"] >= 50, 60 * w["hours"] / w["rows_done"], np.nan)
    w["hours_per_worker"] = w["hours"] / w["workers"]
    return w.sort_values(["activity_name", "week_start"]).reset_index(drop=True)


def pace_for(pace: pd.DataFrame, task: str, week_start, lookback: int = 4) -> dict:
    """Median minutes per row over the `lookback` weeks before `week_start`."""
    week_start = pd.Timestamp(week_start)
    p = pace[(pace["activity_name"] == task) & (pace["week_start"] < week_start)].dropna(subset=["min_per_row"])
    p = p.tail(lookback)
    if p.empty:
        return dict(min_per_row=np.nan, weeks_used=0, from_week=None, to_week=None, hours_per_worker=np.nan)
    return dict(min_per_row=float(p["min_per_row"].median()), weeks_used=len(p),
                from_week=p["week_start"].min(), to_week=p["week_start"].max(),
                hours_per_worker=float(p["hours_per_worker"].median()))


def plan(rows_to_do: float, min_per_row: float, hours_per_person: float) -> dict:
    """The core arithmetic. Guards against missing or zero inputs."""
    if not (rows_to_do > 0 and min_per_row > 0 and hours_per_person > 0):
        return dict(hours_needed=np.nan, people_exact=np.nan, people_rounded=np.nan)
    hours = rows_to_do * min_per_row / 60
    people = hours / hours_per_person
    return dict(hours_needed=hours, people_exact=people, people_rounded=math.ceil(people - 1e-9))


def plan_vs_actual(pace: pd.DataFrame, task: str, lookback: int = 4) -> pd.DataFrame:
    """For each past week: what the planner would have said (knowing the rows done) vs what happened."""
    rows = []
    p = pace[pace["activity_name"] == task].dropna(subset=["min_per_row"])
    for _, r in p.iterrows():
        pf = pace_for(pace, task, r["week_start"], lookback)
        if pf["weeks_used"] < 2:
            continue
        planned = r["rows_done"] * pf["min_per_row"] / 60
        rows.append(dict(week_start=r["week_start"], actual_hours=r["hours"], planned_hours=planned,
                         rows_done=r["rows_done"], variance_hours=r["hours"] - planned,
                         variance_pct=100 * (r["hours"] - planned) / planned if planned else np.nan))
    return pd.DataFrame(rows)
