"""Health Parameters configuration page."""
from __future__ import annotations
from typing import Any
import json
import streamlit as st
import pandas as pd
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.health_parameter_repository import HealthParameterRepository
from state_quant_engine.repositories.scan_strategy_repository import StrategyRepository


def render(settings: Any, version_id: int = 1) -> None:
    st.title("Health Parameters")
    st.caption("Stock Health Score (6 factors, 100 pts) · Market Health Score (3 factors, 100 pts)")

    tab_stock, tab_market = st.tabs(["📈 Stock Health Score", "🌐 Market Health Score"])

    with tab_stock:
        _render_stock_params(settings)

    with tab_market:
        _render_market_params(settings)


def _render_stock_params(settings: Any) -> None:
    """Edit per-stock health parameters (stored in DB)."""
    session = get_session()
    try:
        hp_repo    = HealthParameterRepository(session)
        strat_repo = StrategyRepository(session)
        params     = hp_repo.get_all()
        strategies = strat_repo.get_all()

        if not params:
            st.warning("No parameters found. Seed the database from Settings.")
            return

        # ── Strategy import ───────────────────────────────────────────────
        if strategies:
            st.subheader("Load Weights from Strategy")
            st.caption(
                "Choose a strategy to pre-fill the weight table below. "
                "Parameters not defined in the strategy are set to **0** and disabled."
            )
            load_opts  = ["— keep current weights —"] + [s.name for s in strategies]
            load_from  = st.selectbox("Strategy", load_opts, index=0, label_visibility="collapsed")

            if load_from != "— keep current weights —":
                seed_strat = next((s for s in strategies if s.name == load_from), None)
                if seed_strat and st.button(f"Apply '{load_from}' weights to Health Parameters", type="primary"):
                    seed_weights = json.loads(seed_strat.parameters) if seed_strat.parameters else {}
                    for param in params:
                        w = seed_weights.get(param.parameter_name, 0.0)
                        param.weight  = float(w)
                        param.enabled = float(w) > 0
                    session.commit()
                    st.success(
                        f"Weights from **{load_from}** applied. "
                        f"Parameters not in that strategy were set to 0 and disabled."
                    )
                    st.rerun()

            st.divider()

        # ── Score thresholds ──────────────────────────────────────────────
        st.subheader("Score Thresholds")
        hs = settings.health_scores
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            buy_t   = st.number_input("BUY Threshold (%)",   value=float(hs.buy_threshold),   min_value=0.0, max_value=100.0, step=1.0)
        with col2:
            hold_t  = st.number_input("HOLD Threshold (%)",  value=float(hs.hold_threshold),  min_value=0.0, max_value=100.0, step=1.0)
        with col3:
            watch_t = st.number_input("WATCH Threshold (%)", value=float(hs.watch_threshold), min_value=0.0, max_value=100.0, step=1.0)
        with col4:
            exit_t  = st.number_input("EXIT Threshold (%)",  value=float(hs.exit_threshold),  min_value=0.0, max_value=100.0, step=1.0)

        st.divider()

        # ── Parameter weight table ────────────────────────────────────────
        st.subheader("Parameter Weights")

        param_data = []
        for p in params:
            param_data.append({
                "ID":          p.id,
                "Parameter":   p.parameter_name,
                "Weight":      p.weight,
                "Enabled":     p.enabled,
                "Threshold":   p.threshold,
                "Description": p.description or "",
            })

        df     = pd.DataFrame(param_data)
        edited = st.data_editor(
            df,
            column_config={
                "ID":          st.column_config.NumberColumn("ID",          disabled=True),
                "Parameter":   st.column_config.TextColumn("Parameter",     disabled=True),
                "Weight":      st.column_config.NumberColumn("Weight",      min_value=0, max_value=100, step=1),
                "Enabled":     st.column_config.CheckboxColumn("Enabled"),
                "Threshold":   st.column_config.NumberColumn("Threshold",   step=0.1),
                "Description": st.column_config.TextColumn("Description"),
            },
            use_container_width=True,
            hide_index=True,
        )

        total_weight = edited[edited["Enabled"]]["Weight"].sum()
        st.caption(f"Total enabled weight: **{total_weight:.0f}** — health score is normalised to %")

        if st.button("Save Parameters", type="primary"):
            for _, row in edited.iterrows():
                param = hp_repo.get_by_id(int(row["ID"]))
                if param:
                    param.weight      = float(row["Weight"])
                    param.enabled     = bool(row["Enabled"])
                    param.threshold   = float(row["Threshold"])
                    param.description = str(row["Description"])
            session.commit()
            settings.health_scores.buy_threshold   = buy_t
            settings.health_scores.hold_threshold  = hold_t
            settings.health_scores.watch_threshold = watch_t
            settings.health_scores.exit_threshold  = exit_t
            st.success("Parameters saved successfully!")
            st.rerun()
    finally:
        session.close()


