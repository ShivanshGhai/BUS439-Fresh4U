"""
Runs streamlit_app.py from top to bottom with a stand-in for the streamlit module,
so every widget takes its default value. Catches errors in the app code itself and
checks every chart compiles to a valid Vega-Lite spec (it does not test layout).
Uses the bundled synthetic demo data. Needs altair (installed with streamlit).
"""
import os
import re
import runpy
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class StopApp(Exception):
    pass


class _Any:
    """Stands in for st.column_config and similar namespaces."""

    def __getattr__(self, name):
        return lambda *a, **k: dict(kind=name, args=a, **k)


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(FakeSt, name)


class FakeSt:
    calls = []
    column_config = _Any()

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
    def multiselect(label, options, default=None, **k):
        return list(default or [])

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
    def text_input(label, value="", **k):
        return value

    @staticmethod
    def data_editor(df, **k):
        assert len(df.columns) > 0
        for c in (k.get("column_config") or {}):
            assert c in df.columns, (c, list(df.columns))
        FakeSt._rec("data_editor", len(df))
        return df

    @staticmethod
    def tabs(names):
        return [_Ctx() for _ in names]

    @staticmethod
    def columns(n, **k):
        return [_Ctx() for _ in range(n if isinstance(n, int) else len(n))]

    @staticmethod
    def expander(*a, **k):
        return _Ctx()

    @staticmethod
    def container(*a, **k):
        return _Ctx()

    @staticmethod
    def stop():
        raise StopApp()

    @staticmethod
    def dataframe(df, **k):
        assert len(df.columns) > 0
        for c in (k.get("column_config") or {}):
            assert c in df.columns, (c, list(df.columns))
        FakeSt._rec("dataframe", len(df))

    @staticmethod
    def altair_chart(chart, **k):
        spec = chart.to_dict()  # raises if the chart is not valid Vega-Lite
        FakeSt._rec("chart", spec)

    @staticmethod
    def markdown(text, *a, **k):
        FakeSt._rec("markdown", text)


def fake_module():
    m = types.ModuleType("streamlit")
    for name in dir(FakeSt):
        if not name.startswith("__"):
            setattr(m, name, getattr(FakeSt, name))
    for name in ["set_page_config", "title", "caption", "info", "warning", "error", "subheader", "code",
                 "download_button", "write", "image", "divider"]:
        setattr(m, name, lambda *a, _n=name, **k: FakeSt._rec(_n, *a, **k))
    m.sidebar = _Ctx()
    return m


def _text(html):
    return re.sub(r"<[^>]+>", " ", html)


class TestAppSmoke(unittest.TestCase):
    def test_app_runs_on_demo_data(self):
        sys.modules["streamlit"] = fake_module()
        sys.modules.pop("app_ui", None)
        FakeSt.calls = []
        try:
            runpy.run_path(os.path.join(ROOT, "streamlit_app.py"), run_name="__main__")
        except StopApp:
            self.fail("app stopped early on demo data")
        finally:
            del sys.modules["streamlit"]
            sys.modules.pop("app_ui", None)
        page = " ".join(_text(a[0]) for n, a, k in FakeSt.calls if n == "markdown" and "<style>" not in a[0])
        page = re.sub(r"\s+", " ", page)
        self.assertIsNone(re.search(r"\bnan\b", page, flags=re.I), "a number printed as nan")
        self.assertIn("Built by GLW BC", page)
        m = re.search(r"Priva totals reconciled (\d+) / (\d+)", page)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), m.group(2), "every total in the loaded demo files should reconcile")
        self.assertGreater(int(m.group(1)), 200)
        for words in ["Busiest week", "Contractor person-weeks", "Present but untagged", "Targets",
                      "Recognised, not used"]:
            self.assertIn(words, page)
        self.assertIn("Files held back 1", page)
        people = re.search(r"People needed (\d+)", page)
        self.assertIsNotNone(people)
        self.assertGreater(int(people.group(1)), 0)
        self.assertGreaterEqual(page.count("What this means"), 8)
        self.assertGreaterEqual(sum(1 for n, *_ in FakeSt.calls if n == "chart"), 6)


if __name__ == "__main__":
    unittest.main()
