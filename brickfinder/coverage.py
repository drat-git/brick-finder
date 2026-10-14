"""Catalog categories describe coverage without restricting building themes."""

CATEGORY_POLICIES = {
    "Building sets": "Eligible for recommendations within the year and piece limits.",
    "Preschool systems": "Included; DUPLO, Primo, and Quatro part IDs remain distinct.",
    "Specialty systems": "Included; specialty part IDs must match like any other part.",
    "Bulk parts and accessories": "Owned sets only: supplies pieces rather than a model to build.",
    "Books and merchandise": "Owned sets only: contributes its validated inventory, not a build recommendation.",
    "Multipacks": "Owned sets only: combines inventories rather than describing one build.",
    "Database records": "Excluded: source reference inventories, not physical sets to own or build.",
}

OWNED_ONLY_CATEGORIES = frozenset({
    "Bulk parts and accessories", "Books and merchandise", "Multipacks",
})

FAMILY_CATEGORIES = {
    **dict.fromkeys(("Duplo", "Primo", "Quatro"), "Preschool systems"),
    **dict.fromkeys(("Bionicle", "Hero Factory", "Clikits", "Galidor", "Scala",
                     "Belville", "Znap"), "Specialty systems"),
    **dict.fromkeys(("Bulk Bricks", "Service Packs", "Power Functions"), "Bulk parts and accessories"),
    **dict.fromkeys(("Books", "Gear"), "Books and merchandise"),
    "Value Packs": "Multipacks",
}


def category_for_themes(themes: list[str] | tuple[str, ...]) -> str:
    """Inspect the whole theme path, including educational service-pack subthemes."""
    if "Database Sets" in themes:
        return "Database records"
    if any(name in themes for name in ("Service Packs", "Supplemental", "Bulk Bricks", "Power Functions")):
        return "Bulk parts and accessories"
    if any(name in themes for name in ("Duplo", "Duplo and Explore", "Primo", "Quatro", "Soft Bricks")):
        return "Preschool systems"
    return FAMILY_CATEGORIES.get(themes[-1], "Building sets")
