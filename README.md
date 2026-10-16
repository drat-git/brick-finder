# Rebuilt

Rebuilt finds other official LEGO sets you have pieces for. Select owned sets, combine their inventories, compare against the catalog, and inspect exact shortages or color substitutions.

The catalog and guest features run from the bundled data without a login. Optional Firebase email/password accounts save named collections; the on-demand planner finds which physical copies to dismantle for one complete build.

## Frontend

The redesigned interface runs in Streamlit, including Streamlit Community Cloud. It uses the same HTML, CSS, JavaScript, catalog, and matcher as the standalone local preview. Streamlit's component API connects the frontend to Python; no separate API server or frontend build is needed on the hosted app.

For frontend development, the standalone preview is still available:

```bash
python -m brickfinder.web --port 8502
```

Open `http://127.0.0.1:8502`. The frontend is in `frontend/`; the standalone server uses HTTP for the same requests that the deployed app sends through Streamlit. Private drafts and sign-in live only in the active server session. Refreshing starts a fresh draft and requires signing in again. No inventory or authentication is stored in browser storage.

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

Each duplicate is a separate physical copy with its own UUID, label, missing-piece adjustments, and protection setting. Effective inventory is the sum of each catalog inventory minus that copy’s missing pieces, plus additional loose parts. Missing pieces never create loose parts. Recommendations are evaluated independently against that same inventory; multiple recommended builds cannot necessarily be assembled simultaneously.

- **Exact colors:** compare quantities for each `(part ID, color ID)`.
- **Flexible colors:** combine colors for each part ID, then compare quantities. Printed variants and different molds are still distinct.
- **Completion:** `sum(min(available quantity, required quantity)) / total required quantity`.
- **Ranking:** completion descending, missing quantity ascending, required piece count descending, then set number.
- **Complete:** only zero missing pieces qualifies. A rounded partial percentage never displays as 100%.
- **Color allocation:** reserve all exact-color matches first, then allocate remaining colors to deficits. A piece can be used only once within a recommendation.

The interface defaults to exact colors, 100% completion, and 20–1,000-piece recommendations, so the initial results contain every required part in its original color. The color selector sits below Find my next build; users can choose flexible colors or use Almost there to explore builds needing extra pieces. Each search-and-add adds one copy and clears the search. Duplicate sets stay in one selected entry with quantity controls. Clicking a selected set's name or image opens its details and instruction link. Removing an entry removes all its copies. Clearing the collection requires confirmation. Selected owned sets are excluded from results. Piece changes invalidate results and plans. Protection affects only planning; recommendations continue to include protected copies. Display filters reuse matches cached only in the individual visitor’s server session.

## Saved collections and physical inventories

Use **Manage** in the existing collection panel for New, Load, Save, Save as, Rename, and confirmed Delete. There is one active editable draft. Saving is explicit; Rename changes the draft until Save is selected. Save as generates a new collection UUID and new UUIDs for all physical copies. New, Load, examples, and sign out offer Save / Discard / Cancel before replacing dirty work. Login preserves a guest draft. Sign out clears the private draft, authentication, cached results, plans, and private UI state. Clear empties the draft without deleting its saved cloud copy. Delete removes the saved copy and leaves an independent local draft.

Open a set’s existing details dialog to manage individual copies. Missing quantities are whole numbers between zero and that copy’s catalog capacity. Zero removes the adjustment. **Keep assembled is planner-only protection:** protected pieces still count in recommendations, but plans cannot use them. A complete recommendation can therefore have an unavailable plan; protected-only shortages are identified explicitly. Group removal still removes all copies. The minus control for duplicate sets opens details so the user chooses the actual copy to remove.

**Loose parts** searches catalog IDs/names, with color selection. Repeated additions accumulate, editing sets the total, and zero removes an entry. Loose-only collections work with matching and planning. Loaded unknown sets, parts/colors, changed inventory versions, and invalid quantities remain visible for correction. They block calculations and saving instead of being silently discarded.

## Firebase configuration

The dedicated Firebase project is **`rebuilt-4c9a4`**. Its `(default)` database uses **Standard edition in `us-east1`**, with the free tier active. Email/password sign-in is enabled, and the repository’s ownership Rules and indexes are deployed. `.firebaserc` selects this project. The local `.streamlit/secrets.toml` contains its Web API configuration and is ignored by Git. Application hosting remains separate; the app has not been published. Guest features still work without configuration.

To configure another environment or deploy the application:

