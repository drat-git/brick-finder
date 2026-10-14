"""Run with: python -m streamlit run app.py."""

from __future__ import annotations

import sqlite3
import time
from html import escape

import streamlit as st

from brickfinder.catalog import Catalog, unpack_catalog
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
.selected-set-name {display:flex;align-items:center;gap:.45rem;flex-wrap:wrap;}
.copy-count {font-size:.8rem;font-weight:500;color:#516469;background:#EEEDE5;padding:.1rem .4rem;border-radius:5px;}
[data-testid="stMetric"] {background:#EEEDE5;padding:1rem;border-radius:12px;}
[data-testid="stImage"] img {border-radius:10px;max-height:180px;object-fit:contain;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px;}
.placeholder {height:150px;display:flex;align-items:center;justify-content:center;background:#EEEDE5;border-radius:10px;font-size:2rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Opening the piece catalog…")
def load_catalog():
    return Catalog(unpack_catalog())


try:
    catalog = load_catalog()
except (OSError, ValueError, sqlite3.Error) as error:
    st.error(f"We couldn't open the set catalog. {error}")
    st.stop()

PRESETS = {
    "Classic": ["11021-1", "11036-1"],
    "Creator": ["31124-1", "31125-1", "31128-1"],
    "City": ["60312-1", "60333-1", "60337-1"],
}
st.session_state.setdefault("collection", {})
st.session_state.setdefault("results", None)
st.session_state.setdefault("result_page", 1)
st.session_state.setdefault("show_clear_confirmation", False)


def invalidate_results():
    st.session_state.results = None
    st.session_state.result_page = 1


def load_example(name):
    st.session_state.collection = {code: 1 for code in PRESETS[name]}
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


def reset_page():
    st.session_state.result_page = 1


def show_more():
    st.session_state.result_page += 1


st.markdown('<div class="eyebrow">BRICK FINDER / A NEW BUILD STARTS HERE</div>', unsafe_allow_html=True)
st.markdown('<div class="hero">Your bricks.<br><span>More possibilities.</span></div>', unsafe_allow_html=True)
st.markdown('<div class="intro">Choose the LEGO sets you own. Discover other official sets you have pieces for, see exactly what is missing, and find their building instructions.</div>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("**No sets handy? Try an example collection.**")
    buttons = st.columns(3)
    for column, name in zip(buttons, PRESETS):
        with column:
            st.button(f"Load {name} example", on_click=load_example, args=(name,),
                      width="stretch", disabled=not all(c in catalog.sets for c in PRESETS[name]))
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
            st.form_submit_button("Add to collection", type="primary", width="stretch", on_click=add_set)
    elif query.strip():
        st.info("No supported set matches that search. Try a shorter name or a set number. See Catalog & assumptions below for coverage.")
    else:
        st.caption(f"Search {len(catalog.sets):,} supported sets. Alternate inventory versions are handled automatically.")

    if st.session_state.collection:
        st.markdown("#### Selected sets")
        for code, quantity in list(st.session_state.collection.items()):
            lego_set = catalog.sets[code]
            with st.container(border=True):
                badge = f'<span class="copy-count">x{quantity}</span>' if quantity > 1 else ""
                st.markdown(f'<div class="selected-set-name"><strong>{escape(lego_set.name)}</strong>{badge}</div>',
                            unsafe_allow_html=True)
                st.caption(f"{code} · {lego_set.num_parts:,} pieces")
                st.button("Remove", key=f"remove_{code}", on_click=remove_set, args=(code,), width="stretch")
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
    metric_cols[0].metric("Set copies", sum(collection.values()))
    metric_cols[1].metric("Available pieces", f"{sum(catalog.sets[c].num_parts * n for c, n in collection.items()):,}")

    mode_label = st.radio("Match colors", ["Flexible colors", "Exact colors"], horizontal=True,
                          key="matching_mode", on_change=invalidate_results)
    mode = "flexible" if mode_label == "Flexible colors" else "exact"
    if mode == "flexible":
        st.caption("Use the same part IDs in any color. Printed parts and mold variants still need to match exactly.")
    else:
        st.caption("Every counted piece must have the required part ID and color. Exact matches can be scarce for small collections.")
    if st.button("Find builds", type="primary", disabled=not collection, width="stretch"):
        with st.spinner("Comparing your pieces with the catalog…"):
            started = time.perf_counter()
            st.session_state.results = recommend(catalog, collection, mode)
            st.session_state.elapsed = time.perf_counter() - started
            st.session_state.result_page = 1

    filter_cols = st.columns(2)
    with filter_cols[0]:
        minimum = st.slider("Minimum completion (%)", min_value=0, max_value=100, value=80,
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
                    st.link_button("Find official instructions ↗", lego_set.instructions_url)
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
    - **Families:** {', '.join(catalog.metadata['families'])}.
    - **Candidates:** regular four- or five-digit set numbers, 2000–2026, 20–1,000 pieces. Owned sets can be older or larger.
    - Selected sets are assumed complete and available to dismantle. Minifigure parts count; spare pieces do not.
    - Every match uses the latest catalog inventory version. Printed parts, stickers, and mold variants are kept distinct.
    - Unsupported or inconsistent inventories are excluded. A catalog match does not independently verify building geometry.
    - Instructions open on LEGO's website; availability varies. Set images describe the original colors.
    - Your collection lasts for this browser session. No account or API key is required.
    """)
    st.caption(f"Catalog prepared {catalog.metadata['built_at'][:10]}. {catalog.metadata['skipped_sets']:,} eligible inventories excluded by validation.")
    st.markdown("Data and set images: [Rebrickable](https://rebrickable.com/downloads/). Instructions: [LEGO](https://www.lego.com/en-us/service/building-instructions). Independent portfolio project; not affiliated with the LEGO Group or Rebrickable.")
