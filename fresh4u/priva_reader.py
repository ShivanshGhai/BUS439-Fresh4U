"""
Generic reader for Priva report exports (pivot-table style .xlsx).

Priva exports nest their row dimensions (e.g. Date > Activity > Location > ...)
by putting each level's label in its own column, with subtotal rows in between.
Optionally one dimension (e.g. Location) is spread across columns, each column
group repeating the measures.

Nothing here relies on fixed column positions:
  * measures are found by their header text;
  * row-dimension NAMES come from the header row, in left-to-right order;
  * row-dimension COLUMNS are the columns that actually hold labels in data rows
    (Priva's header labels are sometimes offset from the data), matched by order;
  * a column dimension is detected when a measure name repeats across the header.

If the structure is not what we expect, read_report() raises ReportError with a
plain-language reason, so the caller can quarantine the file instead of guessing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field

import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PERIOD_RE = re.compile(r"Period:\s*(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})")


class ReportError(Exception):
    """The file cannot be read safely. The message says why, in plain words."""


@dataclass
class Report:
    file: str
    sha256: str
    report_type: str | None
    title: str | None
    period_start: str | None
    period_end: str | None
    exported_at: str | None
    layout: str                      # "rows" or "columns:<dimension>"
    records: pd.DataFrame            # one row per leaf record, canonical column names
    reconciliation: pd.DataFrame     # checks against Priva's own totals
    unmapped: list = field(default_factory=list)   # header names we kept but don't know
    notes: list = field(default_factory=list)

    @property
    def reconciles(self) -> bool:
        return len(self.reconciliation) > 0 and bool(self.reconciliation["match"].all())


def load_mappings(path: str | None = None) -> dict:
    with open(path or os.path.join(HERE, "mappings.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    return {k: v for k, v in m.items() if not k.startswith("_")}


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _strip_total(v) -> str:
    s = str(v).strip()
    return s[:-6].strip() if s.endswith(" Total") else s


def _snake(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _norm(s)).strip("_")


def _alias_index(mapping: dict) -> tuple[dict, dict]:
    dims = {_norm(a): canon for canon, al in mapping["dimensions"].items() for a in al}
    meas = {_norm(a): canon for canon, al in mapping["measures"].items() for a in al}
    return dims, meas


def _all_measure_aliases(mappings: dict) -> set:
    return {_norm(a) for m in mappings.values() for al in m["measures"].values() for a in al}


def _load_rows(path: str) -> list[tuple]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if len(wb.worksheets) != 1:
            # keep going with the first sheet, but the caller is told
            pass
        ws = wb.worksheets[0]
        rows = [tuple(r) for r in ws.iter_rows(values_only=True)]
        n_sheets = len(wb.worksheets)
    finally:
        wb.close()
    width = max((len(r) for r in rows), default=0)
    rows = [r + (None,) * (width - len(r)) for r in rows]
    return rows, n_sheets


def _find_measure_header(rows, measure_aliases) -> int:
    for i, r in enumerate(rows[:15]):
        if sum(1 for c in r if c is not None and _norm(c) in measure_aliases) >= 1:
            return i
    raise ReportError("No recognised measure column (e.g. 'Registered hours') in the first 15 rows. "
                      "This may be a report type we have no mapping for yet.")


def _choose_type(header_names: list[str], mappings: dict) -> tuple[str, dict]:
    best, best_score = None, -1
    for name, m in mappings.items():
        dims, meas = _alias_index(m)
        found = {dims.get(_norm(h)) or meas.get(_norm(h)) for h in header_names} - {None}
        if not set(m["required"]) <= found:
            continue
        score = len(found)
        if score > best_score:
            best, best_score = name, score
    if best is None:
        raise ReportError("Headers " + ", ".join(repr(h) for h in header_names) +
                          " do not contain the required fields of any known report type "
                          "(see mappings.json).")
    return best, mappings[best]


def read_report(path: str, mappings: dict | None = None) -> Report:
    mappings = mappings or load_mappings()
    fname = os.path.basename(path)
    sha = file_sha256(path)
    rows, n_sheets = _load_rows(path)
    notes = []
    if n_sheets > 1:
        notes.append(f"Workbook has {n_sheets} sheets; only the first was read.")
    if len(rows) < 5:
        raise ReportError("The sheet has fewer than 5 rows, so it is not a Priva report export.")

    all_meas = _all_measure_aliases(mappings)
    title_text = " ".join(str(c) for c in rows[0] if c is not None)
    pm = PERIOD_RE.search(title_text)
    title = next((str(c).strip() for c in rows[0] if c is not None), None)

    mh = _find_measure_header(rows, all_meas)
    hdr = rows[mh]
    meas_cols = [i for i, c in enumerate(hdr) if c is not None and _norm(c) in all_meas]
    first_meas = min(meas_cols)
    dim_names = [str(c).strip() for c in hdr[:first_meas] if c is not None]
    if not dim_names:
        raise ReportError("The header row has no dimension names (e.g. 'Date') before the measures.")

    # column dimension? (a measure name that repeats)
    meas_labels = [_norm(hdr[i]) for i in meas_cols]
    pivoted = len(set(meas_labels)) < len(meas_labels)
    col_dim_name = None
    col_value = {}
    if pivoted:
        if mh < 2:
            raise ReportError("Measures repeat across columns but there is no row above them naming the column groups.")
        vals_row = rows[mh - 1]
        name_row = rows[mh - 2]
        col_dim_name = next((str(c).strip() for c in name_row[first_meas:] if c is not None), None)
        if not col_dim_name:
            raise ReportError("Measures repeat across columns but the column dimension has no name.")
        cur = None
        for i in range(first_meas, len(hdr)):
            if vals_row[i] is not None:
                cur = str(vals_row[i]).strip()
            col_value[i] = cur
        if any(col_value[i] is None for i in meas_cols):
            raise ReportError("Some measure columns sit under no column-group label.")
    else:
        for i in meas_cols:
            col_value[i] = None

    report_type, mapping = _choose_type(dim_names + [str(hdr[i]).strip() for i in meas_cols] +
                                        ([col_dim_name] if col_dim_name else []), mappings)
    dim_alias, meas_alias = _alias_index(mapping)
    unmapped = []

    def canon_dim(n):
        c = dim_alias.get(_norm(n))
        if c is None:
            unmapped.append(n)
            return _snake(n)
        return c

    def canon_meas(n):
        c = meas_alias.get(_norm(n))
        if c is None:
            unmapped.append(n)
            return _snake(n)
        return c

    row_dims = [canon_dim(n) for n in dim_names]
    col_dim = canon_dim(col_dim_name) if col_dim_name else None
    meas_of = {i: canon_meas(hdr[i]) for i in meas_cols}
    if len(set(row_dims)) != len(row_dims):
        raise ReportError(f"Two header columns map to the same field: {dim_names}.")

    # ---- data rows ---------------------------------------------------------
    def is_header_like(r):
        labels = [str(c).strip() for c in r[:first_meas] if c is not None]
        return bool(labels) and labels[0] == dim_names[0] and len(labels) >= min(2, len(dim_names))

    body, grand = [], None
    for idx in range(mh + 1, len(rows)):
        r = rows[idx]
        if is_header_like(r):
            continue
        first = next((i for i in range(first_meas) if r[i] is not None), None)
        if first is None:
            # a row with only numbers and no label: Priva puts none of these in data
            if any(r[i] is not None for i in meas_cols):
                raise ReportError(f"Row {idx + 1} has values but no label.")
            continue
        if str(r[first]).strip() == "Grand Total":
            grand = (idx, r)
            break                      # everything after is footer
        body.append((idx, first, r))
    if not body:
        raise ReportError("No data rows found under the header.")
    if grand is None:
        notes.append("No 'Grand Total' row found; only per-group totals were checked.")

    label_cols = sorted({first for _, first, _ in body})
    if len(label_cols) != len(row_dims):
        raise ReportError(
            f"The header names {len(row_dims)} row dimensions ({', '.join(dim_names)}) "
            f"but data labels appear in {len(label_cols)} different columns. The layout is not one we can read safely.")
    level_of = {c: k for k, c in enumerate(label_cols)}
    leaf_level = len(label_cols) - 1

    def values(r):
        out = {}
        for i in meas_cols:
            v = r[i]
            if v is None or v == "":
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ReportError(f"Non-numeric value {v!r} in measure column '{hdr[i]}'.")
            out.setdefault(col_value[i], {})[meas_of[i]] = v
        return out

    recs, top_totals, ctx = [], [], {}
    for j, (idx, first, r) in enumerate(body):
        lvl = level_of[first]
        label = _strip_total(r[first])
        ctx = {k: v for k, v in ctx.items() if k < lvl}
        ctx[lvl] = label
        vals = values(r)
        if lvl == 0:
            top_totals.append((label, vals))
        nxt = level_of[body[j + 1][1]] if j + 1 < len(body) else -1
        if lvl == leaf_level or nxt <= lvl:
            base = {row_dims[k]: ctx.get(k) for k in range(len(row_dims))}
            if lvl != leaf_level:
                notes.append(f"Row {idx + 1}: '{label}' has no detail rows below it; kept as a record at the {row_dims[lvl]} level.")
            for grp, mv in vals.items():
                if pivoted and grp == "Grand Total":
                    continue
                rec = dict(base)
                if pivoted:
                    rec[col_dim] = grp
                rec.update(mv)
                rec["excel_row"] = idx + 1
                recs.append(rec)
    df = pd.DataFrame(recs)
    for c in list(dict.fromkeys(row_dims + ([col_dim] if col_dim else []) + list(meas_of.values()))):
        if c not in df:
            df[c] = pd.NA

    # ---- reconciliation against Priva's own totals -------------------------
    additive = [m for m in mapping.get("additive", []) if m in df.columns]
    checks = []

    def total_of(vals):
        return vals.get("Grand Total", {}) if pivoted else vals.get(None, {})

    top = row_dims[0]
    for label, vals in top_totals:
        tot = total_of(vals)
        sub = df[df[top] == label]
        for m in additive:
            if m not in tot and sub[m].notna().sum() == 0:
                continue
            got, exp = float(pd.to_numeric(sub[m], errors="coerce").sum()), float(tot.get(m, 0.0))
            checks.append(dict(level=top, key=label, measure=m, priva_total=exp, sum_of_records=got))
    if grand is not None:
        tot = total_of(values(grand[1]))
        for m in additive:
            if m in tot:
                got = float(pd.to_numeric(df[m], errors="coerce").sum())
                checks.append(dict(level="file", key="Grand Total", measure=m, priva_total=float(tot[m]), sum_of_records=got))
    rc = pd.DataFrame(checks, columns=["level", "key", "measure", "priva_total", "sum_of_records"])
    if len(rc):
        rc["diff"] = rc.sum_of_records - rc.priva_total
        rc["match"] = rc["diff"].abs() <= (1e-6 * rc.priva_total.abs()).clip(lower=1e-6)
    else:
        rc["diff"], rc["match"] = [], []

    exported = next((str(r[0]) for r in rows[-3:] if r[0] and re.match(r"\d{4}-\d{2}-\d{2} \d", str(r[0]))), None)
    return Report(file=fname, sha256=sha, report_type=report_type, title=title,
                  period_start=pm.group(1) if pm else None, period_end=pm.group(2) if pm else None,
                  exported_at=exported, layout=("columns:" + col_dim) if pivoted else "rows",
                  records=df, reconciliation=rc, unmapped=sorted(set(unmapped)), notes=notes)


def flatten_any(path: str) -> pd.DataFrame:
    """Best-effort flattening of an unknown report, for the quarantine preview.
    Builds a throwaway mapping from whatever headers are present."""
    rows, _ = _load_rows(path)
    for i, r in enumerate(rows[:15]):
        texts = [c for c in r if isinstance(c, str)]
        nums_below = sum(isinstance(c, (int, float)) for rr in rows[i + 1:i + 6] for c in rr)
        if texts and texts[0].strip() and nums_below:
            hdr = r
            break
    else:
        return pd.DataFrame()
    # guess: anything right of the last text-labelled data column is a measure
    names = [str(c).strip() for c in hdr if c is not None]
    fake = {"preview": {"dimensions": {}, "measures": {}, "required": [], "additive": []}}
    for n in names:
        fake["preview"]["measures"][_snake(n)] = [n]
    try:
        # treat the trailing numeric-looking headers as measures, leading ones as dims
        data_rows = rows[rows.index(hdr) + 1:]
        num_cols = {j for rr in data_rows for j, c in enumerate(rr) if isinstance(c, (int, float))}
        dims, meas = {}, {}
        for j, c in enumerate(hdr):
            if c is None:
                continue
            (meas if j in num_cols else dims)[_snake(c)] = [str(c).strip()]
        fake["preview"]["dimensions"], fake["preview"]["measures"] = dims, meas
        return read_report(path, fake).records
    except ReportError:
        return pd.DataFrame()
