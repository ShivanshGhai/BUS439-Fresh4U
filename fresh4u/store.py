"""
History store: one CSV per report type, plus an ingest log and a quarantine folder.

Rules
  * A file whose exact bytes were loaded before is skipped (sha256 in the log).
  * A new file REPLACES every stored row of the same report type inside its period
    (or, without a stated period, on the dates it contains). Re-exporting a week
    therefore corrects it instead of double-counting it.
  * A file that cannot be verified is copied nowhere and changes nothing: it gets a
    plain-language reason (and a best-effort preview) in quarantine/.
  * Source files are only ever read.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd

LOG_COLS = ["loaded_at", "file", "sha256", "report_type", "layout", "period_start", "period_end",
            "records", "hours", "checks", "checks_failed", "status", "replaced_rows", "replaced_from", "message"]


class Store:
    def __init__(self, root: str):
        self.root = root
        self.hist_dir = os.path.join(root, "history")
        self.q_dir = os.path.join(root, "quarantine")
        os.makedirs(self.hist_dir, exist_ok=True)
        os.makedirs(self.q_dir, exist_ok=True)
        self.log_path = os.path.join(root, "ingest_log.csv")
        self.recon_path = os.path.join(root, "reconciliation.csv")

    # ---- log -----------------------------------------------------------------
    def log(self) -> pd.DataFrame:
        if os.path.exists(self.log_path):
            return pd.read_csv(self.log_path, dtype=str)
        return pd.DataFrame(columns=LOG_COLS)

    def _append_log(self, row: dict):
        lg = self.log()
        row = {k: row.get(k, "") for k in LOG_COLS}
        row["loaded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        pd.concat([lg, pd.DataFrame([row])], ignore_index=True).to_csv(self.log_path, index=False)

    def already_loaded(self, sha: str) -> str | None:
        lg = self.log()
        hit = lg[(lg["sha256"] == sha) & (lg["status"] == "loaded")]
        return None if hit.empty else hit.iloc[-1]["file"]

    def already_quarantined(self, sha: str) -> bool:
        lg = self.log()
        return not lg[(lg["sha256"] == sha) & (lg["status"] == "quarantined")].empty

    # ---- history -------------------------------------------------------------
    def hist_path(self, report_type: str) -> str:
        return os.path.join(self.hist_dir, f"{report_type}.csv")

    def history(self, report_type: str) -> pd.DataFrame:
        p = self.hist_path(report_type)
        if not os.path.exists(p):
            return pd.DataFrame()
        return pd.read_csv(p, dtype={"employee_id": str, "date": str, "period_start": str, "period_end": str},
                           low_memory=False)

    def upsert(self, report, extra_cols: dict) -> tuple[int, list]:
        new = report.records.copy()
        for k, v in extra_cols.items():
            new[k] = v
        dated = "date" in new
        if dated:
            new["date"] = new["date"].astype(str)
        old = self.history(report.report_type)
        replaced, from_files = 0, []
        if not old.empty:
            if dated and "date" in old and report.period_start and report.period_end:
                mask = (old["date"] >= report.period_start) & (old["date"] <= report.period_end)
            elif dated and "date" in old:
                mask = old["date"].isin(set(new["date"]))
            else:
                # reports without a date column (Production, Hours, yield...): a file covering an
                # overlapping period replaces the stored one
                mask = (old["period_start"] <= str(report.period_end)) & (old["period_end"] >= str(report.period_start))
            replaced = int(mask.sum())
            from_files = sorted(old.loc[mask, "source_file"].dropna().unique().tolist())
            old = old[~mask]
        out = pd.concat([old, new], ignore_index=True) if not old.empty else new
        sort = [c for c in ("date", "period_start", "source_file", "excel_row") if c in out]
        out = out.sort_values(sort, kind="stable")
        tmp = self.hist_path(report.report_type) + ".tmp"
        out.to_csv(tmp, index=False)
        os.replace(tmp, self.hist_path(report.report_type))   # never leaves a half-written history
        rc = report.reconciliation.assign(file=report.file)
        prev = pd.read_csv(self.recon_path) if os.path.exists(self.recon_path) else pd.DataFrame()
        if not prev.empty:
            prev = prev[prev["file"] != report.file]
        pd.concat([prev, rc], ignore_index=True).to_csv(self.recon_path, index=False)
        return replaced, from_files

    def record_loaded(self, report, replaced, from_files, message=""):
        rc = report.reconciliation
        self._append_log(dict(file=report.file, sha256=report.sha256, report_type=report.report_type,
                              layout=report.layout, period_start=report.period_start, period_end=report.period_end,
                              records=len(report.records),
                              hours=round(float(pd.to_numeric(report.records.get("hours", pd.Series(dtype=float)), errors="coerce").sum()), 4),
                              checks=len(rc), checks_failed=int((~rc["match"]).sum()) if len(rc) else 0,
                              status="loaded", replaced_rows=replaced, replaced_from=";".join(from_files),
                              message=message))

    def record_not_used(self, file: str, sha: str, title: str, reason: str):
        self._append_log(dict(file=file, sha256=sha, report_type=title, status="not used", message=reason))

    def already_seen(self, sha: str) -> bool:
        lg = self.log()
        return not lg[(lg["sha256"] == sha) & (lg["status"] == "not used")].empty

    # ---- quarantine ----------------------------------------------------------
    def quarantine(self, file: str, sha: str, reason: str, preview: pd.DataFrame | None = None,
                   report=None):
        base = os.path.join(self.q_dir, os.path.splitext(file)[0])
        with open(base + ".reason.txt", "w", encoding="utf-8") as fh:
            fh.write(f"File: {file}\nsha256: {sha}\nQuarantined: {datetime.now().isoformat(timespec='seconds')}\n\n")
            fh.write("Why this file was not loaded:\n" + reason + "\n\n")
            fh.write("Nothing in the history changed. Fix the export (or mappings.json) and run again.\n")
            if report is not None and len(report.reconciliation):
                bad = report.reconciliation[~report.reconciliation["match"]]
                if len(bad):
                    fh.write("\nTotals that did not match Priva's own:\n" + bad.to_string(index=False) + "\n")
        if preview is not None and len(preview):
            preview.to_csv(base + ".preview.csv", index=False)
        self._append_log(dict(file=file, sha256=sha, report_type=getattr(report, "report_type", "") or "",
                              status="quarantined", message=reason.splitlines()[0][:300]))
