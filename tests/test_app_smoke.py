"""
Runs streamlit_app.py from top to bottom with a stand-in for the streamlit module,
so every widget takes its default value. Catches errors in the app code itself
(it does not test layout). Uses the bundled synthetic demo data.
"""
import os
import runpy
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(FakeSt, name)


class StopApp(Exception):
    pass


class FakeSt:
    calls = []

    @staticmethod
    def _rec(name, *a, **k):
        FakeSt.calls.append((name, a, k))

    @staticmethod
    def cache_data(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

    @staticmethod
    def radio(label, options, **k):
        return options[k.get("index", 0)]

    @staticmethod
    def selectbox(label, options, index=0, **k):
        options = list(options)
        if "format_func" in k:
            k["format_func"](options[index])
        return options[index]

    @staticmethod
    def slider(label, lo, hi, value=None, **k):
        return value if value is not None else lo

    @staticmethod
    def number_input(label, min_value=None, max_value=None, value=None, **k):
        assert min_value is None or value >= min_value, (label, value)
        assert max_value is None or value <= max_value, (label, value)
        return value

    @staticmethod
    def file_uploader(*a, **k):
        return None

    @staticmethod
    def tabs(names):
        return [_Ctx() for _ in names]

    @staticmethod
    def columns(n):
        return [_Ctx() for _ in range(n if isinstance(n, int) else len(n))]

    @staticmethod
    def expander(*a, **k):
        return _Ctx()

    @staticmethod
    def stop():
        raise StopApp()

    @staticmethod
    def metric(label, value, *a, **k):
        assert "nan" not in str(value).lower(), (label, value)
        FakeSt._rec("metric", label, value)

    @staticmethod
    def dataframe(df, **k):
        assert len(df.columns) > 0
        FakeSt._rec("dataframe", len(df))

    @staticmethod
    def line_chart(df, x=None, y=None, color=None, **k):
        for c in (x, y, color):
            assert c is None or c in df.columns, (c, list(df.columns))
        FakeSt._rec("chart", len(df))

    bar_chart = line_chart

    @staticmethod
    def markdown(text, *a, **k):
        assert "nan" not in text.lower(), text
        FakeSt._rec("markdown", text)

    def __getattr__(self, name):
        return lambda *a, **k: FakeSt._rec(name, *a, **k)


def fake_module():
    m = types.ModuleType("streamlit")
    for name in dir(FakeSt):
        if not name.startswith("__"):
            setattr(m, name, getattr(FakeSt, name))
    for name in ["set_page_config", "title", "caption", "info", "warning", "error", "subheader", "code",
                 "download_button", "write"]:
        setattr(m, name, lambda *a, _n=name, **k: FakeSt._rec(_n, *a, **k))
    return m


class TestAppSmoke(unittest.TestCase):
    def test_app_runs_on_demo_data(self):
        sys.modules["streamlit"] = fake_module()
        FakeSt.calls = []
        try:
            runpy.run_path(os.path.join(ROOT, "streamlit_app.py"), run_name="__main__")
        except StopApp:
            self.fail("app stopped early on demo data")
        finally:
            del sys.modules["streamlit"]
        metrics = {a[0]: a[1] for n, a, k in FakeSt.calls if n == "metric"}
        self.assertEqual(metrics["Files loaded"], 3)
        self.assertEqual(metrics["Files quarantined"], 1)
        self.assertEqual(metrics["Totals that failed"], 0)
        self.assertGreater(int(metrics["People needed"]), 0)
        self.assertGreaterEqual(sum(1 for n, *_ in FakeSt.calls if n == "chart"), 3)


if __name__ == "__main__":
    unittest.main()
