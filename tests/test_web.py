import unittest

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.web import FinderService


class RedesignServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = FinderService(Catalog(unpack_catalog()))
        cls.collection = dict.fromkeys(EXAMPLE_COLLECTIONS["Example 1"], 1)

    def test_default_results_are_complete_in_original_colors(self):
        response = self.service.result_data({"collection": self.collection})
        self.assertGreaterEqual(response["total"], 1)
        self.assertEqual(response["mode"], "exact")
        self.assertEqual(response["minimum"], 100)
        for match in response["matches"]:
            self.assertTrue(match["complete"])
            self.assertEqual(match["exact_matched"], match["required"])
            self.assertEqual(match["missing"], 0)

    def test_flexible_colors_pagination_and_partial_tab(self):
        flexible = self.service.result_data({"collection": self.collection, "mode": "flexible"})
        self.assertEqual(len(flexible["matches"]), min(18, flexible["total"]))
        self.assertTrue(any(m["exact_matched"] < m["required"] for m in flexible["matches"]))
        more = self.service.result_data({"collection": self.collection, "mode": "flexible", "page": 2})
        self.assertEqual(len(more["matches"]), min(36, more["total"]))
        self.assertEqual(more["matches"][:len(flexible["matches"])], flexible["matches"])
        partial = self.service.result_data({"collection": self.collection, "minimum": 80, "only_partial": True})
        self.assertGreater(partial["total"], 0)
        self.assertGreater(partial["ready_count"], 0)
        self.assertTrue(all(not m["complete"] and m["percent"] >= 80 for m in partial["matches"]))

    def test_piece_filters_and_sort_use_the_actual_matcher(self):
        response = self.service.result_data({"collection": self.collection, "mode": "flexible",
                                             "minimum": 50, "sizes": [100, 250], "sort": "pieces"})
        self.assertTrue(all(100 <= m["required"] <= 250 and m["percent"] >= 50 for m in response["matches"]))
        sizes = [m["required"] for m in response["matches"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_breakdowns_and_owned_quantity(self):
        owned = self.service.collection_data({"collection": {"31124-1": 2}})
        self.assertEqual(owned["copies"], 2)
        self.assertEqual(owned["pieces"], 318)
        detail = self.service.breakdown({"collection": self.collection, "code": "30162-1"})
        self.assertTrue(detail["match"]["complete"])
        self.assertEqual(detail["shortages"], [])
        self.assertEqual(detail["substitutions"], [])
        partial = self.service.breakdown({"collection": self.collection, "code": "40014-1"})
        self.assertEqual(sum(r["Missing"] for r in partial["shortages"]), partial["match"]["missing"])

    def test_invalid_requests_are_rejected(self):
        for body in (
            {"collection": []}, {"collection": {"not-a-set": 1}},
            {"collection": {"31124-1": True}}, {"collection": {"31124-1": 0}},
            {"collection": {"31124-1": 1.5}},
            {"collection": self.collection, "mode": "made-up"},
            {"collection": self.collection, "minimum": 101},
            {"collection": self.collection, "sizes": [10, 1000]},
            {"collection": self.collection, "sizes": [500, 100]},
            {"collection": self.collection, "page": 0},
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.service.result_data(body)
        with self.assertRaises(ValueError):
            self.service.breakdown({"collection": self.collection, "code": "76042-1"})

    def test_catalog_examples_and_empty_collection(self):
        data = self.service.bootstrap()
        self.assertEqual(len(data["examples"]), 3)
        self.assertTrue(all(len(example["sets"]) == 6 for example in data["examples"]))
        self.assertEqual(len(data["featured"]), 3)
        self.assertEqual(self.service.result_data({})["matches"], [])


if __name__ == "__main__":
    unittest.main()
