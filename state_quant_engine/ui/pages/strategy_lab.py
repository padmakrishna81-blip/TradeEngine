"""Strategy Lab page."""
from __future__ import annotations
from typing import Any
import json
import streamlit as st
import pandas as pd
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.scan_strategy_repository import StrategyRepository
from state_quant_engine.repositories.health_parameter_repository import HealthParameterRepository
from state_quant_engine.services.scanner_service import ScannerService

_SIGNAL_STYLE = {
    "BUY":   {"bg": "#00C853", "fg": "#000000"},
    "HOLD":  {"bg": "#2979FF", "fg": "#FFFFFF"},
    "WATCH": {"bg": "#FF6D00", "fg": "#FFFFFF"},
    "EXIT":  {"bg": "#D50000", "fg": "#FFFFFF"},
    "ERROR": {"bg": "#AA00FF", "fg": "#FFFFFF"},
}

_TABLE_CSS = """
<style>
  .sqe-lab-table { width:100%; border-collapse:collapse; font-size:0.9em; }
  .sqe-lab-table th { background:#1e2a3a; color:#aac4e0; padding:8px 10px;
                      text-align:left; border-bottom:2px solid #2e3f55; white-space:nowrap; }
  .sqe-lab-table td { padding:7px 10px; border-bottom:1px solid #1e2a3a; vertical-align:middle; }
  .sqe-lab-table tr:hover td { background:#1a2435; }
</style>
"""


def _badge(sig: str) -> str:
    s = _SIGNAL_STYLE.get(sig, {"bg": "#555", "fg": "#fff"})
    return (f'<span style="background:{s["bg"]};color:{s["fg"]};'
            f'padding:3px 10px;border-radius:4px;font-weight:700;font-size:0.85em">{sig}</span>')


