# Architecture and engineering decisions

[Project overview](../README.md) · [Development guide](development.md) · [Catalog coverage](catalog.md)

## Runtime boundaries

Rebuilt serves a custom HTML/CSS/JavaScript interface as a Streamlit component. A correlated request/response bridge connects it to Python; the same frontend also runs through the standalone HTTP server in `brickfinder/web.py`. A serialized transport queue prevents concurrent component requests from overwriting an in-flight action. Cancellation, response correlation, credential scrubbing, and conflict propagation have dedicated transport tests.

Only the public catalog is globally cached. The lightweight `FinderService` is recreated on Streamlit reruns so a code deployment cannot retain an outdated service class. Each visitor has a private `UserSession` containing their draft, authentication, recommendation cache, and plans. The SQLite catalog is read-only. Firebase is needed only for accounts and saved collections.

## Inventory accounting

Each physical set copy has a UUID, optional label, catalog inventory version, missing-piece adjustments, and `keep_assembled` setting. Two copies of the same set can have different conditions. Loose pieces are stored separately by `(part ID, color ID)`.

For each part/color:

```text
available = sum(catalog quantity − missing quantity for each copy) + loose quantity
```

Missing pieces never create loose stock. New copies start complete and unprotected. Missing quantities cannot exceed a copy's catalog capacity; zero removes an adjustment. Minifigure components count, while spare pieces do not.

Unknown sets, parts/colors, inventory-version changes, and invalid quantities in a loaded collection remain visible for correction. They block calculations and saving instead of being silently dropped.

## Matching and ranking

- **Exact mode** compares quantities keyed by `(part ID, color ID)`.
- **Flexible mode** combines colors for each part ID. Prints and molds remain distinct.
- **Completion** is `sum(min(available, required)) / sum(required)`.
- **Ranking** sorts by completion descending, missing quantity ascending, required quantity descending, then set number.
- **Complete** means zero missing pieces. An incomplete result's display percentage is capped below 100%.

Flexible-color breakdowns reserve every exact-color match first, then allocate remaining colors to deficits. Each available piece is used at most once within a recommendation.

The interface defaults to exact colors and 100% completion. Owned set entries are excluded from recommendations. Display filters reuse the visitor's cached matches; inventory changes invalidate results and plans. Protection applies only to planning: protected copies still count in discovery, so a complete recommendation can have an unavailable plan.

## Minimum-dismantling planner

`plan_build(catalog, collection, target_set_num, mode, time_limit_seconds=5.0)` runs only after a build is selected. It checks complete feasibility using unprotected copies and loose stock; it does not optimize partial builds.

CP-SAT uses a Boolean selection variable for each copy and integer allocation variables for pieces from selected copies or loose stock. Allocation must satisfy every target quantity without exceeding a source's capacity. If the target requires `N` pieces, the objective is:

```text
minimize (N + 1) × selected copies + color substitutions
```

At most `N` pieces can be substituted, so one fewer opened copy takes priority over any color improvement. Exact mode prohibits substitutions. Loose-only plans can require zero copies.

A deterministic greedy plan supplies a solver hint and a complete timeout fallback. The solver uses stable source ordering, seed 0, and one worker. A separate validation pass checks target fulfillment, source capacities, and color allocation before any picking list is returned.

Only proven optimal results are called minimum. A complete result without an optimality proof says **Best plan found; minimum not proven**. The five-second limit bounds solver search, not model preparation and validation. Model/solver errors never return unchecked allocations. Plans include the inventory snapshot and color mode; edits invalidate them. Plans never consume, reserve, or save stock.

### Why greedy selection is insufficient

```text
Target: 2 × X + 2 × Y
A: 1 × X + 1 × Y
B: 2 × X
C: 2 × Y

A-first greedy path: A + B + C → 3 copies
Optimal selection:  B + C     → 2 copies
```

The fixture is in [`tests/test_planner.py`](../tests/test_planner.py). The same suite compares 40 generated cases against exhaustive search in both color modes, including protected copies and loose stock.

## Draft lifecycle and persistence

There is one active editable draft. Saving is explicit. New, Load, examples, and sign out offer Save / Discard / Cancel before replacing dirty work. Login preserves a guest draft. Save as creates a new collection UUID and new copy UUIDs. Clear empties the draft without deleting its saved cloud copy. Deleting a saved collection leaves an independent local draft.

Firebase email/password authentication uses the REST API. Firestore calls carry the user's ID token, so the checked-in Rules enforce ownership; application operations never use the Admin SDK. ID/refresh tokens remain in the visitor's server session, refresh on demand, and clear on sign out. Password inputs and component request bodies are scrubbed after submission. Inventory and authentication are not persisted in browser storage. Refresh starts a fresh draft and requires sign-in again.

```text
users/{uid}/collections/{collection UUID}   complete collection snapshot
users/{uid}/names/{normalized-name hash}   case-insensitive name reservation
```

A collection document includes revision, catalog fingerprint, owner, name, server-controlled timestamps, physical copies, adjustments, and loose pieces. Snapshots and name reservations commit atomically. Saves use expected revisions and Firestore update-time preconditions; a stale write preserves local work and offers Reload or Save as. Deletes remove the snapshot and reservation in one commit. Independently writable child paths are denied.

Names allow 1–100 characters. Snapshots are capped at **750,000 UTF-8 bytes**, leaving headroom under Firestore's document limit, and the payload is excluded from indexes. Oversized saves fail before writing and preserve the draft. Snapshot storage simplifies consistent saves, while limiting piece-level cloud queries and very large collections.

A cloud storage failure preserves the draft and leaves catalog matching available. Authentication failures return an actionable error without discarding collection edits. Rules and emulator tests cover guest denial, cross-user access, guessed child writes, concurrent name reservations, stale revisions, and atomic failure.

## Evidence and boundaries

[`data/demo_results.json`](../data/demo_results.json) records matching results; [`data/planner_results.json`](../data/planner_results.json) records greedy/optimized comparisons. The latter proves optimality on 15 catalog targets in approximately 1–32 ms locally on Python 3.13.16 / Apple Silicon. Greedy and optimized copy counts are equal on that small real-data sample; the separate adversarial fixture demonstrates a strict improvement. These are reproducible local observations, not hosted latency or general improvement guarantees.

Rebuilt validates parts lists and allocations, not assembly geometry. It does not infer mold compatibility or create instructions. Recommendations are independent alternatives rather than a simultaneous production plan. See the [development guide](development.md#benchmarks) to reproduce the measurements.
