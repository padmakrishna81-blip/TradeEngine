"""Shared chart components."""
from __future__ import annotations
from typing import List, Any
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import streamlit as st


def heatmap_chart(results: List[Any]) -> None:
    """Render a health score heatmap for all scanned symbols."""
    if not results:
        st.write("No data available.")
        return
    df = pd.DataFrame([{"Symbol": r.symbol, "Score %": r.score_pct, "Signal": r.recommendation} for r in results])
    color_map = {"BUY": "green", "HOLD": "dodgerblue", "WATCH": "orange", "EXIT": "red", "ERROR": "purple"}
    colors = [color_map.get(sig, "gray") for sig in df["Signal"]]
    fig = go.Figure(go.Bar(
        x=df["Symbol"], y=df["Score %"],
        marker_color=colors,
        text=df["Score %"].map(lambda x: f"{x:.0f}"),
        textposition="outside",
    ))
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0), yaxis_range=[0, 110])
    st.plotly_chart(fig, use_container_width=True)


def allocation_pie(summary: Any) -> None:
    """Render portfolio allocation pie chart."""
    if not summary.positions:
        st.write("No open positions.")
        return
    df = pd.DataFrame(summary.positions)
    if df.empty:
        st.write("No position data.")
        return
    grouped = df.groupby("symbol")["value"].sum().reset_index()
    available_row = pd.DataFrame([{"symbol": "Available", "value": max(0, summary.available)}])
    grouped = pd.concat([grouped, available_row], ignore_index=True)
    fig = px.pie(grouped, values="value", names="symbol", hole=0.4)
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig, use_container_width=True)
