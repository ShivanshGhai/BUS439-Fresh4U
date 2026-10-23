# Fresh4U Priva pipeline

Turns Priva report exports (.xlsx) into one verified, growing history and the analysis
tables the planner, coaching view and review list are built on.
Supersedes the one-off `Cleaned data/clean_priva.py` (same results, verified record-for-record).

Needs Python 3.10+ with `pandas` and `openpyxl`. Nothing else.

## Run it

From this folder:

```
python3 run.py --inbox "../Fresh4U Fall 2026"
```

Drop new exports into the inbox folder (any name) and run the same command again.
Only new files are read; the first full load of 14 files takes about 45 s, later runs a few seconds.
`--budget 30` stops after 30 s of reading (exit code 3 means "run again to continue").

## What happens to each file

1. **Read by header names**, never by column position. Moved columns, extra blank columns, or
   locations spread across columns are all handled. The report type is recognised from its headers
   using `fresh4u/mappings.json`.
2. **Checked against Priva's own totals.** Every daily subtotal and the Grand Total must equal the
   sum of the records underneath, for hours, result and area.
3. **Loaded or quarantined.**
   - Passes → added to `data/history/<report type>.csv`.
   - Fails → nothing changes; `data/quarantine/<file>.reason.txt` says why in plain words,
     and `.preview.csv` shows what could be read.
4. **Outputs rebuilt** in `outputs/`.

Safety rules:

| Situation | What the pipeline does |
|---|---|
| Same file loaded twice (even renamed) | Skipped: recognised by its contents (sha256) |
| A period re-exported after corrections in Priva | The new file replaces that period; never double-counted |
| New column in an export (e.g. Start time) | Kept automatically; named in the log so it can be added to `mappings.json` |
| Required field missing, totals don't add up, dates outside the stated period, unknown report type | Quarantined with the reason |
| Source files | Only ever read. Never moved, renamed or edited |

Everything loaded is listed in `data/ingest_log.csv` (file, hash, period, records, hours,
checks passed, rows replaced). Every total check is in `data/reconciliation.csv`.

## Outputs

| File | One row = | For |
|---|---|---|
| `labour_records_clean.csv` | one Priva registration | Master table with every flag and the Excel row it came from |
| `labour_daily_employee_location.csv` | employee × row × task × day | Analysis across all periods |
| `weekly_by_task.csv` | task × week | Planner inputs: hours, rows done, minutes per row, workers |
| `review_list.csv` | one suspicious registration, with a plain reason | Supervisor's weekly check (fix in Priva's Validation & Correction, re-export, re-run) |
| `data_quality_summary.csv` | one flag | How much time each issue touches |
| `<type>_records.csv` | one record | Other report types once they are mapped (e.g. `hours`) |

## Adding a new kind of report

1. Drop the export in the inbox and run. It will be quarantined with a preview of its headers.
2. Add or extend an entry in `fresh4u/mappings.json`: Priva's header text on the right, our name on the left,
   plus which fields are required and which measures add up.
3. Run again. The file loads with no code change.

The `hours` entry is a first guess at Priva's Hours report and will be confirmed on the first real export.

## Tests

```
python3 -m unittest discover -s tests -v
FRESH4U_INBOX="../Fresh4U Fall 2026" python3 -m unittest discover -s tests -v   # also the 14 real files
```

They cover the 14 real exports (record counts and total hours), moved columns, new fields,
missing fields, broken structure, tampered totals, duplicate loads, corrected re-exports,
dates outside the period and unknown reports.

## Assumptions to confirm with Fresh4U

- Rows 1001–1280 are House 1 and 2001–2280 House 2 (`house_inferred`).
- One full row is 144.5 m² (how Priva records it); "minutes per row" uses this.
- "Review" means a registration took 3× or more the task's median minutes per row.
- Registered hours may include breaks; the Hours report should settle this.
