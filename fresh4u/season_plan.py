"""
Whole-farm, whole-year labour plan (the 52-week calendar).

    hours in a week = harvest (forecast kg / kg per hour)
                    + packing (tonnes x hours per tonne, + a fixed amount per strawberry house picking)
                    + tomato crop work (the weekly pattern recorded in Priva, by plant stage)
                    + strawberry crop work (per house in crop)
                    + clean-out & planting (per house being changed over)
                    + pest control & general (a steady amount)
                    + breaks (a share of the above)
    people = hours / registered hours per person per week

Every rate is worked out from the whole-site weeks that have been loaded (a Production export,
a Management Report). Each new export of that kind adds a week and the rates update.
Each rate carries where it came from and how sure we are ("Measured", "Assumed"...).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ROW_M2 = 144.5
HOUSES_T = ["House 1", "House 2"]
HOUSES_S = ["House 3", "House 4"]
CROP_WORK_TASKS = ["Clipping", "Deleafing", "Lowering", "Pruning Flowers/Fruit", "Truss Clips", "Twisting", "Sweeping"]

CATEGORIES = ["Tomato harvest", "Tomato crop work", "Packing & grading", "Strawberry harvest",
              "Strawberry crop work", "Clean-out & planting", "Pest control & general", "Breaks (unpaid)"]

# Assumptions with no data behind them yet. Each is a setting in the app.
DEFAULTS = dict(changeover_weeks=5,        # weeks to clean out and replant one house
                tomato_late_factor=0.5,    # crop work at the last pick, as a share of the last measured autumn week
                tomato_yield_pct=100.0, strawberry_yield_pct=100.0,
                hours_per_person=None,     # None = measured from the Hours report
                crew=None)                 # None = TFW + local people active in the Hours report


# ---- helpers ------------------------------------------------------------------------------------
def crop_of(*labels) -> str:
    for s in labels:
        s = str(s or "")
        if re.search(r"\bTOM\b|\(T\)|Tomato", s):
            return "Tomato"
        if re.search(r"\bSTR\b|\(S\)|Strawberr|\(H4\)", s):
            return "Strawberry"
    return "General"


def house_of_location(loc) -> str | None:
    s = str(loc or "")
    m = re.match(r"^Row (\d)\d{3}$", s)
    if m:
        return f"House {m.group(1)}"
    m = re.match(r"^(House \d)", s)
    return m.group(1) if m else None


def task_name(activity: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", re.sub(r"\s+", " ", str(activity))).strip()


def iso_weeks_of(start: str, end: str) -> list[tuple[int, int]]:
    """ISO (year, week) pairs whose Monday-Saturday falls inside [start, end]."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out, d = [], s
    while d <= e:
        y, w, _ = d.isocalendar()
        if (y, w) not in out:
            mon = pd.Timestamp(dt.date.fromisocalendar(y, w, 1))
            if mon >= s - pd.Timedelta(days=1) and mon + pd.Timedelta(days=5) <= e:
                out.append((y, w))
        d += pd.Timedelta(days=1)
    return out


@dataclass
class Rate:
    key: str
    item: str
    value: float
    unit: str
    low: float | None = None
    high: float | None = None
    based_on: str = ""
    evidence: str = "Measured"          # Measured | Measured, thin | Assumed | Setting


@dataclass
class Anchor:
    """One whole-site week as Priva recorded it (per-week hours by category, kg by house)."""
    label: str
    source: str
    iso: list                            # [(year, week), ...] the anchor covers
    weeks: float                         # how many weeks the totals cover
    cat: dict                            # category -> hours per week
    pick: dict                           # house -> picking hours per week
    house_work: dict                     # house -> non-picking hours per week located in that house
    tom_crop7: float                     # the 7 R&D crop-work tasks, hours per week
    kg: dict = field(default_factory=dict)        # house -> tonnes per week
    changeover_houses: list = field(default_factory=list)


