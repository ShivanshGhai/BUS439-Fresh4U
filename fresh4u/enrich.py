"""
Turns the stored Performance history into analysis-ready tables.

Every rule is visible here and nothing is deleted: suspicious records are FLAGGED
so totals always reconcile with Priva. Columns that a given export lacks
(e.g. Result before Feb 15, End time after May 9) simply stay empty.
"""
from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

ROW_M2 = 144.5            # area of one full row, as recorded by Priva
AREA_OUTLIER_M2 = 50_000  # larger than any single house: an entry error
SLOW_MULTIPLE = 3         # "review" when >= 3x the task's median minutes per row


def _loc_type(s: str) -> str:
    if s in ("", "nan", "None") or s == "Unknown":
        return "Unknown"
    if re.match(r"^Row \d+$", s):
        return "Row"
    if re.match(r"^House \d+$", s):
        return "House"
    return "Other"


def enrich_performance(h: pd.DataFrame) -> pd.DataFrame:
    df = h.copy()
    for c in ["hours", "result", "area_m2", "perf_per_hour_priva"]:
        if c not in df:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["location", "employee_group", "end_time", "start_time"]:
        if c not in df:
            df[c] = pd.NA
    df["date"] = pd.to_datetime(df["date"].astype(str).str.slice(0, 10), format="%Y-%m-%d")
    df["employee_id"] = df["employee_id"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    for c in ["activity", "location", "employee_group"]:
        df[c] = df[c].astype("string").str.strip()

    am = df["activity"].str.extract(r"^(.*?)\s*\(([^)]*)\)\s*$")
    df["activity_name"] = am[0].fillna(df["activity"]).str.strip()
    df["activity_code"] = am[1]

    df["location_type"] = df["location"].fillna("Unknown").astype(str).map(_loc_type)
    df["row_number"] = pd.to_numeric(df["location"].str.extract(r"^Row (\d+)$")[0], errors="coerce").astype("Int64")
    rn = df["row_number"].astype("float")
    # ASSUMPTION (confirm with Fresh4U): 1xxx rows are House 1, 2xxx rows are House 2
    df["house_inferred"] = np.select([rn.between(1001, 1999).to_numpy(bool), rn.between(2001, 2999).to_numpy(bool)],
                                     ["House 1", "House 2"], default="")
    df.loc[df["location_type"] == "House", "house_inferred"] = df["location"]
    df["house_inferred"] = df["house_inferred"].replace("", np.nan)

    def clock(col):
        t = pd.to_datetime(df[col].astype("string"), format="%H:%M:%S", errors="coerce")
        return t.dt.strftime("%H:%M:%S")
    df["end_time"] = clock("end_time")
    df["start_time"] = clock("start_time")
    day = df["date"].dt.strftime("%Y-%m-%d")
    df["end_datetime"] = pd.to_datetime(day + " " + df["end_time"], errors="coerce")
    start_actual = pd.to_datetime(day + " " + df["start_time"], errors="coerce")
    df["start_datetime"] = start_actual.fillna(df["end_datetime"] - pd.to_timedelta(df["hours"], unit="h"))
    df["start_is_estimated"] = start_actual.isna() & df["start_datetime"].notna()

    df["area_m2_clean"] = df["area_m2"].where(~(df["area_m2"] > AREA_OUTLIER_M2))
    df.loc[df["area_m2_clean"].abs() < 1e-9, "area_m2_clean"] = 0.0
    df["implied_density"] = np.where(df["area_m2_clean"] > 0, (df["result"] / df["area_m2_clean"]).round(2), np.nan)
    df["perf_per_hour"] = np.where((df["hours"] > 0) & df["result"].notna(), df["result"] / df["hours"], np.nan)
    df["area_per_hour"] = np.where(df["hours"] > 0, df["area_m2_clean"] / df["hours"], np.nan)
    df["min_per_row"] = np.where(df["area_m2_clean"] > 0, 60 * df["hours"] / (df["area_m2_clean"] / ROW_M2), np.nan)
    df["week_start"] = df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")
    df["weekday"] = df["date"].dt.day_name()
    df["productivity_eligible"] = ((df["location_type"] == "Row") & (df["hours"] >= 1 / 60) &
                                   (df["area_m2_clean"] > 0) & (df["activity_name"] != "Sweeping"))

    f = pd.DataFrame(index=df.index)
    f["hours_missing"] = df["hours"].isna()
    f["hours_nonpositive"] = df["hours"] <= 0
    f["hours_gt_12_single_record"] = df["hours"] > 12
    f["location_unknown"] = df["location_type"] == "Unknown"
    f["location_house_level"] = df["location_type"] == "House"
    f["area_missing"] = df["area_m2"].isna()
    f["area_outlier"] = df["area_m2"] > AREA_OUTLIER_M2
    f["hours_but_zero_area"] = (df["hours"] > 0) & (df["area_m2_clean"] == 0)
    f["density_not_3_3"] = df["implied_density"].notna() & (df["implied_density"] != 3.3)
    f["very_short_record_lt_1min"] = df["hours"] < (1 / 60)
    f["perf_mismatch_vs_priva"] = (df["perf_per_hour_priva"].notna() & df["perf_per_hour"].notna() &
                                   ((df["perf_per_hour_priva"] - df["perf_per_hour"]).abs() > 0.01 * df["perf_per_hour"].abs() + 0.01))
    med = df.loc[df["productivity_eligible"]].groupby("activity_name")["min_per_row"].median()
    f["review_slow_vs_task"] = df["productivity_eligible"] & (df["min_per_row"] >= SLOW_MULTIPLE * df["activity_name"].map(med))
    eg = df.groupby(["date", "employee_id"])["employee_group"].transform("nunique")
    f["employee_multi_group_same_day"] = eg > 1
    key = ["date", "activity", "location", "employee_group", "employee_id", "end_time", "hours", "result", "area_m2"]
    f["exact_duplicate"] = df.duplicated(subset=key, keep=False)
    df = df.join(f.add_prefix("flag_"))
    df["flag_any"] = f.drop(columns=["location_house_level", "density_not_3_3"]).any(axis=1)

    # a reason a supervisor can read, for the review list
    reasons = {
        "review_slow_vs_task": "Took 3x+ the usual time per row - possibly not tagged out (break, task change)",
        "hours_but_zero_area": "Hours registered but no area credited",
        "location_unknown": "Hours with no location",
        "area_outlier": "Area larger than a whole house - entry error",
        "hours_gt_12_single_record": "More than 12 hours in one registration",
        "employee_multi_group_same_day": "Employee appears in two groups on the same day",
        "exact_duplicate": "Identical registration appears twice",
    }
    def why(row):
        return "; ".join(t for k, t in reasons.items() if row[f"flag_{k}"])
    rv = df[[f"flag_{k}" for k in reasons]].any(axis=1)
    df["review_reason"] = ""
    df.loc[rv, "review_reason"] = df.loc[rv].apply(why, axis=1)
    return df


def write_outputs(df: pd.DataFrame, out: str) -> dict:
    os.makedirs(out, exist_ok=True)
    first = ["date", "week_start", "weekday", "activity_name", "activity_code", "location", "location_type",
             "house_inferred", "row_number", "employee_group", "employee_id", "start_time", "end_time",
             "start_datetime", "start_is_estimated", "end_datetime", "hours", "result", "area_m2", "area_m2_clean",
             "implied_density", "min_per_row", "area_per_hour", "perf_per_hour", "perf_per_hour_priva",
             "productivity_eligible", "review_reason", "source_file", "period_start", "period_end", "excel_row"]
    cols = [c for c in first if c in df] + [c for c in df if c.startswith("flag_")] + \
           [c for c in df if c not in first and not c.startswith("flag_") and c != "activity"]
    df = df.sort_values(["date", "activity_name", "location", "employee_id", "end_time"], na_position="first")
    df[cols].to_csv(os.path.join(out, "labour_records_clean.csv"), index=False)

    ssum = lambda s: s.sum(min_count=1)
    grain = ["date", "week_start", "activity_name", "location", "location_type", "house_inferred", "row_number",
             "employee_group", "employee_id"]
    daily = (df.groupby(grain, dropna=False)
               .agg(hours=("hours", "sum"), result=("result", ssum), area_m2=("area_m2_clean", ssum),
                    registrations=("hours", "size")).reset_index())
    daily["min_per_row"] = np.where(daily["area_m2"] > 0, 60 * daily["hours"] / (daily["area_m2"] / ROW_M2), np.nan)
    daily.to_csv(os.path.join(out, "labour_daily_employee_location.csv"), index=False)

    e = df[df["productivity_eligible"]]
    wk = (df.groupby(["week_start", "activity_name"]).agg(hours=("hours", "sum"), workers=("employee_id", "nunique")).reset_index()
            .merge(e.groupby(["week_start", "activity_name"]).agg(eligible_hours=("hours", "sum"),
                                                                    rows_done=("area_m2_clean", lambda s: s.sum() / ROW_M2)).reset_index(),
                   how="left"))
    wk["min_per_row"] = np.where(wk["rows_done"] >= 50, 60 * wk["eligible_hours"] / wk["rows_done"], np.nan)
    wk.to_csv(os.path.join(out, "weekly_by_task.csv"), index=False)

    review = df[df["review_reason"] != ""]
    rcols = ["date", "activity_name", "location", "employee_group", "employee_id", "start_time", "end_time",
             "hours", "min_per_row", "review_reason", "source_file", "excel_row"]
    review[[c for c in rcols if c in review]].sort_values(["date", "employee_id"]).to_csv(
        os.path.join(out, "review_list.csv"), index=False)

    issues = []
    tot = df["hours"].sum()
    for c in [c for c in df if c.startswith("flag_") and c != "flag_any"]:
        n = int(df[c].sum())
        if n:
            hrs = df.loc[df[c], "hours"].sum()
            issues.append(dict(flag=c, records=n, hours=round(hrs, 1), pct_of_hours=round(100 * hrs / tot, 2)))
    pd.DataFrame(issues).to_csv(os.path.join(out, "data_quality_summary.csv"), index=False)
    return dict(records=len(df), hours=round(float(tot), 3), review_records=len(review),
                first_date=str(df["date"].min().date()), last_date=str(df["date"].max().date()))
