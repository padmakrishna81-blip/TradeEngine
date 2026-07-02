"""Health Parameters configuration page — Entry, Hold, Market (separate tabs)."""
from __future__ import annotations
from typing import Any
import json
import streamlit as st
import pandas as pd
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.health_parameter_repository import (
    HealthParameterRepository, SCOPE_ENTRY, SCOPE_HOLD,
)
from state_quant_engine.repositories.scan_strategy_repository import StrategyRepository


def render(settings: Any, version_id: int = 1) -> None:
    st.title("Health Parameters")
    st.caption(
        "**Entry Health** (Scanner → BUY/WAIT) and **Hold Health** (Portfolio → HOLD/AVG/EXIT) "
        "use separate parameter sets with different contribution rules."
    )

    tab_entry, tab_hold, tab_market = st.tabs([
        "📊 Entry Health (Scanner)", "📈 Hold Health (Portfolio)", "🌐 Market Health"
    ])

    with tab_entry:
        _render_scope_tab(settings, SCOPE_ENTRY, "Entry Health Score",
                          "Used by Scanner. Determines BUY vs WAIT for fresh positions. "
                          "Total weight normalises to 100%. Profit % is NOT used here.")

    with tab_hold:
        _render_scope_tab(settings, SCOPE_HOLD, "Hold Health Score",
                          "Used by Portfolio. Determines HOLD / AVG / EXIT for held positions. "
                          "**Profit %** parameter is included — set threshold = profit % that triggers exit review.")

    with tab_market:
        _render_market_params(settings)


def _render_scope_tab(settings: Any, scope: str, title: str, caption_text: str) -> None:
    st.subheader(title)
    st.caption(caption_text)

    session = get_session()
    try:
        hp_repo    = HealthParameterRepository(session)
        strat_repo = StrategyRepository(session)
        params     = hp_repo.get_by_scope(scope)
        strategies = strat_repo.get_all()

        if not params:
            st.warning(f"No {scope} parameters found. Click **Re-seed Defaults** in Settings → Advanced.")
            return

        # ── Import weights from strategy ──────────────────────────────────
        if strategies and scope == SCOPE_ENTRY:
            st.write("**Load weights from strategy**")
            load_opts = ["— keep current —"] + [s.name for s in strategies]
            load_from = st.selectbox("Strategy", load_opts, key=f"strat_load_{scope}")
            if load_from != "— keep current —":
                seed_strat = next((s for s in strategies if s.name == load_from), None)
                if seed_strat and st.button(f"Apply '{load_from}' weights", key=f"apply_{scope}",
                                             type="primary"):
                    seed_w = json.loads(seed_strat.parameters) if seed_strat.parameters else {}
                    for p in params:
                        w = seed_w.get(p.parameter_name, 0.0)
                        p.weight  = float(w)
                        p.enabled = float(w) > 0
                    session.commit()
                    st.success(f"Weights from '{load_from}' applied. Undefined params set to 0.")
                    st.rerun()
            st.divider()

        # ── Score thresholds (entry only) ─────────────────────────────────
        if scope == SCOPE_ENTRY:
            st.subheader("Score Thresholds")
            pr = settings.portfolio_rules
            c1, c2 = st.columns(2)
            with c1:
                buy_t = st.number_input("BUY threshold (%)", value=float(pr.entry_buy_threshold),
                                         min_value=50.0, max_value=95.0, step=1.0,
                                         help="Entry Health must reach this to generate BUY")
            with c2:
                st.info("Below BUY threshold → **WAIT**")
            st.divider()

        # ── Parameter table ───────────────────────────────────────────────
        st.subheader("Parameter Weights")
        param_data = [{"ID": p.id, "Parameter": p.parameter_name,
                        "Weight": p.weight, "Enabled": p.enabled,
                        "Threshold": p.threshold, "Description": p.description or ""}
                       for p in params]
        df     = pd.DataFrame(param_data)
        edited = st.data_editor(
            df,
            column_config={
                "ID":          st.column_config.NumberColumn("ID",       disabled=True),
                "Parameter":   st.column_config.TextColumn("Parameter",  disabled=True),
                "Weight":      st.column_config.NumberColumn("Weight",   min_value=0, max_value=100, step=1),
                "Enabled":     st.column_config.CheckboxColumn("Enabled"),
                "Threshold":   st.column_config.NumberColumn("Threshold", step=0.1,
                               help="For 'Profit %': profit % at which contribution = 100%"),
                "Description": st.column_config.TextColumn("Description"),
            },
            column_order=["Parameter", "Weight", "Enabled", "Threshold", "Description"],
            use_container_width=True, hide_index=True,
        )

        total_w = edited[edited["Enabled"]]["Weight"].sum()
        color   = "green" if 99 <= total_w <= 101 else "orange"
        st.caption(f"Total enabled weight: :{color}[**{total_w:.0f}**] (normalised to 100%)")

        if st.button(f"Save {title}", type="primary", key=f"save_{scope}"):
            for _, row in edited.iterrows():
                p = hp_repo.get_by_id(int(row["ID"]))
                if p:
                    p.weight      = float(row["Weight"])
                    p.enabled     = bool(row["Enabled"])
                    p.threshold   = float(row["Threshold"])
                    p.description = str(row["Description"])
            session.commit()

            if scope == SCOPE_ENTRY:
                from state_quant_engine.ui.pages.settings import _save_yaml
                settings.portfolio_rules.entry_buy_threshold = float(buy_t)
                _save_yaml({"portfolio_rules": {"entry_buy_threshold": float(buy_t)}})

            st.success(f"{title} parameters saved.")
            st.rerun()
    finally:
        session.close()