# ---- anchors -----------------------------------------------------------------------------------
def _kg_for(yield_df: pd.DataFrame, iso: list) -> dict:
    if yield_df is None or yield_df.empty:
        return {}
    y = yield_df[yield_df["house"].notna()]
    sel = y[[(int(a), int(b)) in set(iso) for a, b in zip(y["year"], y["iso_week"])]]
    if sel.empty:
        return {}
    return (sel.groupby("house")["kg"].sum() / 1000 / len(iso)).to_dict()


def production_anchors(prod: pd.DataFrame, yield_df: pd.DataFrame) -> list[Anchor]:
    out = []
    if prod is None or prod.empty:
        return out
    for (ps, pe), d in prod.groupby(["period_start", "period_end"]):
        iso = iso_weeks_of(ps, pe)
        if not iso:
            continue
        n = len(iso)
        d = d.copy()
        d["crop"] = [crop_of(g) if crop_of(g) != "General" else crop_of(a) for g, a in zip(d["activity_group"], d["activity"])]
        d["house"] = d["location"].map(house_of_location)
        d["task"] = d["activity"].map(task_name)

        def cat(r):
            a, g, c = str(r.activity), str(r.activity_group), r.crop
            h = None if pd.isna(r.house) else r.house
            if a.startswith("Break"):
                return "breaks"
            if re.search(r"Clean-Out|Planting", g) or a.startswith("Misc planting"):
                return "changeover"
            if a.startswith("Picking"):
                return "tom_pick" if c == "Tomato" else "str_pick"
            if c == "General":
                return "general"
            if c == "Tomato":
                if h is None:
                    return "tom_pack"
                return "tom_crop7" if r.task in CROP_WORK_TASKS else "tom_other"
            return "str_pack" if h is None else "str_house"
        d["cat"] = d.apply(cat, axis=1)
        tot = d.groupby("cat")["hours"].sum() / n
        picks = d[d["cat"].isin(["tom_pick", "str_pick"])]
        pick = picks.groupby("house")["hours"].sum()
        unloc = picks.loc[picks["house"].isna(), "hours"].sum()
        if pick.sum() > 0 and unloc:
            pick = pick * (1 + unloc / pick.sum())       # spread unlocated picking over houses pro rata
        hw = d[d["cat"].isin(["tom_crop7", "tom_other", "str_house"])].groupby("house")["hours"].sum() / n
        kg = _kg_for(yield_df, iso)
        co = [h for h in HOUSES_S if kg and kg.get(h, 0) == 0 and tot.get("changeover", 0) > 0]
        c = {
            "Tomato harvest": tot.get("tom_pick", 0.0),
            "Tomato crop work": tot.get("tom_crop7", 0.0) + tot.get("tom_other", 0.0),
            "Packing & grading": tot.get("tom_pack", 0.0) + tot.get("str_pack", 0.0),
            "Strawberry harvest": tot.get("str_pick", 0.0),
            "Strawberry crop work": tot.get("str_house", 0.0),
            "Clean-out & planting": tot.get("changeover", 0.0),
            "Pest control & general": tot.get("general", 0.0),
            "Breaks (unpaid)": tot.get("breaks", 0.0),
        }
        a = Anchor(label=f"{pd.Timestamp(ps):%b %d} – {pd.Timestamp(pe):%b %d, %Y}", source="Production export",
                   iso=iso, weeks=n, cat=c, pick=(pick / n).to_dict(), house_work=hw.to_dict(),
                   tom_crop7=tot.get("tom_crop7", 0.0), kg=kg, changeover_houses=co)
        a.tom_pack, a.str_pack, a.tom_other = tot.get("tom_pack", 0.0), tot.get("str_pack", 0.0), tot.get("tom_other", 0.0)
        a.unlabelled = 0.0
        out.append(a)
    return out


