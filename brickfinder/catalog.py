"""Read-only access to the bundled catalog. No external API is required."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from brickfinder.coverage import category_for_themes

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LegoSet:
    set_num: str
    name: str
    year: int
    family: str
    num_parts: int
    img_url: str
    inventory_version: int
    candidate: bool
    coverage_category: str = ""

    @property
    def instructions_url(self):
        base = "https://www.lego.com/en-us/service/building-instructions"
        number = self.set_num.rsplit("-", 1)[0]
        return base + "/" + number if number.isascii() and number.isdigit() else base

    @property
    def category(self):
        return self.coverage_category or category_for_themes((self.family,))

    @property
    def safe_image_url(self):
        parsed = urlparse(self.img_url)
        if parsed.scheme == "https" and parsed.hostname == "cdn.rebrickable.com":
            return self.img_url
        return ""


def unpack_catalog(archive: Path = ROOT / "data/catalog.sqlite.gz", cache: Path | None = None) -> Path:
    if not archive.is_file():
        raise FileNotFoundError("The bundled catalog is missing. Run python -m brickfinder.build_catalog first.")
    with archive.open("rb") as handle:
        fingerprint = hashlib.file_digest(handle, "sha256").hexdigest()
    cache = cache or ROOT / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"catalog-{fingerprint}.sqlite"
    if not target.exists():
        descriptor, temporary = tempfile.mkstemp(dir=cache, suffix=".sqlite.tmp")
        try:
            with os.fdopen(descriptor, "wb") as dest, gzip.open(archive, "rb") as source:
                shutil.copyfileobj(source, dest)
            os.replace(temporary, target)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
    return target


class Catalog:
    def __init__(self, database: Path):
        self.database = database.resolve()
        with self.database.open("rb") as handle:
            self.fingerprint = hashlib.file_digest(handle, "sha256").hexdigest()
        with closing(self.connect()) as connection:
            self.metadata = {key: json.loads(value) for key, value in connection.execute("SELECT key,value FROM metadata")}
            if self.metadata.get("schema_version") != 2:
                raise ValueError("Unsupported catalog version. Rebuild the catalog with this app version.")
            self.sets = {row[0]: LegoSet(*row[:7], bool(row[7]), row[8])
                         for row in connection.execute("SELECT * FROM sets ORDER BY name,set_num")}
            self.parts = dict(connection.execute("SELECT part_num,name FROM parts"))
            self.colors = {row[0]: {"name": row[1], "rgb": row[2]}
                           for row in connection.execute("SELECT color_id,name,rgb FROM colors")}
        self.candidates = tuple(s for s in self.sets.values() if s.candidate)

    def connect(self):
        return sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)

    def search(self, text: str, limit: int = 30) -> list[LegoSet]:
        query = text.strip().casefold()
        if not query:
            return []
        terms = query.split()
        result = [s for s in self.sets.values()
                  if all(t in f"{s.set_num} {s.name}".casefold() for t in terms)]
        return sorted(result, key=lambda s: (s.set_num.casefold() != query and s.set_num.rsplit("-", 1)[0].casefold() != query,
                                            not s.name.casefold().startswith(query), s.name, s.set_num))[:limit]

    @lru_cache(maxsize=128)
    def inventory(self, code: str) -> dict[tuple[str, int], int]:
        if code not in self.sets:
            raise ValueError(f"Set {code} is not in the supported catalog")
        with closing(self.connect()) as connection:
            return {(p, c): n for p, c, n in connection.execute(
                "SELECT part_num,color_id,quantity FROM requirements WHERE set_num=?", (code,))}

    @lru_cache(maxsize=1)
    def candidate_inventories(self):
        result = {s.set_num: {} for s in self.candidates}
        with closing(self.connect()) as connection:
            for code, part, color, quantity in connection.execute("""
                SELECT r.set_num,r.part_num,r.color_id,r.quantity FROM requirements r
                JOIN sets s ON s.set_num=r.set_num WHERE s.candidate=1
            """):
                result[code][(part, color)] = quantity
        return result

    def aggregate(self, collection: dict[str, int]) -> Counter:
        from brickfinder.inventory import CollectionState, available_inventory
        if isinstance(collection, CollectionState):
            return available_inventory(self, collection)
        available = Counter()
        for code, quantity in collection.items():
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                raise ValueError("Set quantities must be positive whole numbers")
            for key, count in self.inventory(code).items():
                available[key] += count * quantity
        return available
