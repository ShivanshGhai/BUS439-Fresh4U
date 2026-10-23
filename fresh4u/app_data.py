"""
Runs the pipeline on a set of files in a throwaway folder and returns everything the app shows.
Kept separate from the Streamlit code so it can be tested without Streamlit.
"""
from __future__ import annotations

import os
import tempfile

import pandas as pd

from . import planner
from .coaching import strengths
from .enrich import enrich_performance
from .store import Store


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
        st = Store(data)
        log = st.log()
        recon = pd.read_csv(st.recon_path) if os.path.exists(st.recon_path) else pd.DataFrame()
        reasons = {}
        for f in sorted(os.listdir(st.q_dir)):
            if f.endswith(".reason.txt"):
                with open(os.path.join(st.q_dir, f), encoding="utf-8") as fh:
                    reasons[f[:-len(".reason.txt")]] = fh.read()
        hist = st.history("performance")
    result = dict(log=log, recon=recon, quarantine=reasons, records=pd.DataFrame(), pace=pd.DataFrame(),
                  strengths=pd.DataFrame(), review=pd.DataFrame())
    if hist.empty:
        return result
    rec = enrich_performance(hist)
    result["records"] = rec
    result["pace"] = planner.weekly_pace(rec)
    result["strengths"] = strengths(rec)
    rv = rec[rec["review_reason"] != ""]
    cols = ["date", "activity_name", "location", "employee_group", "employee_id", "end_time", "hours",
            "min_per_row", "review_reason", "source_file", "excel_row"]
    result["review"] = rv[[c for c in cols if c in rv]].sort_values(["date", "employee_id"]).reset_index(drop=True)
    return result
