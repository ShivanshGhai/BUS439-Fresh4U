"""
Generates SYNTHETIC Priva-style site reports for the public demo, in the same layouts as the real
exports, so the demo runs through the same readers and total checks:

  * Production (tactical)  - weekly yield per crop, 2025 (52 weeks) and 2026 to week 15
  * Production             - hours / result / area per activity group x activity x location, Mar 15-28 2026
  * Hours                  - paid / present / registered hours per person per weekday, Mar 15-28 2026
  * Management Report      - labour hours per crop block x activity x weekday, week 2025-43

No Fresh4U records are used. Curves and rates are invented, loosely shaped like a greenhouse with two
tomato and two strawberry houses. People are "Demo Person 001"... with numbers 5001... Every title says
SYNTHETIC DEMO.

    python3 scripts/make_demo_reports.py demo_data
"""
import os
import sys
from datetime import date, timedelta

import numpy as np
import openpyxl

OUT = sys.argv[1] if len(sys.argv) > 1 else "demo_data"
rng = np.random.default_rng(2026)
ROW_M2 = 144.5
ROWS = {"House 1": range(1001, 1281), "House 2": range(2001, 2281), "House 3": range(3001, 3561), "House 4": range(4001, 4561)}
P_START, P_END = date(2026, 3, 15), date(2026, 3, 28)      # Sunday .. Saturday, ISO weeks 11-13 overlap -> 12, 13


def sheet():
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Sheet")
    return wb, ws


def put(ws, width, cells):
    r = [None] * width
    for c, v in cells.items():
        r[c] = v
    ws.append(r)


# ---- yield ---------------------------------------------------------------------------------------
def bell(weeks, start, end, peak, height):
    w = np.asarray(weeks, float)
    x = np.clip((w - start) / (end - start), 0, 1)
    y = height * np.sin(np.pi * x) ** 1.4 * np.exp(-((w - peak) / 18) ** 2 * 0.4)
    return np.where((w >= start) & (w <= end), y, 0.0)


def yield_series(year):
    wk = np.arange(1, 53)
    shift = 0 if year == 2025 else -1
    s = {
        "H1-Demo Tomato": bell(wk, 15 + shift, 49, 26, 98000),
        "H2-Demo Tomato": bell(wk, 15 + shift, 50, 27, 95000),
        "H3-Demo Strawberry": bell(wk, 10, 27, 17, 23000) + bell(wk, 34, 46, 39, 6000),
        "H4-Demo Strawberry (lit)": np.where((wk >= 29) & (wk <= 33), 0.0, 4200 + 1800 * np.cos(wk / 52 * 2 * np.pi)),
    }
    if year == 2026:                       # House 3 is being changed over in spring 2026
        s["H3-Demo Strawberry"] = np.where(wk <= 15, 0.0, s["H3-Demo Strawberry"])
    out = {}
    for k, v in s.items():
        noise = np.exp(rng.normal(0, 0.12, len(v)))
        out[k] = np.round(v * noise, 1)
    return out