def mgmt_anchors(mr: pd.DataFrame, yield_df: pd.DataFrame) -> list[Anchor]:
    out = []
    if mr is None or mr.empty:
        return out
    for (y, w), d in mr.groupby(["iso_year", "iso_week"]):
        acts = d[d["row_kind"] == "activity"].groupby(["block", "row_label"])["hours"].sum().reset_index()
        blocks = d[d["row_kind"] == "block"].groupby("block")["hours"].sum()
        pick, hw = {}, {}
        tom_pack = str_pack = general = unlab = tom7 = tom_other = 0.0
        for b, tot_b in blocks.items():
            rows = acts[acts["block"] == b]
            hb = {"H1": "House 1", "H2": "House 2", "H3": "House 3", "H4": "House 4"}.get(str(b)[:2])
            if hb:
                pk = rows.loc[rows["row_label"].str.startswith("Picking"), "hours"].sum()
                pick[hb] = pick.get(hb, 0.0) + pk
                hw[hb] = hw.get(hb, 0.0) + tot_b - pk
                if hb in HOUSES_T:
                    t7 = rows.loc[rows["row_label"].map(task_name).isin(CROP_WORK_TASKS), "hours"].sum()
                    tom7 += t7
                    tom_other += tot_b - pk - t7
                continue
            for _, r in rows.iterrows():
                lab = str(r["row_label"])
                if re.search(r"misc", lab, re.I) and crop_of(lab) == "Tomato":
                    tom_pack += r["hours"]
                elif re.search(r"misc", lab, re.I) and crop_of(lab) == "Strawberry":
                    str_pack += r["hours"]
                elif re.search(r"bug|general", lab, re.I):
                    general += r["hours"]
                else:
                    unlab += r["hours"]
            unlab += tot_b - rows["hours"].sum()          # anything in the block not broken down
        iso = [(int(y), int(w))]
        kg = _kg_for(yield_df, iso)
        c = {
            "Tomato harvest": sum(pick.get(h, 0) for h in HOUSES_T),
            "Tomato crop work": sum(hw.get(h, 0) for h in HOUSES_T),
            "Packing & grading": tom_pack + str_pack,
            "Strawberry harvest": sum(pick.get(h, 0) for h in HOUSES_S),
            "Strawberry crop work": sum(hw.get(h, 0) for h in HOUSES_S),
            "Clean-out & planting": 0.0,
            "Pest control & general": general,
            "Breaks (unpaid)": unlab,
        }
        a = Anchor(label=f"Week {int(w)}, {int(y)}", source="Management Report", iso=iso, weeks=1, cat=c,
                   pick=pick, house_work=hw, tom_crop7=tom7, kg=kg)
        a.tom_pack, a.str_pack, a.tom_other, a.unlabelled = tom_pack, str_pack, tom_other, unlab
        out.append(a)
    return out


# ---- rates ----------------------------------------------------------------------------------------
def _pooled(points):
    t = sum(p[0] for p in points)
    h = sum(p[1] for p in points)
    return t * 1000 / h if h else np.nan


