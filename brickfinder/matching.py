"""Quantity-aware matching with explicit exact and color-flexible modes."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Literal

from brickfinder.catalog import Catalog, LegoSet

Mode = Literal["exact", "flexible"]


def by_part(inventory):
    result = Counter()
    for (part, _color), count in inventory.items():
        result[part] += count
    return result


def matched_quantity(available, required):
    return sum(min(available.get(key, 0), quantity) for key, quantity in required.items())


@dataclass(frozen=True)
class Match:
    lego_set: LegoSet
    mode: Mode
    matched: int
    required: int
    exact_matched: int

    @property
    def missing(self):
        return self.required - self.matched

    @property
    def complete(self):
        return self.missing == 0

    @property
    def percent(self):
        return self.matched / self.required * 100

    @property
    def exact_percent(self):
        return self.exact_matched / self.required * 100

    @property
    def display_percent(self):
        # A rounded partial match must never look like a complete inventory.
        return f"{100 if self.complete else min(round(self.percent, 1), 99.9):.1f}%"

    @property
    def exact_display_percent(self):
        complete = self.exact_matched == self.required
        return f"{100 if complete else min(round(self.exact_percent, 1), 99.9):.1f}%"


def recommend(catalog: Catalog, collection: dict[str, int], mode: Mode = "flexible") -> list[Match]:
    if mode not in ("exact", "flexible"):
        raise ValueError("Unknown matching mode")
    if not collection:
        return []
    available = catalog.aggregate(collection)
    flexible_available = by_part(available)
    inventories = catalog.candidate_inventories()
    result = []
    for lego_set in catalog.candidates:
        if lego_set.set_num in collection:
            continue
        required = inventories[lego_set.set_num]
        total = sum(required.values())
        if total <= 0:
            continue
        exact = matched_quantity(available, required)
        matched = exact if mode == "exact" else matched_quantity(flexible_available, by_part(required))
        result.append(Match(lego_set, mode, matched, total, exact))
    result.sort(key=lambda m: (-m.percent, m.missing, -m.required, m.lego_set.set_num))
    return result


def filter_matches(matches: list[Match], minimum: float, sizes: tuple[int, int]) -> list[Match]:
    return [m for m in matches if m.percent >= minimum and sizes[0] <= m.required <= sizes[1]]


def shortage_rows(catalog: Catalog, collection: dict[str, int], match: Match) -> list[dict]:
    available = catalog.aggregate(collection)
    required = catalog.inventory(match.lego_set.set_num)
    rows = []
    if match.mode == "exact":
        for (part, color), count in required.items():
            owned = available.get((part, color), 0)
            if owned < count:
                rows.append({"Part ID": part, "Part": catalog.parts[part],
                             "Required color": catalog.colors[color]["name"],
                             "Required": count, "Available": owned, "Missing": count - owned})
    else:
        owned_by_part = by_part(available)
        available_colors = defaultdict(list)
        for (part, color), count in sorted(available.items()):
            available_colors[part].append(f"{catalog.colors[color]['name']} ({count})")
        for part, count in by_part(required).items():
            owned = owned_by_part.get(part, 0)
            if owned < count:
                rows.append({"Part ID": part, "Part": catalog.parts[part],
                             "Required": count, "Available": owned, "Missing": count - owned,
                             "Available colors": ", ".join(available_colors[part]) or "None"})
    return sorted(rows, key=lambda row: (-row["Missing"], row["Part ID"]))


def color_change_rows(catalog: Catalog, collection: dict[str, int], match: Match) -> list[dict]:
    """Allocate exact colors first, then each leftover piece at most once."""
    if match.mode != "flexible":
        return []
    remaining = catalog.aggregate(collection)
    required = catalog.inventory(match.lego_set.set_num)
    deficits = []
    for (part, color), count in sorted(required.items()):
        exact = min(remaining[part, color], count)
        remaining[part, color] -= exact
        if count > exact:
            deficits.append((part, color, count - exact))
    colors_by_part = defaultdict(list)
    for part, color in sorted(remaining):
        colors_by_part[part].append(color)
    rows = []
    for part, requested_color, deficit in deficits:
        for color in colors_by_part[part]:
            used = min(remaining[part, color], deficit)
            if used:
                rows.append({"Part ID": part, "Part": catalog.parts[part],
                             "Instruction color": catalog.colors[requested_color]["name"],
                             "Use your color": catalog.colors[color]["name"], "Quantity": used})
                remaining[part, color] -= used
                deficit -= used
            if not deficit:
                break
    return rows
