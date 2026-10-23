"""
Tests for the Fresh4U Priva pipeline.  Standard library only:

    python3 -m unittest discover -s tests -v

Set FRESH4U_INBOX to the folder with the real exports to also run the
regression tests on them (they are skipped otherwise).
"""
import glob
import os
import shutil
import sys
import tempfile
import unittest

import openpyxl
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fresh4u.priva_reader import ReportError, read_report  # noqa: E402
import run  # noqa: E402

INBOX = os.environ.get("FRESH4U_INBOX", "")
REAL = sorted(glob.glob(os.path.join(INBOX, "R&D Analytics *.xlsx"))) if INBOX else []

# Expected values from the first verified run (Oct 22, 2026)
EXPECTED_RECORDS = {
    "20260118": 2769, "20260201": 2747, "20260215": 4210, "20260301": 3775, "20260315": 4717,
    "20260329": 6356, "20260412": 6092, "20260426": 6247, "20260510": 4916, "20260524": 5023,
    "20260607": 4680, "20260621": 5106, "20260705": 5928, "20260719": 5624,
}
EXPECTED_TOTAL_HOURS = 37206.095


# ---------------------------------------------------------------------------
# Small synthetic Priva-style exports
# ---------------------------------------------------------------------------
def write_pivot(path, period=("2026-09-01", "2026-09-02"), header=None, rows=None, title="Test report",
                grand=None, gap_cols=(1,), extra_top=None):
    """Writes a sheet shaped like a Priva pivot export.
    rows: list of (level, label, {measure: value}); levels are 0..n-1 for the header dims."""
    header = header or ["Date", "Activity", "Location", "Employee group", "Employee (short)"]
    measures = ["Registered hours", "Result", "Area"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ndim = len(header)
    # data label columns are spaced out like Priva's (with blank columns between)
    label_cols = []
    c = 1
    for i in range(ndim):
        label_cols.append(c)
        c += 1 + (1 if i in gap_cols else 0)
    first_meas = c + 1
    ws.cell(1, 1, title)
    ws.cell(1, first_meas + 1, f"Period: {period[0]} to {period[1]}")
    ws.cell(2, first_meas, "Grand Total")
    for i, h in enumerate(header):
        ws.cell(3, label_cols[i], h)
    for j, m in enumerate(measures):
        ws.cell(3, first_meas + j, m)
    r = 4
    for lvl, label, vals in rows:
        ws.cell(r, label_cols[lvl], label)
        for j, m in enumerate(measures):
            if m in vals:
                ws.cell(r, first_meas + j, vals[m])
        r += 1
    if grand is not None:
        ws.cell(r, 1, "Grand Total")
        for j, m in enumerate(measures):
            if m in grand:
                ws.cell(r, first_meas + j, grand[m])
        r += 1
    ws.cell(r, 1, "2026-09-03 10:00 AM")
    wb.save(path)


def simple_rows(day="2026-09-01", h=(1.0, 0.5)):
    t = sum(h)
    return [
        (0, f"{day} Total", {"Registered hours": t, "Result": 3.3 * 144.5 * len(h), "Area": 144.5 * len(h)}),
        (1, "Clipping (T)", {"Registered hours": t, "Result": 3.3 * 144.5 * len(h), "Area": 144.5 * len(h)}),
        (2, "Row 1001", {"Registered hours": h[0], "Result": 476.85, "Area": 144.5}),
        (3, "TFW", {"Registered hours": h[0], "Result": 476.85, "Area": 144.5}),
        (4, "2412", {"Registered hours": h[0], "Result": 476.85, "Area": 144.5}),
        (2, "Row 1002", {"Registered hours": h[1], "Result": 476.85, "Area": 144.5}),
        (3, "Contractor", {"Registered hours": h[1], "Result": 476.85, "Area": 144.5}),
        (4, "9925", {"Registered hours": h[1], "Result": 476.85, "Area": 144.5}),
    ]


def grand_of(rows):
    tops = [v for lvl, _, v in rows if lvl == 0]
    return {m: sum(t[m] for t in tops) for m in tops[0]}


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.inbox = os.path.join(self.dir, "inbox")
        os.makedirs(self.inbox)
        self.data = os.path.join(self.dir, "data")
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_pipeline(self):
        return run.main(["--inbox", self.inbox, "--data", self.data, "--out", self.out, "--quiet"])

    def log(self):
        return pd.read_csv(os.path.join(self.data, "ingest_log.csv"), dtype=str)

    def hist(self):
        p = os.path.join(self.data, "history", "performance.csv")
        return pd.read_csv(p, dtype={"employee_id": str}) if os.path.exists(p) else pd.DataFrame()


# ---------------------------------------------------------------------------
class TestReader(Tmp):
    def test_basic_file_reads_and_reconciles(self):
        rows = simple_rows()
        p = os.path.join(self.inbox, "a.xlsx")
        write_pivot(p, rows=rows, grand=grand_of(rows))
        r = read_report(p)
        self.assertEqual(r.report_type, "performance")
        self.assertEqual(len(r.records), 2)
        self.assertAlmostEqual(r.records.hours.sum(), 1.5)
        self.assertTrue(r.reconciles)
        self.assertEqual(set(r.records.employee_id), {"2412", "9925"})
        self.assertEqual(set(r.records.date), {"2026-09-01"})

    def test_columns_moved_and_header_offset(self):
        """Different spacing between columns must not matter."""
        rows = simple_rows()
        p = os.path.join(self.inbox, "b.xlsx")
        write_pivot(p, rows=rows, grand=grand_of(rows), gap_cols=(0, 2, 3))
        r = read_report(p)
        self.assertAlmostEqual(r.records.hours.sum(), 1.5)
        self.assertTrue(r.reconciles)

    def test_extra_dimension_is_kept(self):
        """A new field in the export (e.g. Start time) comes through without code changes."""
        rows = simple_rows()
        rows2 = []
        for lvl, lab, v in rows:
            rows2.append((lvl, lab, v))
            if lvl == 4:
                rows2.append((5, "07:30:00", v))
        p = os.path.join(self.inbox, "c.xlsx")
        write_pivot(p, header=["Date", "Activity", "Location", "Employee group", "Employee (short)", "Start time"],
                    rows=rows2, grand=grand_of(rows))
        r = read_report(p)
        self.assertIn("start_time", r.records)
        self.assertEqual(r.records.start_time.tolist(), ["07:30:00", "07:30:00"])
        self.assertTrue(r.reconciles)

    def test_unknown_dimension_kept_and_reported(self):
        rows = simple_rows()
        p = os.path.join(self.inbox, "d.xlsx")
        write_pivot(p, header=["Date", "Activity", "Crop variety", "Employee group", "Employee (short)"],
                    rows=rows, grand=grand_of(rows))
        r = read_report(p)
        self.assertIn("crop_variety", r.records)
        self.assertEqual(r.unmapped, ["Crop variety"])

    def test_report_without_required_fields_is_refused(self):
        rows = simple_rows()
        p = os.path.join(self.inbox, "e.xlsx")
        write_pivot(p, header=["Date", "Activity", "Location", "Employee group", "Crew"], rows=rows,
                    grand=grand_of(rows))
        with self.assertRaises(ReportError):
            read_report(p)

    def test_mismatched_structure_is_refused(self):
        """Header names 5 dimensions but data uses 4 columns."""
        rows = [(lvl, lab, v) for lvl, lab, v in simple_rows() if lvl != 3]
        rows = [(lvl if lvl < 3 else 3, lab, v) for lvl, lab, v in rows]
        p = os.path.join(self.inbox, "f.xlsx")
        write_pivot(p, rows=rows, grand=grand_of(rows))
        with self.assertRaises(ReportError):
            read_report(p)

    def test_not_a_report(self):
        p = os.path.join(self.inbox, "g.xlsx")
        wb = openpyxl.Workbook()
        wb.active["A1"] = "Shopping list"
        wb.active["A2"] = "tomatoes"
        wb.save(p)
        with self.assertRaises(ReportError):
            read_report(p)


class TestPipeline(Tmp):
    def test_tampered_totals_are_quarantined_and_history_untouched(self):
        rows = simple_rows()
        good = os.path.join(self.inbox, "good.xlsx")
        write_pivot(good, rows=rows, grand=grand_of(rows))
        self.run_pipeline()
        before = self.hist().hours.sum()
        rows_bad = [(lvl, lab, dict(v, **({"Registered hours": 9.0} if lab == "2412" else {})))
                    for lvl, lab, v in simple_rows(day="2026-09-02")]
        bad = os.path.join(self.inbox, "bad.xlsx")
        write_pivot(bad, rows=rows_bad, grand=grand_of(rows_bad), period=("2026-09-02", "2026-09-02"))
        self.run_pipeline()
        self.assertAlmostEqual(self.hist().hours.sum(), before)
        self.assertTrue(os.path.exists(os.path.join(self.data, "quarantine", "bad.reason.txt")))
        lg = self.log()
        self.assertEqual(lg[lg.file == "bad.xlsx"].status.tolist(), ["quarantined"])

    def test_same_file_twice_is_not_double_counted(self):
        rows = simple_rows()
        p = os.path.join(self.inbox, "a.xlsx")
        write_pivot(p, rows=rows, grand=grand_of(rows))
        self.run_pipeline()
        shutil.copy(p, os.path.join(self.inbox, "a copy.xlsx"))
        self.run_pipeline()
        self.assertAlmostEqual(self.hist().hours.sum(), 1.5)

    def test_reexport_of_same_period_replaces_it(self):
        rows = simple_rows(h=(1.0, 0.5))
        write_pivot(os.path.join(self.inbox, "week.xlsx"), rows=rows, grand=grand_of(rows))
        self.run_pipeline()
        rows2 = simple_rows(h=(1.0, 0.75))      # supervisor corrected a registration in Priva
        write_pivot(os.path.join(self.inbox, "week corrected.xlsx"), rows=rows2, grand=grand_of(rows2))
        self.run_pipeline()
        h = self.hist()
        self.assertAlmostEqual(h.hours.sum(), 1.75)
        self.assertEqual(set(h.source_file), {"week corrected.xlsx"})

    def test_new_period_appends(self):
        r1 = simple_rows("2026-09-01")
        write_pivot(os.path.join(self.inbox, "w1.xlsx"), rows=r1, grand=grand_of(r1), period=("2026-09-01", "2026-09-01"))
        r2 = simple_rows("2026-09-08")
        write_pivot(os.path.join(self.inbox, "w2.xlsx"), rows=r2, grand=grand_of(r2), period=("2026-09-08", "2026-09-08"))
        self.run_pipeline()
        self.assertAlmostEqual(self.hist().hours.sum(), 3.0)
        self.assertTrue(os.path.exists(os.path.join(self.out, "labour_records_clean.csv")))

    def test_dates_outside_period_are_quarantined(self):
        rows = simple_rows("2026-10-15")
        write_pivot(os.path.join(self.inbox, "x.xlsx"), rows=rows, grand=grand_of(rows), period=("2026-09-01", "2026-09-14"))
        self.run_pipeline()
        self.assertTrue(self.hist().empty)
        self.assertEqual(self.log().status.tolist(), ["quarantined"])

    def test_unknown_report_is_quarantined_with_preview(self):
        p = os.path.join(self.inbox, "mystery.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "Mystery report"
        ws["A3"], ws["C3"], ws["E3"] = "Date", "Crate", "Kilograms"
        ws["A4"], ws["E4"] = "2026-09-01 Total", 10
        ws["C5"], ws["E5"] = "Crate 7", 10
        ws["A6"], ws["E6"] = "Grand Total", 10
        wb.save(p)
        self.run_pipeline()
        self.assertTrue(os.path.exists(os.path.join(self.data, "quarantine", "mystery.reason.txt")))
        self.assertTrue(self.hist().empty)


@unittest.skipUnless(REAL, "set FRESH4U_INBOX to the folder of real exports")
class TestRealExports(unittest.TestCase):
    def test_every_real_file_reconciles(self):
        total = 0.0
        for f in REAL:
            r = read_report(f)
            key = os.path.basename(f).split()[-1][:8]
            self.assertTrue(r.reconciles, f)
            self.assertEqual(r.report_type, "performance", f)
            if key in EXPECTED_RECORDS:
                self.assertEqual(len(r.records), EXPECTED_RECORDS[key], f)
            total += r.records.hours.sum()
        if len(REAL) == 14:
            self.assertAlmostEqual(total, EXPECTED_TOTAL_HOURS, places=3)

    def test_inserting_columns_into_a_real_file_changes_nothing(self):
        src = REAL[0]
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "shifted.xlsx")
            wb = openpyxl.load_workbook(src)
            ws = wb.worksheets[0]
            ws.insert_cols(2, 2)          # two blank columns inside the label area
            ws.insert_cols(ws.max_column - 1, 1)   # and one between measure columns
            wb.save(p)
            a, b = read_report(src), read_report(p)
            self.assertEqual(len(a.records), len(b.records))
            self.assertAlmostEqual(a.records.hours.sum(), b.records.hours.sum(), places=6)
            self.assertTrue(b.reconciles)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
