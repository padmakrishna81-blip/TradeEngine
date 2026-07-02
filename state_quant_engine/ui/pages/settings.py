"""Settings page."""
from __future__ import annotations
from typing import Any
import streamlit as st
import pandas as pd
import yaml
import os
from state_quant_engine.services.seed_service import seed_defaults
from state_quant_engine.engine.indicators.data_fetcher import get_cache
from state_quant_engine.config.settings import _MODULE_DIR


def _save_yaml(updates: dict) -> None:
    """Deep-merge `updates` dict into the YAML config file and re-read settings."""
    yaml_path = os.path.join(_MODULE_DIR, "default.yaml")
    with open(yaml_path, "r") as f:
        raw = yaml.safe_load(f) or {}

    def deep_merge(base: dict, patch: dict) -> dict:
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    deep_merge(raw, updates)
    with open(yaml_path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)


def render(settings: Any, version_id: int = 1) -> None:
    st.title("Settings")
    st.caption("Application configuration")

    tab_general, tab_capital, tab_alloc, tab_data, tab_advanced = st.tabs(
        ["General", "Capital & Profit", "Symbol Allocation", "Data", "Advanced"]
    )

    with tab_general:
        st.subheader("Market Settings")
        col1, col2 = st.columns(2)
        with col1:
            open_time = st.text_input("Market Open", value=settings.market.open_time)
            tz = st.text_input("Timezone", value=settings.market.timezone)
        with col2:
            close_time = st.text_input("Market Close", value=settings.market.close_time)
            theme = st.selectbox("Theme", ["dark", "light"], index=0 if settings.app.theme == "dark" else 1)

        if st.button("Save General Settings"):
            settings.market.open_time  = open_time
            settings.market.close_time = close_time
            settings.market.timezone   = tz
            settings.app.theme         = theme
            _save_yaml({
                "market": {"open_time": open_time, "close_time": close_time, "timezone": tz},
                "app":    {"theme": theme},
            })
            st.success("General settings saved.")

    with tab_capital:
        st.subheader("ETF Capital")
        etf_total  = st.number_input("ETF Total Capital (₹)", value=float(settings.etf_capital.total), step=100000.0)
        etf_chunks = st.number_input("ETF Number of Chunks", value=int(settings.etf_capital.num_chunks),
                                      min_value=1, max_value=10, step=1)
        etf_chunks = int(etf_chunks)

        st.write("**Chunk Allocation %** — how much of ETF capital each chunk uses")
        etf_chunk_pcts = []
        etf_triggers   = []
        cols = st.columns(etf_chunks)
        for i in range(etf_chunks):
            default_pct = settings.etf_capital.chunk_percentages[i] \
                if i < len(settings.etf_capital.chunk_percentages) else 20.0
            default_trig = settings.etf_capital.next_buy_triggers[i] \
                if i < len(settings.etf_capital.next_buy_triggers) else 1.0
            with cols[i]:
                etf_chunk_pcts.append(
                    st.number_input(f"Chunk {i+1} %", value=float(default_pct),
                                    min_value=1.0, max_value=100.0, step=1.0,
                                    key=f"etf_pct_{i}"))
                trig_label = "Entry" if i == 0 else f"Drop {i+1} %"
                etf_triggers.append(
                    st.number_input(trig_label, value=float(default_trig),
                                    min_value=0.1, max_value=20.0, step=0.1,
                                    help="% price drop below previous chunk to trigger this buy" if i > 0
                                         else "First chunk — entry trigger (not a drop)",
                                    key=f"etf_trig_{i}"))
        total_pct = sum(etf_chunk_pcts)
        color = "green" if 99 <= total_pct <= 101 else "red"
        st.caption(f"Total allocation: :{color}[**{total_pct:.0f}%**] (should sum to 100%)")

        st.divider()
        st.subheader("Stock Capital")
        stock_total  = st.number_input("Stock Total Capital (₹)", value=float(settings.stock_capital.total), step=100000.0)
        stock_max    = st.number_input("Max per Stock (₹)", value=float(settings.stock_capital.max_per_stock or 100000), step=10000.0)
        stock_num    = st.number_input("Max Stocks", value=int(settings.stock_capital.num_stocks or 10), min_value=1, max_value=50)
        stock_chunks = st.number_input("Stock Chunks per Position", value=int(settings.stock_capital.num_chunks),
                                        min_value=1, max_value=10, step=1)
        stock_chunks = int(stock_chunks)

        st.write("**Stock Chunk Allocation %** — per-chunk split of max-per-stock capital")
        stock_chunk_pcts = []
        stock_triggers   = []
        cols2 = st.columns(stock_chunks)
        for i in range(stock_chunks):
            default_pct  = settings.stock_capital.chunk_percentages[i] \
                if i < len(settings.stock_capital.chunk_percentages) else round(100/stock_chunks, 1)
            default_trig = settings.etf_capital.next_buy_triggers[i] \
                if i < len(settings.etf_capital.next_buy_triggers) else 1.0
            with cols2[i]:
                stock_chunk_pcts.append(
                    st.number_input(f"Chunk {i+1} %", value=float(default_pct),
                                    min_value=1.0, max_value=100.0, step=1.0,
                                    key=f"stk_pct_{i}"))
                trig_label = "Entry" if i == 0 else f"Drop {i+1} %"
                stock_triggers.append(
                    st.number_input(trig_label, value=float(default_trig),
                                    min_value=0.1, max_value=20.0, step=0.1,
                                    key=f"stk_trig_{i}"))
        stk_total_pct = sum(stock_chunk_pcts)
        stk_color = "green" if 99 <= stk_total_pct <= 101 else "red"
        st.caption(f"Total allocation: :{stk_color}[**{stk_total_pct:.0f}%**]")

        if st.button("Save Capital Settings"):
            settings.etf_capital.total               = etf_total
            settings.etf_capital.num_chunks          = etf_chunks
            settings.etf_capital.chunk_percentages   = etf_chunk_pcts
            settings.etf_capital.next_buy_triggers   = etf_triggers
            settings.stock_capital.total             = stock_total
            settings.stock_capital.max_per_stock     = stock_max
            settings.stock_capital.num_stocks        = stock_num
            settings.stock_capital.num_chunks        = stock_chunks
            settings.stock_capital.chunk_percentages = stock_chunk_pcts
            _save_yaml({
                "etf_capital": {
                    "total": etf_total, "num_chunks": etf_chunks,
                    "chunk_percentages": etf_chunk_pcts,
                    "next_buy_triggers": etf_triggers,
                },
                "stock_capital": {
                    "total": stock_total, "max_per_stock": stock_max,
                    "num_stocks": stock_num, "num_chunks": stock_chunks,
                    "chunk_percentages": stock_chunk_pcts,
                },
            })
            st.success("Capital settings saved.")

        st.divider()
        st.subheader("Profit Management")
        st.caption("Controls exit signal logic in Portfolio page.")
        pm = settings.profit_management
        col1, col2 = st.columns(2)
        with col1:
            pm_threshold = st.number_input(
                "Profit Threshold (%)",
                value=float(pm.profit_threshold), min_value=0.5, max_value=50.0, step=0.5,
                help="At this profit %, the system evaluates whether to exit, partially exit, or strong-hold.",
            )
            sh_health = st.number_input(
                "Strong Hold min Health (%)",
                value=float(pm.strong_hold_health_min), min_value=50.0, max_value=100.0, step=5.0,
                help="Health score must be >= this to qualify for STRONG HOLD override.",
            )
        with col2:
            sh_trend = st.selectbox(
                "Strong Hold Trend",
                ["Bullish", "Neutral"],
                index=0 if pm.strong_hold_trend == "Bullish" else 1,
                help="Trend must equal this value to qualify for STRONG HOLD.",
            )

        if st.button("Save Profit Management"):
            pm.profit_threshold       = pm_threshold
            pm.partial_exit_threshold = pm_threshold
            pm.full_exit_threshold    = pm_threshold
            pm.strong_hold_health_min = sh_health
            pm.strong_hold_trend      = sh_trend
            _save_yaml({
                "profit_management": {
                    "profit_threshold":       pm_threshold,
                    "partial_exit_threshold": pm_threshold,
                    "full_exit_threshold":    pm_threshold,
                    "strong_hold_health_min": sh_health,
                    "strong_hold_trend":      sh_trend,
                }
            })
            st.success("Profit management settings saved.")

    # ── Symbol Allocation tab ─────────────────────────────────────────────
    with tab_alloc:
        st.subheader("Symbol Capital Allocation")
        st.caption(
            "Assign what **% of the ETF pool** (or Stock pool) each symbol gets. "
            "Chunk size = symbol_allocation × chunk%. "
            "Symbols without an allocation default to equal split."
        )

        from state_quant_engine.database.connection import get_session
        from state_quant_engine.repositories.watchlist_repository import WatchlistRepository
        from state_quant_engine.repositories.symbol_allocation_repository import SymbolAllocationRepository

        session = get_session()
        try:
            wl_repo   = WatchlistRepository(session)
            alloc_repo = SymbolAllocationRepository(session)

            etf_items   = wl_repo.get_by_type("ETF")
            stock_items = wl_repo.get_by_type("STOCK")
            existing    = alloc_repo.get_all_as_dict()

            def _alloc_editor(items, asset_type: str, total_capital: float, key_prefix: str):
                if not items:
                    st.info(f"No {asset_type} symbols in watchlist.")
                    return []

                st.write(f"**{asset_type} Pool: ₹{total_capital:,.0f}**")
                rows = []
                for item in items:
                    pct = existing.get(item.symbol, 0.0)
                    rows.append({
                        "Symbol": item.symbol,
                        "Name": item.name or item.symbol,
                        "Allocation %": pct,
                        "Allocated ₹": round(total_capital * pct / 100, 0),
                    })
                df = pd.DataFrame(rows)
                edited = st.data_editor(
                    df,
                    column_config={
                        "Symbol":       st.column_config.TextColumn("Symbol", disabled=True),
                        "Name":         st.column_config.TextColumn("Name",   disabled=True),
                        "Allocation %": st.column_config.NumberColumn(
                            "Allocation %", min_value=0.0, max_value=100.0, step=0.5,
                            help="% of total pool capital assigned to this symbol"),
                        "Allocated ₹":  st.column_config.NumberColumn("Allocated ₹", disabled=True),
                    },
                    use_container_width=True, hide_index=True, key=f"{key_prefix}_editor",
                )
                total_pct = edited["Allocation %"].sum()
                color = "green" if 99 <= total_pct <= 101 else "orange" if total_pct < 99 else "red"
                st.caption(
                    f"Total allocated: :{color}[**{total_pct:.1f}%**]"
                    + (" ✓ (sums to ~100%)" if 99 <= total_pct <= 101 else
                       " ⚠ remaining will use equal-split fallback" if total_pct < 99 else
                       " ✗ over 100%! reduce some symbols")
                )
                return list(zip(
                    edited["Symbol"].tolist(),
                    edited["Allocation %"].tolist(),
                ))

            etf_allocs   = _alloc_editor(etf_items,   "ETF",
                                          settings.etf_capital.total,   "etf")
            st.divider()
            stock_allocs = _alloc_editor(stock_items, "STOCK",
                                          settings.stock_capital.total, "stk")

            if st.button("Save Allocations", type="primary"):
                for sym, pct in etf_allocs + stock_allocs:
                    atype = "ETF" if any(i.symbol == sym for i in etf_items) else "STOCK"
                    alloc_repo.upsert(sym, atype, float(pct))
                    # Also update in-memory settings
                    settings.symbol_allocations[sym] = float(pct)
                session.commit()
                st.success("Symbol allocations saved. Trade Engine will now use per-symbol capital sizing.")
        finally:
            session.close()

    with tab_data:
        st.subheader("Data Settings")
        period = st.selectbox("Download Period", ["3mo", "6mo", "1y", "2y", "5y"],
                               index=["3mo", "6mo", "1y", "2y", "5y"].index(settings.data.download_period))
        col_ttl, col_dd = st.columns(2)
        with col_ttl:
            cache_ttl = st.number_input("Cache TTL (minutes)", value=int(settings.data.cache_ttl_minutes), min_value=1, max_value=60)
        with col_dd:
            drawdown_days = st.number_input(
                "Default Drawdown Window (days)",
                value=int(settings.data.drawdown_days),
                min_value=5, max_value=504, step=1,
                help="Rolling N-day high used to compute drawdown. Override per-scan in Strategy Lab.",
            )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save Data Settings"):
                settings.data.download_period    = period
                settings.data.cache_ttl_minutes  = cache_ttl
                settings.data.drawdown_days      = int(drawdown_days)
                _save_yaml({
                    "data": {
                        "download_period":    period,
                        "cache_ttl_minutes":  int(cache_ttl),
                        "drawdown_days":      int(drawdown_days),
                    }
                })
                st.success(f"Data settings saved (drawdown window: {int(drawdown_days)} days).")
        with col2:
            if st.button("Clear Cache", type="secondary"):
                get_cache().clear()
                st.success("Cache cleared.")

    with tab_advanced:
        st.subheader("Database")
        st.write(f"Database path: `{settings.database.path}`")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Re-seed Defaults"):
                seed_defaults(settings)
                st.success("Default data seeded.")
        with col2:
            db_path = settings.database.path
            if st.button("Backup Database"):
                import shutil
                from datetime import datetime
                backup = db_path.replace(".db", f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
                if os.path.exists(db_path):
                    shutil.copy2(db_path, backup)
                    st.success(f"Backed up to {backup}")
                else:
                    st.warning("Database file not found.")

        st.divider()
        st.subheader("Logs")
        log_path = settings.logging.path
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.readlines()
            last_lines = log_content[-100:] if len(log_content) > 100 else log_content
            st.code("".join(last_lines), language="text")
        else:
            st.info("No log file found yet.")
