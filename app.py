"""STATE Quant Engine - Main entry point."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

st.set_page_config(
    page_title="STATE Quant Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from state_quant_engine.config.settings import Settings
from state_quant_engine.database.connection import init_db
from state_quant_engine.database.logging_setup import setup_logging
from state_quant_engine.auth import check_auth
from state_quant_engine.ui.navigation import render_navigation


def main():
    settings = Settings()
    setup_logging(
        log_path=settings.logging.path,
        level=settings.logging.level,
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
    )
    # DB must be ready before auth (login queries app_user table)
    init_db(settings.database.path)

    if not check_auth():
        return

    render_navigation(settings)


if __name__ == "__main__":
    main()