def fit_rates(anchors: list[Anchor], hours_df: pd.DataFrame | None = None) -> dict:
    """Every rate the plan uses, with its provenance. Needs at least one anchor."""
    R = {}
    names = ", ".join(a.label for a in anchors)

    def add(key, item, value, unit, low=None, high=None, based_on="", evidence="Measured"):
        R[key] = Rate(key, item, float(value) if value is not None else np.nan, unit, low, high, based_on, evidence)

    tp = [(a.kg.get(h, 0), a.pick.get(h, 0)) for a in anchors for h in HOUSES_T if a.kg.get(h, 0) > 0 and a.pick.get(h, 0) > 0]
    if tp:
        r = [t * 1000 / h for t, h in tp]
        add("tom_pick_kgph", "Tomato picking", _pooled(tp), "kg/h", min(r), max(r),
            f"{len(tp)} house-weeks: {names}", "Measured" if len(tp) >= 3 else "Measured, thin")
    for h in HOUSES_S:
        pts = [(a.kg.get(h, 0), a.pick.get(h, 0)) for a in anchors if a.kg.get(h, 0) > 0 and a.pick.get(h, 0) > 0]
        if pts:
            r = [t * 1000 / x for t, x in pts]
            add(f"str_pick_kgph_{h[-1]}", f"Strawberry picking, {h}", _pooled(pts), "kg/h", min(r), max(r),
                f"{len(pts)} house-week{'s' if len(pts) > 1 else ''}", "Measured" if len(pts) >= 2 else "Measured, thin")
    sp_all = [(a.kg.get(h, 0), a.pick.get(h, 0)) for a in anchors for h in HOUSES_S if a.kg.get(h, 0) > 0 and a.pick.get(h, 0) > 0]
    if sp_all:
        add("str_pick_kgph", "Strawberry picking, any house", _pooled(sp_all), "kg/h", based_on="all strawberry house-weeks")
    tk = [(sum(a.kg.get(h, 0) for h in HOUSES_T), a.tom_pack) for a in anchors if sum(a.kg.get(h, 0) for h in HOUSES_T) > 0]
    if tk:
        r = sorted(h / t for t, h in tk)
        add("tom_pack_h_per_t", "Tomato packing & grading", sum(h for _, h in tk) / sum(t for t, _ in tk), "h per tonne",
            r[0], r[-1], "Unlocated tomato tasks (packing, scales, misc)")
    sk = [(a.str_pack / n) for a in anchors for n in [sum(1 for h in HOUSES_S if a.kg.get(h, 0) > 0)] if n]
    if sk:
        add("str_pack_per_house", "Strawberry packing & misc", float(np.mean(sk)), "h/week per house picking",
            min(sk), max(sk), "Unlocated strawberry tasks")
    sh = [(a.kg.get(h, 0), a.house_work.get(h, 0)) for a in anchors for h in HOUSES_S if a.kg.get(h, 0) > 0]
    if len(sh) >= 2:
        t_, h_ = np.array(sh).T
        b, c0 = np.polyfit(t_, h_, 1)
        add("str_house_b", "Strawberry crop work", b, "h per tonne picked, per house", based_on=f"{len(sh)} house-weeks",
            evidence="Measured, thin" if len(sh) < 5 else "Measured")
        add("str_house_a", "Strawberry crop work (fixed part)", c0, "h/week per house", evidence="Measured, thin")
        add("str_house_floor", "Strawberry crop work, minimum", float(h_.min()), "h/week per house in crop",
            based_on="lowest house-week seen", evidence="Measured, thin")
    elif sh:
        add("str_house_b", "Strawberry crop work", 0.0, "h per tonne", evidence="Assumed")
        add("str_house_a", "Strawberry crop work (fixed part)", sh[0][1], "h/week per house", evidence="Measured, thin")
        add("str_house_floor", "Strawberry crop work, minimum", sh[0][1], "h/week per house", evidence="Measured, thin")
    gen = [a.cat["Pest control & general"] for a in anchors]
    add("general_per_week", "Pest control & general", float(np.mean(gen)), "h/week", min(gen), max(gen),
        "Bug breeding, forklift, irrigation")
    to = [a.tom_other for a in anchors if a.tom_crop7 > 0]
    if to:
        add("tom_other_per_week", "Other tomato house work", float(np.mean(to)), "h/week while the crop is in",
            min(to), max(to), "IPM, leaks, fertiliser in H1–H2")
    co = [a.cat["Clean-out & planting"] / len(a.changeover_houses) for a in anchors if a.changeover_houses]
    if co:
        add("changeover_per_house_week", "Clean-out & planting", float(np.mean(co)), "h/week per house",
            based_on="; ".join(f"{', '.join(a.changeover_houses)} changeover, {a.label}" for a in anchors if a.changeover_houses),
            evidence="Measured, thin" if len(co) < 2 else "Measured")
    else:
        add("changeover_per_house_week", "Clean-out & planting", 450.0, "h/week per house", evidence="Assumed",
            based_on="No changeover in the loaded weeks")
    br = [(a.cat["Breaks (unpaid)"], sum(v for k, v in a.cat.items() if k != "Breaks (unpaid)"))
          for a in anchors if a.source == "Production export"]
    if br:
        add("break_share", "Breaks (unpaid)", sum(b for b, _ in br) / sum(w for _, w in br), "share of worked hours",
            based_on="Break (All) activity")
    else:
        add("break_share", "Breaks (unpaid)", 0.1, "share of worked hours", evidence="Assumed")
    if hours_df is not None and not hours_df.empty:
        hh = hours_df.copy()
        per = hh.groupby(["period_start", "period_end"])
        hpp, crew, pp = [], [], []
        for (ps, pe), d in per:
            n = max(len(iso_weeks_of(ps, pe)), 1)
            e = d.groupby(["employee_id", "employee_group"])["registered_hours"].sum().reset_index()
            act = e[e["registered_hours"] > 0]
            if len(act):
                hpp.append(act["registered_hours"].sum() / len(act) / n)
                crew.append(int(act["employee_group"].isin(["TFW", "Local"]).sum()))
                pp.append(len(act))
        if hpp:
            add("hours_per_person", "People per week", float(np.mean(hpp)), "registered h per active person per week",
                based_on=f"Hours report, {pp[-1]} active people")
            add("crew", "TFW + local crew", float(np.mean(crew)), "people", based_on="Hours report, TFW + Local active")
    if "hours_per_person" not in R:
        add("hours_per_person", "People per week", 45.0, "registered h per person per week", evidence="Assumed")
    if "crew" not in R:
        add("crew", "TFW + local crew", 45.0, "people", evidence="Assumed")
    return R


