"""Dashboard page."""
from __future__ import annotations
from typing import Any
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from state_quant_engine.services.portfolio_service import PortfolioService
from state_quant_engine.services.scanner_service import ScannerService
from state_quant_engine.ui.components.metrics import metric_card
from state_quant_engine.ui.components.charts import heatmap_chart, allocation_pie


def _ver_badge(version_id: int, is_live: bool, name: str) -> str:
    if is_live:
        return '<span style="background:#00C853;color:#000;padding:2px 10px;border-radius:10px;font-size:0.8em;font-weight:700">🟢 LIVE</span>'
    return f'<span style="background:#FF6D00;color:#fff;padding:2px 10px;border-radius:10px;font-size:0.8em;font-weight:700">🧪 {name}</span>'


def render(settings: Any, version_id: int = 1) -> None:
    is_live = st.session_state.get("version_is_live", True)
    ver_name = st.session_state.get("version_name", "Live")

    st.markdown(
        f'<h1>Dashboard &nbsp; {_ver_badge(version_id, is_live, ver_name)}</h1>',
        unsafe_allow_html=True,
    )
    st.caption("Portfolio overview and market signals")

    scanner = ScannerService(settings)
    portfolio_svc = PortfolioService(settings)

    with st.spinner("Loading dashboard..."):
        if "scan_results" not in st.session_state:
            st.session_state.scan_results = []

        col_refresh, _ = st.columns([1, 5])
        with col_refresh:
            if st.button("Refresh Data", type="primary"):
                st.session_state.scan_results = scanner.run(version_id=version_id)
                st.rerun()

        results = st.session_state.scan_results
        summary = portfolio_svc.get_summary(results, version_id=version_id)

    st.subheader("Portfolio Metrics")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Portfolio Value", f"₹{summary.current_value:,.0f}", f"{summary.mtm_pct:+.2f}%")
    with c2:
        metric_card("Today's MTM", f"₹{summary.mtm:+,.0f}", "unrealized")
    with c3:
        metric_card("Capital Utilized", f"₹{summary.allocated:,.0f}", f"{summary.allocated/summary.total_capital*100:.1f}% of total")
    with c4:
        metric_card("Capital Available", f"₹{summary.available:,.0f}", "free capital")

    st.divider()
    st.subheader("Trade Signals")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.metric("BUY Signals", summary.buy_signals)
    with s2:
        st.metric("HOLD Signals", summary.hold_signals)
    with s3:
        st.metric("EXIT Signals", summary.exit_signals)

    if results:
        st.divider()
        st.subheader("Top 10 Ranked Assets")
        top10 = results[:10]

        _SIGNAL_STYLE = {
            "BUY":   {"bg": "#00C853", "fg": "#000000"},
            "HOLD":  {"bg": "#2979FF", "fg": "#FFFFFF"},
            "WATCH": {"bg": "#FF6D00", "fg": "#FFFFFF"},
            "EXIT":  {"bg": "#D50000", "fg": "#FFFFFF"},
            "ERROR": {"bg": "#AA00FF", "fg": "#FFFFFF"},
        }

        rows_html = []
        for r in top10:
            sig = _SIGNAL_STYLE.get(r.recommendation, {"bg": "#555", "fg": "#fff"})
            badge = (f'<span style="background:{sig["bg"]};color:{sig["fg"]};'
                     f'padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.85em">'
                     f'{r.recommendation}</span>')
            profit_color = "#00C853" if r.current_profit >= 0 else "#D50000"
            score_color = "#00C853" if r.score_pct >= 70 else ("#FF6D00" if r.score_pct >= 40 else "#D50000")
            rows_html.append(
                f"<tr>"
                f"<td style='text-align:center'>{r.rank}</td>"
                f"<td><b>{r.symbol}</b></td>"
                f"<td>{r.name}</td>"
                f"<td style='text-align:center'>{r.asset_type}</td>"
                f"<td style='text-align:right'>₹{r.price:.2f}</td>"
                f"<td style='text-align:center;color:{score_color};font-weight:700'>{r.score_pct:.1f}%</td>"
                f"<td style='text-align:center'>{badge}</td>"
                f"<td style='text-align:right;color:{profit_color};font-weight:700'>{r.current_profit:+.2f}%</td>"
                f"</tr>"
            )
        table_html = f"""
        <style>
          .sqe-dash-table {{ width:100%; border-collapse:collapse; font-size:0.9em; }}
          .sqe-dash-table th {{ background:#1e2a3a; color:#aac4e0; padding:8px 10px;
                                text-align:left; border-bottom:2px solid #2e3f55; }}
          .sqe-dash-table td {{ padding:7px 10px; border-bottom:1px solid #1e2a3a; vertical-align:middle; }}
          .sqe-dash-table tr:hover td {{ background:#1a2435; }}
        </style>
        <table class="sqe-dash-table">
          <thead><tr>
            <th>#</th><th>Symbol</th><th>Name</th><th>Type</th>
            <th>Price</th><th>Health %</th><th>Signal</th><th>Profit %</th>
          </tr></thead>
          <tbody>{"".join(rows_html)}</tbody>
        </table>
        """
        st.markdown(table_html, unsafe_allow_html=True)

        st.divider()
        col_heat, col_pie = st.columns(2)
        with col_heat:
            st.subheader("Health Score Heatmap")
            heatmap_chart(results)
        with col_pie:
            st.subheader("Portfolio Allocation")
            allocation_pie(summary)
    else:
        st.info("Click **Refresh Data** to load market data and run the scanner.")
