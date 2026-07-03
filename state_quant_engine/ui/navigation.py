"""Streamlit navigation and page router."""
from __future__ import annotations
from typing import Any
import streamlit as st
from state_quant_engine.services.seed_service import seed_defaults
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.version_repository import VersionRepository
from state_quant_engine.ui.pages import (
    dashboard, watchlist, scanner,
    portfolio, trade_engine, reports, backtesting,
    settings, strategy_lab, versions, scoring_profiles,
)


PAGES = {
    "Dashboard":        dashboard,
    "Scoring Profiles": scoring_profiles,
    "Watchlist":        watchlist,
    "Scanner":          scanner,
    "Portfolio":        portfolio,
    "Trade Engine":     trade_engine,
    "Strategy Lab":     strategy_lab,
    "Reports":          reports,
    "Backtesting":      backtesting,
    "Settings":         settings,
    "Versions":         versions,
}


def _load_versions():
    session = get_session()
    try:
        repo = VersionRepository(session)
        return repo.get_all_ordered()
    finally:
        session.close()


def render_navigation(app_settings: Any) -> None:
    """Render sidebar navigation and dispatch to selected page."""
    seed_defaults(app_settings)
    # Make settings accessible to sub-pages via session state
    st.session_state["_settings"] = app_settings

    with st.sidebar:
        st.title("📈 SQE")
        st.caption("STATE Quant Engine")
        st.divider()

        # ── Version selector ─────────────────────────────────────────────
        ver_list = _load_versions()
        if not ver_list:
            # fallback: seed didn't run yet
            from state_quant_engine.repositories.version_repository import VersionRepository
            session = get_session()
            VersionRepository(session).seed_live()
            session.close()
            ver_list = _load_versions()

        ver_names   = [v.name for v in ver_list]
        ver_ids     = [v.id  for v in ver_list]
        live_name   = next((v.name for v in ver_list if v.is_live), ver_names[0])
        live_index  = ver_names.index(live_name)

        # Preserve selection across reruns
        if "version_id" not in st.session_state:
            st.session_state.version_id   = ver_ids[live_index]
            st.session_state.version_name = live_name
            st.session_state.version_is_live = True

        selected_name = st.selectbox(
            "Trading Version",
            ver_names,
            index=ver_names.index(st.session_state.version_name)
                  if st.session_state.version_name in ver_names else live_index,
            key="version_selector",
        )
        sel_ver = next(v for v in ver_list if v.name == selected_name)
        st.session_state.version_id      = sel_ver.id
        st.session_state.version_name    = sel_ver.name
        st.session_state.version_is_live = sel_ver.is_live

        # Coloured badge
        if sel_ver.is_live:
            st.markdown(
                '<span style="background:#00C853;color:#000;padding:3px 12px;'
                'border-radius:12px;font-weight:700;font-size:0.8em">🟢 LIVE</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<span style="background:#FF6D00;color:#fff;padding:3px 12px;'
                f'border-radius:12px;font-weight:700;font-size:0.8em">🧪 PAPER</span>',
                unsafe_allow_html=True,
            )

        st.divider()
        selection = st.radio(
            "Navigation",
            list(PAGES.keys()),
            label_visibility="collapsed",
        )
        st.divider()
        username = st.session_state.get("username", "")
        st.caption(f"👤 {username}  ·  v{app_settings.app.version}")
        if st.button("Sign Out", type="secondary", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    version_id = st.session_state.version_id
    page_module = PAGES[selection]
    page_module.render(app_settings, version_id)
