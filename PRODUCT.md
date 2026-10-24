# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Fresh4U growers, greenhouse managers and supervisors** (The Fresh4U Group, BC greenhouse: tomatoes in H1/H2, strawberries in H3/H4). They plan crews for the season, set task paces, and fix Priva registrations before Tuesday payroll. Seen first at the Oct 27 site visit.
- **BUS 439 class and instructor** (Simon Fraser University, Fall 2026): the app carries the team's Nov 3 presentation, often on a projector, and must land in seconds.
Both audiences matter about equally (confirmed by Shivansh, 2026-10-24).

## Product Purpose
A labour planner built on Fresh4U's own Priva exports. It answers "how many people do we need each week of the year, is each task on track, and can this week's numbers be trusted?" Success: a manager trusts the answer enough to act on it (time TFW and contractor staffing, enter targets into Priva, fix the weekly list).

## Positioning
Every number is reconciled to Priva's own totals before it is shown (754 of 754 on the real exports), and the plan, the targets and the weekly check use the same rates, so the loop tightens each week. Priva today uses one blanket norm (13.5 min/row) for every task; the app exposes that and replaces it with per-task, per-season targets from history.

## Operating Context
Priva exports (R&D Analytics, Production, Hours, Production (tactical), Management Report) dropped in a folder or uploaded. Weekly rhythm: export → check → fix in Priva's Validation & Correction → payroll. Year rhythm: yield curve, crop changeovers, TFW crew plus contractors above it. Run locally with real data; synthetic demo data for anything public.

## Capabilities and Constraints
- Streamlit app (`streamlit_app.py`, styling and charts in `app_ui.py`, Altair charts). Tabs: Overview, Year plan, Targets, Weekly check, Data trust, More.
- Streamlit reruns the whole script on every control change: no entrance or count-up animation.
- Employee names are never shown or stored; people appear by employee number.
- Open questions for the grower (changeover length, clean-out hours, Aug–Sep crop work) are labelled "assumed" in the app.

## Brand Commitments
- The Fresh4U Group logo (`assets/fresh4u_group_logo.png`) stays. Its green (#00972D) and tomato red (#F91C1C) stay as brand colours; everything else in the visual system is open (confirmed 2026-10-24).
- Team credit: built by GLW BC for BUS 439, SFU.

## Evidence on Hand
Real Oct 23 exports (local only), bundled synthetic demo exports in `demo_data/`. No testimonials, customers or savings figures exist; none may be invented.

## Product Principles
1. Answer first, explain second: the headline number and what to do lead; method notes sit behind expanders.
2. Trust is shown, not claimed: reconciliation and evidence are visible next to every number.
3. Colour means something: red only for failed checks, amber for things to check, green for passed.
4. Same numbers everywhere: plan, targets and check share one set of rates.