# ---- tomato crop-work curve -----------------------------------------------------------------------
def crop_work_points(perf_records: pd.DataFrame | None, anchors: list[Anchor]) -> dict:
    """ISO week -> (hours of the 7 crop-work tasks, source). Recorded weeks only."""
    pts = {}
    if perf_records is not None and not perf_records.empty:
        r = perf_records[perf_records["activity_name"].isin(CROP_WORK_TASKS)]
        periods = perf_records[["period_start", "period_end"]].drop_duplicates()
        covered = set()
        for ps, pe in periods.itertuples(index=False):
            covered |= set(iso_weeks_of(ps, pe))
        iso = r["date"].dt.isocalendar()
        w = r.assign(y=iso["year"].astype(int), w=iso["week"].astype(int)).groupby(["y", "w"])["hours"].sum()
        for (y, wk), h in w.items():
            if (y, wk) in covered:
                pts[int(wk)] = (float(h), f"recorded {y}")
    for a in anchors:
        if a.source == "Management Report" and a.tom_crop7 > 0:
            wk = a.iso[0][1]
            if wk not in pts:
                pts[wk] = (a.tom_crop7, f"recorded {a.iso[0][0]} (Management Report)")
    return pts


def tomato_curve(points: dict, harvest_weeks: list[int], changeover: set, late_factor: float) -> tuple[dict, dict]:
    cw, src = {}, {}
    last_pick = max(harvest_weeks) if harvest_weeks else 52
    meas = sorted(points)
    for wk in range(1, 53):
        if wk in changeover:
            cw[wk], src[wk] = 0.0, "changeover"
        elif wk in points:
            cw[wk], src[wk] = points[wk][0], points[wk][1]
        elif meas and meas[0] < wk < meas[-1]:
            lo = max(m for m in meas if m < wk)
            hi = min(m for m in meas if m > wk)
            f = (wk - lo) / (hi - lo)
            cw[wk], src[wk] = points[lo][0] * (1 - f) + points[hi][0] * f, "interpolated"
        elif meas and wk < meas[0] and (not changeover or wk > max(w for w in changeover if w < meas[0]) if any(w < meas[0] for w in changeover) else True):
            cw[wk], src[wk] = points[meas[0]][0], "assumed (as first recorded week)"
        elif meas and meas[-1] < wk <= last_pick:
            f = (wk - meas[-1]) / max(last_pick - meas[-1], 1)
            cw[wk], src[wk] = points[meas[-1]][0] * (1 - f * (1 - late_factor)), "assumed taper"
        else:
            cw[wk], src[wk] = 0.0, "no crop"
    return cw, src


