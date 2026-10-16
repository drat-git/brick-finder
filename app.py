"""Run the redesigned frontend with: python -m streamlit run app.py."""

from __future__ import annotations

import sqlite3

import streamlit as st
from streamlit.components.v1 import declare_component

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.component import COMPONENT_KEY, RESPONSE_KEY, component_response
from brickfinder.web import FRONTEND, FinderService
from brickfinder.session import UserSession
from brickfinder.firebase_store import FirebaseConfig, CloudError

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
def load_catalog(database):
    return Catalog(database)


try:
    # Recreate the lightweight service so code updates cannot reuse an old class.
    service = FinderService(load_catalog(unpack_catalog()))
except (OSError, ValueError, sqlite3.Error) as error:
    st.error(f"We couldn't open the set catalog. {error}")
    st.stop()


def session_config():
    try:
        secrets = st.secrets.to_dict()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        secrets = {}
    try:
        return FirebaseConfig.read(secrets)
    except CloudError:
        return FirebaseConfig()  # Optional cloud configuration cannot disable guests.


if "rebuilt_private_session" not in st.session_state:
    st.session_state.rebuilt_private_session = UserSession(service.catalog, session_config())


def respond_to_frontend():
    request = st.session_state[COMPONENT_KEY]
    session = st.session_state.rebuilt_private_session
    if isinstance(request,dict) and request.get("path")=="/api/session" and (request.get("body") or {}).get("fresh"):
        if session.auth:
            session.auth.clear()
        session = UserSession(service.catalog,session_config())
        st.session_state.rebuilt_private_session = session
    try:
        st.session_state[RESPONSE_KEY] = component_response(service,request,session)
    finally:
        # Component widget state must not retain submitted credentials.
        if isinstance(request,dict) and isinstance(request.get("body"),dict):
            request["body"].pop("password",None)


frontend = declare_component("rebuilt", path=str(FRONTEND))
frontend(response=st.session_state.get(RESPONSE_KEY), key=COMPONENT_KEY, on_change=respond_to_frontend, default=None)
