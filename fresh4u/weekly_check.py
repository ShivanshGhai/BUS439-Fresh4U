"""
Weekly check before payroll: can this period's numbers be trusted?

Joins what Priva knows about presence (Hours report) with what was registered (Production and the
per-registration exports), and lists what a supervisor should fix in Priva's Validation & Correction
before pay is run. No names: people are shown by employee number, which Priva searches by.

Checks
  1. Present but untagged: present hours minus registered hours, per person.
  2. Registrations that took 3x+ the usual time per row (likely not tagged out at a break or task change).
  3. Locations that cannot be right: a strawberry task in a tomato house (or the reverse),
     or hours with no location for a task that is always done in a row.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd


def _mask(cond) -> "np.ndarray":
    """A plain True/False array for np.select (newer numpy refuses pandas' nullable booleans); missing = False."""
    return pd.array(cond, dtype="boolean").fillna(False).to_numpy(dtype=bool)


UNTAGGED_MIN_HOURS = 2.0       # flag someone when untagged time over the period is at least this...
UNTAGGED_MIN_SHARE = 0.05      # ...and at least this share of their present hours
ALWAYS_UNLOCATED = re.compile(r"^(Break|Packing|Scales|Forklift|Bug breeding|Mixing fertilizer|Transport|Unknown|Hand Watering|Misc planting|Filling pots)", re.I)


def periods(hours: pd.DataFrame) -> list[tuple[str, str]]:
    if hours is None or hours.empty:
        return []
    return sorted({(a, b) for a, b in zip(hours["period_start"], hours["period_end"])}, reverse=True)


def untagged(hours: pd.DataFrame, period: tuple[str, str]) -> pd.DataFrame:
    h = hours[(hours["period_start"] == period[0]) & (hours["period_end"] == period[1])]
    e = h.groupby(["employee_id", "employee_group"]).agg(
        present=("present_hours", "sum"), registered=("registered_hours", "sum"), paid=("paid_hours", "sum"),
        days_present=("days_present", "sum")).reset_index()
    e = e[e["present"] > 0].copy()
    e["untagged"] = (e["present"] - e["registered"]).clip(lower=0)
    e["untagged_min_per_day"] = np.where(e["days_present"] > 0, 60 * e["untagged"] / e["days_present"], np.nan)
    e["flag"] = (e["untagged"] >= UNTAGGED_MIN_HOURS) & (e["untagged"] >= UNTAGGED_MIN_SHARE * e["present"])
    return e.sort_values("untagged", ascending=False).reset_index(drop=True)


def slow_registrations(review: pd.DataFrame, period: tuple[str, str]) -> pd.DataFrame:
    if review is None or review.empty:
        return pd.DataFrame()
    d = pd.to_datetime(review["date"])
    return review[(d >= period[0]) & (d <= period[1])].reset_index(drop=True)


def location_problems(prod: pd.DataFrame, period: tuple[str, str]) -> pd.DataFrame:
    if prod is None or prod.empty:
        return pd.DataFrame(columns=["activity", "location", "hours", "problem"])
    p = prod[(prod["period_start"] == period[0]) & (prod["period_end"] == period[1])].copy()
    if p.empty:
        return pd.DataFrame(columns=["activity", "location", "hours", "problem"])
    loc = p["location"].astype("string").fillna("Unknown")
    row = loc.str.extract(r"^Row (\d)\d{3}$")[0]
    house = row.map(lambda r: f"House {r}" if isinstance(r, str) else None)
    house = house.where(house.notna(), loc.str.extract(r"^(House \d)")[0])
    crop_act = np.where(p["activity"].str.contains(r"\(S\)|Strawberr", regex=True), "Strawberry",
                        np.where(p["activity"].str.contains(r"\(T\)|Tomato", regex=True), "Tomato", ""))
    crop_house = house.map({"House 1": "Tomato", "House 2": "Tomato", "House 3": "Strawberry", "House 4": "Strawberry"})
    wrong = (crop_act != "") & crop_house.notna() & (crop_house.to_numpy(dtype=object) != crop_act)
    nowhere = (loc == "Unknown") & ~p["activity"].str.match(ALWAYS_UNLOCATED) & (p["hours"] > 0.5)
    p["problem"] = np.select([_mask(wrong), _mask(nowhere)], ["Task for the other crop's house", "Hours with no row for a row task"], "")
    p["house"] = house
    out = (p[p["problem"] != ""].groupby(["activity", "house", "problem"], dropna=False)
           .agg(hours=("hours", "sum"), locations=("location", "nunique")).reset_index()
           .sort_values("hours", ascending=False).reset_index(drop=True))
    return out


def summary(unt: pd.DataFrame, slow: pd.DataFrame, locs: pd.DataFrame) -> dict:
    f = unt[unt["flag"]] if len(unt) else unt
    return dict(people=int(len(unt)), present=float(unt["present"].sum()) if len(unt) else 0.0,
                registered=float(unt["registered"].sum()) if len(unt) else 0.0,
                untagged=float(unt["untagged"].sum()) if len(unt) else 0.0,
                people_flagged=int(len(f)), untagged_flagged=float(f["untagged"].sum()) if len(f) else 0.0,
                slow=int(len(slow)), slow_hours=float(slow["hours"].sum()) if len(slow) else 0.0,
                loc_items=int(len(locs)), loc_hours=float(locs["hours"].sum()) if len(locs) else 0.0)


def supervisor_list(unt: pd.DataFrame, slow: pd.DataFrame, locs: pd.DataFrame) -> pd.DataFrame:
    """One list to work through in Validation & Correction, most hours first."""
    rows = []
    for r in unt[unt["flag"]].itertuples():
        rows.append(dict(check="Present but untagged", employee=r.employee_id, group=r.employee_group, where="",
                         task="", hours=r.untagged,
                         what_to_do=f"{r.untagged:.1f} h present with no task ({r.untagged_min_per_day:.0f} min a day). "
                                    "Add the missing registration or confirm it was a break."))
    for r in slow.itertuples():
        rows.append(dict(check="Took 3x+ the usual time", employee=r.employee_id, group=getattr(r, "employee_group", ""),
                         where=str(r.location), task=r.activity_name, hours=r.hours,
                         what_to_do=f"{pd.Timestamp(r.date):%b %d}, ended {r.end_time}: {r.review_reason}. "
                                    "Check the end time or split the registration."))
    for r in locs.itertuples():
        rows.append(dict(check="Location can't be right", employee="", group="",
                         where="no row" if pd.isna(r.house) else str(r.house),
                         task=r.activity, hours=r.hours,
                         what_to_do=f"{r.problem}. Correct the location or the task."))
    return pd.DataFrame(rows, columns=["check", "employee", "group", "where", "task", "hours", "what_to_do"]
                        ).sort_values("hours", ascending=False).reset_index(drop=True)
