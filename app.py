"""Run the redesigned frontend with: python -m streamlit run app.py."""

from __future__ import annotations

import sqlite3

import streamlit as st
from streamlit.components.v1 import declare_component

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.component import COMPONENT_KEY, RESPONSE_KEY, component_response
from brickfinder.web import FRONTEND, FinderService

st.set_page_config(page_title="Rebuilt — More builds. Same bricks.", page_icon="🧱", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
[data-testid="stHeader"], [data-testid="stToolbar"] {display:none;}
[data-testid="stMain"] {overflow:hidden;}
[data-testid="stMainBlockContainer"] {max-width:none;padding:0;}
[data-testid="stVerticalBlock"] {gap:0;}
[data-testid="stCustomComponentV1"] {display:block;width:100%;height:100dvh;border:0;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def load_service(database):
    return FinderService(Catalog(database))


try:
    service = load_service(unpack_catalog())
except (OSError, ValueError, sqlite3.Error) as error:
    st.error(f"We couldn't open the set catalog. {error}")
    st.stop()


def respond_to_frontend():
    st.session_state[RESPONSE_KEY] = component_response(service, st.session_state[COMPONENT_KEY])


frontend = declare_component("rebuilt", path=str(FRONTEND))
frontend(response=st.session_state.get(RESPONSE_KEY), key=COMPONENT_KEY, on_change=respond_to_frontend, default=None)
