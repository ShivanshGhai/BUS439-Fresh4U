"""
Readers for the two Priva exports that are not pivot tables of the usual shape:

  * Production (tactical): weekly yield per crop label, one row per week under a year heading.
  * Management Report: labour hours per crop block x activity x weekday for one week.

Each returns the same Report object as priva_reader.read_report, with its own checks against
the totals printed in the file. Anything unexpected raises ReportError (the file is quarantined).
"""
from __future__ import annotations

import datetime as dt
import os
import re

import pandas as pd

from .priva_reader import Report, ReportError, _load_rows, file_sha256

YIELD_TITLE = "Production (tactical)"
MGMT_TITLE = "Management Report"
HOUSE_OF = {"H1": ("House 1", "Tomato"), "H2": ("House 2", "Tomato"),
            "H3": ("House 3", "Strawberry"), "H4": ("House 4", "Strawberry")}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def _checks(rows: list[dict]) -> pd.DataFrame:
    rc = pd.DataFrame(rows, columns=["level", "key", "measure", "priva_total", "sum_of_records"])
    rc["diff"] = rc["sum_of_records"] - rc["priva_total"]
    rc["match"] = rc["diff"].abs() <= (1e-6 * rc["priva_total"].abs()).clip(lower=1e-6)
    return rc


def special_kind(path: str) -> str | None:
    rows, _ = _load_rows(path)
    first = " ".join(_norm(c) for c in rows[0] if c is not None) if rows else ""
    if first.startswith(YIELD_TITLE):
        return "yield"
    if MGMT_TITLE in first:
        return "mgmt_report"
    return None


# ---- yield ------------------------------------------------------------------------------------
def read_yield(path: str) -> Report:
    rows, _ = _load_rows(path)
    if len(rows) < 8:
        raise ReportError("The yield report has fewer than 8 rows.")
    crop_row, meas_row = rows[2], rows[3]
    if _norm(meas_row[0]) != "Year":
        raise ReportError("Row 4 of the yield report should start with 'Year'; the layout has changed.")
    crop_of, cur = {}, None
    for j, c in enumerate(crop_row):
        if c not in (None, ""):
            cur = _norm(c)
        crop_of[j] = cur
    meas_of = {j: _norm(c) for j, c in enumerate(meas_row) if c not in (None, "") and j >= 4}
    kg_cols = {j: crop_of[j] for j, m in meas_of.items() if m == "Crop production" and crop_of.get(j)}
    m2_cols = {crop_of[j]: j for j, m in meas_of.items() if m == "Production / m²" and crop_of.get(j)}
    if not kg_cols:
        raise ReportError("No 'Crop production' columns found in the yield report.")

    recs, year_totals, year_only, year, grand = [], {}, {}, None, None
    for i, r in enumerate(rows[4:], start=4):
        lab0 = _norm(r[0]) if r[0] not in (None, "") else ""
        m = re.match(r"^(\d{4})( Total)?$", lab0)
        if m:
            year = int(m.group(1))
            vals = {kg_cols[j]: float(r[j]) for j in kg_cols if r[j] not in (None, "")}
            if m.group(2):
                year_totals[year] = vals
            elif vals:
                year_only[year] = vals      # a year shown only as one line, without weeks (e.g. 2024)
            continue
        if lab0 == "Grand Total":
            grand = {kg_cols[j]: float(r[j]) for j in kg_cols if r[j] not in (None, "")}
            break
        wk = re.match(r"^Week (\d+)$", _norm(r[2])) if r[2] not in (None, "") else None
        if not wk:
            continue
        if year is None:
            raise ReportError(f"Row {i + 1} has a week but no year above it.")
        for j, crop in kg_cols.items():
            if crop == "Grand Total" or r[j] in (None, ""):
                continue
            h = HOUSE_OF.get(crop[:2])
            k2 = m2_cols.get(crop)
            recs.append(dict(year=year, iso_week=int(wk.group(1)), crop_label=crop,
                             house=h[0] if h else None, crop=h[1] if h else "Unknown",
                             kg=float(r[j]), kg_per_m2=(float(r[k2]) if k2 is not None and r[k2] not in (None, "") else None),
                             excel_row=i + 1))
    df = pd.DataFrame(recs)
    if df.empty:
        raise ReportError("No weekly yield rows found.")
    checks = []
    for y, tot in year_totals.items():
        for crop, v in tot.items():
            if crop == "Grand Total":
                got = float(df.loc[df.year == y, "kg"].sum())
            else:
                got = float(df.loc[(df.year == y) & (df.crop_label == crop), "kg"].sum())
            checks.append(dict(level="year", key=f"{y} {crop}", measure="kg", priva_total=v, sum_of_records=got))
    if grand:
        for crop, v in grand.items():
            got = float(df["kg"].sum() if crop == "Grand Total" else df.loc[df.crop_label == crop, "kg"].sum())
            got += sum(vals.get(crop, 0.0) for vals in year_only.values())
            checks.append(dict(level="file", key=f"Grand Total {crop}", measure="kg", priva_total=v, sum_of_records=got))
    rc = _checks(checks)
    years = sorted(df.year.unique())
    first = df[df.year == years[0]].iso_week.min()
    last = df[df.year == years[-1]].iso_week.max()
    ps = dt.date.fromisocalendar(int(years[0]), int(first), 1).isoformat()
    pe = dt.date.fromisocalendar(int(years[-1]), int(last), 7).isoformat()
    notes = [f"{y}: {vals.get('Grand Total', sum(vals.values())):,.0f} kg shown as one line with no weeks; not used."
             for y, vals in year_only.items()]
    unk = df.loc[df.crop == "Unknown", "kg"].sum()
    if unk:
        notes.append(f"{unk:,.0f} kg are under crop labels with no house (e.g. 'Unknown').")
    return Report(file=os.path.basename(path), sha256=file_sha256(path), report_type="yield", title=YIELD_TITLE,
                  period_start=ps, period_end=pe, exported_at=None, layout="weeks",
                  records=df, reconciliation=rc, notes=notes)