1. Use the dedicated Rebuilt project, or create/select another dedicated project. Enable **Authentication → Email/Password**. Signup uses `accounts:signUp` and immediately requires an ID token and refresh token; the app never requests a verification email. Recovery, OAuth, remember-me, and verification flows are outside scope.
2. For a new project, create a Cloud Firestore database and deploy the repository’s `firestore.rules` and `firestore.indexes.json` to that dedicated project. For `rebuilt-4c9a4`, these are already deployed; use `npx -y firebase-tools@latest deploy --only auth,firestore --project rebuilt-4c9a4 --account YOUR_GOOGLE_EMAIL` for configuration updates. Do not deploy into an unrelated project or enable billing without approval. The bundled SQLite catalog stays local and read-only.
3. Set `FIREBASE_PROJECT_ID` and `FIREBASE_API_KEY` in the environment or copy `.streamlit/secrets.toml.example` to the ignored `.streamlit/secrets.toml`. In Streamlit Community Cloud use the same secrets. The API key is the project’s Firebase Web API key. No service-account key or Admin SDK is used for application operations.
4. Verify signup, Save, logout, login, Load, conflicts, and two-user isolation before application deployment. On October 15, 2026, these checks passed against the hosted `rebuilt-4c9a4` project using disposable accounts. Rename/name release, independent Save as, revision conflicts, and denied guest/cross-user access were checked through the real APIs; login → Save → sign out → login → Load also passed through the redesigned Streamlit interface. Test accounts and inventory documents were removed. Initial permission errors during provisioning stopped after the new Firebase configuration propagated.

Firebase REST calls carry the signed-in user’s ID token, so Firestore Security Rules enforce ownership. ID/refresh tokens live only in the individual server session, refresh on demand, and are cleared on sign out. Password inputs and component request bodies are scrubbed after submission. Only public catalog data is globally cached. A storage outage preserves the local draft and guest calculations.

Each collection is one complete snapshot under `users/{uid}/collections/{uuid}`, with revision, catalog fingerprint, owner, name, and server-controlled creation/update timestamps. A companion hashed, lowercase name reservation under `users/{uid}/names/{hash}` enforces case-insensitive uniqueness. Saves and renames commit the snapshot and reservations together, using Firestore update-time preconditions plus expected revisions. A stale write preserves local work and offers Reload or Save as. Deletes remove the snapshot and name reservation in one commit. Copies/adjustments/loose pieces are inside the owned snapshot; all independent child paths are denied by Rules.

