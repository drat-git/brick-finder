import csv
import json
import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from brickfinder.build_catalog import build_catalog
from brickfinder.catalog import Catalog, unpack_catalog


def write_table(directory, name, header, rows):
    with (directory / f"{name}.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / "source"
        cls.source.mkdir()
        cls.output = cls.root / "output"
        write_table(cls.source, "sets", ["set_num", "name", "year", "theme_id", "num_parts", "img_url"], [
            ["10000-1", "Nested Robot", 2020, 22, 9, "https://cdn.rebrickable.com/media/sets/10000-1.jpg"],
            ["10001-1", "Child", 2020, 22, 2, ""],
            ["10002-1", "Cycle A", 2020, 22, 20, ""],
            ["10003-1", "Cycle B", 2020, 22, 20, ""],
            ["10004-1", "Missing figure", 2020, 22, 20, ""],
            ["10005-1", "Empty", 2020, 22, 0, ""],
            ["10006-1", "Wrong total", 2020, 22, 99, ""],
            ["20000-1", "Target", 2020, 23, 20, "http://untrusted.example/image.jpg"],
        ])
        write_table(cls.source, "themes", ["id", "name", "parent_id"], [[22, "Creator", ""], [23, "Creator child", 22]])
        write_table(cls.source, "parts", ["part_num", "name", "part_cat_id", "part_material"], [["a", "Brick", 1, "Plastic"], ["b", "Head", 1, "Plastic"]])
        write_table(cls.source, "colors", ["id", "name", "rgb"], [[1, "Red", "FF0000"], [2, "Blue", "0000FF"]])
        write_table(cls.source, "minifigs", ["fig_num", "name", "num_parts", "img_url"], [["fig-1", "Figure", 1, ""]])
        write_table(cls.source, "inventories", ["id", "version", "set_num"], [
            [1, 1, "10000-1"], [2, 2, "10000-1"], [3, 1, "10001-1"], [4, 1, "fig-1"],
            [5, 1, "10002-1"], [6, 1, "10003-1"], [7, 1, "10004-1"], [8, 1, "10005-1"],
            [9, 1, "10006-1"], [10, 1, "20000-1"],
        ])
        write_table(cls.source, "inventory_parts", ["inventory_id", "part_num", "color_id", "quantity", "is_spare", "img_url"], [
            [1, "missing-old-part", 1, 500, "False", ""],
            [2, "a", 1, 1, "False", ""], [2, "a", 1, 1, "False", ""], [2, "b", 2, 99, "True", ""],
            [3, "a", 1, 2, "False", ""], [4, "b", 2, 1, "False", ""],
            [9, "a", 1, 1, "False", ""], [10, "a", 1, 20, "False", ""],
        ])
        write_table(cls.source, "inventory_minifigs", ["inventory_id", "fig_num", "quantity"], [[2, "fig-1", 3], [7, "fig-missing", 1]])
        write_table(cls.source, "inventory_sets", ["inventory_id", "set_num", "quantity"], [[2, "10001-1", 2], [5, "10003-1", 1], [6, "10002-1", 1]])
        cls.info = build_catalog(cls.source, cls.output)
        cls.database = unpack_catalog(cls.output / "catalog.sqlite.gz", cls.root / "cache")
        cls.catalog = Catalog(cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.catalog.inventory.cache_clear()
        cls.temporary.cleanup()

    def test_latest_inventory_nested_quantities_duplicates_and_spares(self):
        self.assertEqual(self.catalog.inventory("10000-1"), {("a", 1): 6, ("b", 2): 3})
        self.assertEqual(self.catalog.sets["10000-1"].inventory_version, 2)
        self.assertEqual(sum(self.catalog.aggregate({"10000-1": 2}).values()), 18)

    def test_unsupported_inventories_are_reported_and_excluded(self):
        skipped = json.loads((self.output / "unsupported_sets.json").read_text())
        self.assertEqual({r["set_num"] for r in skipped}, {"10002-1", "10003-1", "10004-1", "10005-1", "10006-1"})
        self.assertTrue(any("cycle" in r["reason"] for r in skipped))
        self.assertNotIn("10002-1", self.catalog.sets)

    def test_candidate_scope_and_search(self):
        self.assertEqual([s.set_num for s in self.catalog.candidates], ["20000-1"])
        self.assertEqual(self.catalog.search("10000")[0].name, "Nested Robot")
        self.assertEqual(self.catalog.search("nested robot")[0].set_num, "10000-1")
        self.assertEqual(self.catalog.search("' OR 1=1"), [])
        self.assertEqual(self.catalog.search(" "), [])

    def test_database_is_read_only_and_unpack_is_reusable(self):
        with closing(self.catalog.connect()) as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM sets")
        self.assertEqual(unpack_catalog(self.output / "catalog.sqlite.gz", self.root / "cache"), self.database)

    def test_invalid_quantities_and_unknown_sets(self):
        for value in [0, -1, True, 1.5, "2"]:
            with self.assertRaises(ValueError):
                self.catalog.aggregate({"10000-1": value})
        with self.assertRaises(ValueError):
            self.catalog.aggregate({"missing": 1})

    def test_instruction_and_image_links(self):
        self.assertEqual(self.catalog.sets["10000-1"].instructions_url, "https://www.lego.com/en-us/service/building-instructions/10000")
        self.assertTrue(self.catalog.sets["10000-1"].safe_image_url)
        self.assertEqual(self.catalog.sets["20000-1"].safe_image_url, "")

    def test_missing_source_does_not_create_output(self):
        with self.assertRaisesRegex(ValueError, "Missing source files"):
            build_catalog(self.root / "absent", self.root / "bad_output")
        self.assertFalse((self.root / "bad_output").exists())


if __name__ == "__main__":
    unittest.main()
