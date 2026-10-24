# Fresh4U labour planner

A prototype for **Fresh4U** (BUS 439, Simon Fraser University, Fall 2026 · team GLW BC).
It helps Fresh4U plan its labour with its own Priva data, as a loop:

1. **Year plan**: how many people each week, on which activities, for the whole farm and the whole year.
2. **Targets**: a pace per task and season, so "is this week on track?" has an answer (and Priva's own
   % performance can mean something).
3. **Weekly check**: before payroll, what to fix in Priva so pay is right and the plan learns from clean data.

Nothing is used until it adds up to Priva's own totals.

> **No client data is in this repository.** The demo runs on clearly labelled SYNTHETIC exports
> (`scripts/make_demo_data.py`, `scripts/make_demo_reports.py`). Real Priva exports stay on Fresh4U's and
> the team's computers; the app reads them from a local folder and never stores employee names.

## What it does

| Part | Question it answers | How |
|---|---|---|
| **Pipeline** (`run.py`, `fresh4u/`) | Can we trust the numbers? | Reads each Priva export by its headers, checks every record against Priva's own subtotals and grand totals, loads only files that pass, quarantines the rest with a plain reason. Re-exports replace their period; duplicates are ignored; names are replaced by employee numbers. |
| **Year plan** (`season_plan.py`) | How many people do we need each week of the year? | Harvest = forecast kg ÷ kg per hour; packing per tonne; tomato crop work from the weekly pattern Priva recorded; strawberry crop work, clean-out & planting, pest control and breaks. Rates pooled from every whole-site week loaded, each with its evidence. |
| **Targets** (`targets.py`) | Is each task on track? | Median minutes per row per task and season from history, with good/slow weeks; shown as the m²/h norm to enter in Priva; the grower's numbers replace ours. A week is compared with the other weeks of its season. |
| **Weekly check** (`weekly_check.py`) | What do supervisors fix before payroll? | Present-but-untagged time (Hours report), registrations taking 3×+ the usual time, locations that can't be right. One list, most hours first. |
| More: one-task planner, crew strengths, review list, trends | Last iteration's views | Kept for reference. Crew strengths are parked until we know how "Greenhouse Incentive" pay works. |

Reports read: R&D Analytics / Performance registrations, **Production** (hours by activity × location),
**Hours** (paid / present / registered per person), **Production (tactical)** (weekly yield) and the
**Management Report**. Others (Climate, Quality Evaluation, Reader scan log, Weighing log, Performance
summaries) are recognised and listed as "not used" with the reason.

On the real exports (25 files, Jan–Oct 2026 plus yield since 2025) every one of 754 Priva totals reconciles,
and the year plan reproduces the two recorded whole-site weeks to within 2–3% of total hours.

## Run it

```bash
pip install -r requirements.txt

# the app: demo data, a folder of exports on this computer, or uploads
streamlit run streamlit_app.py
#   then pick "Exports on this computer" and paste the folder (e.g. the 'Main project' folder),
#   or start it with FRESH4U_EXPORTS="/path/to/Main project" streamlit run streamlit_app.py

# the pipeline alone (originals are only read)
python3 run.py --inbox "path/to/Priva exports" --data data --out outputs --recursive

# tests
python3 -m unittest discover -s tests -v
FRESH4U_EXPORTS="/path/to/Main project" FRESH4U_INBOX="/path/to/Fresh4U Fall 2026" \
  python3 -m unittest discover -s tests -v          # also the real-data checks
```

In folder mode the history is kept in `data/` (git-ignored), so the first run takes about a minute and
later runs only read new exports. `demo_data/`, `data/` and `outputs/` folders inside the chosen folder are skipped.

## Repository layout

```
streamlit_app.py        the app: Overview, Year plan, Targets, Weekly check, Data trust, More
app_ui.py               brand theme, page styling and charts
run.py                  pipeline command
fresh4u/
  priva_reader.py       header-driven reader for Priva pivot exports + reconciliation + name removal
  special.py            readers for the yield report and the Management Report
  mappings.json         Priva header names -> our field names, per report type; reports not used, with reasons
  store.py              history, ingest log, quarantine
  enrich.py             flags, derived metrics, output tables
  season_plan.py        the 52-week year plan
  targets.py            per-task, per-season targets and "on track"
  weekly_check.py       the pre-payroll check
  planner.py, coaching.py   one-task planner and crew strengths
  app_data.py           runs the pipeline for the app (in memory, or on a local folder with a kept history)
  insights.py           plain-language interpretation for every view, written from the live numbers
scripts/                synthetic demo exports in Priva's layouts
demo_data/              the synthetic exports (one hand-edited on purpose, to show it is caught)
tests/                  regression, robustness, loop (plan / targets / check), app smoke test
docs/PIPELINE.md        pipeline details and safety rules
```

## Status and limits

- Prototype for client feedback, not a production system.
- Whole-site hours exist for two weeks so far (Jul 12–25 2026 and week 43 2025). The plan's rates come from
  them, so its check against them shows the pieces add up, not that the forecast is right. A year of weekly
  hours by activity would test it.
- Assumed, to confirm with the grower: how long a changeover takes, tomato clean-out hours, tomato crop work
  between August and the end of the season.
- Rows 1xxx–4xxx = Houses 1–4 is from Priva's locations; one row is 144.5 m² as Priva records it.
- Crew strengths measure speed only, for supervisors; they are not a basis for pay or discipline.
