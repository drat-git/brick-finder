"""Physical inventories and the shared accounting used by matching and planning."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from typing import NamedTuple
from uuid import UUID, uuid4


class PartKey(NamedTuple):
    part_id: str
    color_id: int


def new_id() -> str:
    return str(uuid4())


def whole_quantity(value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"Quantity must be a whole number of at least {minimum}")
    return value


@dataclass
class OwnedSetCopy:
    set_num: str
    inventory_version: int
    id: str = field(default_factory=new_id)
    label: str = ""
    keep_assembled: bool = False
    missing: dict[PartKey, int] = field(default_factory=dict)

    def set_missing(self, catalog, key: PartKey, quantity: int):
        whole_quantity(quantity)
        if key not in catalog.inventory(self.set_num):
            raise ValueError("This part/color is not in this copy's inventory")
        if quantity > catalog.inventory(self.set_num)[key]:
            raise ValueError("Missing quantity exceeds this copy's inventory")
        if quantity:
            self.missing[key] = quantity
        else:
            self.missing.pop(key, None)


@dataclass
class CollectionState:
    name: str = "Untitled collection"
    id: str = field(default_factory=new_id)
    revision: int = 0
    catalog_fingerprint: str = ""
    copies: list[OwnedSetCopy] = field(default_factory=list)
    loose: dict[PartKey, int] = field(default_factory=dict)

    def __bool__(self):
        return bool(self.copies or self.loose)

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(copy.set_num for copy in self.copies))

    @classmethod
    def from_counts(cls, catalog, counts, name="Untitled collection"):
        result = cls(name=name, catalog_fingerprint=catalog_fingerprint(catalog))
        for code, count in counts.items():
            whole_quantity(count, 1)
            for _ in range(count):
                result.add_set(catalog, code)
        return result

    def add_set(self, catalog, code):
        if code not in catalog.sets:
            raise ValueError("Unknown catalog set")
        copy = OwnedSetCopy(code, catalog.sets[code].inventory_version,
                            label=f"{code} copy {self.counts.get(code, 0) + 1}")
        self.copies.append(copy)
        return copy

    def set_loose(self, catalog, key: PartKey, quantity: int, *, add=False):
        whole_quantity(quantity)
        validate_key(catalog, key)
        total = quantity + self.loose.get(key, 0) if add else quantity
        if total:
            self.loose[key] = total
        else:
            self.loose.pop(key, None)

    def save_as(self, name):
        if not name.strip():
            raise ValueError("Collection name cannot be empty")
        result = deepcopy(self)
        result.id, result.revision, result.name = new_id(), 0, name.strip()
        for copy in result.copies:
            copy.id = new_id()
        return result

    def payload(self):
        def quantities(items):
            return [{"part_id": p, "color_id": c, "quantity": n} for (p, c), n in sorted(items.items())]
        return {"id": self.id, "name": self.name, "revision": self.revision,
                "catalog_fingerprint": self.catalog_fingerprint,
                "copies": [{"id": c.id, "set_num": c.set_num, "label": c.label,
                            "keep_assembled": c.keep_assembled, "inventory_version": c.inventory_version,
                            "missing": quantities(c.missing)} for c in self.copies],
                "loose": quantities(self.loose)}

    @classmethod
    def from_payload(cls, data):
        # Catalog validation is deliberately separate: obsolete records must remain editable.
        def quantities(rows):
            result = {}
            for row in rows:
                key = PartKey(row["part_id"], row["color_id"])
                if key in result:
                    raise ValueError("Duplicate inventory record")
                result[key] = row["quantity"]
            return result
        return cls(id=data["id"], name=data["name"], revision=data["revision"],
                   catalog_fingerprint=data["catalog_fingerprint"],
                   copies=[OwnedSetCopy(id=c["id"], set_num=c["set_num"], label=c["label"],
                                        keep_assembled=c["keep_assembled"], inventory_version=c["inventory_version"],
                                        missing=quantities(c.get("missing", []))) for c in data.get("copies", [])],
                   loose=quantities(data.get("loose", [])))

    def snapshot(self, mode=None):
        return hashlib.sha256(json.dumps([self.payload(), mode], sort_keys=True).encode()).hexdigest()


def catalog_fingerprint(catalog):
    if hasattr(catalog, "fingerprint"):
        return catalog.fingerprint
    return hashlib.sha256(json.dumps(getattr(catalog, "metadata", {}), sort_keys=True).encode()).hexdigest()


def validate_key(catalog, key):
    part, color = key
    if part not in catalog.parts or isinstance(color, bool) or not isinstance(color, int) or color not in catalog.colors:
        raise ValueError(f"Unknown catalog part/color: {part} / {color}")


@dataclass(frozen=True)
class InventoryIssue:
    record_id: str
    message: str


def validate_collection(catalog, collection: CollectionState) -> list[InventoryIssue]:
    issues = []

    def issue(record, message):
        issues.append(InventoryIssue(record, message))

    def uuid_valid(value):
        try:
            UUID(value)
            return True
        except (ValueError, TypeError, AttributeError):
            return False

    if not uuid_valid(collection.id):
        issue(collection.id, "Invalid collection UUID")
    if not isinstance(collection.name, str) or not collection.name.strip():
        issue(collection.id, "Collection name cannot be empty")
    try:
        whole_quantity(collection.revision)
    except ValueError as error:
        issue(collection.id, str(error))
    ids = set()
    for copy in collection.copies:
        if not uuid_valid(copy.id) or copy.id in ids:
            issue(copy.id, "Invalid or duplicate copy UUID")
        ids.add(copy.id)
        if copy.set_num not in catalog.sets:
            issue(copy.id, f"Unknown set {copy.set_num}; remove or replace this record")
            continue
        if (type(copy.inventory_version) is not int or
                copy.inventory_version != catalog.sets[copy.set_num].inventory_version):
            issue(copy.id, "Inventory version changed; review missing pieces and accept the current version")
        if not isinstance(copy.keep_assembled, bool) or not isinstance(copy.label, str):
            issue(copy.id, "Copy label or protection flag is invalid")
        required = catalog.inventory(copy.set_num)
        for key, quantity in copy.missing.items():
            try:
                validate_key(catalog, key)
                whole_quantity(quantity, 1)
                if key not in required or quantity > required[key]:
                    raise ValueError(f"Missing {key} exceeds this copy's inventory")
            except ValueError as error:
                issue(copy.id, str(error))
    for key, quantity in collection.loose.items():
        try:
            validate_key(catalog, key)
            whole_quantity(quantity, 1)
        except ValueError as error:
            issue("loose", str(error))
    return issues


def inventory_sources(catalog, collection: CollectionState, *, planner=False) -> dict[str, Counter]:
    issues = validate_collection(catalog, collection)
    if issues:
        raise ValueError("; ".join(i.message for i in issues))
    sources = {"loose": Counter(collection.loose)}
    for copy in sorted(collection.copies, key=lambda c: c.id):
        if planner and copy.keep_assembled:
            continue
        sources[copy.id] = Counter(catalog.inventory(copy.set_num)) - Counter(copy.missing)
    return sources


def available_inventory(catalog, collection, *, planner=False) -> Counter:
    if not isinstance(collection, CollectionState):
        # Legacy callers keep their quantity-based API and catalog validation.
        return catalog.aggregate(collection)
    available = Counter()
    for source in inventory_sources(catalog, collection, planner=planner).values():
        available.update(source)
    return available