def write_yield(path):
    crops = ["H1-Demo Tomato", "H2-Demo Tomato", "H3-Demo Strawberry", "H4-Demo Strawberry (lit)"]
    area = {"H1-Demo Tomato": 40460.0, "H2-Demo Tomato": 40460.0, "H3-Demo Strawberry": 80920.0,
            "H4-Demo Strawberry (lit)": 80920.0}
    data = {2025: yield_series(2025), 2026: {k: v[:15] for k, v in yield_series(2026).items()}}
    W = 5 + 4 * (len(crops) + 1)
    wb, ws = sheet()
    col = {c: 5 + 4 * i for i, c in enumerate(crops + ["Grand Total"])}
    put(ws, W, {0: "Production (tactical) - SYNTHETIC DEMO"})
    put(ws, W, {5: "Crop", 6: "Data"})
    put(ws, W, {col[c]: c for c in col})
    hdr = {0: "Year", 1: "Week", 3: "Day"}
    for c in col:
        hdr.update({col[c]: "Production / m²", col[c] + 1: "Cumulative production /  m²",
                    col[c] + 2: "Crop production", col[c] + 3: "Crop production cumulative"})
    put(ws, W, hdr)
    grand = {c: 0.0 for c in col}
    for year, series in data.items():
        n = len(next(iter(series.values())))
        tot = {c: float(np.sum(series[c])) for c in crops}
        tot["Grand Total"] = sum(tot.values())
        cells = {0: f"{year} Total"}
        for c in col:
            a = area.get(c, sum(area.values()))
            cells.update({col[c]: tot[c] / a, col[c] + 1: tot[c] / a, col[c] + 2: tot[c], col[c] + 3: tot[c]})
            grand[c] += tot[c]
        put(ws, W, cells)
        put(ws, W, {0: "Year", 1: "Week", 3: "Day", 5: "Crop", 6: "Data"})
        put(ws, W, {})
        cum = {c: 0.0 for c in col}
        for i in range(n):
            cells = {2: f"Week {i + 1}"}
            wk_tot = 0.0
            for c in crops:
                v = float(series[c][i])
                if v > 0:
                    cum[c] += v
                    wk_tot += v
                    cells.update({col[c]: v / area[c], col[c] + 1: cum[c] / area[c], col[c] + 2: v, col[c] + 3: cum[c]})
            if wk_tot:
                cum["Grand Total"] += wk_tot
                g = col["Grand Total"]
                cells.update({g: wk_tot / sum(area.values()), g + 2: wk_tot, g + 3: cum["Grand Total"]})
            put(ws, W, cells)
    put(ws, W, {0: "Year", 1: "Week", 3: "Day", 5: "Crop", 6: "Data"})
    put(ws, W, {})
    cells = {0: "Grand Total"}
    for c in col:
        cells[col[c] + 2] = grand[c]
    put(ws, W, cells)
    put(ws, W, {0: "2026-10-23 12:00 PM"})
    wb.save(path)
    return data


# ---- production (site activity x location) ---------------------------------------------------------
# group, activity, house (None = no location), hours per week (both houses), result per hour (None = area-based)
ACTIVITIES = [
    ("Greenhouse Incentive TOM", "Picking Tomatoes", "T", 140.0, "kg"),
    ("Greenhouse Incentive TOM", "Clipping (T)", "T", 560.0, None),
    ("Greenhouse Incentive TOM", "Deleafing (T)", "T", 420.0, None),
    ("Greenhouse Incentive TOM", "Truss Clips (T)", "T", 230.0, None),
    ("Greenhouse Incentive TOM", "Pruning Flowers/Fruit (T)", "T", 190.0, None),
    ("Greenhouse Incentive TOM", "Lowering (T)", "T", 150.0, None),
    ("Greenhouse Incentive STR", "Picking Strawberries", "H4", 28.0, "kg"),
    ("Greenhouse Incentive STR", "Combing (S)", "H4", 160.0, None),
    ("MIscellaneous STR", "Inspecting Plants (S)", "H4", 40.0, None),
    ("IPM TOM", "Putting out bios (T)", "T", 25.0, None),
    ("IPM TOM", "Scouting (T)", "T", 22.0, None),
    ("MIscellaneous TOM", "Packing Tomatoes", None, 3.4, "per_t"),
    ("MIscellaneous TOM", "Scales (T)", None, 0.35, "per_t"),
    ("MIscellaneous STR", "Scales (H4)", None, 40.0, None),
    ("Greenhouse Clean-Out STR", "Leaf Blowing (S)", "H3", 110.0, None),
    ("Greenhouse Clean-Out STR", "Removing pots (S)", "H3", 95.0, None),
    ("Greenhouse Planting STR", "Planting (S)", "H3", 70.0, None),
    ("Greenhouse Planting STR", "Filling pots (S)", None, 55.0, None),
    ("Bug Project", "Bug breeding (1)", None, 55.0, None),
    ("Miscellaneous General", "Forklift/warehouse", None, 14.0, None),
    ("Unknown", "Break (All)", None, 0.1, "break"),
]


