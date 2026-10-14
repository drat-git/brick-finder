import unittest
from collections import Counter

from brickfinder.catalog import LegoSet
from brickfinder.matching import Match, color_change_rows, filter_matches, recommend, shortage_rows


class FakeCatalog:
    def __init__(self):
        self.sets = {
            "10000-1": LegoSet("10000-1", "Owned", 2020, "Creator", 4, "", 1, True),
            "10001-1": LegoSet("10001-1", "Target", 2020, "Creator", 3, "", 1, True),
            "10002-1": LegoSet("10002-1", "Other", 2020, "Creator", 3, "", 1, True),
        }
        self.candidates = tuple(self.sets.values())
        self.bags = {
            "10000-1": {("a", 1): 1, ("a", 2): 2, ("b", 1): 1},
            "10001-1": {("a", 1): 2, ("a", 3): 1},
            "10002-1": {("a", 1): 1, ("b", 1): 1, ("printed", 1): 1},
        }
        self.parts = {"a": "Brick", "b": "Plate", "printed": "Printed brick"}
        self.colors = {1: {"name": "Red"}, 2: {"name": "Blue"}, 3: {"name": "Green"}}

    def inventory(self, code):
        return self.bags[code]

    def candidate_inventories(self):
        return self.bags

    def aggregate(self, collection):
        available = Counter()
        for code, q in collection.items():
            for key, n in self.bags[code].items():
                available[key] += n * q
        return available


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.catalog = FakeCatalog()
        self.collection = {"10000-1": 1}

    def test_exact_requires_quantity_and_color(self):
        target = next(m for m in recommend(self.catalog, self.collection, "exact") if m.lego_set.set_num == "10001-1")
        self.assertEqual((target.matched, target.missing), (1, 2))
        self.assertEqual(sum(r["Missing"] for r in shortage_rows(self.catalog, self.collection, target)), 2)

    def test_flexible_does_not_double_count_available_colors(self):
        self.catalog.bags["10000-1"] = {("a", 2): 2}
        target = next(m for m in recommend(self.catalog, self.collection) if m.lego_set.set_num == "10001-1")
        self.assertEqual((target.matched, target.missing), (2, 1))
        changes = color_change_rows(self.catalog, self.collection, target)
        self.assertEqual(sum(r["Quantity"] for r in changes), 2)
        self.assertEqual(sum(r["Missing"] for r in shortage_rows(self.catalog, self.collection, target)), 1)

    def test_exact_colors_reserved_before_substitution(self):
        target = recommend(self.catalog, self.collection)[0]
        self.assertTrue(target.complete)
        changes = color_change_rows(self.catalog, self.collection, target)
        self.assertEqual(sum(r["Quantity"] for r in changes), 2)
        self.assertTrue(all(r["Use your color"] == "Blue" for r in changes))

    def test_printed_variants_do_not_substitute(self):
        other = next(m for m in recommend(self.catalog, self.collection) if m.lego_set.set_num == "10002-1")
        self.assertEqual(other.missing, 1)
        self.assertEqual(shortage_rows(self.catalog, self.collection, other)[0]["Part ID"], "printed")

    def test_duplicate_copies_increase_available_quantity(self):
        self.catalog.bags["10001-1"] = {("b", 1): 2}
        once = recommend(self.catalog, self.collection, "exact")
        twice = recommend(self.catalog, {"10000-1": 2}, "exact")
        self.assertFalse(next(m for m in once if m.lego_set.set_num == "10001-1").complete)
        self.assertTrue(next(m for m in twice if m.lego_set.set_num == "10001-1").complete)

    def test_owned_sets_are_excluded_and_results_are_independent(self):
        matches = recommend(self.catalog, self.collection)
        self.assertEqual(matches[0].lego_set.set_num, "10001-1")
        self.assertNotIn("10000-1", [m.lego_set.set_num for m in matches])
        self.assertEqual(matches[1].matched, 2)

    def test_ranking_and_filters(self):
        matches = recommend(self.catalog, self.collection)
        self.assertEqual(len(filter_matches(matches, 80, (1, 10))), 1)
        self.assertEqual(filter_matches(matches, 0, (4, 10)), [])
        self.catalog.bags["10002-1"] = dict(self.catalog.bags["10001-1"])
        self.assertEqual([m.lego_set.set_num for m in recommend(self.catalog, self.collection)], ["10001-1", "10002-1"])

    def test_partial_percent_never_displays_100(self):
        match = Match(self.catalog.sets["10001-1"], "exact", 9999, 10000, 9999)
        self.assertEqual(match.display_percent, "99.9%")
        self.assertEqual(match.exact_display_percent, "99.9%")
        self.assertFalse(match.complete)

    def test_empty_collection_and_invalid_mode(self):
        self.assertEqual(recommend(self.catalog, {}), [])
        with self.assertRaises(ValueError):
            recommend(self.catalog, self.collection, "unknown")


if __name__ == "__main__":
    unittest.main()
