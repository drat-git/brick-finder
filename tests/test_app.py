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
        self.assertEqual(app.radio(key="matching_mode").value, "Exact colors")
        self.assertEqual(app.slider(key="minimum").value, 100)
        button(app, "Example 1").click().run()
        self.assertFalse(app.exception)
        expected_collection = dict.fromkeys(EXAMPLE_COLLECTIONS["Example 1"], 1)
        self.assertEqual(app.session_state["collection"], expected_collection)
        button(app, "Find builds").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["results"][0].complete)
        results_by_code = {m.lego_set.set_num: m for m in app.session_state["results"]}
        self.assertGreater(len(app.checkbox), 0)
        for checkbox in app.checkbox:
            code = checkbox.key.removeprefix("breakdown_exact_")
            match = results_by_code[code]
            self.assertEqual(match.mode, "exact")
            self.assertEqual(match.missing, 0)
            self.assertEqual(match.exact_matched, match.required)
        app.checkbox[0].check().run()
        self.assertTrue(any("No pieces are missing" in c.value for c in app.caption))
        self.assertFalse(any("Suggested color changes" in m.value for m in app.markdown))
        app.radio(key="matching_mode").set_value("Flexible colors").run()
        self.assertIsNone(app.session_state["results"])
        button(app, "Find builds").click().run()
        self.assertFalse(app.exception)
        complete_count = sum(m.complete for m in app.session_state["results"])
        self.assertGreaterEqual(complete_count, 2)
        color_example = next(m for m in app.session_state["results"][:20]
                             if m.exact_matched < m.required)
        table_count = len(app.dataframe)
        app.checkbox(key=f"breakdown_flexible_{color_example.lego_set.set_num}").check().run()
        self.assertFalse(app.exception)
        self.assertGreater(len(app.dataframe), table_count)
        self.assertTrue(any("Color" in c.label or "piece" in c.label for c in app.checkbox))
        self.assertEqual(len(app.checkbox), min(complete_count, 20))
        self.assertTrue(app.get("link_button"))
        app.slider(key="minimum").set_value(80).run()
        self.assertEqual(app.slider(key="minimum").value, 80)
        app.slider(key="minimum").set_value(100).run()
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

    def test_selected_set_details_show_the_right_set_without_changing_results(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        button(app, "Example 1").click().run()
        app.text_input[0].set_value("76042").run()
        button(app, "Add to collection").click().run()
        button(app, "Find builds").click().run()
        collection = dict(app.session_state["collection"])
        results = app.session_state["results"]
        for code, name, year, theme, pieces, copies in (
            ("6864-1", "Batmobile and the Two-Face Chase", 2012, "Super Heroes DC", "532", 1),
            ("76042-1", "The SHIELD Helicarrier", 2015, "Super Heroes Marvel", "2,996", 2),
        ):
            with self.subTest(code=code):
                app.button(key=f"details_{code}").click().run()
                self.assertFalse(app.exception)
                dialog = app.get("dialog")[0]
                self.assertTrue(dialog.proto.dialog.is_open)
                self.assertEqual(dialog.proto.dialog.title, "Set details")
                self.assertEqual(dialog.get("subheader")[0].value, name)
                self.assertEqual(dialog.get("imgs")[0].proto.imgs[0].url,
                                 f"https://cdn.rebrickable.com/media/sets/{code}.jpg")
                details = [m.value for m in dialog.get("markdown")]
                for field, value in (("Set number", code), ("Year released", year),
                                     ("Theme", theme), ("Pieces", pieces), ("Copies in collection", copies)):
                    self.assertIn(f"**{field}:** {value}", details)
                app.button(key="close_set_details").click().run()
                self.assertFalse(any(d.proto.dialog.is_open for d in app.get("dialog")))
                self.assertEqual(app.session_state["collection"], collection)
                self.assertIs(app.session_state["results"], results)
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
