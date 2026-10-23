import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fresh4u import coaching, planner  # noqa: E402


def records(speeds, weeks=6, task="Clipping", rows_per_week=10):
    """Synthetic enriched records: each worker does rows_per_week full rows a week at a fixed minutes-per-row."""
    out = []
    start = pd.Timestamp("2026-03-02")
    for w in range(weeks):
        ws = start + pd.Timedelta(weeks=w)
        for emp, mpr in speeds.items():
            for i in range(rows_per_week):
                out.append(dict(date=ws + pd.Timedelta(days=i % 5), week_start=ws, activity_name=task,
                                employee_id=emp, employee_group="TFW", hours=mpr / 60,
                                area_m2_clean=144.5, productivity_eligible=True))
    return pd.DataFrame(out)


class TestPlanner(unittest.TestCase):
    def test_plan_arithmetic(self):
        p = planner.plan(560, 60, 40)
        self.assertAlmostEqual(p["hours_needed"], 560.0)
        self.assertAlmostEqual(p["people_exact"], 14.0)
        self.assertEqual(p["people_rounded"], 14)
        self.assertEqual(planner.plan(561, 60, 40)["people_rounded"], 15)

    def test_plan_guards_bad_inputs(self):
        for args in [(0, 60, 40), (560, 0, 40), (560, 60, 0), (560, np.nan, 40)]:
            self.assertTrue(np.isnan(planner.plan(*args)["hours_needed"]))

    def test_pace_uses_only_previous_weeks(self):
        df = records({"A": 60, "B": 60}, weeks=3)
        df.loc[df.week_start == df.week_start.max(), "hours"] *= 10   # a crazy last week
        pace = planner.weekly_pace(df)
        # 2 workers x 10 rows = 20 rows/week, below the 50-row floor: no pace
        self.assertTrue(pace["min_per_row"].isna().all())
        df = records({e: 60 for e in "ABCDEF"}, weeks=3)
        last = df.week_start.max()
        df.loc[df.week_start == last, "hours"] *= 10
        pace = planner.weekly_pace(df)
        pf = planner.pace_for(pace, "Clipping", last)
        self.assertAlmostEqual(pf["min_per_row"], 60.0)
        self.assertEqual(pf["weeks_used"], 2)

    def test_plan_vs_actual(self):
        df = records({e: 60 for e in "ABCDEF"}, weeks=5)
        pva = planner.plan_vs_actual(planner.weekly_pace(df), "Clipping")
        self.assertTrue((pva["variance_hours"].abs() < 1e-9).all())


class TestCoaching(unittest.TestCase):
    def test_bands(self):
        df = records({"fast": 45, "mid1": 60, "mid2": 60, "mid3": 62, "slow": 80}, weeks=6)
        s = coaching.strengths(df, ramp_weeks=0).set_index("employee_id")
        self.assertEqual(s.loc["fast", "band"], "Strong")
        self.assertEqual(s.loc["mid1", "band"], "Typical")
        self.assertEqual(s.loc["slow", "band"], "Developing")

    def test_not_enough_data(self):
        df = records({"a": 60, "b": 60, "c": 60}, weeks=3)
        s = coaching.strengths(df, min_weeks=4)
        self.assertTrue((s["band"] == "Not enough data").all())

    def test_new_people_ramp_up_not_developing(self):
        df = records({"new": 80, "b": 60, "c": 60, "d": 60}, weeks=5)
        s = coaching.strengths(df, ramp_weeks=6).set_index("employee_id")
        self.assertEqual(s.loc["new", "band"], "Ramping up")

    def test_no_rank_column(self):
        s = coaching.strengths(records({"a": 50, "b": 60, "c": 70}, weeks=5))
        self.assertFalse(any("rank" in c for c in s.columns))


if __name__ == "__main__":
    unittest.main()
