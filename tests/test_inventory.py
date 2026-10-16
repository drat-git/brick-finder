import unittest
from copy import deepcopy

from brickfinder.inventory import (CollectionState, PartKey, available_inventory,
                                   inventory_sources, validate_collection)
from brickfinder.matching import recommend, shortage_rows, color_change_rows
from tests.test_matching import FakeCatalog


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.catalog = FakeCatalog()
        self.collection = CollectionState.from_counts(self.catalog, {"10000-1": 2})

    def test_duplicates_have_independent_missing_and_protection(self):
        a, b = self.collection.copies
        a.set_missing(self.catalog, PartKey("a", 2), 2)
        b.set_missing(self.catalog, PartKey("b", 1), 1)
        a.keep_assembled = True
        self.assertNotEqual(a.id, b.id)
        self.assertEqual(available_inventory(self.catalog, self.collection), {("a", 1): 2, ("a", 2): 2, ("b", 1): 1})
        self.assertEqual(available_inventory(self.catalog, self.collection, planner=True), {("a", 1): 1, ("a", 2): 2})
        self.assertEqual(self.collection.loose, {})
        a.set_missing(self.catalog, PartKey("a", 2), 0)
        self.assertNotIn(("a", 2), a.missing)

    def test_invalid_quantities_and_missing_above_capacity(self):
        copy = self.collection.copies[0]
        for invalid in (-1, 1.5, True, "2", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                copy.set_missing(self.catalog, PartKey("a", 1), invalid)
        with self.assertRaises(ValueError):
            copy.set_missing(self.catalog, PartKey("a", 1), 2)
        with self.assertRaises(ValueError):
            copy.set_missing(self.catalog, PartKey("printed", 1), 1)
        with self.assertRaises(ValueError):
            CollectionState.from_counts(self.catalog, {"10000-1": True})

    def test_loose_add_edit_remove_and_validate(self):
        key = PartKey("a", 1)
        self.collection.set_loose(self.catalog, key, 2, add=True)
        self.collection.set_loose(self.catalog, key, 3, add=True)
        self.assertEqual(self.collection.loose[key], 5)
        self.collection.set_loose(self.catalog, key, 1)
        self.assertEqual(self.collection.loose[key], 1)
        self.collection.set_loose(self.catalog, key, 0)
        self.assertFalse(self.collection.loose)
        for key, value in ((PartKey("unknown", 1), 1), (PartKey("a", 999), 1), (PartKey("a", 1), -1), (PartKey("a", 1), True)):
            with self.assertRaises(ValueError):
                self.collection.set_loose(self.catalog, key, value)

    def test_loose_only_and_protected_recommendations(self):
        loose = CollectionState(loose={PartKey("a", 1): 2, PartKey("a", 3): 1})
        match = next(m for m in recommend(self.catalog, loose, "exact") if m.lego_set.set_num == "10001-1")
        self.assertTrue(match.complete)
        for copy in self.collection.copies:
            copy.keep_assembled = True
        self.assertTrue(recommend(self.catalog, self.collection)[0].complete)
        self.assertFalse(available_inventory(self.catalog, self.collection, planner=True))

    def test_legacy_and_domain_agree_for_all_matching_views(self):
        legacy = {"10000-1": 2}
        for mode in ("exact", "flexible"):
            old = recommend(self.catalog, legacy, mode)
            new = recommend(self.catalog, self.collection, mode)
            self.assertEqual(old, new)
            for match in old:
                self.assertEqual(shortage_rows(self.catalog, legacy, match), shortage_rows(self.catalog, self.collection, match))
                self.assertEqual(color_change_rows(self.catalog, legacy, match), color_change_rows(self.catalog, self.collection, match))

    def test_obsolete_loaded_records_preserved_and_blocked(self):
        self.collection.copies[0].inventory_version = 999
        self.collection.copies[1].set_num = "removed-set"
        self.collection.loose[PartKey("removed-part", 1)] = 3
        loaded = CollectionState.from_payload(self.collection.payload())
        before = deepcopy(loaded.payload())
        self.assertGreaterEqual(len(validate_collection(self.catalog, loaded)), 3)
        with self.assertRaises(ValueError):
            inventory_sources(self.catalog, loaded)
        self.assertEqual(loaded.payload(), before)

    def test_snapshots_and_save_as_regenerate_all_ids(self):
        cloned = self.collection.save_as("Copy")
        self.assertNotEqual(cloned.id, self.collection.id)
        self.assertFalse(set(c.id for c in cloned.copies) & set(c.id for c in self.collection.copies))
        self.assertEqual(cloned.counts, self.collection.counts)
        self.assertNotEqual(self.collection.snapshot("exact"), self.collection.snapshot("flexible"))
        before = self.collection.snapshot()
        self.collection.copies[0].keep_assembled = True
        self.assertNotEqual(self.collection.snapshot(), before)
