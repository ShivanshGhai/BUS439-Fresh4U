"""
Per-task, per-season targets built from Fresh4U's own history, and "is this week on track?".

A target is the median weekly pace (minutes per row) for that task in that season, from the
weeks Priva recorded. The fastest quarter of weeks ("good week") and slowest quarter give a range.
Tasks only seen in one Production export get that period's pace, marked as thin evidence.

Priva's own "% performance" divides by ONE norm for every activity (e.g. 643.77 m2/h in October,
which is 13.5 min/row for every task), so it says nothing per task today. Targets agreed with the
grower can be entered into Priva as a norm per activity: norm (m2/h) = 60 x 144.5 / minutes per row.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _mask(cond) -> "np.ndarray":
    """A plain True/False array for np.select (newer numpy refuses pandas' nullable booleans); missing = False."""
    return pd.array(cond, dtype="boolean").fillna(False).to_numpy(dtype=bool)

ROW_M2 = 144.5
SEASONS = {1: "Winter (Jan–Mar)", 2: "Winter (Jan–Mar)", 3: "Winter (Jan–Mar)",
           4: "Spring (Apr–Jun)", 5: "Spring (Apr–Jun)", 6: "Spring (Apr–Jun)",
           7: "Summer (Jul–Sep)", 8: "Summer (Jul–Sep)", 9: "Summer (Jul–Sep)",
           10: "Autumn (Oct–Dec)", 11: "Autumn (Oct–Dec)", 12: "Autumn (Oct–Dec)"}
SEASON_ORDER = ["Winter (Jan–Mar)", "Spring (Apr–Jun)", "Summer (Jul–Sep)", "Autumn (Oct–Dec)"]
ON_TRACK_BAND = 0.10     # within 10% of target counts as on track


def season_of(d) -> str:
    return SEASONS[pd.Timestamp(d).month]


def norm_m2_per_hour(min_per_row: float) -> float:
    return 60 * ROW_M2 / min_per_row if min_per_row and min_per_row > 0 else np.nan


def _crop(activity: str) -> str:
    a = str(activity)
    if "(S)" in a or "Strawberr" in a:
        return "Strawberry"
    if "(T)" in a or "Tomato" in a:
        return "Tomato"
    return "General"


def priva_norm_today(records: pd.DataFrame) -> pd.DataFrame:
    """The norm Priva's '% performance' currently divides by, per export (implied: value / %)."""
    if records is None or records.empty or "pct_of_norm_priva" not in records:
        return pd.DataFrame(columns=["source_file", "norm_m2_per_hour", "as_min_per_row", "activities"])
    r = records.dropna(subset=["pct_of_norm_priva", "area_per_hour_priva"])
    r = r[r["pct_of_norm_priva"] > 0]
    if r.empty:
        return pd.DataFrame(columns=["source_file", "norm_m2_per_hour", "as_min_per_row", "activities"])
    r = r.assign(norm=(r["area_per_hour_priva"] / (r["pct_of_norm_priva"] / 100)).round(2))
    out = r.groupby("source_file").agg(norm_m2_per_hour=("norm", "median"), distinct=("norm", "nunique"),
                                       activities=("activity_name", "nunique")).reset_index()
    out["as_min_per_row"] = 60 * ROW_M2 / out["norm_m2_per_hour"]
    return out


def history_targets(pace: pd.DataFrame) -> pd.DataFrame:
    """From weekly pace (planner.weekly_pace): one row per task x season."""
    p = pace.dropna(subset=["min_per_row"]).copy()
    if p.empty:
        return pd.DataFrame()
    p["season"] = p["week_start"].map(season_of)
    g = p.groupby(["activity_name", "season"])
    t = g.agg(target_min_per_row=("min_per_row", "median"),
              good_week=("min_per_row", lambda s: s.quantile(0.25)),
              slow_week=("min_per_row", lambda s: s.quantile(0.75)),
              weeks=("min_per_row", "size"), rows_per_week=("rows_done", "median"),
              first_week=("week_start", "min"), last_week=("week_start", "max")).reset_index()
    t["evidence"] = np.where(t["weeks"] >= 6, "Measured", np.where(t["weeks"] >= 2, "Measured, thin", "One week"))
    t["source"] = "R&D Analytics registrations"
    t["crop"] = "Tomato"
    return t


def production_targets(prod: pd.DataFrame, min_rows: float = 20) -> pd.DataFrame:
    """Every activity in the Production export(s), with Priva's own row count. One row per task x season."""
    if prod is None or prod.empty or "rows_done_priva" not in prod:
        return pd.DataFrame()
    d = prod.copy()
    d["season"] = d["period_start"].map(season_of)
    d["activity_name"] = d["activity"].str.replace(r"\s*\([^)]*\)\s*$", "", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    d["crop"] = d["activity"].map(_crop)
    g = d.groupby(["activity", "activity_name", "crop", "season"]).agg(
        hours=("hours", "sum"), rows=("rows_done_priva", "sum"), result=("result", "sum"),
        periods=("period_start", "nunique")).reset_index()
    g = g[(g["rows"] >= min_rows) & (g["hours"] >= 1)].copy()
    g["target_min_per_row"] = 60 * g["hours"] / g["rows"]
    g["kg_per_hour"] = np.where(g["activity_name"].str.startswith("Picking"), g["result"] / g["hours"], np.nan)
    g["weeks"] = 2 * g["periods"]
    g["evidence"] = "One fortnight"
    g["source"] = "Production export"
    return g


def build_targets(pace: pd.DataFrame, prod: pd.DataFrame) -> pd.DataFrame:
    """History where it exists (tomato crop work), the Production export for every other task."""
    h = history_targets(pace)
    p = production_targets(prod)
    cols = ["task", "crop", "season", "target_min_per_row", "good_week", "slow_week", "weeks", "kg_per_hour",
            "evidence", "source"]
    out = []
    if not h.empty:
        h = h.rename(columns={"activity_name": "task"})
        h["kg_per_hour"] = np.nan
        out.append(h)
    if not p.empty:
        have = set(zip(h["task"], h["season"])) if not h.empty else set()
        p = p.rename(columns={"activity_name": "task"})
        p = p[[(t, s) not in have for t, s in zip(p["task"], p["season"])]]
        p["good_week"] = np.nan
        p["slow_week"] = np.nan
        out.append(p)
    if not out:
        return pd.DataFrame(columns=cols + ["priva_norm_m2_per_hour"])
    t = pd.concat(out, ignore_index=True)[cols]
    t["priva_norm_m2_per_hour"] = t["target_min_per_row"].map(norm_m2_per_hour)
    t["season"] = pd.Categorical(t["season"], SEASON_ORDER, ordered=True)
    return t.sort_values(["crop", "task", "season"]).reset_index(drop=True)


def week_on_track(pace: pd.DataFrame, targets: pd.DataFrame, week_start) -> pd.DataFrame:
    """Each task's pace in one week against its target for that season (lower minutes per row = faster).
    The target leaves the week itself out, so a week is never graded against its own pace. A task
    whose only data for the season is this week gets no target ("No target yet")."""
    wk = pd.Timestamp(week_start)
    p = pace[(pace["week_start"] == wk)].dropna(subset=["min_per_row"])
    cols = ["task", "actual_min_per_row", "target_min_per_row", "vs_target_pct", "status", "rows_done", "hours",
            "hours_at_target", "hours_over", "target_weeks"]
    if p.empty:
        return pd.DataFrame(columns=cols)
    s = season_of(wk)
    others = pace[(pace["week_start"] != wk)].dropna(subset=["min_per_row"])
    others = others[others["week_start"].map(season_of) == s]
    t = others.groupby("activity_name")["min_per_row"].median()
    n = others.groupby("activity_name")["min_per_row"].size()
    p = p.copy()
    p["target_min_per_row"] = p["activity_name"].map(t)
    p["target_weeks"] = p["activity_name"].map(n).fillna(0).astype(int)
    p["vs_target_pct"] = 100 * (p["min_per_row"] / p["target_min_per_row"] - 1)
    p["status"] = np.select([_mask(p["target_min_per_row"].isna()), _mask(p["vs_target_pct"] > 100 * ON_TRACK_BAND),
                             _mask(p["vs_target_pct"] < -100 * ON_TRACK_BAND)],
                            ["No target yet", "Slower than target", "Faster than target"], default="On track")
    p["hours_at_target"] = p["rows_done"] * p["target_min_per_row"] / 60
    p["hours_over"] = p["hours"] - p["hours_at_target"]
    return (p.rename(columns={"activity_name": "task", "min_per_row": "actual_min_per_row"})
             [["task", "actual_min_per_row", "target_min_per_row", "vs_target_pct", "status", "rows_done", "hours",
               "hours_at_target", "hours_over", "target_weeks"]]
             .sort_values("vs_target_pct", ascending=False, na_position="last").reset_index(drop=True))


def for_priva(targets: pd.DataFrame, agreed: pd.Series | None = None) -> pd.DataFrame:
    """What to type into Priva's activity norms: agreed minutes per row (grower's where given) as m2/h."""
    t = targets.copy()
    t["agreed_min_per_row"] = t["target_min_per_row"] if agreed is None else agreed.fillna(t["target_min_per_row"])
    t["norm_for_priva_m2_per_hour"] = t["agreed_min_per_row"].map(norm_m2_per_hour)
    return t[["task", "crop", "season", "agreed_min_per_row", "norm_for_priva_m2_per_hour", "evidence"]]
