"""Trade Engine page - manual trade execution with chunk logic."""
from __future__ import annotations
from typing import Any
from datetime import date
import streamlit as st
import pandas as pd
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.watchlist_repository import WatchlistRepository
from state_quant_engine.repositories.position_repository import PositionRepository
from state_quant_engine.engine.indicators.data_fetcher import fetch_current_price, fetch_ohlcv
from state_quant_engine.engine.indicators.technical import compute_indicators
from state_quant_engine.engine.health_score_engine import HealthScoreEngine
from state_quant_engine.engine.trade_engine import EntryEngine, HoldEngine, ExitEngine, ChunkEngine
from state_quant_engine.repositories.health_parameter_repository import HealthParameterRepository
from state_quant_engine.services.portfolio_service import PortfolioService


def render(settings: Any, version_id: int = 1) -> None:
    is_live  = st.session_state.get("version_is_live", True)
    ver_name = st.session_state.get("version_name", "Live")
    ver_badge = (
        '<span style="background:#00C853;color:#000;padding:2px 10px;border-radius:10px;font-size:0.8em;font-weight:700">🟢 LIVE</span>'
        if is_live else
        f'<span style="background:#FF6D00;color:#fff;padding:2px 10px;border-radius:10px;font-size:0.8em;font-weight:700">🧪 {ver_name}</span>'
    )
    st.markdown(f'<h1>Trade Engine &nbsp; {ver_badge}</h1>', unsafe_allow_html=True)

    if not is_live:
        st.info(f"📋 Paper-trade mode — all trades are recorded under **{ver_name}** and do not affect live positions.")

    st.caption("Signal evaluation and trade execution")

    session = get_session()
    try:
        wl_repo  = WatchlistRepository(session)
        pos_repo = PositionRepository(session)
        hp_repo  = HealthParameterRepository(session)

        symbols = [w.symbol for w in wl_repo.get_enabled()]
        if not symbols:
            st.warning("No enabled watchlist symbols found.")
            return

        selected = st.selectbox("Select Symbol", symbols)
        wl_item  = wl_repo.get_by_symbol(selected)
        if not wl_item:
            return

        col_eval, _ = st.columns([1, 5])
        with col_eval:
            evaluate = st.button("Evaluate", type="primary")

        eval_key = f"trade_eval_{selected}_{version_id}"
        if evaluate or st.session_state.get(eval_key):
            st.session_state[eval_key] = True

            with st.spinner(f"Fetching data for {selected}..."):
                df = fetch_ohlcv(selected, period=settings.data.download_period)
                ind = compute_indicators(df, selected)

                params = hp_repo.get_enabled()
                param_list = [{"parameter_name": p.parameter_name, "weight": p.weight,
                                "enabled": p.enabled, "threshold": p.threshold} for p in params]

                hs = settings.health_scores
                health_engine = HealthScoreEngine(param_list, hs.buy_threshold, hs.hold_threshold,
                                                    hs.watch_threshold, hs.exit_threshold)
                health = health_engine.compute(ind)

                open_positions = pos_repo.get_by_symbol(selected, version_id=version_id)
                chunks_held    = len(open_positions)

                chunk_engine = ChunkEngine(settings)
                entry_engine = EntryEngine(settings)
                hold_engine  = HoldEngine(settings)
                exit_engine  = ExitEngine(settings)

            st.subheader(f"Analysis: {selected}")
            col1, col2, col3 = st.columns(3)
            col1.metric("Current Price", f"₹{ind.price:.2f}")
            col2.metric("Health Score",  f"{health.score_pct:.1f}%")
            col3.metric("Signal",        health.recommendation)

            st.divider()
            st.subheader("Entry Evaluation")
            svc = PortfolioService(settings)
            summary = svc.get_summary(version_id=version_id)
            available = summary.available
            entry_signal = entry_engine.evaluate(ind, health, chunks_held, available, wl_item.asset_type)

            # Show symbol-specific capital allocation
            from state_quant_engine.engine.trade_engine import _symbol_allocated_capital
            sym_capital = _symbol_allocated_capital(selected, wl_item.asset_type, settings)
            st.caption(
                f"Symbol capital allocation: **₹{sym_capital:,.0f}** "
                f"({'configure in Settings → Symbol Allocation' if sym_capital == 0 else ''})"
            )
            sig_color = {"BUY": "green", "WAIT": "orange", "HOLD": "blue", "NO_TRADE": "red"}.get(entry_signal.action, "gray")
            st.markdown(f"**Entry Signal:** :{sig_color}[{entry_signal.action}]")
            st.write(entry_signal.reason)

            if open_positions:
                st.divider()
                st.subheader("Hold / Exit Evaluation")
                for pos in open_positions:
                    pos.current_price = ind.price
                    if ind.price > 0 and pos.buy_price > 0:
                        pos.current_profit = (ind.price - pos.buy_price) / pos.buy_price * 100
                    hold_signal  = hold_engine.evaluate(ind, health, pos)
                    holding_days = (date.today() - pos.buy_date).days if pos.buy_date else 0
                    exit_signal  = exit_engine.evaluate(ind, health, pos, holding_days)

                    with st.expander(f"Chunk {pos.chunk_no} | Buy: ₹{pos.buy_price:.2f} | P&L: {pos.current_profit:+.2f}%"):
                        c1, c2 = st.columns(2)
                        c1.write(f"**Hold Signal:** {hold_signal.action}")
                        c1.write(hold_signal.reason)
                        c2.write(f"**Exit Signal:** {exit_signal.action}")
                        c2.write(exit_signal.reason)

            st.divider()
            st.subheader("Execute Trade")

            # Derive smart defaults
            from state_quant_engine.engine.trade_engine import suggested_buy_quantity
            default_action = "BUY" if entry_signal.action == "BUY" else "EXIT" if open_positions else "BUY"
            actions = ["BUY", "EXIT", "PARTIAL_EXIT"]

            col_act, col_qty, col_price = st.columns(3)
            with col_act:
                action = st.selectbox("Action", actions,
                                      index=actions.index(default_action))
            with col_qty:
                if action == "BUY":
                    # Suggested quantity based on chunk size and remaining capital
                    sugg_qty = suggested_buy_quantity(
                        selected, wl_item.asset_type, chunks_held,
                        float(ind.price), settings,
                    )
                    # Show the chunk amount for clarity
                    cap_cfg    = settings.etf_capital if wl_item.asset_type == "ETF" else settings.stock_capital
                    chunk_pcts = cap_cfg.chunk_percentages
                    chunk_idx  = chunks_held
                    chunk_pct  = (chunk_pcts[chunk_idx] if chunk_idx < len(chunk_pcts) else chunk_pcts[-1])
                    from state_quant_engine.engine.trade_engine import _symbol_allocated_capital
                    sym_cap    = _symbol_allocated_capital(selected, wl_item.asset_type, settings)
                    chunk_amt  = sym_cap * chunk_pct / 100
                    st.caption(f"Chunk {chunks_held+1}: ₹{chunk_amt:,.0f} ({chunk_pct:.0f}% of ₹{sym_cap:,.0f})")
                    default_qty = sugg_qty
                else:
                    total_qty   = sum(p.quantity for p in open_positions)
                    default_qty = max(1, int(total_qty))
                qty = st.number_input("Quantity", min_value=1, value=max(1, default_qty), step=1)
            with col_price:
                exec_price = st.number_input("Execution Price", value=float(ind.price), min_value=0.01, step=0.05)

            remarks = st.text_input("Remarks (optional)")

            if st.button("Execute Trade", type="primary"):
                svc.execute_trade(selected, action, exec_price, float(qty), remarks, version_id=version_id)
                st.success(f"Trade executed: {action} {qty} {selected} @ ₹{exec_price:.2f} [{ver_name}]")
                st.session_state[eval_key] = False
                st.rerun()

            if open_positions:
                st.divider()
                st.subheader("Chunk Plan")
                avg_price = chunk_engine.compute_average_price(open_positions)
                if avg_price > 0:
                    max_c = settings.etf_capital.num_chunks if wl_item.asset_type == "ETF" else settings.stock_capital.num_chunks
                    if chunks_held < max_c:
                        next_buy = chunk_engine.get_next_buy_price(wl_item.asset_type, avg_price, chunks_held)
                        st.info(f"Avg cost: ₹{avg_price:.2f} | Next chunk trigger: ₹{next_buy:.2f}" if next_buy else "All chunks deployed")
    finally:
        session.close()