# ---- management report --------------------------------------------------------------------------
def read_mgmt_report(path: str) -> Report:
    rows, _ = _load_rows(path)
    week = next((_norm(r[2]) for r in rows[:8] if r[0] and _norm(r[0]).lower().startswith("week cal")), None)
    hdr_i = next((i for i, r in enumerate(rows[:12]) if r[0] and _norm(r[0]) == "Labour hours"), None)
    if not week or hdr_i is None:
        raise ReportError("Could not find the 'Week calender' or 'Labour hours' rows of the Management Report.")
    wm = re.match(r"^(\d{4})-(\d{1,2})$", week)
    if not wm:
        raise ReportError(f"Week label {week!r} is not in the form YYYY-WW.")
    yr, wk = int(wm.group(1)), int(wm.group(2))
    days = {j: _norm(c) for j, c in enumerate(rows[hdr_i]) if c not in (None, "") and j >= 1}
    total_col = next((j for j, d in days.items() if d.lower() == "grand total"), None)
    day_cols = {j: d for j, d in days.items() if j != total_col}

    # Layout: a block label, a blank row, its activity rows, a blank row, the next block label...
    recs, checks, block = [], [], None
    block_rows, children = {}, {}
    expect_block = True
    for i in range(hdr_i + 1, len(rows)):
        r = rows[i]
        lab = _norm(r[0]) if r[0] not in (None, "") else ""
        if lab.startswith("Labour Cost"):
            break
        if not lab:
            if block is not None and children.get(block):
                expect_block = True
            continue
        vals = {d: float(r[j]) for j, d in day_cols.items() if r[j] not in (None, "")}
        tot = float(r[total_col]) if total_col is not None and r[total_col] not in (None, "") else None
        if expect_block:
            expect_block = False
            block = lab
            block_rows[block] = (vals, i + 1)
            children[block] = []
            kind = "block"
        else:
            if block is None:
                raise ReportError(f"Row {i + 1} ('{lab}') sits under no crop block.")
            children[block].append(vals)
            kind = "activity"
        if tot is not None:
            checks.append(dict(level="row", key=f"{block} / {lab}" if kind == "activity" else block,
                               measure="hours (days vs Grand total)", priva_total=tot, sum_of_records=sum(vals.values())))
        for d, v in vals.items():
            recs.append(dict(iso_year=yr, iso_week=wk, block=block, row_label=lab, row_kind=kind, day=d, hours=v,
                             excel_row=i + 1))
    for b, (vals, _) in block_rows.items():
        for d in day_cols.values():
            got = sum(c.get(d, 0.0) for c in children[b])
            if d in vals or got:
                checks.append(dict(level="block", key=f"{b} {d}", measure="hours (activities vs block)",
                                   priva_total=vals.get(d, 0.0), sum_of_records=got))
    df = pd.DataFrame(recs)
    if df.empty:
        raise ReportError("No labour hours found in the Management Report.")
    rc = _checks(checks)
    sunday = dt.date.fromisocalendar(yr, wk, 1) - dt.timedelta(days=1)    # Priva weeks run Sunday..Saturday
    return Report(file=os.path.basename(path), sha256=file_sha256(path), report_type="mgmt_report", title=MGMT_TITLE,
                  period_start=sunday.isoformat(), period_end=(sunday + dt.timedelta(days=6)).isoformat(),
                  exported_at=None, layout="blocks x days", records=df, reconciliation=rc,
                  notes=[f"Week {yr}-{wk:02d} as labelled in the export."])


def read_special(path: str) -> Report | None:
    kind = special_kind(path)
    if kind == "yield":
        return read_yield(path)
    if kind == "mgmt_report":
        return read_mgmt_report(path)
    return None
