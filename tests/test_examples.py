import unittest

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.coverage import OWNED_ONLY_CATEGORIES
from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.matching import recommend


class ExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog(unpack_catalog())

    def test_each_collection_offers_complete_builds_in_both_color_modes(self):
        for name, codes in EXAMPLE_COLLECTIONS.items():
            with self.subTest(example=name):
                self.assertIn(len(codes), (5, 6))
                self.assertEqual(len(set(codes)), len(codes))
                self.assertTrue(all(code in self.catalog.sets for code in codes))
                collection = dict.fromkeys(codes, 1)
                flexible = recommend(self.catalog, collection, "flexible")
                exact = recommend(self.catalog, collection, "exact")
                self.assertGreaterEqual(sum(m.complete for m in flexible), 2)
                self.assertGreaterEqual(sum(m.complete for m in exact), 1)
                # Each demo also shows complete builds that need color changes.
                self.assertGreaterEqual(sum(m.complete and m.exact_matched < m.required
                                            for m in flexible), 2)

    def test_collection_themes(self):
        families = {name: {self.catalog.sets[code].family for code in codes}
                    for name, codes in EXAMPLE_COLLECTIONS.items()}
        self.assertTrue(families["Example 1"] <= {"Super Heroes Marvel", "Super Heroes DC"})
        self.assertEqual(families["Example 2"], {"City"})
        self.assertGreaterEqual(len(families["Example 3"]), 4)

    def test_bundled_catalog_respects_coverage_rules(self):
        for lego_set in self.catalog.candidates:
            with self.subTest(code=lego_set.set_num):
                self.assertTrue(2000 <= lego_set.year <= 2026)
                self.assertTrue(20 <= lego_set.num_parts <= 1000)
                self.assertNotIn(lego_set.category, OWNED_ONLY_CATEGORIES | {"Database records"})
        for code in ("970009-1", "5003122-1"):
            self.assertEqual(self.catalog.sets[code].category, "Bulk parts and accessories")
            self.assertFalse(self.catalog.sets[code].candidate)
        self.assertNotIn("Build-a-Mini-2020", self.catalog.sets)


if __name__ == "__main__":
    unittest.main()
