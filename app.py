"""Run with: python -m streamlit run app.py."""

from __future__ import annotations

import sqlite3
import time
from html import escape

import streamlit as st

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.coverage import OWNED_ONLY_CATEGORIES
from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.matching import color_change_rows, filter_matches, recommend, shortage_rows

st.set_page_config(page_title="Brick Finder · Build something new", page_icon="🧱", layout="wide")

st.markdown("""
<style>
.block-container {max-width:1180px;padding-top:5rem;padding-bottom:3rem;}
h1,h2,h3 {letter-spacing:-.035em;}
.eyebrow {color:#006D77;font-size:.78rem;font-weight:750;letter-spacing:.15em;margin-bottom:.8rem;}
.hero {font-size:clamp(2rem,5vw,3.5rem);line-height:1.08;font-weight:800;letter-spacing:-.05em;margin:0 0 1rem;}
.hero span {color:#006D77;}
.intro {color:#516469;font-size:1.05rem;max-width:680px;line-height:1.6;margin-bottom:1.3rem;}
.step {color:#006D77;font-size:.76rem;font-weight:750;letter-spacing:.13em;margin-bottom:.4rem;}
.result-label {font-weight:700;color:#006D77;}
.selected-set-name {display:flex;align-items:center;justify-content:center;gap:.45rem;flex-wrap:wrap;text-align:center;}
.copy-count {font-size:.8rem;font-weight:500;color:#516469;background:#EEEDE5;padding:.1rem .4rem;border-radius:5px;}
[class*="st-key-selected_set_"] {position:relative;padding:1.1rem 2.25rem 1rem;text-align:center;}
[class*="st-key-selected_set_"] p {text-align:center;}
[class*="st-key-details_"] {align-self:center;}
[class*="st-key-details_"] button {color:#006D77;font-size:.85rem;min-height:1.9rem;padding:.1rem .5rem;}
[class*="st-key-selected_set_"] [class*="st-key-remove_"] {position:absolute;top:.4rem;right:.4rem;width:auto;opacity:0;transition:opacity .15s ease;}
[class*="st-key-selected_set_"]:hover [class*="st-key-remove_"],
[class*="st-key-selected_set_"]:focus-within [class*="st-key-remove_"] {opacity:1;}
[class*="st-key-remove_"] button {width:1.8rem;min-width:1.8rem;height:1.8rem;min-height:1.8rem;padding:0;border:0;border-radius:50%;color:#516469;}
[class*="st-key-remove_"] button::before {content:"×";font-size:1.35rem;line-height:1;}
[class*="st-key-remove_"] button p {position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;}
[class*="st-key-remove_"] button:hover {color:#006D77;background:#EEEDE5;}
[class*="st-key-remove_"] button:focus-visible {outline:2px solid #006D77;outline-offset:2px;}
@media (hover:none), (pointer:coarse) {
    [class*="st-key-selected_set_"] {padding:1.3rem 3.25rem 1rem;}
    [class*="st-key-selected_set_"] [class*="st-key-remove_"] {opacity:1;}
    [class*="st-key-remove_"] button {width:2.75rem;min-width:2.75rem;height:2.75rem;min-height:2.75rem;}
}
@media (prefers-reduced-motion:reduce) {
    [class*="st-key-selected_set_"] [class*="st-key-remove_"] {transition:none;}
}
[data-testid="stMetric"] {background:#EEEDE5;padding:1rem;border-radius:12px;}
[data-testid="stImage"] img {border-radius:10px;max-height:180px;object-fit:contain;}
.st-key-set_details [data-testid="stImage"] img {max-height:340px;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px;}
.placeholder {height:150px;display:flex;align-items:center;justify-content:center;background:#EEEDE5;border-radius:10px;font-size:2rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Opening the piece catalog…")
def load_catalog(database):
    return Catalog(database)


try:
    catalog = load_catalog(unpack_catalog())
except (OSError, ValueError, sqlite3.Error) as error:
    st.error(f"We couldn't open the set catalog. {error}")
    st.stop()

st.session_state.setdefault("collection", {})
st.session_state.setdefault("results", None)
st.session_state.setdefault("result_page", 1)
st.session_state.setdefault("show_clear_confirmation", False)


def invalidate_results():
    st.session_state.results = None
    st.session_state.result_page = 1


def load_example(name):
    st.session_state.collection = {code: 1 for code in EXAMPLE_COLLECTIONS[name]}
    invalidate_results()


def add_set():
    code = st.session_state.selected_search_set
    st.session_state.collection[code] = st.session_state.collection.get(code, 0) + 1
    st.session_state.search_query = ""
    invalidate_results()


def remove_set(code):
    st.session_state.collection.pop(code, None)
    invalidate_results()


def clear_collection():
    st.session_state.collection = {}
    st.session_state.show_clear_confirmation = False
    invalidate_results()


def dismiss_clear_confirmation():
    st.session_state.show_clear_confirmation = False


@st.dialog("Clear collection?", on_dismiss=dismiss_clear_confirmation)
def confirm_clear_collection():
    st.write("Are you sure you want to remove all selected sets?")
    cancel, confirm = st.columns(2)
    with cancel:
        if st.button("Cancel", width="stretch"):
            dismiss_clear_confirmation()
            st.rerun()
    with confirm:
        if st.button("Yes, clear collection", type="primary", width="stretch"):
            clear_collection()
            st.rerun()


@st.dialog("Set details", width="large")
def show_set_details(code):
    lego_set = catalog.sets[code]
    with st.container(key="set_details"):
        st.subheader(lego_set.name)
        picture, info = st.columns([1.15, 1], gap="large")
        with picture:
            if lego_set.safe_image_url:
                st.image(lego_set.safe_image_url, caption=lego_set.name, width="stretch")
            else:
                st.markdown('<div class="placeholder" aria-label="Set image unavailable">🧱</div>',
                            unsafe_allow_html=True)
                st.caption("Set image unavailable.")
        with info:
            st.markdown(f"**Set number:** {lego_set.set_num}")
            st.markdown(f"**Year released:** {lego_set.year}")
            st.markdown(f"**Theme:** {lego_set.family}")
            st.markdown(f"**Pieces:** {lego_set.num_parts:,}")
            st.markdown(f"**Copies in collection:** {st.session_state.collection[code]}")
            if lego_set.category != "Building sets":
                st.markdown(f"**Category:** {lego_set.category}")
            st.link_button("Building instructions ↗", lego_set.instructions_url)
        if st.button("Close", key="close_set_details"):
            st.rerun()


def reset_page():
    st.session_state.result_page = 1


def show_more():
    st.session_state.result_page += 1


st.markdown('<div class="eyebrow">BRICK FINDER</div>', unsafe_allow_html=True)
st.markdown('<div class="hero">Your bricks.<br><span>More possibilities.</span></div>', unsafe_allow_html=True)
st.markdown('<div class="intro">Choose the LEGO sets you own. Discover other official sets you have pieces for, see exactly what is missing, and find their building instructions.</div>', unsafe_allow_html=True)

with st.expander("**No sets handy? Try an example collection.**", expanded=False):
    buttons = st.columns(3)
    for column, name in zip(buttons, EXAMPLE_COLLECTIONS):
        with column:
            st.button(name, on_click=load_example, args=(name,),
                      width="stretch", disabled=not all(c in catalog.sets for c in EXAMPLE_COLLECTIONS[name]))
    st.caption("Loading an example replaces the current selection.")

left, right = st.columns([1, 1.6], gap="large")
with left:
    st.markdown('<div class="step">01 / YOUR COLLECTION</div>', unsafe_allow_html=True)
    st.subheader("What do you have?")
    query = st.text_input("Search by set number or name", placeholder="Try 31124, Super Robot, or train", key="search_query")
    choices = catalog.search(query)
    if choices:
        with st.form("add_set_form"):
            chosen = st.selectbox("Matching sets", options=[s.set_num for s in choices],
                                  format_func=lambda code: f"{catalog.sets[code].name} · {code}",
                                  key="selected_search_set")
            st.caption(f"{catalog.sets[chosen].num_parts:,} pieces · {catalog.sets[chosen].year} · {catalog.sets[chosen].family}")
            if catalog.sets[chosen].category in OWNED_ONLY_CATEGORIES:
                st.caption("Owned sets only: this item's inventoried pieces can contribute to other builds.")
            elif catalog.sets[chosen].category != "Building sets":
                st.caption(catalog.sets[chosen].category + " · Part IDs remain distinct across building systems.")
            st.form_submit_button("Add to collection", type="primary", width="stretch", on_click=add_set)
    elif query.strip():
        st.info("No supported set matches that search. Try a shorter name or a set number. See Catalog & assumptions below for coverage.")
    else:
        st.caption(f"Search {len(catalog.sets):,} supported sets. Alternate inventory versions are handled automatically.")

    if st.session_state.collection:
        st.markdown("#### Selected sets")
        for code, quantity in list(st.session_state.collection.items()):
            lego_set = catalog.sets[code]
            with st.container(border=True, key=f"selected_set_{code}"):
                badge = f'<span class="copy-count">x{quantity}</span>' if quantity > 1 else ""
                st.markdown(f'<div class="selected-set-name"><strong>{escape(lego_set.name)}</strong>{badge}</div>',
                            unsafe_allow_html=True)
                st.caption(f"{code} · {lego_set.num_parts:,} pieces")
                if lego_set.category != "Building sets":
                    st.caption(lego_set.category)
                if st.button("Show details", key=f"details_{code}", type="tertiary"):
                    show_set_details(code)
                st.button(f"Remove {lego_set.name}", key=f"remove_{code}", on_click=remove_set, args=(code,),
                          type="tertiary", help="Remove this set from your collection.")
        if st.button("Clear collection"):
            st.session_state.show_clear_confirmation = True
        if st.session_state.show_clear_confirmation:
            confirm_clear_collection()
    else:
        st.caption("Your collection is empty. Add a set or load an example above.")

with right:
    st.markdown('<div class="step">02 / FIND YOUR NEXT BUILD</div>', unsafe_allow_html=True)
    st.subheader("See what your pieces can do")
    collection = dict(st.session_state.collection)
    metric_cols = st.columns(2)
    metric_cols[0].metric("Sets in collection", sum(collection.values()))
    metric_cols[1].metric("Available pieces", f"{sum(catalog.sets[c].num_parts * n for c, n in collection.items()):,}")

    find_builds = st.button("Find builds", type="primary", disabled=not collection, width="stretch")
    mode_label = st.radio("Match colors", ["Flexible colors", "Exact colors"], index=1, horizontal=True,
                          key="matching_mode", on_change=invalidate_results)
    mode = "flexible" if mode_label == "Flexible colors" else "exact"
    if mode == "flexible":
        st.caption("Use the same part IDs in any color. Printed parts and mold variants still need to match exactly.")
    else:
        st.caption("Every counted piece must have the required part ID and color. Exact matches can be scarce for small collections.")
    if find_builds:
        with st.spinner("Comparing your pieces with the catalog…"):
            started = time.perf_counter()
            st.session_state.results = recommend(catalog, collection, mode)
            st.session_state.elapsed = time.perf_counter() - started
            st.session_state.result_page = 1

    filter_cols = st.columns(2)
    with filter_cols[0]:
        minimum = st.slider("Minimum completion (%)", min_value=0, max_value=100, value=100,
                            step=1, key="minimum", on_change=reset_page)
    with filter_cols[1]:
        sizes = st.slider("Required pieces", min_value=20, max_value=1000, value=(20, 1000),
                          step=1, key="sizes", on_change=reset_page)

    matches = st.session_state.results
    if matches is None:
        st.info("Add your sets and select Find builds to see recommendations.")
    else:
        visible = filter_matches(matches, minimum, sizes)
        complete = sum(m.complete for m in visible)
        complete_label = "complete inventory" if complete == 1 else "complete inventories"
        st.markdown(f"**{len(visible):,} matches · {complete:,} {complete_label}**")
        st.caption(f"Compared {len(matches):,} sets in {st.session_state.elapsed:.2f}s. Each result is a separate build; they share the same available pieces.")
        if not visible:
            st.info("No matches meet these filters. Lower the completion threshold, add more sets, or try flexible colors.")
        for match in visible[:20 * st.session_state.result_page]:
            lego_set = match.lego_set
            with st.container(border=True):
                picture, details = st.columns([1, 2.1])
                with picture:
                    if lego_set.safe_image_url:
                        st.image(lego_set.safe_image_url, width="stretch")
                    else:
                        st.markdown('<div class="placeholder" aria-label="Set image unavailable">🧱</div>', unsafe_allow_html=True)
                with details:
                    st.caption(f"{lego_set.set_num} · {lego_set.family} · {lego_set.year}")
                    if lego_set.category != "Building sets":
                        st.caption(lego_set.category)
                    st.markdown(f"### {lego_set.name}")
                    st.markdown(f"**{match.display_percent}** of required pieces available · **{match.missing:,} missing**")
                    st.caption(f"{match.matched:,} / {match.required:,} required pieces")
                    if mode == "flexible":
                        st.caption(f"Original-color match: {match.exact_display_percent}")
                    if match.complete:
                        if mode == "flexible" and match.exact_matched != match.required:
                            st.success("All required part IDs available; colors may differ.")
                        else:
                            st.success("All required part IDs and colors available.")
                    instructions_label = ("Search official instructions ↗" if lego_set.instructions_url.endswith("building-instructions")
                                          else "Find official instructions ↗")
                    st.link_button(instructions_label, lego_set.instructions_url)
                if st.checkbox("Show piece breakdown", key=f"breakdown_{mode}_{lego_set.set_num}"):
                    shortages = shortage_rows(catalog, collection, match)
                    if shortages:
                        st.markdown("**Missing pieces**")
                        st.dataframe(shortages, hide_index=True, width="stretch")
                    else:
                        st.caption("No pieces are missing in the selected matching mode.")
                    if mode == "flexible":
                        substitutions = color_change_rows(catalog, collection, match)
                        if substitutions:
                            st.markdown("**Suggested color changes**")
                            st.caption("Exact colors are used first. Each remaining piece is allocated once; this is one possible color allocation.")
                            st.dataframe(substitutions, hide_index=True, width="stretch")
        if len(visible) > 20 * st.session_state.result_page:
            st.button("Show 20 more", on_click=show_more, width="stretch")

st.divider()
with st.expander("Catalog & assumptions"):
    st.markdown(f"""
    - **Coverage:** {len(catalog.sets):,} owned-set inventories and {len(catalog.candidates):,} recommendation candidates.
    - **Themes:** all themes qualify, subject to inventory validation and the category rules below.
    - **Candidates:** 2000–2026, 20–1,000 pieces. Owned sets have no year or piece-count limits.
    - **Set numbers:** promotional, magazine, alphanumeric IDs, and set variants are supported without a length restriction.
    - Source reference inventories ("Database Sets") are excluded because they do not describe physical sets.
    - Selected sets are assumed complete and available to dismantle. Minifigure parts count; spare pieces do not.
    - Every match uses the latest catalog inventory version. Printed parts, stickers, and mold variants are kept distinct.
    - Unsupported or inconsistent inventories are excluded. A catalog match does not independently verify building geometry.
    - Instructions open on LEGO's website; availability varies, especially for promotional sets. Alphanumeric IDs open the instruction search page. Set images describe the original colors.
    - Your collection lasts for this browser session. No account or API key is required.
    """)
    st.markdown("**Category coverage**")
    st.dataframe([
        {"Category": row["category"], "Selectable owned sets": row["owned_sets"],
         "Recommendations": row["candidate_sets"], "Treatment": row["policy"]}
        for row in catalog.metadata["category_coverage"]
    ], hide_index=True, width="stretch")
    st.markdown("**Coverage by theme**")
    st.dataframe([
        {"Theme": row["family"], "Category": row["category"],
         "Selectable owned sets": row["owned_sets"], "Recommendations": row["candidate_sets"],
         "Invalid inventories": row["invalid_sets"], "Excluded reference records": row["excluded_by_policy"]}
        for row in catalog.metadata["theme_coverage"]
    ], hide_index=True, width="stretch")
    st.caption(f"Catalog prepared {catalog.metadata['built_at'][:10]}. {len(catalog.metadata['families']):,} included themes. "
               f"{catalog.metadata['skipped_sets']:,} source inventories excluded by validation; "
               f"{catalog.metadata['excluded_by_policy']:,} database reference records excluded.")
    st.markdown("Data and set images: [Rebrickable](https://rebrickable.com/downloads/). Instructions: [LEGO](https://www.lego.com/en-us/service/building-instructions). Independent portfolio project; not affiliated with the LEGO Group or Rebrickable.")