def _results_table(results: list) -> str:
    rows = []
    for r in results:
        score_color  = "#00C853" if r.score_pct >= 70 else ("#FF6D00" if r.score_pct >= 40 else "#D50000")
        profit_color = "#00C853" if r.current_profit >= 0 else "#D50000"
        dd     = f"{r.indicator.drawdown_pct:.1f}%" if r.indicator else "—"
        dd_win = str(r.indicator.drawdown_days) + "d" if r.indicator else "—"
        rows.append(
            f"<tr>"
            f"<td style='text-align:center'>{r.rank}</td>"
            f"<td><b>{r.symbol}</b></td>"
            f"<td>{r.name}</td>"
            f"<td style='text-align:center'>{r.asset_type}</td>"
            f"<td style='text-align:right'>₹{r.price:.2f}</td>"
            f"<td style='text-align:center;color:{score_color};font-weight:700'>{r.score_pct:.1f}%</td>"
            f"<td style='text-align:center'>{_badge(r.recommendation)}</td>"
            f"<td style='text-align:right;color:{profit_color};font-weight:700'>{r.current_profit:+.2f}%</td>"
            f"<td style='text-align:right'>{dd}</td>"
            f"<td style='text-align:center'>{dd_win}</td>"
            f"</tr>"
        )
    return (
        _TABLE_CSS
        + '<table class="sqe-lab-table"><thead><tr>'
        + "<th>#</th><th>Symbol</th><th>Name</th><th>Type</th>"
        + "<th>Price</th><th>Health %</th><th>Signal</th>"
        + "<th>Profit %</th><th>Drawdown</th><th>DD Window</th>"
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def render(settings: Any, version_id: int = 1) -> None:
    st.title("Strategy Lab")
    st.caption("Create, manage, and run named strategy profiles")

    session = get_session()
    try:
        strat_repo = StrategyRepository(session)
        hp_repo    = HealthParameterRepository(session)
        all_params  = hp_repo.get_all()
        # Deduplicate by name — strategy weights use entry-scope params as the canonical set
        seen = set()
        unique_params = []
        for p in all_params:
            if p.parameter_name not in seen:
                seen.add(p.parameter_name)
                unique_params.append(p)
        param_names = [p.parameter_name for p in unique_params]
        all_params  = unique_params   # replace reference used below

        strategies = strat_repo.get_all()
        active     = strat_repo.get_active()

        tab_list, tab_create, tab_run = st.tabs(["Strategies", "Create / Edit", "Run Strategy Scan"])

        # ── Tab 1: list ────────────────────────────────────────────────────
        with tab_list:
            if not strategies:
                st.info("No strategies found. Create one in the 'Create / Edit' tab.")
            else:
                for strat in strategies:
                    is_active = active and strat.id == active.id
                    badge_md  = " 🟢 **[ACTIVE]**" if is_active else ""
                    with st.expander(f"{strat.name}{badge_md}"):
                        c1, c2, c3 = st.columns(3)
                        c1.write(f"**Primary Exit Style:** {strat.exit_style}")
                        c1.caption("ℹ️ Informational — all exit strategies run. Configure active ones in Settings → exit_strategies.")
                        c2.write(f"**Drawdown Window:** {strat.drawdown_days} days")
                        c3.write(f"**Use Case:** {strat.use_case or '—'}")
                        c3.caption("When to apply this strategy (note only).")
                        st.caption(strat.description or "")
                        if strat.parameters:
                            params   = json.loads(strat.parameters)
                            pname_set = set(params.keys())
                            rows = []
                            for pname in param_names:
                                w = params.get(pname, 0.0)
                                rows.append({"Parameter": pname, "Weight": w, "Active": w > 0})
                            st.dataframe(
                                pd.DataFrame(rows),
                                column_config={"Active": st.column_config.CheckboxColumn("Active", disabled=True)},
                                use_container_width=True, hide_index=True,
                            )
                        col_activate, col_delete, _ = st.columns([1, 1, 5])
                        with col_activate:
                            if not is_active and st.button("Set Active", key=f"activate_{strat.id}"):
                                strat_repo.set_active(strat.id)
                                st.success(f"'{strat.name}' set as active.")
                                st.rerun()
                        with col_delete:
                            if st.button("Delete", key=f"delete_{strat.id}", type="secondary"):
                                strat_repo.delete(strat)
                                st.rerun()

        # ── Tab 2: create / edit ───────────────────────────────────────────
        with tab_create:
            st.subheader("Create / Edit Strategy")

            # ── Load-from-strategy dropdown ──────────────────────────────
            load_opts = ["— start blank —"] + [s.name for s in strategies]
            load_from = st.selectbox(
                "Load weights from existing strategy",
                load_opts,
                key="lab_load_from",
                index=0,
                help="Choose a strategy to pre-fill the weights below. Undefined parameters default to 0.",
            )

            # Resolve the seed weights from the selected strategy
            seed_weights: dict = {}
            seed_dd_days: int  = int(settings.data.drawdown_days)
            seed_exit:    str  = "trailing"
            seed_desc:    str  = ""
            seed_use:     str  = ""
            seed_name:    str  = ""

            if load_from != "— start blank —":
                seed_strat = next((s for s in strategies if s.name == load_from), None)
                if seed_strat:
                    seed_weights  = json.loads(seed_strat.parameters) if seed_strat.parameters else {}
                    seed_dd_days  = int(seed_strat.drawdown_days or settings.data.drawdown_days)
                    seed_exit     = seed_strat.exit_style or "trailing"
                    seed_desc     = seed_strat.description or ""
                    seed_use      = seed_strat.use_case or ""
                    seed_name     = seed_strat.name

            st.divider()

            form_suffix = load_from.replace(" ", "_").replace("—", "blank")
            with st.form(f"create_strategy_form_{form_suffix}"):
                col_l, col_r = st.columns(2)
                with col_l:
                    s_name = st.text_input("Strategy Name", value=seed_name)
                    s_desc = st.text_input("Description",   value=seed_desc)
                with col_r:
                    s_use = st.text_input(
                        "Use Case",
                        value=seed_use,
                        help="When to apply this strategy — e.g. 'Long-term ETF bull market', "
                             "'Swing trades on momentum breakouts'. Note only, no effect on calculations.",
                    )
                    exit_opts = ["trailing", "momentum", "health", "time", "risk"]
                    s_exit = st.selectbox(
                        "Primary Exit Style",
                        exit_opts,
                        index=exit_opts.index(seed_exit) if seed_exit in exit_opts else 0,
                        help="Informational label for your preferred exit approach. "
                             "All five exit strategies (trailing, momentum, health, time, risk) "
                             "still run — the first trigger wins. "
                             "Enable/disable individual strategies in Settings → exit_strategies YAML.",
                    )

                s_dd_days = st.number_input(
                    "Drawdown Window (days)",
                    min_value=5, max_value=504,
                    value=seed_dd_days, step=1,
                    help="Rolling N-day high for drawdown scoring stored with this strategy.",
                )

                st.write("**Parameter Weights** (0 = parameter disabled for this strategy)")
                st.caption("Undefined parameters from the loaded strategy default to **0**.")
                cols = st.columns(2)
                weights: dict = {}
                for i, pname in enumerate(param_names):
                    # seed from loaded strategy; unknown param → 0
                    default_w = float(seed_weights.get(pname, 0.0))
                    with cols[i % 2]:
                        weights[pname] = st.number_input(
                            pname, min_value=0.0, max_value=100.0,
                            value=default_w, step=5.0, key=f"w_{form_suffix}_{pname}",
                        )

                submitted = st.form_submit_button("Save Strategy", type="primary")
                if submitted and s_name:
                    strat_repo.upsert(
                        s_name, s_desc, weights, s_exit, s_use,
                        drawdown_days=int(s_dd_days),
                    )
                    st.success(f"Strategy '{s_name}' saved!")
                    st.rerun()

        # ── Tab 3: run scan ───────────────────────────────────────────────
        with tab_run:
            st.subheader("Run Scan with Strategy")
            if not strategies:
                st.warning("No strategies available.")
            else:
                strat_names  = [s.name for s in strategies]
                default_idx  = next(
                    (i for i, s in enumerate(strategies) if active and s.id == active.id), 0
                )
                selected_name = st.selectbox("Select Strategy", strat_names, index=default_idx)
                selected_strat = next((s for s in strategies if s.name == selected_name), None)

                # Show strategy's stored drawdown window, but allow override
                stored_dd = int(selected_strat.drawdown_days) if selected_strat else int(settings.data.drawdown_days)
                drawdown_days = st.number_input(
                    "Drawdown Window (days)",
                    min_value=5, max_value=504,
                    value=stored_dd, step=1,
                    help="Pre-filled from the strategy's saved setting. Change here to override for this scan only.",
                )

                if selected_strat:
                    # Preview the strategy's weights before running
                    with st.expander("Strategy details", expanded=False):
                        c1, c2, c3 = st.columns(3)
                        c1.write(f"**Primary Exit Style:** {selected_strat.exit_style}")
                        c1.caption("ℹ️ All exit strategies run; this is a label only.")
                        c2.write(f"**Stored DD Window:** {selected_strat.drawdown_days}d")
                        c3.write(f"**Use Case:** {selected_strat.use_case or '—'}")
                        c3.caption("When to apply — note only.")
                        if selected_strat.parameters:
                            p = json.loads(selected_strat.parameters)
                            rows = [{"Parameter": k, "Weight": v} for k, v in p.items() if v > 0]
                            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                if selected_strat and st.button("Run Strategy Scan", type="primary"):
                    params_raw = json.loads(selected_strat.parameters) if selected_strat.parameters else {}
                    strategy_params = [
                        {
                            "parameter_name": k,
                            "weight": v,
                            "enabled": v > 0,
                            "threshold": next(
                                (p.threshold for p in all_params if p.parameter_name == k), 0
                            ),
                        }
                        for k, v in params_raw.items()
                    ]
                    scanner = ScannerService(settings)
                    with st.spinner(f"Scanning with '{selected_name}' — drawdown window: {drawdown_days}d..."):
                        results = scanner.run(
                            strategy_params=strategy_params,
                            drawdown_days=int(drawdown_days),
                        )
                        st.session_state.scan_results = results
                        st.session_state.lab_results  = results
                    st.success(f"Scan complete — {len(results)} symbols evaluated.")

                results = st.session_state.get("lab_results", [])
                if results:
                    buy   = sum(1 for r in results if r.recommendation == "BUY")
                    hold  = sum(1 for r in results if r.recommendation == "HOLD")
                    watch = sum(1 for r in results if r.recommendation == "WATCH")
                    exit_ = sum(1 for r in results if r.recommendation == "EXIT")

                    c1, c2, c3, c4 = st.columns(4)
                    for col, count, label, bg, fg in [
                        (c1, buy,   "BUY",   "#00C853", "#000"),
                        (c2, hold,  "HOLD",  "#2979FF", "#fff"),
                        (c3, watch, "WATCH", "#FF6D00", "#fff"),
                        (c4, exit_, "EXIT",  "#D50000", "#fff"),
                    ]:
                        col.markdown(
                            f'<div style="background:{bg};color:{fg};text-align:center;'
                            f'padding:10px;border-radius:8px;font-weight:700;font-size:1.3em">'
                            f'{count}<br><span style="font-size:0.6em">{label}</span></div>',
                            unsafe_allow_html=True,
                        )

                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(_results_table(results), unsafe_allow_html=True)
    finally:
        session.close()
