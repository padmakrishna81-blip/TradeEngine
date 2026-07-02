"""Scanner page."""
from __future__ import annotations
from typing import Any
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from state_quant_engine.services.scanner_service import ScannerService

_SIGNAL_STYLE = {
    "BUY":  {"bg": "#00C853", "fg": "#000000"},
    "WAIT": {"bg": "#607D8B", "fg": "#FFFFFF"},
    "ERROR":{"bg": "#AA00FF", "fg": "#FFFFFF"},
}
_TREND_STYLE = {
    "Bullish":  {"bg": "#00C853", "fg": "#000"},
    "Bearish":  {"bg": "#D50000", "fg": "#fff"},
    "Neutral":  {"bg": "#607D8B", "fg": "#fff"},
    "N/A":      {"bg": "#37474F", "fg": "#aaa"},
    "Error":    {"bg": "#AA00FF", "fg": "#fff"},
}
_RISK_STYLE = {
    "SAFE":     {"bg": "#00897B", "fg": "#fff"},
    "VOLATILE": {"bg": "#F57C00", "fg": "#fff"},
    "RISKY":    {"bg": "#C62828", "fg": "#fff"},
    "N/A":      {"bg": "#37474F", "fg": "#aaa"},
    "Error":    {"bg": "#AA00FF", "fg": "#fff"},
}


def _badge(text: str, style_map: dict, default_bg: str = "#555") -> str:
    s = style_map.get(text, {"bg": default_bg, "fg": "#fff"})
    return (
        f'<span style="background:{s["bg"]};color:{s["fg"]};'
        f'padding:3px 10px;border-radius:4px;font-weight:700;font-size:0.82em">{text}</span>'
    )


