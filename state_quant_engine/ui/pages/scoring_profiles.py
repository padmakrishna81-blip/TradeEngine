"""Scoring Profiles page — manage per-asset-type, per-context scoring profiles."""
from __future__ import annotations
from typing import Any
import streamlit as st
import pandas as pd
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.scoring_profile_repository import (
    ScoringProfileRepository,
    PROFILE_STOCK_ENTRY, PROFILE_STOCK_HOLD,
    PROFILE_ETF_ENTRY, PROFILE_ETF_HOLD,
)


_CONTEXT_LABELS = {
    "entry": "📊 Entry (Scanner → BUY/WAIT)",
    "hold":  "📈 Hold (Portfolio → HOLD/AVG/EXIT)",
}
_ASSET_COLORS = {"ETF": "#2979FF", "STOCK": "#FF6D00"}


def render(settings: Any, version_id: int = 1) -> None:
    st.title("Scoring Profiles")
    st.caption(
        "Each instrument is scored using a dedicated profile based on asset type (ETF/STOCK) "
        "and context (entry scanner or hold portfolio). "
        "Four built-in profiles: **stock_entry, stock_hold, etf_entry, etf_hold**."
    )

    session = get_session()
    try:
        repo     = ScoringProfileRepository(session)
        profiles = repo.get_all_ordered()

        if not profiles:
            st.warning("No profiles found. Click **Re-seed Defaults** in Settings → Advanced.")
            return

        # ── Profile selector ──────────────────────────────────────────────
        prof_names = [f"{p.name}  ({p.asset_type} / {p.context})" for p in profiles]
        sel_label  = st.selectbox("Select Profile to View / Edit", prof_names, key="prof_sel")
        sel_idx    = prof_names.index(sel_label)
        prof       = profiles[sel_idx]

        at_color = _ASSET_COLORS.get(prof.asset_type, "#607D8B")
        st.markdown(
            f'<div style="display:flex;gap:10px;align-items:center;margin:6px 0">'
            f'<span style="background:{at_color};color:#fff;padding:3px 10px;border-radius:4px;font-weight:700">{prof.asset_type}</span>'
            f'<span style="background:#37474F;color:#fff;padding:3px 10px;border-radius:4px">'
            f'{_CONTEXT_LABELS.get(prof.context, prof.context)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        tab_params, tab_meta, tab_new, tab_market = st.tabs(
            ["Parameters", "Profile Settings", "Create New Profile", "🌐 Market Health"]
        )

        # ── Tab 1: Edit parameters ────────────────────────────────────────
        with tab_params:
            st.subheader(f"Parameters — {prof.name}")

            # ── Load from strategy (primary workflow) ─────────────────────
            from state_quant_engine.repositories.scan_strategy_repository import StrategyRepository
            from state_quant_engine.models.orm_models import ProfileParameter as PP
            import json

            strat_repo = StrategyRepository(session)
            strategies = strat_repo.get_all()

            if not strategies:
                st.warning("No strategies found in Strategy Lab. Create strategies there first, then load them here.")
            else:
                st.caption(
                    "Parameters are sourced from Strategy Lab. "
                    "Selecting a strategy **replaces the full parameter set** of this profile — "
                    "all parameters from the strategy are added (weight and enabled state copied). "
                    "Only the **Threshold** column is editable here."
                )
                load_opts = ["— select strategy —"] + [s.name for s in strategies]
                load_from = st.selectbox(
                    "Copy parameters from strategy",
                    load_opts,
                    key=f"strat_load_{prof.id}",
                    label_visibility="collapsed",
                )
                if load_from != "— select strategy —":
                    seed_strat = next((s for s in strategies if s.name == load_from), None)
                    if seed_strat and st.button(
                        f"Apply all parameters from '{load_from}'",
                        type="primary", key=f"apply_strat_{prof.id}",
                    ):
                        seed_w = json.loads(seed_strat.parameters) if seed_strat.parameters else {}

                        # Remove all existing parameters for this profile
                        session.query(PP).filter_by(profile_id=prof.id).delete()
                        session.flush()

                        # Add every parameter from the strategy with weight > 0
                        # Default thresholds and descriptions per known parameter
                        _defaults = {
                            "200 DMA":           (0,    "Price above 200-day moving average. e.g. Nifty at 23000, 200DMA at 21000 → +9.5% above = strong trend"),
                            "50 DMA":            (0,    "Price above 50-day moving average. Shorter-term trend confirmation. e.g. price 500, 50DMA 480 → above = bullish"),
                            "Drawdown":          (0,    "Pullback from N-day high. e.g. stock fell from ₹300 high to ₹282 = -6% drawdown. Ideal entry zone: 5-8%"),
                            "Relative Strength": (0,    "Stock return vs Nifty over 20 days. e.g. stock +8%, Nifty +3% → RS diff = +5% = outperforming"),
                            "Volume Spike":      (1.5,  "Today's volume / 20-day avg volume. e.g. avg 1M shares, today 2M = ratio 2.0. Threshold 1.5 = above avg"),
                            "RSI":               (50,   "RSI(14) momentum. 0-100 scale. Threshold 50 = above midpoint. Ideal entry zone 48-60. Below 30 = oversold"),
                            "MACD":              (0,    "MACD line vs signal line. Positive = bullish cross. e.g. MACD=0.45, Signal=0.30 → bullish momentum"),
                            "ADX":               (20,   "Trend strength (0-100). Threshold 20 = trending market. Above 25 = strong trend, below 20 = sideways"),
                            "ATR":               (0,    "Average True Range = daily volatility in ₹. e.g. ATR=15 on a ₹500 stock = 3% daily moves"),
                            "VIX":               (20,   "India VIX = fear index. Threshold 20 = below = calm market. Above 25 = fear, above 30 = panic"),
                            "Breadth":           (0.5,  "Fraction of stocks above 200 EMA. e.g. 0.65 = 65% of Nifty50 in uptrend. Below 0.4 = narrow rally"),
                            "Profit %":          (10.0, "Current MTM profit %. Threshold = target profit for exit review. e.g. 10 means at 10% profit, exit scoring activates"),
                        }
                        for pname, w in seed_w.items():
                            if float(w) > 0:
                                thr, desc = _defaults.get(pname, (0.0, ""))
                                session.add(PP(
                                    profile_id=prof.id,
                                    parameter_name=pname,
                                    weight=float(w),
                                    enabled=True,
                                    threshold=thr,
                                    description=desc,
                                ))
                        session.commit()
                        st.success(
                            f"Applied {len([v for v in seed_w.values() if float(v) > 0])} "
                            f"parameters from '{load_from}'. "
                            "Adjust thresholds below if needed, then save."
                        )
                        st.rerun()

            # ── Parameter table: Weight (read-only) + Threshold (editable) ─
            raw_params = (
                session.query(PP).filter_by(profile_id=prof.id)
                .order_by(PP.parameter_name).all()
            )

            if not raw_params:
                st.info("No parameters yet. Select a strategy above and click Apply.")
            else:
                st.divider()
                data = [{"Parameter": p.parameter_name,
                          "Weight": p.weight,
                          "Threshold": p.threshold,
                          "Description": p.description or ""}
                         for p in raw_params]
                df = pd.DataFrame(data)

                # ── HTML display table (read-only, full-width description) ──
                rows_html = []
                for p in raw_params:
                    rows_html.append(
                        f"<tr>"
                        f"<td style='font-weight:600;white-space:nowrap;padding:6px 10px'>{p.parameter_name}</td>"
                        f"<td style='text-align:center;padding:6px 10px'>{p.weight:.0f}%</td>"
                        f"<td style='text-align:center;padding:6px 10px'>{p.threshold}</td>"
                        f"<td style='font-size:0.82em;color:#bbb;padding:6px 10px'>{p.description or ''}</td>"
                        f"</tr>"
                    )
                total_w = df["Weight"].sum()
                wcolor  = "#00C853" if 99 <= total_w <= 101 else "#FF6D00"
                st.markdown(
                    f"""
                    <style>
                      .pp-table{{width:100%;border-collapse:collapse;font-size:0.9em}}
                      .pp-table th{{background:#1e2a3a;color:#aac4e0;padding:7px 10px;
                                    text-align:left;border-bottom:2px solid #2e3f55;white-space:nowrap}}
                      .pp-table td{{border-bottom:1px solid #1a2535;vertical-align:top}}
                      .pp-table tr:hover td{{background:#1a2435}}
                    </style>
                    <table class="pp-table">
                      <thead><tr>
                        <th style="width:14%">Parameter</th>
                        <th style="width:9%;text-align:center">Weight</th>
                        <th style="width:10%;text-align:center">Threshold</th>
                        <th>Description &amp; Example</th>
                      </tr></thead>
                      <tbody>{"".join(rows_html)}</tbody>
                    </table>
                    <p style="font-size:0.8em;margin-top:4px">
                      Total weight: <b style="color:{wcolor}">{total_w:.0f}%</b>
                      &nbsp;·&nbsp; {len(raw_params)} parameters
                    </p>
                    """,
                    unsafe_allow_html=True,
                )

                # ── Editable threshold inputs (compact, in one row per param) ──
                st.markdown("**Edit Thresholds:**")
                thresh_values = {}
                desc_values   = {}
                cols_per_row  = 3
                param_chunks  = [raw_params[i:i+cols_per_row]
                                  for i in range(0, len(raw_params), cols_per_row)]
                for chunk in param_chunks:
                    cols = st.columns(cols_per_row)
                    for col, p in zip(cols, chunk):
                        with col:
                            thresh_values[p.parameter_name] = st.number_input(
                                p.parameter_name,
                                value=float(p.threshold),
                                step=0.1,
                                key=f"thr_{prof.id}_{p.parameter_name}",
                            )

                if st.button("Save Thresholds", type="primary",
                              key=f"save_params_{prof.id}"):
                    for p in raw_params:
                        p.threshold = thresh_values.get(p.parameter_name, p.threshold)
                    session.commit()
                    st.success("Thresholds saved.")
                    st.rerun()

        # ── Tab 2: Profile settings ───────────────────────────────────────
        with tab_meta:
            st.subheader(f"Profile Settings — {prof.name}")
            is_builtin = prof.name in (PROFILE_STOCK_ENTRY, PROFILE_STOCK_HOLD,
                                        PROFILE_ETF_ENTRY, PROFILE_ETF_HOLD)
            if is_builtin:
                st.caption("ℹ️ Built-in profile — name and asset_type are fixed. Other fields are editable.")

            with st.form(f"meta_{prof.id}"):
                desc = st.text_input("Description", value=prof.description or "")
                bench = st.text_input("Benchmark Ticker", value=prof.benchmark or "^NSEI",
                                       help="Yahoo Finance ticker for relative strength benchmark")

                if prof.context == "entry":
                    c1, c2 = st.columns(2)
                    buy_thr = c1.number_input("BUY Threshold (%)", value=float(prof.buy_threshold),
                                               min_value=40.0, max_value=95.0, step=1.0)
                    c2.info("Below BUY threshold → **WAIT**")
                    st.write("**Hard Gates** (force WAIT if condition fails)")
                    g1, g2, g3 = st.columns(3)
                    gate_200   = g1.checkbox("Price above 200 DMA", value=prof.hard_gate_above_200dma)
                    gate_macd  = g2.checkbox("No strong MACD bearish", value=prof.hard_gate_no_bear_macd)
                    gate_dd    = g3.number_input("Max drawdown gate (%)",
                                                   value=float(prof.hard_gate_max_drawdown),
                                                   min_value=-50.0, max_value=0.0, step=1.0)
                    exit_thr = float(prof.exit_threshold)
                    avg_thr  = float(prof.avg_threshold)
                else:
                    c1, c2, c3 = st.columns(3)
                    exit_thr = c1.number_input("EXIT if health < (%)", value=float(prof.exit_threshold),
                                                min_value=10.0, max_value=70.0, step=1.0)
                    avg_thr  = c2.number_input("AVG if health ≥ (%)", value=float(prof.avg_threshold),
                                                min_value=30.0, max_value=90.0, step=1.0)
                    c3.info("Between thresholds → **HOLD**")
                    buy_thr = float(prof.buy_threshold)
                    gate_200  = False
                    gate_macd = False
                    gate_dd   = float(prof.hard_gate_max_drawdown)

                if st.form_submit_button("Save Profile Settings", type="primary"):
                    prof.description           = desc
                    prof.benchmark             = bench
                    prof.buy_threshold         = float(buy_thr)
                    prof.exit_threshold        = float(exit_thr)
                    prof.avg_threshold         = float(avg_thr)
                    prof.hard_gate_above_200dma = bool(gate_200)
                    prof.hard_gate_no_bear_macd = bool(gate_macd)
                    prof.hard_gate_max_drawdown = float(gate_dd)
                    session.commit()
                    st.success("Profile settings saved.")
                    st.rerun()

        # ── Tab 3: Create new profile ─────────────────────────────────────
        with tab_new:
            st.subheader("Create Custom Profile")
            st.caption("Create a custom scoring profile for a specific instrument category.")
            with st.form("new_profile_form"):
                c1, c2, c3 = st.columns(3)
                np_name    = c1.text_input("Profile Name", placeholder="e.g. midcap_entry")
                np_type    = c2.selectbox("Asset Type", ["STOCK", "ETF", "BOTH"])
                np_context = c3.selectbox("Context", ["entry", "hold"])
                np_desc    = st.text_input("Description")
                np_bench   = st.text_input("Benchmark", value="^NSEI")
                if st.form_submit_button("Create Profile", type="primary"):
                    if not np_name.strip():
                        st.error("Name is required.")
                    elif repo.get_by_name(np_name.strip()):
                        st.error(f"Profile '{np_name}' already exists.")
                    else:
                        repo.upsert_profile(
                            name=np_name.strip(), asset_type=np_type, context=np_context,
                            description=np_desc, benchmark=np_bench,
                        )
                        st.success(f"Profile '{np_name}' created. Add parameters in the Parameters tab.")
                        st.rerun()

        # ── Tab 4: Market Health (merged from old Health Parameters page) ──
        with tab_market:
            from state_quant_engine.ui.pages.health_parameters import _render_market_params
            _render_market_params(settings)

        # ── Profile overview table ────────────────────────────────────────
        st.divider()
        with st.expander("All Profiles Summary"):
            rows = []
            for p in profiles:
                param_count = (
                    session.query(__import__("state_quant_engine.models.orm_models",
                                             fromlist=["ProfileParameter"]).ProfileParameter)
                    .filter_by(profile_id=p.id, enabled=True).count()
                )
                rows.append({
                    "Profile": p.name, "Asset Type": p.asset_type, "Context": p.context,
                    "Benchmark": p.benchmark, "Parameters": param_count,
                    "BUY / EXIT Threshold": (
                        f"BUY ≥ {p.buy_threshold:.0f}%" if p.context == "entry"
                        else f"EXIT < {p.exit_threshold:.0f}%"
                    ),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    finally:
        session.close()
