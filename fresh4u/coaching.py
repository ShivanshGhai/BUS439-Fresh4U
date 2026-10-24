"""
Crew strengths and coaching view.

Designed to be safe to show supervisors:
  * no league table: each person gets a band per task, not a rank;
  * speed is compared with the same task in the same week (so a slow week for everyone
    does not count against anyone);
  * nobody is banded on too little data (default: at least 4 weeks and 8 hours on the task);
  * people in their first weeks are marked "Ramping up" instead of "Developing";
  * it measures speed only. It says nothing about quality.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _mask(cond) -> "np.ndarray":
    """A plain True/False array for np.select (newer numpy refuses pandas' nullable booleans); missing = False."""
    return pd.array(cond, dtype="boolean").fillna(False).to_numpy(dtype=bool)


ROW_M2 = 144.5
BANDS = ["Strong", "Typical", "Developing"]


def worker_week_speed(records: pd.DataFrame, min_hours: float = 2.0) -> pd.DataFrame:
    e = records[records["productivity_eligible"]]
    ww = (e.groupby(["activity_name", "employee_id", "employee_group", "week_start"])
            .agg(hours=("hours", "sum"), area=("area_m2_clean", "sum")).reset_index())
    ww = ww[ww["hours"] >= min_hours].copy()
    ww["min_per_row"] = 60 * ww["hours"] / (ww["area"] / ROW_M2)
    med = ww.groupby(["activity_name", "week_start"])["min_per_row"].transform("median")
    ww["speed_index"] = 100 * med / ww["min_per_row"]      # 100 = that week's typical; 120 = 20% faster
    return ww


def strengths(records: pd.DataFrame, min_weeks: int = 4, min_hours: float = 8.0,
              band_pct: float = 10.0, ramp_weeks: int = 6) -> pd.DataFrame:
    ww = worker_week_speed(records)
    first_seen = records.groupby("employee_id")["date"].min()
    last_day = records["date"].max()
    g = (ww.groupby(["employee_id", "employee_group", "activity_name"])
           .agg(weeks=("week_start", "nunique"), hours=("hours", "sum"),
                speed_index=("speed_index", lambda s: float(100 * np.exp(np.log(s / 100).mean()))),
                last_week=("week_start", "max"))
           .reset_index())
    g["first_seen"] = g["employee_id"].map(first_seen)
    g["weeks_since_start"] = ((last_day - g["first_seen"]).dt.days // 7).astype(int)
    enough = (g["weeks"] >= min_weeks) & (g["hours"] >= min_hours)
    lo, hi = 100 - band_pct, 100 + band_pct
    band = np.select([_mask(~enough), _mask(g["speed_index"] >= hi), _mask(g["speed_index"] <= lo)], ["Not enough data", "Strong", "Developing"],
                     default="Typical")
    ramping = (band == "Developing") & (g["weeks_since_start"] < ramp_weeks)
    g["band"] = np.where(ramping, "Ramping up", band)
    g["speed_index"] = g["speed_index"].round(0)
    return g.sort_values(["activity_name", "employee_id"]).reset_index(drop=True)


def best_task(strength_table: pd.DataFrame) -> pd.DataFrame:
    """Each person's relatively strongest task (only among tasks with enough data)."""
    s = strength_table[strength_table["band"] != "Not enough data"]
    if s.empty:
        return pd.DataFrame(columns=["employee_id", "best_task", "speed_index"])
    idx = s.groupby("employee_id")["speed_index"].idxmax()
    out = s.loc[idx, ["employee_id", "activity_name", "speed_index", "band"]].rename(columns={"activity_name": "best_task"})
    return out.reset_index(drop=True)
