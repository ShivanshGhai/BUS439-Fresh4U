"""
Fresh4U Priva pipeline - one command.

    python3 run.py --inbox "<folder with Priva .xlsx exports>" --data data --out outputs

Each run:
  1. reads every .xlsx in the inbox that has not been loaded before (originals are never changed);
  2. works out the report type and layout from the headers (see fresh4u/mappings.json);
  3. checks the records add up to Priva's own daily and grand totals;
  4. loads files that pass into data/history/<type>.csv (a re-export of a period replaces it),
     and puts files that fail in data/quarantine/ with the reason;
  5. rebuilds the analysis tables in outputs/.

--budget SECONDS stops reading new files after that long (exit code 3 = run again to continue).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fresh4u.priva_reader import ReportError, file_sha256, flatten_any, load_mappings, read_report  # noqa: E402
from fresh4u.store import Store  # noqa: E402
from fresh4u.enrich import enrich_performance, write_outputs  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inbox", required=True, help="folder holding Priva .xlsx exports (read only)")
    ap.add_argument("--data", default="data", help="where history, log and quarantine live")
    ap.add_argument("--out", default="outputs", help="where analysis tables are written")
    ap.add_argument("--budget", type=float, default=None, help="stop reading new files after N seconds")
    ap.add_argument("--accept-unverified", action="store_true",
                    help="load files that have no Priva totals to check against (default: quarantine them)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    say = (lambda *x: None) if a.quiet else print
    store = Store(a.data)
    mappings = load_mappings()
    t0 = time.time()
    files = sorted(f for f in glob.glob(os.path.join(a.inbox, "*.xlsx")) if not os.path.basename(f).startswith("~$"))
    if not files:
        say(f"No .xlsx files in {a.inbox}")
    loaded = quarantined = skipped = 0
    for path in files:
        name = os.path.basename(path)
        sha = file_sha256(path)
        prev = store.already_loaded(sha)
        if prev:
            skipped += 1
            continue
        if a.budget is not None and time.time() - t0 > a.budget:
            say("PARTIAL: time budget reached - run again to continue.")
            return 3
        try:
            rep = read_report(path, mappings)
        except ReportError as e:
            if not store.already_quarantined(sha):
                store.quarantine(name, sha, str(e), preview=flatten_any(path))
            quarantined += 1
            say(f"QUARANTINED  {name}: {e}")
            continue
        reason = None
        if len(rep.reconciliation) == 0 and not a.accept_unverified:
            reason = "The file has no Priva totals to check the records against, so it cannot be verified."
        elif len(rep.reconciliation) and not rep.reconciles:
            n = int((~rep.reconciliation["match"]).sum())
            reason = f"{n} of {len(rep.reconciliation)} totals in the file do not match the sum of its records."
        elif rep.period_start and rep.period_end and len(rep.records):
            d = rep.records["date"].astype(str)
            outside = ((d < rep.period_start) | (d > rep.period_end)).sum()
            if outside:
                reason = f"{outside} records are dated outside the file's stated period {rep.period_start} to {rep.period_end}."
        if reason:
            if not store.already_quarantined(sha):
                store.quarantine(name, sha, reason, preview=rep.records, report=rep)
            quarantined += 1
            say(f"QUARANTINED  {name}: {reason}")
            continue
        replaced, from_files = store.upsert(rep, dict(source_file=name, sha256=sha, period_start=rep.period_start,
                                                     period_end=rep.period_end, layout=rep.layout))
        msg = "; ".join(rep.notes[:3] + ([f"new fields kept: {', '.join(rep.unmapped)}"] if rep.unmapped else []))
        store.record_loaded(rep, replaced, from_files, msg)
        loaded += 1
        extra = f", replaced {replaced} rows from {', '.join(from_files)}" if replaced else ""
        say(f"LOADED       {name}: {rep.report_type}, {len(rep.records)} records, "
            f"{len(rep.reconciliation)} totals checked{extra}")
        if rep.unmapped:
            say(f"             new fields kept as-is (add to mappings.json to name them): {', '.join(rep.unmapped)}")

    say(f"\n{loaded} loaded, {quarantined} quarantined, {skipped} already loaded.")
    hist = store.history("performance")
    if not hist.empty:
        summary = write_outputs(enrich_performance(hist), a.out)
        say(f"Outputs rebuilt in {a.out}: {summary['records']:,} records, {summary['hours']:,.1f} hours, "
            f"{summary['first_date']} to {summary['last_date']}, {summary['review_records']:,} records to review.")
    for t in [t for t in mappings if t != "performance"]:
        h = store.history(t)
        if not h.empty:
            h.to_csv(os.path.join(a.out, f"{t}_records.csv"), index=False)
            say(f"{t}: {len(h):,} records in {a.out}/{t}_records.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
