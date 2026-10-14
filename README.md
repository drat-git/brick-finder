# Brick Finder

Find other official LEGO sets you have pieces for. Select owned sets, combine their inventories, compare against the catalog, and inspect exact shortages or color substitutions.

The app runs entirely from a bundled catalog. No Rebrickable account, API key, or login is needed by visitors.

## Run locally

Use Python 3.13. From the project directory:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the URL printed by Streamlit. The compressed catalog is included; downloading or importing data is not required to run the app. It is unpacked into an ignored `.cache` directory when first opened.

## How matching works

Owned quantities are multiplied by the number of set copies, then combined. Recommendations are evaluated independently against that same inventory; multiple recommended builds cannot necessarily be assembled simultaneously.

- **Exact colors:** compare quantities for each `(part ID, color ID)`.
- **Flexible colors:** combine colors for each part ID, then compare quantities. Printed variants and different molds are still distinct.
- **Completion:** `sum(min(available quantity, required quantity)) / total required quantity`.
- **Ranking:** completion descending, missing quantity ascending, required piece count descending, then set number.
- **Complete:** only zero missing pieces qualifies. A rounded partial percentage never displays as 100%.
- **Color allocation:** reserve all exact-color matches first, then allocate remaining colors to deficits. A piece can be used only once within a recommendation.

The interface defaults to flexible colors, 80% completion, and 20–1,000-piece recommendations. Each search-and-add adds one copy and clears the search. Duplicate sets stay in one selected entry with an `x2`, `x3`, etc. label; single copies have no count label. Removing an entry removes all its copies. Clearing the collection requires confirmation. Selected owned sets are excluded from results. Collection changes invalidate previous results; display filters do not rerun the matcher.

## Data and coverage

Catalog prepared from the user's Rebrickable downloads on October 14, 2026:

| Measure | Count |
| --- | ---: |
| Selectable owned sets | 6,058 |
| Recommendation candidates | 4,194 |
| Eligible sets excluded by validation | 312 |
| Compressed database | 5.4 MB |

Supported families: Creator, Classic, City, Town, Space, Pirates, Castle, Technic, Racers, Train, Seasonal, Star Wars, Friends, Ninjago, Speed Champions, BrickHeadz, Ideas, Architecture, Icons, and Botanicals.

Owned sets may come from any year or size within these families. Candidates use four- or five-digit set numbers, variant `-1`, years 2000–2026, and 20–1,000 pieces. This is a bounded catalog, not every official LEGO set.

The importer selects the highest inventory version, expands minifigures and nested sets with quantities, excludes spare pieces, and checks part/color references and totals. Missing, empty, cyclic, or inconsistent inventories are excluded and recorded in `data/unsupported_sets.json`. Inventory versions are alternatives; they are never added together.

Source fingerprints, schema version, coverage, and archive checksum are in `data/catalog_info.json`. Raw downloads and the uncompressed database are excluded from Git. Instructions link to LEGO's set-specific pages; availability varies and multiple booklets are handled on LEGO's website. Set images use the source CDN URLs and depict the original colors.

## Rebuild the catalog

Place these CSVs in `rebrickable_downloads/`: `sets`, `themes`, `parts`, `colors`, `inventories`, `inventory_parts`, `inventory_minifigs`, `inventory_sets`, and `minifigs` (each ending in `.csv`). Then:

```bash
python -m brickfinder.build_catalog
python scripts/benchmark.py --output data/demo_results.json
```

Importing and benchmarking are explicit development steps. The running app never downloads new archives or scrapes Rebrickable pages. Changing the compressed catalog changes its cache fingerprint, so the next app startup unpacks the new snapshot.

## Tests and measured results

```bash
python -m unittest discover -s tests -v
python scripts/benchmark.py
```

Tests cover quantities, duplicate sets, color allocation, printed parts, ranking, rounded percentages, version selection, nested inventories, spare exclusion, invalid inventories, read-only catalog access, and the Streamlit collection/search/results flow.

Local measurements on Python 3.13.16 / Apple Silicon: the first flexible search including candidate loading took approximately 0.53 seconds; subsequent flexible searches approximately 0.12 seconds; exact searches approximately 0.04 seconds. These are local measurements, not a hosted latency guarantee. Reproduce them with the benchmark script; recorded results are in `data/demo_results.json`.

| Example collection | Flexible-color result | Exact-color result |
| --- | --- | --- |
| Classic: 11021 + 11036 | 1 complete build; 23 at least 90% complete | No complete builds; best 66.7% |
| Creator: 31124 + 31125 + 31128 | Best 89.1%, missing 6 pieces | Best 51.5% |
| City: 60312 + 60333 + 60337 | Best 92%, missing 2 pieces | Best 60% |

The Classic example fully covers the inventory for Halloween Bat (40014) when colors can change. Exact-color matches can be scarce; the app shows that honestly.

## Deploy

1. Push the app, package, tests, configuration, dependency file, and generated compressed catalog to GitHub. Do not push raw CSVs, virtual environments, caches, or credentials.
2. In [Streamlit Community Cloud](https://share.streamlit.io/), select **Create app**, the repository's `main` branch, and `app.py`.
3. In **Advanced settings**, choose **Python 3.13**. No secrets are required.
4. Deploy, then verify a fresh browser session: load Classic, find builds, open a piece breakdown, switch to exact colors, and follow an instruction link.
5. Make the deployed app viewable publicly if Community Cloud initially creates it as private.

GitHub Actions runs the tests on Python 3.13. To roll back, revert the relevant app/catalog commit in GitHub and redeploy the previous working state. Runtime exceptions appear in Streamlit's app logs.

## Assumptions and limits

- Selected sets are complete and available to dismantle; missing owned pieces cannot be entered in version one.
- Minifigure components count. Spare pieces do not.
- Part IDs, prints, stickers, and mold variants remain distinct. We do not infer mechanical compatibility or verify building geometry.
- Flexible colors can change the appearance of the finished build. The table gives one possible color allocation.
- Collections last for the current browser session only. There are no user accounts, saved collections, pricing, custom models, generated instructions, or photo recognition.
- Result images and instructions require internet access; inventory matching does not.

## Attribution

Catalog data and set-image links: [Rebrickable](https://rebrickable.com/downloads/). Building instructions: [LEGO](https://www.lego.com/en-us/service/building-instructions). See `DATA_SOURCE.md` for the downloaded data's permission statement and handling rules.

Independent portfolio project. Not affiliated with the LEGO Group or Rebrickable. LEGO is a trademark of the LEGO Group.
