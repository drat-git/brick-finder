"""Reproduce example-collection results and timing without opening the UI."""

import argparse
import json
import platform
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.matching import recommend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    began = perf_counter()
    catalog = Catalog(unpack_catalog())
    report = {"python": platform.python_version(), "architecture": platform.machine(),
              "candidate_sets": len(catalog.candidates), "catalog_load_seconds": round(perf_counter() - began, 4),
              "examples": []}
    for name, codes in EXAMPLE_COLLECTIONS.items():
        for mode in ("flexible", "exact"):
            start = perf_counter()
            results = recommend(catalog, dict.fromkeys(codes, 1), mode)
            report["examples"].append({
                "collection": name, "set_numbers": codes, "mode": mode,
                "seconds": round(perf_counter() - start, 4),
                "complete": sum(m.complete for m in results),
                "at_least_90_percent": sum(m.percent >= 90 for m in results),
                "top": [{"set_num": m.lego_set.set_num, "name": m.lego_set.name,
                         "percent": round(m.percent, 2), "missing": m.missing} for m in results[:3]],
            })
    serialized = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    print(serialized)


if __name__ == "__main__":
    main()