def write_production(path, kg_tom_t, kg_str_h4_t):
    weeks = 2
    recs = []      # (group, activity, location, hours, result, area, rows)
    worked = 0.0
    for g, a, where, h, kind in ACTIVITIES:
        if kind == "break":
            continue
        if kind == "kg":
            kgph = 165.0 if where == "T" else 23.0
            kg = (kg_tom_t if where == "T" else kg_str_h4_t) * 1000 * weeks
            hours = kg / kgph
        elif kind == "per_t":
            hours = h * kg_tom_t * weeks
        else:
            hours = h * weeks
        hours *= float(np.exp(rng.normal(0, 0.05)))
        if hours <= 0:
            continue                      # e.g. no tomatoes to pick yet in March
        worked += hours
        if where is None:
            recs.append((g, a, "Unknown", hours, None, None, None))
            continue
        houses = ["House 1", "House 2"] if where == "T" else ["House 3" if where == "H3" else "House 4"]
        rows = [r for hs in houses for r in ROWS[hs]]
        pick = rng.choice(rows, size=min(len(rows), 120), replace=False)
        share = rng.dirichlet(np.ones(len(pick)))
        for r, s in zip(sorted(pick), share):
            hh = hours * s
            n_rows = max(1, round(hh * 60 / 40))
            area = ROW_M2 * n_rows
            res = (kg * s if kind == "kg" else area * 3.3)
            recs.append((g, a, f"Row {r}", hh, res, area, float(n_rows)))
    # two deliberate slips for the weekly check to find: a strawberry task on a tomato row, a row task with no row
    recs.append(("Greenhouse Clean-Out STR", "Leaf Blowing (S)", "Row 1105", 3.2, 144.5, 144.5, 1.0))
    recs.append(("Greenhouse Incentive STR", "Combing (S)", "Unknown", 5.5, None, None, None))
    worked += 8.7
    recs.append(("Unknown", "Break (All)", "Unknown", worked * 0.095, None, None, None))
    W = 15
    wb, ws = sheet()
    put(ws, W, {0: "Production - SYNTHETIC DEMO", 10: f"Period: {P_START} to {P_END}"})
    put(ws, W, {6: "Grand Total"})
    put(ws, W, {0: "Activity group", 3: "Activity", 4: "Location", 6: "Registered hours", 7: "Result", 8: "Area",
                11: "Performance / hour", 12: "Number of rows", 13: "Performance / m²"})

    def vals(rs):
        h = sum(r[3] for r in rs)
        res = [r[4] for r in rs if r[4] is not None]
        ar = [r[5] for r in rs if r[5] is not None]
        nr = [r[6] for r in rs if r[6] is not None]
        out = {6: h}
        if res:
            out[7] = sum(res)
            out[11] = sum(res) / h if h else None
        if ar:
            out[8] = sum(ar)
        if nr:
            out[12] = sum(nr)
        return out
    groups = sorted({r[0] for r in recs})
    for g in groups:
        gr = [r for r in recs if r[0] == g]
        put(ws, W, {0: f"{g} Total", **vals(gr)})
        for a in sorted({r[1] for r in gr}):
            ar = [r for r in gr if r[1] == a]
            put(ws, W, {1: a, **vals(ar)})
            for r in ar:
                put(ws, W, {2: r[2], **vals([r])})
    put(ws, W, {0: "Grand Total", **vals(recs)})
    put(ws, W, {0: "2026-10-23 12:00 PM", 10: " 1 / 1"})
    wb.save(path)


# ---- hours ---------------------------------------------------------------------------------------
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
HMEAS = ["Paid hours", "# Absent", "# Present", "Employee number", "Registered hours", "Present hours", "Presence"]