Snapshots are limited to **750,000 UTF-8 bytes** to leave headroom under Firestore’s document limit. Oversized saves fail before writing and preserve the draft; split them into smaller collections. Names allow 1–100 characters. These limits apply to cloud saves, while guest accounting remains local. The payload is excluded from Firestore indexes. See [Firebase’s user-token REST authorization](https://firebase.google.com/docs/firestore/use-rest-api), [atomic writes](https://firebase.google.com/docs/firestore/manage-data/transactions), and [document limits](https://firebase.google.com/docs/firestore/quotas).

## Minimum-dismantling plans

Open a recommendation with **View build**, then select **Plan this build**. No optimizer runs during ordinary candidate searches. Plans list selected physical copy labels/UUIDs, source-grouped picking lists, loose pieces used, requested/supplied colors, substitutions, and shortages. Plans are advisory and never consume, reserve, or save pieces.

The pure API is `plan_build(catalog, collection, target_set_num, mode, time_limit_seconds=5.0)` in `brickfinder/planner.py`. It first checks complete feasibility using unprotected copies plus loose parts. It does not optimize partial builds. Exact mode requires each part/color; flexible mode permits other colors of the same part ID. Prints and molds stay distinct.

OR-Tools CP-SAT minimizes `(required pieces + 1) × selected copies + substituted pieces`. It uses stable source order, seed 0, and one worker. A deterministic greedy complete plan provides a hint and timeout fallback. Every allocation is independently checked for exact target fulfillment and source capacity. Plans carry the actual catalog/collection snapshot and color mode; edits invalidate them. Loose-only zero-copy plans are valid and proven optimal.

Only proven optimal results are called minimum. Time-limited complete results say **“Best plan found; minimum not proven.”** Five seconds bounds solver search, not model preparation and validation. Large collections can create many variables. Solver/model errors produce an error result without unchecked allocations. See [CP-SAT solution statuses](https://developers.google.com/optimization/cp/cp_solver).

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
python scripts/benchmark_planner.py --output data/planner_results.json
```

Firebase integration and Security Rules checks require Node.js 22+ and Java 21+:

```bash
npm ci --ignore-scripts
npx firebase emulators:exec --only auth,firestore --project demo-rebuilt "node --test tests/test_rules.mjs && python -m unittest tests.test_firebase_emulator -v"
```

These use a demo project and disposable emulator accounts, with no hosted credentials. The ordinary Python suite skips the four emulator-only cases. Emulator tests cover immediate signup sessions, CRUD, rename/name release, Save as UUIDs, atomic failure, stale revisions, concurrent case-insensitive names, denied guest access, and cross-user parent/child attacks. Normal tests also cover dirty navigation, sign-out clearing, per-copy adjustments, loose-only matching, protected-only shortages, timeouts, and 40 generated exhaustive solver comparisons in both color modes. Node transport tests cover serialized requests, cancellation, message correlation, password scrubbing, and revision-conflict propagation.

To try account flows locally, start `npx firebase emulators:start --only auth,firestore --project demo-rebuilt`, then launch Streamlit with `FIREBASE_PROJECT_ID=demo-rebuilt`, `FIREBASE_API_KEY=emulator-key`, `FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099`, and `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080`. Both emulator hosts must be loopback addresses and configured together. Emulator data is temporary; no local test account belongs to a hosted project.

Tests cover quantities, duplicate sets, color allocation, printed parts, ranking, rounded percentages, version selection, nested inventories, spare exclusion, invalid inventories, read-only catalog access, expanded themes and identifier formats, recommendation boundaries, category/exclusion accounting, complete example builds in both color modes, Streamlit request handling, stable component identity, and browser transport queueing/cancellation.

Local measurements on Python 3.13.16 / Apple Silicon: the first flexible search including candidate loading took approximately 1.07 seconds; subsequent flexible searches approximately 0.25 seconds; exact searches approximately 0.08 seconds. These are local measurements, not a hosted latency guarantee. Reproduce them with the benchmark script; recorded results are in `data/demo_results.json`.

| Example collection | Theme | Owned sets | Complete flexible-color builds | Complete exact-color builds |
| --- | --- | ---: | ---: | ---: |
| Example 1 | Superheroes | 6 | 48 | 1 |
| Example 2 | City | 6 | 50 | 2 |
| Example 3 | Mixed themes | 6 | 72 | 6 |

Collections are defined once in `brickfinder/examples.py` and shared by the UI and benchmark. Each has at least two complete builds that need color changes as well as at least one complete exact-color build. Example 1 can build Quinjet (30162) in exact colors; Examples 2 and 3 can build Flexible Rails (7499) and Tracks (60205) in exact colors. Flexible-color counts include exact-color builds. Each result is evaluated independently, and owned sets are excluded.

The recorded planner benchmark (`data/planner_results.json`) measured 15 bundled-catalog targets on Python 3.13.16 / Apple Silicon. All proved optimal in **0.0014–0.0317 seconds**, requiring 1–6 physical copies. Greedy and optimized copy counts were equal on this small real-catalog sample. The separate A/B/C adversarial fixture improved from **3 greedy copies to 2 optimized copies**. These local timings are not hosted latency guarantees and do not imply average improvement on arbitrary collections. Reproduce with `python scripts/benchmark_planner.py`.

## Deploy

1. Push the app, package, tests, configuration, dependency file, and generated compressed catalog to GitHub. Do not push raw CSVs, virtual environments, caches, or credentials.
2. In [Streamlit Community Cloud](https://share.streamlit.io/), select **Create app**, the repository's `main` branch, and `app.py`.
3. In **Advanced settings**, choose **Python 3.13**. Guest mode needs no secrets. Optional cloud saves require the dedicated Firebase setup and configuration above.
4. Deploy, then verify a fresh browser session: load Example 1, find builds in exact colors, open a piece breakdown, switch to flexible colors, and follow an instruction link. `app.py` serves the redesigned frontend directly as a Streamlit component; do not deploy `frontend/index.html` as a separate app.
5. Make the deployed app viewable publicly if Community Cloud initially creates it as private.

GitHub Actions runs the tests on Python 3.13. To roll back, revert the relevant app/catalog commit in GitHub and redeploy the previous working state. Runtime exceptions appear in Streamlit's app logs.

## Assumptions and limits

- New copies start complete and unprotected; enter missing pieces and planner protection explicitly.
- Minifigure components count. Spare pieces do not.
- Part IDs, prints, stickers, and mold variants remain distinct. We do not infer mechanical compatibility or verify building geometry.
- Flexible colors can change the appearance of the finished build. The table gives one possible color allocation.
- Guest drafts last for the active session. Optional Firebase saves are explicit. Simultaneous-build planning, favorites, build history, pricing, custom models, generated instructions, and photo recognition are outside scope.
- Result images and instructions require internet access; inventory matching does not.

## Attribution

Catalog data and set-image links: [Rebrickable](https://rebrickable.com/downloads/). Building instructions: [LEGO](https://www.lego.com/en-us/service/building-instructions). See `DATA_SOURCE.md` for the downloaded data's permission statement and handling rules.

Independent portfolio project. Not affiliated with the LEGO Group or Rebrickable. LEGO is a trademark of the LEGO Group.

## Implementation workspace

The Firebase implementation is based on the preserved Rebuilt redesign, including its resizable divider and technical explanation dialog. The original `main` checkout was restored clean at `424d904`; feature work is on `codex/rebuilt-firebase` in the attached `rebuilt-firebase` worktree. The source `codex/frontend-redesign` worktree and its uncommitted frontend edits were left untouched.
