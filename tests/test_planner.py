import itertools
import random
import unittest
from collections import Counter
from copy import deepcopy
from unittest.mock import patch
from uuid import UUID

from ortools.sat.python import cp_model

from brickfinder.catalog import LegoSet
from brickfinder.inventory import CollectionState, inventory_sources
from brickfinder.matching import by_part, matched_quantity
from brickfinder.planner import Allocation, inventory_snapshot, plan_build, validate_allocations
from tests.test_matching import FakeCatalog


def catalog_for(bags):
    c = FakeCatalog()
    c.bags = bags
    c.sets = {s: LegoSet(s, s, 2020, "Creator", sum(b.values()), "", 1, True) for s, b in bags.items()}
    c.candidates = tuple(c.sets.values())
    return c


class PlannerTests(unittest.TestCase):
    def test_greedy_failure_is_optimized_to_two_copies(self):
        c = catalog_for({"A": {("a", 1): 1, ("b", 1): 1}, "B": {("a", 1): 2},
                         "C": {("b", 1): 2}, "T": {("a", 1): 2, ("b", 1): 2}})
        collection = CollectionState.from_counts(c, dict.fromkeys("ABC", 1))
        for n, copy in enumerate(collection.copies, 1):
            copy.id = str(UUID(int=n))
        before = deepcopy(collection.payload())
        result = plan_build(c, collection, "T", "exact")
        self.assertEqual(result.status, "optimal", result.message)
        self.assertEqual(result.greedy_copy_count, 3)
        self.assertEqual(result.dismantling_count, 2)
        self.assertEqual(result.selected_copy_ids, [collection.copies[1].id, collection.copies[2].id])
        self.assertEqual(collection.payload(), before)

    def test_duplicate_copies_and_loose_only_zero_cost(self):
        c = catalog_for({"A": {("a", 1): 1}, "T": {("a", 1): 2}})
        collection = CollectionState.from_counts(c, {"A": 2})
        result = plan_build(c, collection, "T", "exact")
        self.assertEqual(result.dismantling_count, 2)
        collection.loose["a", 1] = 2
        result = plan_build(c, collection, "T", "exact")
        self.assertEqual(result.status, "optimal")
        self.assertEqual(result.dismantling_count, 0)
        self.assertTrue(all(a.source_id == "loose" for a in result.allocations))

    def test_protected_shortages_and_printed_parts(self):
        c = catalog_for({"A": {("a", 1): 1}, "B": {("printed", 1): 1}, "T": {("a", 1): 1, ("printed", 1): 2}})
        collection = CollectionState.from_counts(c, {"A": 1, "B": 1})
        collection.copies[0].keep_assembled = True
        result = plan_build(c, collection, "T", "flexible")
        self.assertEqual(result.status, "insufficient inventory")
        shortages = {s.part_id: s for s in result.shortages}
        self.assertEqual(shortages["a"].protected_quantity, 1)
        self.assertEqual(shortages["printed"].protected_quantity, 0)
        self.assertFalse(result.allocations)

    def test_flexible_lexicographic_colors_and_exact_reservation(self):
        c = catalog_for({"A": {("a", 2): 3}, "B": {("a", 1): 2, ("a", 3): 1},
                         "T": {("a", 1): 2, ("a", 3): 1}})
        collection = CollectionState.from_counts(c, {"A": 1, "B": 1})
        result = plan_build(c, collection, "T", "flexible")
        self.assertEqual(result.dismantling_count, 1)
        self.assertEqual(result.color_substitutions, 0)
        self.assertEqual(result.selected_copy_ids, [collection.copies[1].id])
        collection.copies.pop()
        self.assertEqual(plan_build(c, collection, "T", "exact").status, "insufficient inventory")
        self.assertEqual(plan_build(c, collection, "T", "flexible").color_substitutions, 3)
        collection.loose = {("a", 1): 2, ("a", 2): 1}
        result = plan_build(c, collection, "T", "flexible")
        self.assertEqual((result.dismantling_count, result.color_substitutions), (0, 1))

    def test_validator_rejects_double_counting_and_incomplete_demand(self):
        required, sources = {("a", 1): 2}, {"loose": {("a", 2): 1}}
        with self.assertRaises(ValueError):
            validate_allocations(required, sources, [Allocation("a", 1, 2, 2, "loose")], [], "flexible")
        with self.assertRaises(ValueError):
            validate_allocations(required, sources, [Allocation("a", 1, 2, 1, "loose")], [], "flexible")

    def test_timeout_unknown_and_feasible_never_claim_minimum(self):
        c = catalog_for({"A": {("a", 1): 2}, "T": {("a", 1): 2}})
        collection = CollectionState.from_counts(c, {"A": 1})
        for budget in (0, 1e-9):
            result = plan_build(c, collection, "T", "exact", budget)
            self.assertEqual(result.status, "feasible")
            self.assertFalse(result.minimum_proven)
            self.assertIn("minimum not proven", result.message)
        with patch("brickfinder.planner.cp_model.CpSolver.solve", return_value=cp_model.UNKNOWN):
            self.assertEqual(plan_build(c, collection, "T", "exact").status, "feasible")
        original = cp_model.CpSolver.solve
        def feasible(solver, model):
            original(solver, model)
            return cp_model.FEASIBLE
        with patch.object(cp_model.CpSolver, "solve", feasible):
            self.assertFalse(plan_build(c, collection, "T", "exact").minimum_proven)

    def test_generated_cases_match_exhaustive_lexicographic_optimum(self):
        rng = random.Random(42)
        keys = [(p, color) for p in ("a", "b", "printed") for color in (1, 2)]
        for case in range(40):
            bags = {str(i): {k: rng.randint(1, 3) for k in keys if rng.random() < .5} for i in range(5)}
            bags["T"] = {k: rng.randint(1, 3) for k in keys if rng.random() < .5} or {("a", 1): 1}
            c = catalog_for(bags)
            collection = CollectionState.from_counts(c, dict.fromkeys(map(str, range(5)), 1))
            collection.loose = {k: 1 for k in keys if rng.random() < .25}
            collection.copies[0].keep_assembled = case % 3 == 0
            for mode in ("exact", "flexible"):
                with self.subTest(case=case, mode=mode):
                    sources = inventory_sources(c, collection, planner=True)
                    copies = [s for s in sources if s != "loose"]
                    best = None
                    required = bags["T"]
                    total = sum(required.values())
                    for n in range(len(copies) + 1):
                        for ids in itertools.combinations(copies, n):
                            available = Counter(sources["loose"])
                            for id in ids:
                                available.update(sources[id])
                            coverage = matched_quantity(available, required) if mode == "exact" else matched_quantity(by_part(available), by_part(required))
                            if coverage == total:
                                objective = (n, total - matched_quantity(available, required))
                                best = min(best, objective) if best is not None else objective
                        if best is not None:
                            break
                    result = plan_build(c, collection, "T", mode)
                    if best is None:
                        self.assertEqual(result.status, "insufficient inventory")
                    else:
                        self.assertEqual(result.status, "optimal", result.message)
                        self.assertEqual((result.dismantling_count, result.color_substitutions), best)
                        validate_allocations(required, sources, result.allocations, result.selected_copy_ids, mode)

    def test_invalid_inventory_or_mode_reports_error(self):
        c = FakeCatalog()
        collection = CollectionState.from_counts(c, {"10000-1": 1})
        self.assertEqual(plan_build(c, collection, "10001-1", "bad").status, "error")
        collection.copies[0].missing["a", 1] = 50
        self.assertEqual(plan_build(c, collection, "10001-1", "exact").status, "error")

    def test_plan_identity_includes_current_catalog_inventory_and_color_mode(self):
        c = catalog_for({"A": {("a", 1): 2}, "T": {("a", 1): 2}})
        collection = CollectionState.from_counts(c, {"A": 1})
        c.fingerprint = "first-catalog"
        plan = plan_build(c, collection, "T", "exact")
        self.assertEqual(plan.inventory_snapshot, inventory_snapshot(c, collection, "exact"))
        self.assertNotEqual(plan.inventory_snapshot, inventory_snapshot(c, collection, "flexible"))
        c.fingerprint = "changed-catalog"
        self.assertNotEqual(plan.inventory_snapshot, inventory_snapshot(c, collection, "exact"))
