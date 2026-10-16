# Catalog coverage and validation

[Project overview](../README.md) · [Architecture](architecture.md) · [Development guide](development.md)

## Snapshot coverage


The bundled catalog was prepared from a Rebrickable CSV snapshot on October 14, 2026:

| Measure | Count |
| --- | ---: |
| Source records audited | 28,537 |
| Selectable owned sets/items | 19,702 |
| Recommendation candidates | 10,116 |
| Included root themes | 149 |
| Inventories excluded by validation | 8,704 |
| Synthetic reference records excluded | 131 |
| Compressed database | 11.6 MB |

All source themes qualify without a theme allowlist. This includes Harry Potter, Minecraft, Disney, Jurassic World, Lord of the Rings, Marvel, DC, DUPLO, and specialty systems alongside the original themes. The catalog button shows selectable and recommendation counts by category; full category and theme coverage is recorded in [`data/catalog_info.json`](../data/catalog_info.json).

Owned sets/items have no year or piece-count limits and require a valid, nonempty inventory. Recommendations remain limited to 2000–2026 and 20–1,000 pieces. Source identifiers of any length, alphanumeric promotional IDs, magazine sets, and set variants are supported; there is no four-/five-digit or `-1` restriction. Set variants are separate source entries; inventory versions are alternative inventories for the same entry.

| Category | Selectable owned inventories | Recommendations | Treatment |
| --- | ---: | ---: | --- |
| Building sets | 14,722 | 8,945 | All building themes qualify within recommendation limits. |
| Preschool systems | 1,802 | 676 | DUPLO, Primo, Quatro, and educational preschool sets are included. |
| Specialty systems | 722 | 495 | Bionicle, Hero Factory, and other specialty systems are included. |
| Bulk parts and accessories | 1,412 | 0 | Usable as owned inventory, including educational service packs and supplemental parts. |
| Books and merchandise | 1,044 | 0 | Validated inventoried pieces can contribute to other builds. |
| Multipacks | 0 | 0 | Owned inventory only; none in this snapshot pass validation. |
| Database records | 0 | 0 | Synthetic reference entries do not describe physical sets and are excluded. |

Part IDs remain distinct across building systems; including DUPLO or specialty themes does not imply that their parts substitute for ordinary bricks. Category rules inspect the full theme hierarchy, so an educational service pack is classified as parts rather than as a build. This is coverage of the supplied snapshot, not a live catalog of every LEGO product.

The importer selects the highest inventory version, expands minifigures and nested sets with quantities, excludes spare pieces, and checks part/color references and totals. Missing, empty, cyclic, or inconsistent inventories are excluded and recorded in [`data/unsupported_sets.json`](../data/unsupported_sets.json). Synthetic database reference records and their exclusion reasons are recorded separately in [`data/excluded_sets.json`](../data/excluded_sets.json). Every source record is accounted for as selectable, invalid, or excluded by policy. Inventory versions are alternatives; they are never added together.

Source fingerprints, schema version, coverage by theme/category/identifier format, and archive checksum are in [`data/catalog_info.json`](../data/catalog_info.json). Raw downloads and the uncompressed database are excluded from Git. Numeric set IDs link to LEGO's set-specific instruction pages; alphanumeric IDs open its instruction search page. Instruction availability varies, especially for promotional sets, and multiple booklets are handled on LEGO's website. Set images use the source CDN URLs and depict the original colors.

## Rebuild the catalog

Place these CSVs in `rebrickable_downloads/`: `sets`, `themes`, `parts`, `colors`, `inventories`, `inventory_parts`, `inventory_minifigs`, `inventory_sets`, and `minifigs` (each ending in `.csv`). Then:

```bash
python -m brickfinder.build_catalog
python scripts/benchmark.py --output data/demo_results.json
```

Importing and benchmarking are explicit development steps. The running app never downloads new archives or scrapes Rebrickable pages. Changing the compressed catalog changes its cache fingerprint, so the next app run unpacks and loads the new snapshot rather than reusing a cached older catalog.

See [data attribution and permissions](../DATA_SOURCE.md).
