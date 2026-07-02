"""STATE Quant Engine - Main entry point."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from state_quant_engine.config.settings import Settings
from state_quant_engine.database.connection import init_db
from state_quant_engine.database.logging_setup import setup_logging
from state_quant_engine.ui.navigation import render_navigation


def main():
    """Main application entry point."""
    settings = Settings()
    setup_logging(
        log_path=settings.logging.path,
        level=settings.logging.level,
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
    )
    st.set_page_config(
        page_title=settings.app.name,
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_db(settings.database.path)
    render_navigation(settings)


if __name__ == "__main__":
    main()