def _changeover(series: pd.Series, n_weeks: int) -> set:
    on = (series.reindex(range(1, 53)).fillna(0) > 0).to_numpy()
    out = set()
    if not on.any():
        return out
    for i in range(52):
        if on[i] and not on[(i + 1) % 52]:
            gap = 0
            while not on[(i + 1 + gap) % 52] and gap < 52:
                gap += 1
            if gap >= 3:
                for j in range(min(n_weeks, gap)):
                    out.add(((i + 1 + j) % 52) + 1)
    return out


# ---- the plan ----------------------------------------------------------------------------------------
def basis_years(yield_df: pd.DataFrame) -> list[int]:
    """Years with yield for all 52 weeks (a full season to plan from)."""
    if yield_df is None or yield_df.empty:
        return []
    w = yield_df.groupby("year")["iso_week"].agg(["min", "max", "nunique"])
    return [int(y) for y, r in w.iterrows() if r["max"] >= 52 and r["min"] <= 2]


def weekly_kg(yield_df: pd.DataFrame, year: int, tom_pct=100.0, str_pct=100.0) -> pd.DataFrame:
    y = yield_df[(yield_df["year"] == year) & yield_df["house"].notna()]
    k = y.groupby(["iso_week", "house"])["kg"].sum().unstack("house").reindex(range(1, 53)).fillna(0.0) / 1000
    k = k.reindex(columns=HOUSES_T + HOUSES_S, fill_value=0.0)
    k[HOUSES_T] *= tom_pct / 100
    k[HOUSES_S] *= str_pct / 100
    return k


def build_plan(kt: pd.DataFrame, R: dict, cw_points: dict, settings: dict | None = None) -> pd.DataFrame:
    s = {**DEFAULTS, **(settings or {})}
    v = {k: r.value for k, r in R.items()}
    hpp = s["hours_per_person"] or v["hours_per_person"]
    harvest = kt[HOUSES_T].sum(axis=1)
    hw = [int(w) for w in harvest[harvest > 0].index]
    tom_co = _changeover(harvest, s["changeover_weeks"])
    s_co = {h: _changeover(kt[h], s["changeover_weeks"]) for h in HOUSES_S}
    cw, src = tomato_curve(cw_points, hw, tom_co, s["tomato_late_factor"])
    rows = []
    for wk in range(1, 53):
        t_t, t_s = kt.loc[wk, HOUSES_T], kt.loc[wk, HOUSES_S]
        r = {"iso_week": wk}
        r["Tomato harvest"] = t_t.sum() * 1000 / v["tom_pick_kgph"] if "tom_pick_kgph" in v else 0.0
        sh = 0.0
        for h in HOUSES_S:
            rate = v.get(f"str_pick_kgph_{h[-1]}", v.get("str_pick_kgph", np.nan))
            sh += t_s[h] * 1000 / rate if t_s[h] > 0 else 0.0
        r["Strawberry harvest"] = sh
        crop_on = src[wk] not in ("changeover", "no crop")
        r["Tomato crop work"] = cw[wk] + (v.get("tom_other_per_week", 0.0) if crop_on else 0.0)
        picking_s = int((t_s > 0).sum())
        r["Packing & grading"] = v.get("tom_pack_h_per_t", 0.0) * t_t.sum() + v.get("str_pack_per_house", 0.0) * picking_s
        r["Strawberry crop work"] = sum(max(v.get("str_house_a", 0) + v.get("str_house_b", 0) * t, v.get("str_house_floor", 0))
                                        for t in t_s if t > 0)
        n_co = int(wk in tom_co) + sum(wk in s_co[h] for h in HOUSES_S)
        r["Clean-out & planting"] = v["changeover_per_house_week"] * n_co
        r["Pest control & general"] = v["general_per_week"]
        work = sum(r[c] for c in CATEGORIES if c != "Breaks (unpaid)")
        r["Breaks (unpaid)"] = work * v["break_share"]
        r["Total hours"] = work + r["Breaks (unpaid)"]
        r["People"] = r["Total hours"] / hpp
        r["Tomato t"], r["Strawberry t"] = float(t_t.sum()), float(t_s.sum())
        r["Tomato crop work from"] = src[wk]
        r["Changeover"] = ", ".join((["H1–H2"] if wk in tom_co else []) + [h.replace("House ", "H") for h in HOUSES_S if wk in s_co[h]])
        rows.append(r)
    return pd.DataFrame(rows)