def write_hours(path, n_people=60):
    people = []
    for i in range(n_people):
        grp = "TFW" if i < 22 else ("Local" if i < 24 else "Contractor")
        untag = float(rng.choice([0.05, 0.1, 0.15, 0.6, 1.4], p=[0.4, 0.3, 0.15, 0.1, 0.05]))
        days = {}
        for d in DAYS[1:]:
            if rng.random() < (0.93 if grp != "Contractor" else 0.82):
                present = 2 * float(rng.normal(9.6, 0.6))          # two of each weekday in the fortnight
                reg = present - 2 * untag * float(rng.uniform(0.5, 1.5))
                days[d] = dict(present=present, registered=max(reg, 0), paid=max(reg, 0) * 0.91, n=2)
        people.append((grp, f"Demo Person {i + 1:03d}", 5001 + i, days))
    W = 4 + len(HMEAS) * (len(DAYS) + 1)
    col = {d: 4 + len(HMEAS) * k for k, d in enumerate(DAYS + ["Grand Total"])}
    wb, ws = sheet()
    put(ws, W, {0: "Hours - SYNTHETIC DEMO", 10: f"Period: {P_START} to {P_END}"})
    put(ws, W, {4: "Day"})
    put(ws, W, {col[d]: d for d in col})
    hdr = {0: "Employee group", 2: "Employee"}
    for d in col:
        hdr.update({col[d] + k: m for k, m in enumerate(HMEAS)})
    put(ws, W, hdr)

    def cells_for(dmap, number=None):
        c = {}
        tot = dict(present=0.0, registered=0.0, paid=0.0, n=0, absent=0)
        for d in DAYS:
            x = dmap.get(d)
            b = col[d]
            if x:
                c.update({b: x["paid"], b + 2: x["n"], b + 4: x["registered"], b + 5: x["present"]})
                for k in ("present", "registered", "paid", "n"):
                    tot[k] += x[k]
            else:
                c[b + 1] = 2
                tot["absent"] += 2
            if number is not None:
                c[b + 3] = number
                c[b + 6] = "Present" if x else "Absent"
        g = col["Grand Total"]
        c.update({g: tot["paid"], g + 1: tot["absent"] or None, g + 2: tot["n"] or None,
                  g + 4: tot["registered"], g + 5: tot["present"]})
        if number is not None:
            c[g + 3] = number
            c[g + 6] = "Present" if tot["n"] else "Absent"
        return {k: v for k, v in c.items() if v is not None}

    def add(maps):
        out = {}
        for m in maps:
            for d, x in m.items():
                o = out.setdefault(d, dict(present=0.0, registered=0.0, paid=0.0, n=0))
                for k in o:
                    o[k] += x[k]
        return out
    for grp in ["Contractor", "Local", "TFW"]:
        ps = [p for p in people if p[0] == grp]
        gm = add([p[3] for p in ps])
        gc = cells_for(gm)
        # group-level absent counts are the sum over people
        for d in DAYS + ["Grand Total"]:
            b = col[d]
            ab = sum((2 if d not in p[3] else 0) for p in ps) if d != "Grand Total" else \
                sum(2 * sum(1 for dd in DAYS if dd not in p[3]) for p in ps)
            gc[b + 1] = ab
        put(ws, W, {0: grp, **gc})
        put(ws, W, {0: "Employee group", 2: "Employee", 4: "Day"})
        put(ws, W, {})
        for p in ps:
            put(ws, W, {1: p[1], **cells_for(p[3], p[2])})
    allm = add([p[3] for p in people])
    gc = cells_for(allm)
    for d in DAYS + ["Grand Total"]:
        b = col[d]
        gc[b + 1] = sum((2 if d not in p[3] else 0) for p in people) if d != "Grand Total" else \
            sum(2 * sum(1 for dd in DAYS if dd not in p[3]) for p in people)
    put(ws, W, {0: "Grand Total", **gc})
    put(ws, W, {0: "2026-10-23 12:00 PM", 10: " 1 / 1"})
    wb.save(path)


