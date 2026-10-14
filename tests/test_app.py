import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from brickfinder.examples import EXAMPLE_COLLECTIONS

ROOT = Path(__file__).resolve().parents[1]


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


class AppTests(unittest.TestCase):
    def test_example_matching_breakdown_filters_and_collection_edits(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(button(app, "Find builds").disabled)
        button(app, "Example 1").click().run()
        self.assertFalse(app.exception)
        expected_collection = dict.fromkeys(EXAMPLE_COLLECTIONS["Example 1"], 1)
        self.assertEqual(app.session_state["collection"], expected_collection)
        button(app, "Find builds").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["results"][0].complete)
        complete_count = sum(m.complete for m in app.session_state["results"])
        self.assertGreaterEqual(complete_count, 2)
        color_example = next(m for m in app.session_state["results"][:20]
                             if m.exact_matched < m.required)
        table_count = len(app.dataframe)
        app.checkbox(key=f"breakdown_flexible_{color_example.lego_set.set_num}").check().run()
        self.assertFalse(app.exception)
        self.assertGreater(len(app.dataframe), table_count)
        self.assertTrue(any("Color" in c.label or "piece" in c.label for c in app.checkbox))
        app.slider(key="minimum").set_value(100).run()
        self.assertEqual(len(app.checkbox), min(complete_count, 20))
        self.assertTrue(app.get("link_button"))
        app.radio[0].set_value("Exact colors").run()
        self.assertIsNone(app.session_state["results"])
        button(app, "Find builds").click().run()
        self.assertFalse(app.exception)
        self.assertGreaterEqual(len(app.checkbox), 1)
        self.assertTrue(app.session_state["results"][0].complete)
        app.slider(key="sizes").set_value((1000, 1000)).run()
        self.assertEqual(len(app.checkbox), 0)
        self.assertTrue(any("No matches" in message.value for message in app.info))
        app.slider(key="sizes").set_value((20, 1000)).run()
        app.text_input[0].set_value("76042").run()
        button(app, "Add to collection").click().run()
        self.assertEqual(app.session_state["collection"]["76042-1"], 2)
        self.assertIsNone(app.session_state["results"])
        app.button(key="remove_76042-1").click().run()
        expected_collection.pop("76042-1")
        self.assertEqual(app.session_state["collection"], expected_collection)
        button(app, "Clear collection").click().run()
        self.assertEqual(app.session_state["collection"], expected_collection)
        button(app, "Cancel").click().run()
        self.assertEqual(app.session_state["collection"], expected_collection)
        button(app, "Clear collection").click().run()
        button(app, "Yes, clear collection").click().run()
        self.assertEqual(app.session_state["collection"], {})
        self.assertTrue(button(app, "Find builds").disabled)
        self.assertFalse(app.exception)

    def test_examples_replace_the_collection_and_invalidate_results(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        for name, codes in EXAMPLE_COLLECTIONS.items():
            with self.subTest(example=name):
                button(app, name).click().run()
                self.assertEqual(app.session_state["collection"], dict.fromkeys(codes, 1))
                self.assertIsNone(app.session_state["results"])
                button(app, "Find builds").click().run()
                self.assertTrue(app.session_state["results"][0].complete)
                self.assertFalse(app.exception)

    def test_search_add_duplicate_and_no_results(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        app.text_input[0].set_value("31124").run()
        self.assertFalse(app.exception)
        button(app, "Add to collection").click().run()
        self.assertEqual(app.session_state["collection"], {"31124-1": 1})
        self.assertEqual(app.text_input[0].value, "")
        self.assertFalse(app.number_input)
        self.assertFalse(any('class="copy-count"' in m.value for m in app.markdown))
        self.assertFalse(any("pieces per copy" in c.value for c in app.caption))
        app.text_input[0].set_value("31124").run()
        button(app, "Add to collection").click().run()
        self.assertEqual(app.session_state["collection"], {"31124-1": 2})
        self.assertFalse(app.number_input)
        self.assertTrue(any('class="copy-count">x2</span>' in m.value for m in app.markdown))
        self.assertFalse(app.exception)
        self.assertFalse(app.warning)
        app.text_input[0].set_value("no-such-set-xyz").run()
        self.assertTrue(any("No supported set" in message.value for message in app.info))
        self.assertFalse(app.exception)

    def test_coverage_policy_and_owned_only_parts_pack(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        self.assertTrue(any("Owned sets have no year or piece-count limits" in m.value for m in app.markdown))
        self.assertTrue(any("without a length restriction" in m.value for m in app.markdown))
        self.assertTrue(any("Category coverage" in m.value for m in app.markdown))
        app.text_input[0].set_value("10003-1").run()
        self.assertTrue(any("Owned sets only" in c.value for c in app.caption))
        button(app, "Add to collection").click().run()
        self.assertEqual(app.session_state["collection"], {"10003-1": 1})
        self.assertTrue(any("Bulk parts and accessories" in c.value for c in app.caption))
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
