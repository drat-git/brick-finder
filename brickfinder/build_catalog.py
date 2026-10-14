"""Build the deployable catalog: python -m brickfinder.build_catalog."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = frozenset({
    "Creator", "Classic", "City", "Town", "Space", "Pirates", "Castle",
    "Technic", "Racers", "Train", "Seasonal", "Star Wars", "Friends",
    "Ninjago", "Speed Champions", "Brickheadz", "LEGO Ideas and CUUSOO",
    "Architecture", "Icons", "Botanicals",
})
SCHEMA_VERSION = 1


def file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_csv(directory: Path, name: str):
    with (directory / f"{name}.csv").open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


class InventoryError(ValueError):
    pass


def build_catalog(source: Path, output: Path, last_year: int = 2026) -> dict:
    required = ("sets", "themes", "parts", "colors", "inventories",
                "inventory_parts", "inventory_minifigs", "inventory_sets", "minifigs")
    missing = [f"{name}.csv" for name in required if not (source / f"{name}.csv").is_file()]
    if missing:
        raise ValueError("Missing source files: " + ", ".join(missing))

    sets = {r["set_num"]: r for r in read_csv(source, "sets")}
    themes = {r["id"]: r for r in read_csv(source, "themes")}
    parts = {r["part_num"]: r for r in read_csv(source, "parts")}
    colors = {r["id"]: r for r in read_csv(source, "colors")}
    figures = {r["fig_num"] for r in read_csv(source, "minifigs")}
    latest = {}
    for row in read_csv(source, "inventories"):
        previous = latest.get(row["set_num"])
        rank = (int(row["version"]), int(row["id"]))
        if previous is None or rank > (int(previous["version"]), int(previous["id"])):
            latest[row["set_num"]] = row

    selected_ids = {r["id"] for r in latest.values()}
    direct = defaultdict(Counter)
    children = defaultdict(list)
    invalid = {}
    for row in read_csv(source, "inventory_parts"):
        inventory = row["inventory_id"]
        if inventory not in selected_ids:
            continue
        if row["is_spare"] not in {"True", "False"}:
            invalid[inventory] = "Invalid spare-piece flag"
        if row["part_num"] not in parts or row["color_id"] not in colors:
            invalid[inventory] = "Missing part or color reference"
        quantity = int(row["quantity"])
        if quantity <= 0:
            invalid[inventory] = "Nonpositive part quantity"
        if row["is_spare"] == "False":
            direct[inventory][(row["part_num"], int(row["color_id"]))] += quantity
    for name, field, known in (("inventory_minifigs", "fig_num", figures),
                               ("inventory_sets", "set_num", sets)):
        for row in read_csv(source, name):
            inventory = row["inventory_id"]
            if inventory not in selected_ids:
                continue
            quantity = int(row["quantity"])
            if row[field] not in known or quantity <= 0:
                invalid[inventory] = "Invalid nested inventory reference or quantity"
            children[inventory].append((row[field], quantity))

    resolved = {}

    def flatten(code: str, trail: frozenset[str] = frozenset()):
        if code in trail:
            raise InventoryError(f"Inventory cycle involving {code}")
        if code in resolved:
            return resolved[code]
        if code not in latest:
            raise InventoryError(f"Missing inventory for {code}")
        inventory = latest[code]["id"]
        if inventory in invalid:
            raise InventoryError(invalid[inventory])
        result = direct[inventory].copy()
        for child, quantity in children[inventory]:
            for key, count in flatten(child, trail | {code}).items():
                result[key] += count * quantity
        if not result:
            raise InventoryError(f"Empty inventory for {code}")
        resolved[code] = result
        return result

    def root_theme(theme_id: str):
        seen = set()
        while True:
            if theme_id in seen or theme_id not in themes:
                raise InventoryError("Unresolved theme hierarchy")
            seen.add(theme_id)
            theme = themes[theme_id]
            if not theme["parent_id"]:
                return theme["name"]
            theme_id = theme["parent_id"]

    accepted, skipped = [], []
    for code, row in sorted(sets.items()):
        if not re.fullmatch(r"\d{4,5}-\d+", code):
            continue
        try:
            family = root_theme(row["theme_id"])
            if family not in FAMILIES:
                continue
            inventory = flatten(code)
            count = sum(inventory.values())
            if count != int(row["num_parts"]):
                raise InventoryError(f"Expanded total {count} differs from listed {row['num_parts']}")
            candidate = (code.endswith("-1") and 2000 <= int(row["year"]) <= last_year
                         and 20 <= count <= 1000)
            accepted.append((code, row, family, inventory, candidate))
        except InventoryError as error:
            skipped.append({"set_num": code, "name": row["name"], "reason": str(error)})

    if not accepted:
        raise ValueError("No usable inventories found; refusing to produce an empty catalog")
    output.mkdir(parents=True, exist_ok=True)
    database = output / "catalog.sqlite"
    temporary = output / "catalog.building.sqlite"
    if temporary.exists():
        temporary.unlink()
    used_parts = {p for _, _, _, bag, _ in accepted for p, _ in bag}
    with closing(sqlite3.connect(temporary)) as connection:
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE parts (part_num TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE colors (color_id INTEGER PRIMARY KEY, name TEXT NOT NULL, rgb TEXT NOT NULL);
            CREATE TABLE sets (set_num TEXT PRIMARY KEY, name TEXT NOT NULL, year INTEGER NOT NULL,
                family TEXT NOT NULL, num_parts INTEGER NOT NULL, img_url TEXT NOT NULL,
                inventory_version INTEGER NOT NULL, candidate INTEGER NOT NULL);
            CREATE TABLE requirements (set_num TEXT NOT NULL REFERENCES sets,
                part_num TEXT NOT NULL REFERENCES parts, color_id INTEGER NOT NULL REFERENCES colors,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                PRIMARY KEY(set_num, part_num, color_id)) WITHOUT ROWID;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        connection.executemany("INSERT INTO parts VALUES (?,?)",
                               ((p, parts[p]["name"]) for p in sorted(used_parts)))
        connection.executemany("INSERT INTO colors VALUES (?,?,?)",
                               ((int(c), r["name"], r["rgb"]) for c, r in colors.items()))
        for code, row, family, inventory, candidate in accepted:
            connection.execute("INSERT INTO sets VALUES (?,?,?,?,?,?,?,?)", (
                code, row["name"], int(row["year"]), family, sum(inventory.values()),
                row.get("img_url", ""), int(latest[code]["version"]), int(candidate)))
            connection.executemany("INSERT INTO requirements VALUES (?,?,?,?)",
                                   ((code, p, c, n) for (p, c), n in sorted(inventory.items())))
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "source": "https://rebrickable.com/downloads/",
            "families": sorted(FAMILIES),
            "owned_sets": len(accepted),
            "candidate_sets": sum(candidate for *_, candidate in accepted),
            "skipped_sets": len(skipped),
            "candidate_years": [2000, last_year],
            "candidate_pieces": [20, 1000],
            "source_sha256": {name: file_sha256(source / f"{name}.csv")
                              for name in required},
        }
        connection.executemany("INSERT INTO metadata VALUES (?,?)",
                               ((k, json.dumps(v)) for k, v in metadata.items()))
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Catalog failed its reference checks")
        connection.commit()
        connection.execute("VACUUM")
    temporary.replace(database)
    archive = output / "catalog.sqlite.gz"
    archive_temporary = output / "catalog.sqlite.gz.tmp"
    with database.open("rb") as source_handle, archive_temporary.open("wb") as target:
        with gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as compressed:
            while block := source_handle.read(1024 * 1024):
                compressed.write(block)
    archive_temporary.replace(archive)
    metadata["database_bytes"] = database.stat().st_size
    metadata["compressed_bytes"] = archive.stat().st_size
    metadata["archive_sha256"] = file_sha256(archive)
    (output / "catalog_info.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (output / "unsupported_sets.json").write_text(json.dumps(skipped, indent=2) + "\n")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "rebrickable_downloads")
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    parser.add_argument("--last-year", type=int, default=2026)
    args = parser.parse_args()
    result = build_catalog(args.source, args.output, args.last_year)
    print(json.dumps({k: result[k] for k in ("owned_sets", "candidate_sets", "skipped_sets", "compressed_bytes")}, indent=2))


if __name__ == "__main__":
    main()