def check_against_anchors(anchors: list[Anchor], R: dict, cw_points: dict, yield_df: pd.DataFrame,
                          settings: dict | None = None) -> pd.DataFrame:
    """For each recorded week: what Priva recorded vs what the plan gives with that week's own yield."""
    out = []
    for a in anchors:
        years = sorted({y for y, _ in a.iso})
        rows = []
        for y in years:
            kt = weekly_kg(yield_df, y)
            p = build_plan(kt, R, cw_points, settings)
            rows.append(p[p["iso_week"].isin([w for yy, w in a.iso if yy == y])])
        p = pd.concat(rows)
        for c in CATEGORIES + ["Total hours"]:
            obs = sum(a.cat.values()) if c == "Total hours" else a.cat.get(c, 0.0)
            out.append(dict(week=a.label, source=a.source, category=c, recorded=obs, plan=float(p[c].mean())))
    return pd.DataFrame(out)


def rates_table(R: dict, settings: dict | None = None) -> pd.DataFrame:
    s = {**DEFAULTS, **(settings or {})}
    rows = [dict(item=r.item, value=r.value, unit=r.unit, low=r.low, high=r.high, based_on=r.based_on, evidence=r.evidence)
            for r in R.values() if r.key not in ("str_house_a", "str_house_floor", "str_pick_kgph")]
    rows += [dict(item="Weeks to change over a house", value=s["changeover_weeks"], unit="weeks", based_on="No data yet",
                  evidence="Assumed"),
             dict(item="Tomato crop work after the last recorded week", value=s["tomato_late_factor"],
                  unit="share left at the last pick", based_on="No data yet", evidence="Assumed"),
             dict(item="Tomato changeover (H1–H2)", value=R["changeover_per_house_week"].value, unit="h/week, same as one house",
                  based_on="No tomato clean-out recorded yet", evidence="Assumed")]
    return pd.DataFrame(rows)


def summary(plan: pd.DataFrame, crew: float) -> dict:
    p = plan
    peak = p.loc[p["People"].idxmax()]
    low = p.loc[p["People"].idxmin()]
    busy = p[p["People"] > 100]
    return dict(total_hours=float(p["Total hours"].sum()), peak_people=float(peak["People"]), peak_week=int(peak["iso_week"]),
                low_people=float(low["People"]), low_week=int(low["iso_week"]), median_people=float(p["People"].median()),
                weeks_over_crew=int((p["People"] > crew).sum()), weeks_over_100=int(len(busy)),
                first_over_100=int(busy["iso_week"].min()) if len(busy) else None,
                last_over_100=int(busy["iso_week"].max()) if len(busy) else None,
                contractor_person_weeks=float((p["People"] - crew).clip(lower=0).sum()))