def render(settings: Any, version_id: int = 1) -> None:
    is_live  = st.session_state.get("version_is_live", True)
    ver_name = st.session_state.get("version_name", "Live")
    ver_badge = (
        '<span style="background:#00C853;color:#000;padding:2px 10px;border-radius:10px;font-size:0.8em;font-weight:700">🟢 LIVE</span>'
        if is_live else
        f'<span style="background:#FF6D00;color:#fff;padding:2px 10px;border-radius:10px;font-size:0.8em;font-weight:700">🧪 {ver_name}</span>'
    )
    st.markdown(f'<h1>Scanner &nbsp; {ver_badge}</h1>', unsafe_allow_html=True)
    st.caption("Real-time health scoring and recommendations")

    # ── Watchlist selector ────────────────────────────────────────────────
    from state_quant_engine.database.connection import get_session
    from state_quant_engine.repositories.watchlist_group_repository import WatchlistGroupRepository
    _session = get_session()
    try:
        _grp_repo = WatchlistGroupRepository(_session)
        _groups   = _grp_repo.get_all_ordered()
    finally:
        _session.close()

    _group_names = [g.name for g in _groups]
    _default_idx = next((i for i, g in enumerate(_groups) if g.is_default), 0)

    scanner = ScannerService(settings)

    col_wl, col_run, col_filter = st.columns([2, 1, 1])
    with col_wl:
        sel_wl_name = st.selectbox(
            "Watchlist",
            _group_names,
            index=_default_idx,
            key="scanner_watchlist",
            label_visibility="collapsed",
            help="Select which watchlist to scan",
        )
        sel_wl_group = next((g for g in _groups if g.name == sel_wl_name), _groups[_default_idx])
    with col_run:
        if st.button("Run Scan", type="primary"):
            with st.spinner(f"Scanning '{sel_wl_name}'..."):
                st.session_state.scan_results = scanner.run(
                    version_id=version_id,
                    watchlist_group_id=sel_wl_group.id,
                )
    with col_filter:
        filter_type = st.selectbox("Filter", ["All", "ETF", "STOCK"],
                                    label_visibility="collapsed")

    results = st.session_state.get("scan_results", [])

    if not results:
        st.info("Click **Run Scan** to fetch data and score all watchlist symbols.")
        return

    filtered = results if filter_type == "All" else [r for r in results if r.asset_type == filter_type]

    # ── Market Health banner ───────────────────────────────────────────────
    if filtered:
        r0 = filtered[0]
        if r0.market_score > 0:
            mh = r0.market_score
            mh_color = "#00C853" if mh >= 80 else ("#2979FF" if mh >= 60 else
                                                     "#FF6D00" if mh >= 40 else "#D50000")
            st.markdown(
                f'<div style="background:#111c2a;border-radius:8px;padding:10px 16px;'
                f'margin:4px 0 12px;display:flex;align-items:center;gap:14px">'
                f'<span style="font-weight:700;font-size:0.9em;color:#aac4e0">📊 Market Health</span>'
                f'<span style="font-size:1.3em;font-weight:700;color:{mh_color}">{mh:.0f}%</span>'
                f'<span style="background:{mh_color};color:#000;padding:2px 10px;border-radius:4px;'
                f'font-weight:700;font-size:0.82em">{r0.deploy_label}</span>'
                f'<span style="color:#777;font-size:0.82em">→ deploy '
                f'<b>{r0.deploy_pct:.0f}%</b> of planned chunk capital</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    buy   = [r for r in filtered if r.recommendation == "BUY"]
    wait  = [r for r in filtered if r.recommendation == "WAIT"]

    c1, c2 = st.columns(2)
    for col, items, label, bg, fg in [
        (c1, buy,  "BUY",  "#00C853", "#000"),
        (c2, wait, "WAIT", "#607D8B", "#fff"),
    ]:
        col.markdown(
            f'<div style="background:{bg};color:{fg};text-align:center;padding:12px;'
            f'border-radius:8px;font-weight:700;font-size:1.4em">{len(items)}<br>'
            f'<span style="font-size:0.6em">{label}</span></div>',
            unsafe_allow_html=True,
        )

    st.caption("ℹ️ Scanner shows only fresh entry candidates. Stocks already in your portfolio are shown in the **Portfolio** screen.")

    st.divider()

    # ── Sort ──────────────────────────────────────────────────────────────
    sort_by = st.selectbox("Sort by", ["Health Score", "Symbol", "Profit", "Asset Type"], index=0)
    if sort_by == "Health Score":
        filtered.sort(key=lambda r: r.score_pct, reverse=True)
    elif sort_by == "Symbol":
        filtered.sort(key=lambda r: r.symbol)
    elif sort_by == "Profit":
        filtered.sort(key=lambda r: r.current_profit, reverse=True)
    elif sort_by == "Asset Type":
        filtered.sort(key=lambda r: r.asset_type)

    # ── AI Assessment ─────────────────────────────────────────────────────

    with st.expander("🤖 Trend & Risk Assessment (free web data)", expanded=False):
        st.caption(
            "Fetches latest news from Google News RSS, Yahoo Finance analyst ratings, "
            "and Moneycontrol. No API key required."
        )
        if st.button("Assess Trend & Risk for all symbols", type="primary"):
            from state_quant_engine.services.assessment_service import assess_trend_and_risk
            with st.spinner("Fetching web data for each symbol... (may take 20-40 s)"):
                assessed = assess_trend_and_risk(list(filtered))
            sym_map = {r.symbol: r for r in assessed}
            for r in st.session_state.scan_results:
                if r.symbol in sym_map:
                    r.trend        = sym_map[r.symbol].trend
                    r.trend_reason = sym_map[r.symbol].trend_reason
                    r.risk         = sym_map[r.symbol].risk
                    r.risk_reason  = sym_map[r.symbol].risk_reason
            st.success("Assessment complete.")
            st.rerun()

    # ── Main table ────────────────────────────────────────────────────────
    rows_html = []
    for r in filtered:
        score_color  = "#00C853" if r.score_pct >= 70 else ("#FF6D00" if r.score_pct >= 40 else "#D50000")
        profit_color = "#00C853" if r.current_profit >= 0 else "#D50000"
        next_buy     = f"₹{r.next_buy_price:.2f}" if r.next_buy_price else "—"

        trend_cell = _badge(r.trend, _TREND_STYLE) if r.trend else "—"
        risk_cell  = _badge(r.risk,  _RISK_STYLE)  if r.risk  else "—"

        # Drawdown cell: "−6.3% (52d H: ₹285)"
        if r.indicator and r.indicator.swing_high > 0:
            dd   = r.indicator.drawdown_pct
            sh   = r.indicator.swing_high
            ddays = r.indicator.drawdown_days
            dd_color = ("#00C853" if 5 <= abs(dd) <= 8
                        else "#FFC107" if abs(dd) < 12
                        else "#D50000" if abs(dd) > 15
                        else "#FF6D00")
            dd_cell = (f'<span style="color:{dd_color};font-weight:700">{dd:.1f}%</span>'
                       f'<br><small style="color:#777">{ddays}d H: ₹{sh:.0f}</small>')
        else:
            dd_cell = "—"

        # CMP + day % change cell
        day_chg    = r.change_pct
        chg_color  = "#00C853" if day_chg >= 0 else "#D50000"
        chg_arrow  = "▲" if day_chg >= 0 else "▼"
        prev_close = r.prev_close
        cmp_cell   = (
            f'<span style="font-weight:700">₹{r.price:.2f}</span>'
            f'<br><small style="color:{chg_color}">{chg_arrow} {day_chg:+.2f}%</small>'
            + (f'<br><small style="color:#555">Prev ₹{prev_close:.2f}</small>' if prev_close > 0 else "")
        )

        rows_html.append(
            f"<tr>"
            f"<td style='text-align:center'>{r.rank}</td>"
            f"<td><b>{r.symbol}</b></td>"
            f"<td>{r.name}</td>"
            f"<td style='text-align:center'>{r.asset_type}</td>"
            f"<td style='text-align:right'>{cmp_cell}</td>"
            f"<td style='text-align:center;color:{score_color};font-weight:700'>{r.score_pct:.1f}%</td>"
            f"<td style='text-align:center'>{_badge(r.recommendation, _SIGNAL_STYLE)}</td>"
            f"<td style='text-align:right;color:{profit_color};font-weight:700'>{r.current_profit:+.2f}%</td>"
            f"<td style='text-align:center'>{r.chunks_held}</td>"
            f"<td style='text-align:right'>{next_buy}</td>"
            f"<td style='text-align:center'>{dd_cell}</td>"
            f"<td style='text-align:center'>{trend_cell}</td>"
            f"<td style='text-align:center'>{risk_cell}</td>"
            f"</tr>"
        )

    table_html = f"""
    <style>
      .sqe-table {{ width:100%; border-collapse:collapse; font-size:0.88em; }}
      .sqe-table th {{ background:#1e2a3a; color:#aac4e0; padding:8px 10px;
                       text-align:left; border-bottom:2px solid #2e3f55; white-space:nowrap; }}
      .sqe-table td {{ padding:7px 10px; border-bottom:1px solid #1e2a3a; vertical-align:middle; }}
      .sqe-table tr:hover td {{ background:#1a2435; }}
    </style>
    <table class="sqe-table">
      <thead><tr>
        <th>#</th><th>Symbol</th><th>Name</th><th>Type</th>
        <th>CMP / Day %</th><th>Health %</th><th>Signal</th>
        <th>Profit %</th><th>Chunks</th><th>Next Buy</th>
        <th>Drawdown</th><th>Trend</th><th>Risk</th>
      </tr></thead>
      <tbody>{"".join(rows_html)}</tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Detail view + Quick trade ─────────────────────────────────────────
    st.divider()
    selected_symbol = st.selectbox("View details for", [r.symbol for r in filtered])
    if selected_symbol:
        detail = next((r for r in filtered if r.symbol == selected_symbol), None)
        if detail:
            _render_detail(detail)


def _render_detail(r):
    sig = _SIGNAL_STYLE.get(r.recommendation, {"bg": "#555", "fg": "#fff"})
    st.markdown(
        f'<h3>{r.symbol} &nbsp; <span style="background:{sig["bg"]};color:{sig["fg"]};'
        f'padding:4px 14px;border-radius:6px;font-size:0.75em">{r.recommendation}</span></h3>',
        unsafe_allow_html=True,
    )
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("CMP",          f"₹{r.price:.2f}")
    chg_delta = f"{r.change_pct:+.2f}% vs prev ₹{r.prev_close:.2f}" if r.prev_close > 0 else None
    col_b.metric("Day Change",   f"{r.change_pct:+.2f}%", delta=chg_delta)
    col_c.metric("Health Score", f"{r.score_pct:.1f}%")
    col_d.metric("Profit",       f"{r.current_profit:+.2f}%")

    # Trend / Risk pills
    if r.trend:
        t_style = _TREND_STYLE.get(r.trend, {"bg": "#555", "fg": "#fff"})
        ri_style = _RISK_STYLE.get(r.risk, {"bg": "#555", "fg": "#fff"})
        st.markdown(
            f'<div style="display:flex;gap:12px;margin:8px 0">'
            f'<span style="background:{t_style["bg"]};color:{t_style["fg"]};padding:4px 14px;border-radius:6px;font-weight:700">📈 {r.trend}</span>'
            f'<span style="background:{ri_style["bg"]};color:{ri_style["fg"]};padding:4px 14px;border-radius:6px;font-weight:700">⚠ {r.risk}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if r.trend_reason or r.risk_reason:
            st.caption(f"Trend: {r.trend_reason}  |  Risk: {r.risk_reason}")

    if r.indicator:
        ind = r.indicator
        st.write("**Technical Indicators**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("EMA20",   f"₹{ind.ema20:.2f}")
        c2.metric("EMA50",   f"₹{ind.ema50:.2f}")
        c3.metric("EMA200",  f"₹{ind.ema200:.2f}")
        c4.metric("RSI",     f"{ind.rsi14:.1f}")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("MACD",      f"{ind.macd_line:.4f}")
        c6.metric("ADX",       f"{ind.adx14:.1f}")
        c7.metric("ATR",       f"₹{ind.atr14:.2f}")
        c8.metric("Vol Ratio", f"{ind.volume_ratio:.2f}x")

        # ── Drawdown breakdown ────────────────────────────────────────────
        st.write("**Drawdown Analysis**")
        dd_pct  = ind.drawdown_pct          # negative, e.g. -6.3
        dd_days = ind.drawdown_days
        sh      = ind.swing_high
        cmp     = ind.price
        dd_abs  = abs(dd_pct)

        # Bell-curve bucket label
        if dd_abs < 2:
            dd_quality = "⬆ Extended — no healthy pullback yet"
            dd_color   = "#FF6D00"
        elif dd_abs < 5:
            dd_quality = "🟡 Mild pullback"
            dd_color   = "#FFC107"
        elif dd_abs < 8:
            dd_quality = "✅ Ideal zone (5–8%)"
            dd_color   = "#00C853"
        elif dd_abs < 12:
            dd_quality = "🟡 Moderate pullback"
            dd_color   = "#FFC107"
        elif dd_abs <= 15:
            dd_quality = "⚠️ Deep pullback — caution"
            dd_color   = "#FF6D00"
        else:
            dd_quality = "🔴 Excessive — possible trend damage"
            dd_color   = "#D50000"

        d1, d2, d3, d4 = st.columns(4)
        d1.metric(f"{dd_days}-Day High",  f"₹{sh:.2f}",
                  help=f"Highest closing price over the last {dd_days} trading days")
        d2.metric("CMP (Current Price)",  f"₹{cmp:.2f}")
        d3.metric("Drawdown ₹",           f"₹{cmp - sh:.2f}",
                  delta=f"{dd_pct:.2f}%",
                  help=f"CMP minus the {dd_days}-day high")
        d4.metric("Drawdown %",           f"{dd_pct:.2f}%")

        st.markdown(
            f'<div style="background:#1a2435;border-radius:6px;padding:8px 14px;'
            f'margin:4px 0;display:flex;align-items:center;gap:10px">'
            f'<span style="color:{dd_color};font-weight:700;font-size:0.9em">{dd_quality}</span>'
            f'<span style="color:#777;font-size:0.8em">— '
            f'({dd_days}d high ₹{sh:.2f} → CMP ₹{cmp:.2f} = {dd_pct:.2f}%)</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if r.component_scores:
        st.write("**Component Scores**")
        comp_df = pd.DataFrame([{"Component": k, "Score": v} for k, v in r.component_scores.items()])
        fig = go.Figure(go.Bar(
            x=comp_df["Score"], y=comp_df["Component"], orientation="h",
            marker_color=["#00C853" if v > 0 else "#D50000" for v in comp_df["Score"]],
            text=comp_df["Score"].map(lambda v: f"{v:.0f}"), textposition="outside",
        ))
        fig.update_layout(height=320, margin=dict(l=0, r=40, t=10, b=0),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#ccc"))
        st.plotly_chart(fig, use_container_width=True)

    if r.reasons:
        with st.expander("Analysis Details"):
            for reason in r.reasons:
                icon = "✅" if any(kw in reason.lower() for kw in
                                   ["above", "bullish", "spike", "breadth", "within"]) else "❌"
                st.write(f"{icon} {reason}")

    # ── Quick BUY / EXIT from scanner ────────────────────────────────────
    st.divider()
    st.write("**Quick Trade**")
    version_id = st.session_state.get("version_id", 1)
    ver_name   = st.session_state.get("version_name", "Live")
    _settings  = st.session_state.get("_settings")

    # Compute suggested BUY quantity from chunk rules
    sugg_qty   = 1
    chunk_info = ""
    if _settings and r.price > 0:
        try:
            from state_quant_engine.engine.trade_engine import (
                suggested_buy_quantity, _symbol_allocated_capital,
            )
            asset_type = r.asset_type
            # Scanner only shows fresh entries (no open position for this symbol)
            sugg_qty   = suggested_buy_quantity(r.symbol, asset_type, 0, r.price, _settings)
            cap_cfg    = _settings.etf_capital if asset_type == "ETF" else _settings.stock_capital
            chunk_pct  = cap_cfg.chunk_percentages[0] if cap_cfg.chunk_percentages else 20
            sym_cap    = _symbol_allocated_capital(r.symbol, asset_type, _settings)
            chunk_amt  = sym_cap * chunk_pct / 100
            # Apply market deploy multiplier if available
            deploy = r.deploy_pct if hasattr(r, "deploy_pct") and r.deploy_pct else 100.0
            chunk_amt  *= deploy / 100
            chunk_info = (f"Chunk 1: ₹{chunk_amt:,.0f} "
                          f"({chunk_pct:.0f}% of ₹{sym_cap:,.0f}"
                          + (f", {deploy:.0f}% market deploy" if deploy < 100 else "") + ")")
        except Exception:
            pass

    # Scanner = fresh entry → always default BUY
    action_options = ["BUY", "EXIT", "PARTIAL_EXIT"]

    with st.form(key=f"scanner_trade_{r.symbol}_{version_id}"):
        if chunk_info:
            st.caption(chunk_info)
        col_a, col_q, col_p = st.columns(3)
        with col_a:
            action = st.selectbox("Action", action_options, index=0)  # BUY always default
        with col_q:
            qty = st.number_input("Quantity", min_value=1, value=max(1, sugg_qty), step=1)
        with col_p:
            exec_price = st.number_input("Price", value=float(r.price),
                                          min_value=0.01, step=0.05)
        remarks = st.text_input("Remarks", value=f"Chunk 1 — Entry Health {r.score_pct:.0f}%")
        if st.form_submit_button(f"Execute {action} [{ver_name}]", type="primary"):
            if _settings:
                from state_quant_engine.services.portfolio_service import PortfolioService
                PortfolioService(_settings).execute_trade(
                    r.symbol, action, exec_price, float(qty), remarks, version_id=version_id
                )
                st.success(f"{action} {qty} {r.symbol} @ ₹{exec_price:.2f} [{ver_name}]")
            else:
                st.error("Settings not available — use Trade Engine page instead.")