def _render_market_params(settings: Any) -> None:
    st.subheader("Market Health Parameters")
    st.caption(
        "3 parameters — VIX (40) + Breadth (40) + Nifty 200 DMA (20). "
        "Drives capital deployment multiplier (not stock selection)."
    )

    params = list(settings.market_health_parameters) or [
        {"name": "VIX",            "weight": 40, "enabled": True, "threshold": 20,
         "description": "India VIX — graduated scoring"},
        {"name": "Market Breadth", "weight": 40, "enabled": True, "threshold": 0.5,
         "description": "Fraction of stocks above 200 EMA"},
        {"name": "Nifty 200 DMA",  "weight": 20, "enabled": True, "threshold": 0,
         "description": "NIFTY 50 above its own 200 EMA"},
    ]

    df = pd.DataFrame([{"Parameter": p["name"], "Weight": p["weight"], "Enabled": p["enabled"],
                         "Threshold": p.get("threshold", 0), "Description": p.get("description", "")}
                        for p in params])
    edited = st.data_editor(
        df,
        column_config={
            "Parameter":   st.column_config.TextColumn("Parameter", disabled=True),
            "Weight":      st.column_config.NumberColumn("Weight",  min_value=0, max_value=100, step=1),
            "Enabled":     st.column_config.CheckboxColumn("Enabled"),
            "Threshold":   st.column_config.NumberColumn("Threshold", step=0.1),
            "Description": st.column_config.TextColumn("Description"),
        },
        use_container_width=True, hide_index=True,
    )
    total_w = edited[edited["Enabled"]]["Weight"].sum()
    c = "green" if 99 <= total_w <= 101 else "red"
    st.caption(f"Total weight: :{c}[**{total_w:.0f}**]")

    st.divider()
    st.subheader("Capital Deployment Tiers")
    tiers = list(settings.market_deploy_tiers) or [
        {"min": 80, "deploy_pct": 100, "label": "Full Deploy"},
        {"min": 60, "deploy_pct": 75,  "label": "75% Deploy"},
        {"min": 40, "deploy_pct": 50,  "label": "50% Deploy"},
        {"min":  0, "deploy_pct": 25,  "label": "25% / Hold Cash"},
    ]
    tier_df     = pd.DataFrame([{"Min Score %": t["min"], "Deploy %": t["deploy_pct"],
                                   "Label": t["label"]} for t in tiers])
    edited_tier = st.data_editor(
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
            for _, row in edited_tier.iterrows()
        ]
        st.success("Market health config updated in session. Restart to persist.")
