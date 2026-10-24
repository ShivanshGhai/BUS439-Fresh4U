"""
Runs the pipeline and returns everything the app shows. Kept separate from the Streamlit code so it
can be tested without Streamlit.

  process(files)               uploaded or demo files, in a throwaway folder (nothing is kept)
  process_folder(folder, data) exports already on this computer; the history is kept in `data`, so the
                               second run only reads new files
"""
from __future__ import annotations

import os
import tempfile

import pandas as pd

from . import planner
from . import season_plan as sp
from . import targets as tg
from .coaching import strengths
from .enrich import enrich_performance
from .store import Store

REVIEW_COLS = ["date", "activity_name", "location", "employee_group", "employee_id", "end_time", "hours",
               "min_per_row", "review_reason", "source_file", "excel_row"]


def _collect(st: Store) -> dict:
    log = st.log()
    recon = pd.read_csv(st.recon_path) if os.path.exists(st.recon_path) else pd.DataFrame()
    reasons = {}
    for f in sorted(os.listdir(st.q_dir)):
        if f.endswith(".reason.txt"):
            with open(os.path.join(st.q_dir, f), encoding="utf-8") as fh:
                reasons[f[:-len(".reason.txt")]] = fh.read()
    out = dict(log=log, recon=recon, quarantine=reasons, records=pd.DataFrame(), pace=pd.DataFrame(),
               strengths=pd.DataFrame(), review=pd.DataFrame())
    for t in ("production", "hours", "yield", "mgmt_report"):
        out[t] = st.history(t)
    hist = st.history("performance")
    if not hist.empty:
        rec = enrich_performance(hist)
        out["records"] = rec
        out["pace"] = planner.weekly_pace(rec)
        out["strengths"] = strengths(rec)
        rv = rec[rec["review_reason"] != ""]
        out["review"] = rv[[c for c in REVIEW_COLS if c in rv]].sort_values(["date", "employee_id"]).reset_index(drop=True)
    # the year plan and targets need the site-wide reports
    out["anchors"] = sp.production_anchors(out["production"], out["yield"]) + sp.mgmt_anchors(out["mgmt_report"], out["yield"])
    out["rates"] = sp.fit_rates(out["anchors"], out["hours"]) if out["anchors"] and not out["yield"].empty else {}
    out["cw_points"] = sp.crop_work_points(out["records"] if not out["records"].empty else None, out["anchors"])
    out["targets"] = tg.build_targets(out["pace"], out["production"]) if (len(out["pace"]) or len(out["production"])) \
        else pd.DataFrame()
    out["priva_norm"] = tg.priva_norm_today(out["records"])
    return out


def process(files: list[tuple[str, bytes]]) -> dict:
    """files: (name, contents). Nothing is kept after the call returns."""
    import run  # the command-line entry point, so the app and the CLI share one code path

    with tempfile.TemporaryDirectory() as d:
        inbox, data, out = (os.path.join(d, x) for x in ("inbox", "data", "outputs"))
        os.makedirs(inbox)
        for name, content in files:
            with open(os.path.join(inbox, os.path.basename(name)), "wb") as fh:
                fh.write(content)
        run.main(["--inbox", inbox, "--data", data, "--out", out, "--quiet"])
        return _collect(Store(data))


def process_folder(folder: str, data_dir: str) -> dict:
    """Every .xlsx under `folder` (sub-folders included). Originals are only read."""
    import run

    out_dir = os.path.join(os.path.dirname(os.path.abspath(data_dir)), "outputs")
    run.main(["--inbox", folder, "--data", data_dir, "--out", out_dir, "--recursive", "--quiet"])
    return _collect(Store(data_dir))


def folder_fingerprint(folder: str) -> tuple:
    """Changes whenever an export is added, removed or replaced (for caching)."""
    items = []
    for root, _, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(".xlsx") and not f.startswith("~$"):
                p = os.path.join(root, f)
                st = os.stat(p)
                items.append((os.path.relpath(p, folder), st.st_size, int(st.st_mtime)))
    return tuple(sorted(items))
