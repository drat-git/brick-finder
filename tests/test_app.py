import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


class AppTests(unittest.TestCase):
    def test_example_matching_breakdown_filters_and_collection_edits(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(button(app, "Find builds").disabled)
        button(app, "Load Classic example").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["collection"], {"11021-1": 1, "11036-1": 1})
        button(app, "Find builds").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["results"][0].complete)
        self.assertEqual(app.session_state["results"][0].lego_set.set_num, "40014-1")
        app.checkbox[0].check().run()
        self.assertFalse(app.exception)
        self.assertGreater(len(app.dataframe), 0)
        self.assertTrue(any("Color" in c.label or "piece" in c.label for c in app.checkbox))
        app.slider(key="minimum").set_value(100).run()
        self.assertEqual(len(app.checkbox), 1)
        self.assertTrue(app.get("link_button"))
        app.radio[0].set_value("Exact colors").run()
        self.assertIsNone(app.session_state["results"])
        button(app, "Find builds").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.checkbox), 0)
        self.assertTrue(any("No matches" in message.value for message in app.info))
        app.number_input(key="qty_11021-1").set_value(2).run()
        self.assertEqual(app.session_state["collection"]["11021-1"], 2)
        self.assertIsNone(app.session_state["results"])
        app.button(key="remove_11021-1").click().run()
        self.assertNotIn("11021-1", app.session_state["collection"])
        button(app, "Clear collection").click().run()
        self.assertEqual(app.session_state["collection"], {})
        self.assertTrue(button(app, "Find builds").disabled)
        self.assertFalse(app.exception)

    def test_search_add_duplicate_and_no_results(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        app.text_input[0].set_value("31124").run()
        self.assertFalse(app.exception)
        button(app, "Add to collection").click().run()
        self.assertEqual(app.session_state["collection"], {"31124-1": 1})
        button(app, "Add to collection").click().run()
        self.assertEqual(app.session_state["collection"], {"31124-1": 2})
        self.assertEqual(app.number_input(key="qty_31124-1").value, 2)
        self.assertFalse(app.exception)
        app.text_input[0].set_value("no-such-set-xyz").run()
        self.assertTrue(any("No supported set" in message.value for message in app.info))
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
