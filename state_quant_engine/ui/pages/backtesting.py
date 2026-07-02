"""Backtesting page."""
from __future__ import annotations
from typing import Any
from datetime import date, timedelta
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from state_quant_engine.backtest.backtester import run_backtest


def render(settings: Any, version_id: int = 1) -> None:
    st.title("Backtesting")
    st.caption("Simulate historical performance of trading strategies")

    with st.form("backtest_form"):
        col1, col2 = st.columns(2)
        with col1:
            symbol = st.text_input("Symbol", value="RELIANCE.NS")
            asset_type = st.selectbox("Asset Type", ["STOCK", "ETF"])
            capital = st.number_input("Capital (₹)", value=100000.0, min_value=10000.0, step=10000.0)
        with col2:
            start_date = st.date_input("Start Date", value=date.today() - timedelta(days=365))
            end_date = st.date_input("End Date", value=date.today())
            chunk_strategy = st.selectbox("Chunk Strategy", ["Equal", "Aggressive", "Conservative"])

        run_bt = st.form_submit_button("Run Backtest", type="primary")

    if run_bt:
        with st.spinner("Running backtest..."):
            result = run_backtest(
                symbol=symbol,
                asset_type=asset_type,
                capital=capital,
                start_date=start_date,
                end_date=end_date,
                chunk_strategy=chunk_strategy,
                settings=settings,
            )

        if result.error:
            st.error(f"Backtest failed: {result.error}")
            return

        st.divider()
        st.subheader("Results")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Trades", result.total_trades)
        c2.metric("Win Rate", f"{result.win_rate:.1f}%")
        c3.metric("CAGR", f"{result.cagr:.2f}%")
        c4.metric("Max Drawdown", f"{result.max_drawdown:.2f}%")

        c5, c6, c7 = st.columns(3)
        c5.metric("Sharpe Ratio", f"{result.sharpe:.2f}")
        c6.metric("Profit Factor", f"{result.profit_factor:.2f}")
        c7.metric("Final Equity", f"₹{result.final_equity:,.0f}")

        if result.trades:
            st.divider()
            st.subheader("Trade Log")
            trade_df = pd.DataFrame(result.trades)
            st.dataframe(trade_df, use_container_width=True, hide_index=True)

        if result.equity_curve:
            st.divider()
            st.subheader("Equity Curve")
            eq_df = pd.DataFrame(result.equity_curve)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=eq_df["date"], y=eq_df["equity"], mode="lines", name="Equity", line=dict(color="cyan")))
            fig.add_trace(go.Scatter(x=eq_df["date"], y=eq_df["benchmark"], mode="lines", name="Buy & Hold", line=dict(color="gray", dash="dash")))
            fig.update_layout(title="Equity Curve vs Buy & Hold", yaxis_title="Portfolio Value (₹)", height=400)
            st.plotly_chart(fig, use_container_width=True)

        if result.profit_curve:
            st.subheader("Profit Curve")
            pc_df = pd.DataFrame(result.profit_curve)
            fig2 = go.Figure(go.Bar(x=pc_df["trade"], y=pc_df["profit_pct"],
                                     marker_color=["green" if p >= 0 else "red" for p in pc_df["profit_pct"]]))
            fig2.update_layout(title="Per-Trade Profit/Loss %", yaxis_title="P&L %", height=300)
            st.plotly_chart(fig2, use_container_width=True)