# ---- management report -----------------------------------------------------------------------------
def write_mgmt(path, kg_by_house):
    blocks = {
        "General Labour": {"Bug Project": 35, "Miscellaneous General": 20, "MIscellaneous STR": 150,
                           "MIscellaneous TOM": 3.6 * (kg_by_house["House 1"] + kg_by_house["House 2"]), "None": 160},
        "H1-Demo Tomato": {"Clipping (T)": 90, "Deleafing  (T)": 130, "Lowering (T)": 30,
                           "Picking Tomatoes": 1000 * kg_by_house["House 1"] / 168, "Pruning Flowers/Fruit (T)": 12},
        "H2-Demo Tomato": {"Clipping (T)": 95, "Deleafing  (T)": 110, "Lowering (T)": 25,
                           "Picking Tomatoes": 1000 * kg_by_house["House 2"] / 168, "Spot Spraying (T)": 30},
        "H3-Demo Strawberry": {"Combing (S)": 110, "Inspecting Plants (S)": 8,
                               "Picking Strawberries": 1000 * kg_by_house["House 3"] / 30},
        "H4-Demo Strawberry (lit)": {"Combing (S)": 95, "Inspecting Plants (S)": 40, "Pruning runners (S)": 30,
                                     "Picking Strawberries": 1000 * kg_by_house["House 4"] / 23},
    }
    daycol = {d: 5 + 3 * i for i, d in enumerate(DAYS)}
    gt = 5 + 3 * 7 + 2
    W = gt + 2
    share = np.array([0.0, 0.2, 0.2, 0.18, 0.17, 0.2, 0.05])
    wb, ws = sheet()
    put(ws, W, {4: "Management Report - SYNTHETIC DEMO"})
    put(ws, W, {})
    put(ws, W, {})
    put(ws, W, {0: "Week calender", 2: "2025-43"})
    put(ws, W, {0: "Site", 2: "Demo Site"})
    put(ws, W, {0: "Labour hours", **{c: d for d, c in daycol.items()}, gt: "Grand total"})
    put(ws, W, {})
    put(ws, W, {})
    for b, acts in blocks.items():
        rows = {}
        for a, h in acts.items():
            sp = share * float(np.exp(rng.normal(0, 0.05)))
            rows[a] = {d: h * s for d, s in zip(DAYS, sp / sp.sum()) if h * s > 0}
        btot = {d: sum(r.get(d, 0) for r in rows.values()) for d in DAYS}
        put(ws, W, {0: b, **{daycol[d]: v for d, v in btot.items() if v}, gt: sum(btot.values())})
        put(ws, W, {})
        for a, r in rows.items():
            put(ws, W, {0: a, **{daycol[d]: v for d, v in r.items()}, gt: sum(r.values())})
        put(ws, W, {})
    put(ws, W, {0: "Labour Cost / m2", **{c: d for d, c in daycol.items()}, gt: "Grand total"})
    wb.save(path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    y = write_yield(os.path.join(OUT, "SYNTHETIC DEMO Production (tactical).xlsx"))
    # weeks 11-12 of 2026 (Mar 15-28 is Sunday..Saturday of ISO weeks 12-13; Priva weeks start Sunday)
    tom = float(np.mean([y[2026]["H1-Demo Tomato"][w] + y[2026]["H2-Demo Tomato"][w] for w in (11, 12)])) / 1000
    h4 = float(np.mean([y[2026]["H4-Demo Strawberry (lit)"][w] for w in (11, 12)])) / 1000
    write_production(os.path.join(OUT, "SYNTHETIC DEMO Production 20260315.xlsx"), tom, h4)
    write_hours(os.path.join(OUT, "SYNTHETIC DEMO Hours 20260315.xlsx"))
    k43 = {"House 1": y[2025]["H1-Demo Tomato"][42] / 1000, "House 2": y[2025]["H2-Demo Tomato"][42] / 1000,
           "House 3": y[2025]["H3-Demo Strawberry"][42] / 1000, "House 4": y[2025]["H4-Demo Strawberry (lit)"][42] / 1000}
    write_mgmt(os.path.join(OUT, "SYNTHETIC DEMO Management Report 2025-43.xlsx"), k43)
    print("wrote 4 synthetic site reports to", OUT)
