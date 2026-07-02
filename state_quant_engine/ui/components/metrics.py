"""Shared metric card component."""
from __future__ import annotations
import streamlit as st


def metric_card(label: str, value: str, delta: str = "") -> None:
    """Render a styled metric card."""
    st.metric(label=label, value=value, delta=delta if delta else None)
