"""Compare deterministic greedy plans with CP-SAT on the bundled catalog."""
import argparse
import json
import platform
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brickfinder.catalog import Catalog, LegoSet, unpack_catalog
from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.inventory import CollectionState
from brickfinder.matching import recommend
from brickfinder.planner import plan_build


def stable_collection(catalog, counts, name):
    collection = CollectionState.from_counts(catalog, counts, name)
    collection.id = str(uuid5(NAMESPACE_URL, name))
    for index, copy in enumerate(collection.copies):
        copy.id = str(uuid5(NAMESPACE_URL, f"{name}/{copy.set_num}/{index}"))
    return collection


def measure(catalog, collection, target, mode):
    greedy = plan_build(catalog, collection, target, mode, time_limit_seconds=0)
    optimized = plan_build(catalog, collection, target, mode)
    if optimized.status not in ("optimal", "feasible") or greedy.status not in ("optimal", "feasible"):
        raise RuntimeError(optimized.message + " " + greedy.message)
    return {"collection": collection.name, "target": target, "mode": mode,
            "greedy_copies": greedy.dismantling_count, "optimized_copies": optimized.dismantling_count,
            "greedy_seconds": round(greedy.elapsed_seconds, 6), "optimized_seconds": round(optimized.elapsed_seconds, 6),
            "substitutions": optimized.color_substitutions, "status": optimized.status}


class GreedyFailureCatalog:
    parts = {"x": "X", "y": "Y"}
    colors = {1: {"name": "Red"}}
    bags = {"A": {("x", 1): 1, ("y", 1): 1}, "B": {("x", 1): 2},
            "C": {("y", 1): 2}, "T": {("x", 1): 2, ("y", 1): 2}}
    sets = {s: LegoSet(s, s, 2020, "Fixture", sum(b.values()), "", 1, True) for s, b in bags.items()}
    def inventory(self, code):
        return self.bags[code]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--targets-per-mode", type=int, default=3)
    args = parser.parse_args()
    catalog = Catalog(unpack_catalog())
    rows = []
    for name, codes in EXAMPLE_COLLECTIONS.items():
        collection = stable_collection(catalog, dict.fromkeys(codes, 1), name)
        for mode in ("exact", "flexible"):
            matches = [m for m in recommend(catalog, collection, mode) if m.complete][:args.targets_per_mode]
            rows.extend(measure(catalog, collection, m.lego_set.set_num, mode) for m in matches)
    fixture = GreedyFailureCatalog()
    collection = stable_collection(fixture, dict.fromkeys("ABC", 1), "Greedy failure")
    # Ordered IDs make the tie select A first, reproducing the documented trap.
    for n, copy in enumerate(collection.copies, 1):
        copy.id = f"00000000-0000-0000-0000-{n:012d}"
    rows.append(measure(fixture, collection, "T", "exact"))
    report = {"python": platform.python_version(), "architecture": platform.machine(),
              "catalog_fingerprint": catalog.fingerprint, "time_limit_seconds": 5, "results": rows}
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output)


if __name__ == "__main__":
    main()