def _render_market_params(settings: Any) -> None:
    """Edit Market Health Score parameters (in-memory from YAML / settings)."""
    st.subheader("Market Health Parameters")
    st.caption(
        "These 3 parameters score overall market conditions. "
        "The score drives **how much capital** to deploy per chunk — "
        "not which stock to buy."
    )

    params = list(settings.market_health_parameters) or [
        {"name": "VIX",            "weight": 40, "enabled": True, "threshold": 20,
         "description": "India VIX — graduated scoring"},
        {"name": "Market Breadth", "weight": 40, "enabled": True, "threshold": 0.5,
         "description": "Fraction of stocks above 200 EMA"},
        {"name": "Nifty 200 DMA",  "weight": 20, "enabled": True, "threshold": 0,
         "description": "NIFTY 50 above its own 200 EMA"},
    ]

    df = pd.DataFrame([{
        "Parameter":   p["name"],
        "Weight":      p["weight"],
        "Enabled":     p["enabled"],
        "Threshold":   p.get("threshold", 0),
        "Description": p.get("description", ""),
    } for p in params])

    edited = st.data_editor(
        df,
        column_config={
            "Parameter":   st.column_config.TextColumn("Parameter", disabled=True),
            "Weight":      st.column_config.NumberColumn("Weight", min_value=0, max_value=100, step=1),
            "Enabled":     st.column_config.CheckboxColumn("Enabled"),
            "Threshold":   st.column_config.NumberColumn("Threshold", step=0.1),
            "Description": st.column_config.TextColumn("Description"),
        },
        use_container_width=True, hide_index=True,
    )
    total_w = edited[edited["Enabled"]]["Weight"].sum()
    color = "green" if 99 <= total_w <= 101 else "red"
    st.caption(f"Total weight: :{color}[**{total_w:.0f}**] (should sum to 100)")

    st.divider()
    st.subheader("Capital Deployment Tiers")
    st.caption("Market Health Score → deploy X% of planned chunk capital.")

    tiers = list(settings.market_deploy_tiers) or [
        {"min": 80, "deploy_pct": 100, "label": "Full Deploy"},
        {"min": 60, "deploy_pct": 75,  "label": "75% Deploy"},
        {"min": 40, "deploy_pct": 50,  "label": "50% Deploy"},
        {"min":  0, "deploy_pct": 25,  "label": "25% / Hold Cash"},
    ]
    tier_df = pd.DataFrame([{
        "Min Score %": t["min"],
        "Deploy %":    t["deploy_pct"],
        "Label":       t["label"],
    } for t in tiers])
    edited_tiers = st.data_editor(
        tier_df,
        column_config={
            "Min Score %": st.column_config.NumberColumn("Min Score %", min_value=0, max_value=100),
            "Deploy %":    st.column_config.NumberColumn("Deploy %",    min_value=0, max_value=100),
            "Label":       st.column_config.TextColumn("Label"),
        },
        use_container_width=True, hide_index=True,
    )

    if st.button("Save Market Health Config", type="primary"):
        settings.market_health_parameters = [
            {"name": row["Parameter"], "weight": float(row["Weight"]),
             "enabled": bool(row["Enabled"]), "threshold": float(row["Threshold"]),
             "description": str(row["Description"])}
            for _, row in edited.iterrows()
        ]
        settings.market_deploy_tiers = [
            {"min": int(row["Min Score %"]), "deploy_pct": float(row["Deploy %"]),
             "label": str(row["Label"])}
            for _, row in edited_tiers.iterrows()
        ]
        st.success("Market health config updated in session. Restart to persist.")
