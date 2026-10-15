# Brick Finder

Find other official LEGO sets you have pieces for. Select owned sets, combine their inventories, compare against the catalog, and inspect exact shortages or color substitutions.

The app runs entirely from a bundled catalog. No Rebrickable account, API key, or login is needed by visitors.

## Frontend

The redesigned interface runs in Streamlit, including Streamlit Community Cloud. It uses the same HTML, CSS, JavaScript, catalog, and matcher as the standalone local preview. Streamlit's component API connects the frontend to Python; no separate API server or frontend build is needed on the hosted app.

For frontend development, the standalone preview is still available:

```bash
python -m brickfinder.web --port 8502
```

Open `http://127.0.0.1:8502`. The frontend is in `frontend/`; the standalone server uses HTTP for the same requests that the deployed app sends through Streamlit. Collections last for the browser tab's session.

The previous Streamlit UI remains recoverable from Git history at commit `ef27fb1`.

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

The interface defaults to exact colors, 100% completion, and 20–1,000-piece recommendations, so the initial results contain every required part in its original color. The color selector sits below Find my next build; users can choose flexible colors or use Almost there to explore builds needing extra pieces. Each search-and-add adds one copy and clears the search. Duplicate sets stay in one selected entry with quantity controls. Clicking a selected set's name or image opens its details and instruction link. Removing an entry removes all its copies. Clearing the collection requires confirmation. Selected owned sets are excluded from results. Collection changes invalidate previous results; display filters reuse cached matches.

## Data and coverage

Catalog prepared from the user's Rebrickable downloads on October 14, 2026:

| Measure | Count |
| --- | ---: |
| Source records audited | 28,537 |
| Selectable owned sets/items | 19,702 |
| Recommendation candidates | 10,116 |
| Included root themes | 149 |
| Inventories excluded by validation | 8,704 |
| Synthetic reference records excluded | 131 |
| Compressed database | 11.6 MB |

All source themes qualify without a theme allowlist. This includes Harry Potter, Minecraft, Disney, Jurassic World, Lord of the Rings, Marvel, DC, DUPLO, and specialty systems alongside the original themes. The catalog button shows selectable and recommendation counts by category; full category and theme coverage is recorded in `data/catalog_info.json`.

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

The importer selects the highest inventory version, expands minifigures and nested sets with quantities, excludes spare pieces, and checks part/color references and totals. Missing, empty, cyclic, or inconsistent inventories are excluded and recorded in `data/unsupported_sets.json`. Synthetic database reference records and their exclusion reasons are recorded separately in `data/excluded_sets.json`. Every source record is accounted for as selectable, invalid, or excluded by policy. Inventory versions are alternatives; they are never added together.

Source fingerprints, schema version, coverage by theme/category/identifier format, and archive checksum are in `data/catalog_info.json`. Raw downloads and the uncompressed database are excluded from Git. Numeric set IDs link to LEGO's set-specific instruction pages; alphanumeric IDs open its instruction search page. Instruction availability varies, especially for promotional sets, and multiple booklets are handled on LEGO's website. Set images use the source CDN URLs and depict the original colors.

## Rebuild the catalog

Place these CSVs in `rebrickable_downloads/`: `sets`, `themes`, `parts`, `colors`, `inventories`, `inventory_parts`, `inventory_minifigs`, `inventory_sets`, and `minifigs` (each ending in `.csv`). Then:

```bash
python -m brickfinder.build_catalog
python scripts/benchmark.py --output data/demo_results.json
```

Importing and benchmarking are explicit development steps. The running app never downloads new archives or scrapes Rebrickable pages. Changing the compressed catalog changes its cache fingerprint, so the next app run unpacks and loads the new snapshot rather than reusing a cached older catalog.

## Tests and measured results

```bash
python -m unittest discover -s tests -v
node --test tests/test_transport.cjs
python scripts/benchmark.py
```

Tests cover quantities, duplicate sets, color allocation, printed parts, ranking, rounded percentages, version selection, nested inventories, spare exclusion, invalid inventories, read-only catalog access, expanded themes and identifier formats, recommendation boundaries, category/exclusion accounting, complete example builds in both color modes, Streamlit request handling, stable component identity, and browser transport queueing/cancellation.

Local measurements on Python 3.13.16 / Apple Silicon: the first flexible search including candidate loading took approximately 1.07 seconds; subsequent flexible searches approximately 0.25 seconds; exact searches approximately 0.08 seconds. These are local measurements, not a hosted latency guarantee. Reproduce them with the benchmark script; recorded results are in `data/demo_results.json`.

| Example collection | Theme | Owned sets | Complete flexible-color builds | Complete exact-color builds |
| --- | --- | ---: | ---: | ---: |
| Example 1 | Superheroes | 6 | 48 | 1 |
| Example 2 | City | 6 | 50 | 2 |
| Example 3 | Mixed themes | 6 | 72 | 6 |

Collections are defined once in `brickfinder/examples.py` and shared by the UI and benchmark. Each has at least two complete builds that need color changes as well as at least one complete exact-color build. Example 1 can build Quinjet (30162) in exact colors; Examples 2 and 3 can build Flexible Rails (7499) and Tracks (60205) in exact colors. Flexible-color counts include exact-color builds. Each result is evaluated independently, and owned sets are excluded.

## Deploy

1. Push the app, package, tests, configuration, dependency file, and generated compressed catalog to GitHub. Do not push raw CSVs, virtual environments, caches, or credentials.
2. In [Streamlit Community Cloud](https://share.streamlit.io/), select **Create app**, the repository's `main` branch, and `app.py`.
3. In **Advanced settings**, choose **Python 3.13**. No secrets are required.
4. Deploy, then verify a fresh browser session: load Example 1, find builds in exact colors, open a piece breakdown, switch to flexible colors, and follow an instruction link. `app.py` serves the redesigned frontend directly as a Streamlit component; do not deploy `frontend/index.html` as a separate app.
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
