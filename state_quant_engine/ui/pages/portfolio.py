"""Portfolio page — clean summary table + on-demand analysis + inline trade."""
from __future__ import annotations
from typing import Any
import streamlit as st
import pandas as pd
from state_quant_engine.services.portfolio_service import (
    PortfolioService,
    _SIG_COLORS, _ACT_EXIT, _ACT_AVG, _ACT_HOLD,
)
_SIG_PARTIAL_EXIT = _ACT_EXIT   # backward compat for expander button check
_SIG_FULL_EXIT    = _ACT_EXIT

_TREND_STYLE = {
    "Bullish": {"bg": "#00C853", "fg": "#000"},
    "Bearish": {"bg": "#D50000", "fg": "#fff"},
    "Neutral": {"bg": "#607D8B", "fg": "#fff"},
}
_RISK_STYLE = {
    "SAFE":     {"bg": "#00897B", "fg": "#fff"},
    "VOLATILE": {"bg": "#F57C00", "fg": "#fff"},
    "RISKY":    {"bg": "#C62828", "fg": "#fff"},
}

_CSS = """
<style>
.ptable{width:100%;border-collapse:collapse;font-size:0.88em}
.ptable th{background:#1e2a3a;color:#aac4e0;padding:7px 10px;
           text-align:left;border-bottom:2px solid #2e3f55;white-space:nowrap}
.ptable td{padding:6px 10px;border-bottom:1px solid #1a2535;vertical-align:middle}
.ptable tr:hover td{background:#1a2435}
</style>
"""


def _badge(text: str, style_map: dict, fallback_bg: str = "#37474F") -> str:
    s = style_map.get(text, {"bg": fallback_bg, "fg": "#aaa"})
    return (f'<span style="background:{s["bg"]};color:{s["fg"]};'
            f'padding:2px 9px;border-radius:4px;font-weight:700;font-size:0.8em">{text}</span>')


def render(settings: Any, version_id: int = 1) -> None:
    is_live  = st.session_state.get("version_is_live", True)
    ver_name = st.session_state.get("version_name", "Live")
    v_badge  = (
        '<span style="background:#00C853;color:#000;padding:2px 10px;border-radius:10px;'
        'font-size:0.8em;font-weight:700">🟢 LIVE</span>'
        if is_live else
        f'<span style="background:#FF6D00;color:#fff;padding:2px 10px;border-radius:10px;'
        f'font-size:0.8em;font-weight:700">🧪 {ver_name}</span>'
    )
    st.markdown(f'<h1>Portfolio &nbsp; {v_badge}</h1>', unsafe_allow_html=True)

    svc = PortfolioService(settings)

    # ── Action bar ────────────────────────────────────────────────────────
    col_r, col_a, col_s = st.columns([1, 1.4, 5])
    with col_r:
        if st.button("🔄 Refresh", type="secondary", help="Fetch latest prices"):
            if "portfolio_positions" in st.session_state:
                del st.session_state["portfolio_positions"]
            st.rerun()
    with col_a:
        if st.button("🔍 Analyse", type="primary",
                     help="Run health scoring, trend & risk assessment on held positions"):
            with st.spinner("Analysing positions..."):
                positions = svc.analyse_positions(version_id=version_id)
                st.session_state["portfolio_positions"] = positions
            st.rerun()

    # ── Load positions ────────────────────────────────────────────────────
    # Use cached analysed positions if available, else plain summary
    if "portfolio_positions" in st.session_state:
        positions = st.session_state["portfolio_positions"]
    else:
        summary = svc.get_summary(
            st.session_state.get("scan_results"), version_id=version_id
        )
        positions = summary.positions

    # Always re-compute KPIs from latest summary
    summary = svc.get_summary(st.session_state.get("scan_results"), version_id=version_id)

    # ── KPI strip ─────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Capital",  f"₹{summary.total_capital:,.0f}")
    k2.metric("Allocated",      f"₹{summary.allocated:,.0f}",
              f"{summary.allocated/summary.total_capital*100:.1f}%")
    k3.metric("Available",      f"₹{summary.available:,.0f}")
    k4.metric("MTM P&L",        f"₹{summary.mtm:+,.0f}", f"{summary.mtm_pct:+.2f}%")

    if not positions:
        st.info("No open positions. Open positions via Scanner quick-trade or Trade Engine.")
        return

    rules = settings.portfolio_rules
    st.caption(
        f"Thresholds from Scoring Profiles (per asset type) · "
        f"Global hard stops: Stocks **{rules.hard_stop_stock:.0f}%** / ETFs **{rules.hard_stop_etf:.0f}%** · "
        f"Profit target: **{rules.profit_exit_threshold:.0f}%** · "
        f"Configure per-profile in **Scoring Profiles → Profile Settings**"
    )

    # ── Signal legend ─────────────────────────────────────────────────────
    leg = " &nbsp; ".join(
        f'<span style="background:{s["bg"]};color:{s["fg"]};padding:3px 10px;'
        f'border-radius:4px;font-weight:700;font-size:0.78em">{sig}</span>'
        for sig, s in _SIG_COLORS.items()
    )
    st.markdown(leg, unsafe_allow_html=True)
    st.divider()

    # ── Build summary table rows ──────────────────────────────────────────
    df = pd.DataFrame(positions)

    # Aggregate to symbol level for the summary table
    agg = (
        df.groupby("symbol", sort=False)
          .agg(
              chunks      =("chunk",         "count"),
              qty         =("qty",           "sum"),
              cost        =("cost",          "sum"),
              value       =("value",         "sum"),
              cur_price   =("current_price", "last"),
              prev_close  =("prev_close",    "last"),
              day_chg     =("day_chg",       "last"),
              buy_date    =("buy_date",      "min"),
              health_pct  =("health_pct",    "first"),
              exit_signal =("exit_signal",   "first"),
              trend       =("trend",         "first"),
              risk        =("risk",          "first"),
              exit_reason =("exit_reason",   "first"),
              trend_reason=("trend_reason",  "first"),
              risk_reason =("risk_reason",   "first"),
          )
          .reset_index()
    )
    agg["pnl_pct"]  = (agg["value"] - agg["cost"]) / agg["cost"] * 100
    agg["avg_cost"] = agg["cost"] / agg["qty"]

    # ── HTML summary table ────────────────────────────────────────────────
    rows_html = []
    for _, row in agg.iterrows():
        sym      = row["symbol"]
        pc       = "#00C853" if row["pnl_pct"] >= 0 else "#D50000"
        sig      = row["exit_signal"]
        trnd     = row["trend"]
        risk     = row["risk"]
        day_chg  = float(row.get("day_chg", 0) or 0)
        prev_cl  = float(row.get("prev_close", 0) or 0)
        chg_color = "#00C853" if day_chg >= 0 else "#D50000"
        chg_arrow = "▲" if day_chg >= 0 else "▼"

        sig_html  = _badge(sig,  _SIG_COLORS,  "#37474F") if sig  else '<span style="color:#555">—</span>'
        trnd_html = _badge(trnd, _TREND_STYLE, "#37474F") if trnd else '<span style="color:#555">—</span>'
        risk_html = _badge(risk, _RISK_STYLE,  "#37474F") if risk else '<span style="color:#555">—</span>'

        pnl_amt  = float(row["value"]) - float(row["cost"])
        avg_cost_cell = (
            f'<span style="font-weight:600">₹{row["avg_cost"]:.2f}</span>'
            f'<br><small style="color:#888">Qty {row["qty"]:.0f}</small>'
        )
        cmp_cell = (
            f'<span style="font-weight:700">₹{row["cur_price"]:.2f}</span>'
            f'<br><small style="color:{chg_color}">{chg_arrow} {day_chg:+.2f}%</small>'
            + (f'<br><small style="color:#555">Prev ₹{prev_cl:.2f}</small>' if prev_cl > 0 else "")
        )
        pnl_cell = (
            f'<span style="color:{pc};font-weight:700">{row["pnl_pct"]:+.2f}%</span>'
            f'<br><small style="color:{pc}">₹{pnl_amt:+,.0f}</small>'
        )

        rows_html.append(
            f"<tr>"
            f"<td><b>{sym}</b></td>"
            f"<td style='text-align:center'>{int(row['chunks'])}</td>"
            f"<td style='text-align:right'>{avg_cost_cell}</td>"
            f"<td style='text-align:right'>{cmp_cell}</td>"
            f"<td style='text-align:right'>₹{row['cost']:,.0f}</td>"
            f"<td style='text-align:right'>₹{row['value']:,.0f}</td>"
            f"<td style='text-align:right'>{pnl_cell}</td>"
            f"<td style='text-align:center'>{sig_html}</td>"
            f"<td style='text-align:center'>{trnd_html}</td>"
            f"<td style='text-align:center'>{risk_html}</td>"
            f"<td style='text-align:center;white-space:nowrap'><!-- btns here --></td>"
            f"</tr>"
        )

    table_html = (
        _CSS
        + '<table class="ptable"><thead><tr>'
        + '<th>Symbol</th><th>Chunks</th><th>Avg Cost / Qty</th><th>CMP / Day%</th>'
        + '<th>Invested ₹</th><th>Value ₹</th><th>P&L % / ₹</th>'
        + '<th>Signal</th><th>Trend</th><th>Risk</th><th>Trade / Detail</th>'
        + '</tr></thead><tbody>'
        + "".join(rows_html)
        + '</tbody></table>'
    )
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Per-symbol Streamlit buttons (Trade + Detail toggle) ─────────────
    # Rendered as native Streamlit rows below the table so buttons are clickable
    for _, row in agg.iterrows():
        sym       = row["symbol"]
        cur_price = float(row["cur_price"])
        bk        = f"{sym}_v{version_id}"
        is_open   = st.session_state.get(f"detail_open_{bk}", False)

        bc1, bc2, bc3, bc4 = st.columns([0.5, 0.5, 1.2, 6])
        with bc1:
            if st.button("＋", key=f"add_{bk}", help=f"Buy / add {sym}"):
                cur = st.session_state.get(f"trade_{bk}")
                st.session_state[f"trade_{bk}"] = None if cur == "BUY" else "BUY"
                st.rerun()
        with bc2:
            if st.button("－", key=f"sub_{bk}", help=f"Sell / reduce {sym}"):
                cur = st.session_state.get(f"trade_{bk}")
                st.session_state[f"trade_{bk}"] = None if cur == "SELL" else "SELL"
                st.rerun()
        with bc3:
            lbl = "▾ Close Details" if is_open else f"▸ {sym} Details"
            if st.button(lbl, key=f"det_{bk}"):
                st.session_state[f"detail_open_{bk}"] = not is_open
                st.rerun()

        # ── Inline trade form ─────────────────────────────────────────────
        trade_mode = st.session_state.get(f"trade_{bk}")
        if trade_mode:
            action = "BUY" if trade_mode == "BUY" else "PARTIAL_EXIT"
            bg     = "#0d2a1a" if trade_mode == "BUY" else "#2a0d0d"
            label  = "➕ Buy / Add" if trade_mode == "BUY" else "➖ Sell / Reduce"
            sym_rows = df[df["symbol"] == sym]
            total_qty = int(sym_rows["qty"].sum())

            st.markdown(
                f'<div style="background:{bg};border-radius:8px;padding:10px 14px;margin:2px 0 4px">',
                unsafe_allow_html=True,
            )
            with st.form(key=f"tf_{bk}_{trade_mode}"):
                st.caption(f"**{label}** — {sym} @ ₹{cur_price:.2f}")
                fc1, fc2, fc3 = st.columns([1.2, 1, 2])
                with fc1:
                    ep = st.number_input("Price ₹", value=cur_price,
                                         min_value=0.01, step=0.05, key=f"ep_{bk}")
                with fc2:
                    default_qty = total_qty if trade_mode == "SELL" else 1
                    max_v = total_qty if trade_mode == "SELL" else 999999
                    qty = st.number_input("Qty", min_value=1, value=default_qty,
                                          max_value=max_v, step=1, key=f"qty_{bk}")
                with fc3:
                    rem = st.text_input("Remarks", value="", key=f"rem_{bk}")
                ok_lbl = "Buy" if trade_mode == "BUY" else "Sell"
                f1, f2 = st.columns(2)
                with f1:
                    if st.form_submit_button(ok_lbl, type="primary"):
                        svc.execute_trade(sym, action, ep, float(qty), rem,
                                          version_id=version_id)
                        st.session_state.pop(f"trade_{bk}", None)
                        if "portfolio_positions" in st.session_state:
                            del st.session_state["portfolio_positions"]
                        st.success(f"{action} {qty} {sym} @ ₹{ep:.2f}")
                        st.rerun()
                with f2:
                    if st.form_submit_button("Cancel"):
                        st.session_state.pop(f"trade_{bk}", None)
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Detail section (toggled) ──────────────────────────────────────
        if st.session_state.get(f"detail_open_{bk}"):
            sym_rows  = df[df["symbol"] == sym]
            agg_row   = agg[agg["symbol"] == sym].iloc[0]
            pnl_color = "#00C853" if agg_row["pnl_pct"] >= 0 else "#D50000"

            with st.container():
                st.markdown(
                    f'<div style="background:#111c2a;border-radius:10px;'
                    f'padding:12px 16px;margin:4px 0 8px">',
                    unsafe_allow_html=True,
                )

                # Header with badges
                hdr = (
                    f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
                    f'<span style="font-size:1.05em;font-weight:700">{sym}</span>'
                )
                if agg_row["trend"]:
                    hdr += _badge(agg_row["trend"], _TREND_STYLE)
                if agg_row["risk"]:
                    hdr += _badge(agg_row["risk"], _RISK_STYLE)
                if agg_row["exit_signal"]:
                    hdr += _badge(agg_row["exit_signal"], _SIG_COLORS)
                hdr += (
                    f'<span style="color:{pnl_color};font-weight:700;font-size:0.9em">'
                    f'  {agg_row["pnl_pct"]:+.2f}%</span></div>'
                )
                st.markdown(hdr, unsafe_allow_html=True)

                # Analysis pointers
                tips = []
                if agg_row["trend_reason"]: tips.append(f"📈 {agg_row['trend_reason']}")
                if agg_row["risk_reason"]:  tips.append(f"⚠️ {agg_row['risk_reason']}")
                if agg_row["exit_reason"]:  tips.append(f"🚦 {agg_row['exit_reason']}")
                if tips:
                    st.caption("  ·  ".join(tips))

                # Health bar
                hp = float(agg_row["health_pct"])
                if hp > 0:
                    hc = "#00C853" if hp >= 70 else ("#FF6D00" if hp >= 40 else "#D50000")
                    st.markdown(
                        f'<div style="height:5px;background:#222;border-radius:3px;margin:4px 0 2px">'
                        f'<div style="width:{min(hp,100):.0f}%;height:100%;background:{hc};'
                        f'border-radius:3px"></div></div>'
                        f'<small style="color:#888">Health {hp:.0f}%</small>',
                        unsafe_allow_html=True,
                    )

                # KPI row
                d1, d2, d3, d4, d5, d6 = st.columns(6)
                d1.metric("Chunks",   int(agg_row["chunks"]))
                d2.metric("Avg Cost", f"₹{agg_row['avg_cost']:.2f}")
                d3.metric("CMP",      f"₹{agg_row['cur_price']:.2f}")
                day_chg = float(agg_row.get("day_chg", 0) or 0)
                prev_cl = float(agg_row.get("prev_close", 0) or 0)
                d4.metric("Day %",    f"{day_chg:+.2f}%",
                          delta=f"Prev ₹{prev_cl:.2f}" if prev_cl > 0 else None)
                d5.metric("Invested", f"₹{agg_row['cost']:,.0f}")
                d6.metric("Value",    f"₹{agg_row['value']:,.0f}")

                # Chunk-level table
                st.write("**Chunk breakdown:**")
                chunk_rows = []
                for _, cr in sym_rows.iterrows():
                    pc2 = "#00C853" if cr["profit_pct"] >= 0 else "#D50000"
                    chunk_rows.append(
                        f"<tr>"
                        f"<td style='text-align:center;color:#888'>C{int(cr['chunk'])}</td>"
                        f"<td style='text-align:right'>₹{cr['buy_price']:.2f}</td>"
                        f"<td style='text-align:right'>₹{cr['current_price']:.2f}</td>"
                        f"<td style='text-align:center'>{cr['qty']:.0f}</td>"
                        f"<td style='text-align:right'>₹{cr['cost']:,.0f}</td>"
                        f"<td style='text-align:right'>₹{cr['value']:,.0f}</td>"
                        f"<td style='text-align:right;color:{pc2};font-weight:700'>"
                        f"{cr['profit_pct']:+.2f}%</td>"
                        f"<td style='text-align:right;color:#777'>{cr['highest_profit']:+.1f}%</td>"
                        f"<td style='text-align:center;color:#888'>"
                        f"{str(cr['buy_date']) if cr['buy_date'] else '—'}</td>"
                        f"</tr>"
                    )
                chunk_table = (
                    _CSS
                    + '<table class="ptable"><thead><tr>'
                    + '<th>Chunk</th><th>Buy ₹</th><th>Price ₹</th><th>Qty</th>'
                    + '<th>Cost</th><th>Value</th><th>P&L %</th><th>Peak %</th><th>Date</th>'
                    + '</tr></thead><tbody>'
                    + "".join(chunk_rows) + '</tbody></table>'
                )
                st.markdown(chunk_table, unsafe_allow_html=True)

                # Full exit button if signal warrants
                if agg_row["exit_signal"] in (_SIG_FULL_EXIT, _SIG_PARTIAL_EXIT):
                    fe_key = f"fe_open_{bk}"
                    if st.button(
                        f"⬇ {agg_row['exit_signal']} all chunks — {sym}",
                        key=f"fe_btn_{bk}", type="secondary"
                    ):
                        st.session_state[fe_key] = not st.session_state.get(fe_key, False)
                        st.rerun()
                    if st.session_state.get(fe_key):
                        with st.form(key=f"fe_{bk}"):
                            fe1, fe2 = st.columns(2)
                            with fe1:
                                fe_price = st.number_input(
                                    "Exit Price ₹", value=float(agg_row["cur_price"]),
                                    min_value=0.01, step=0.05)
                            with fe2:
                                fe_rem = st.text_input(
                                    "Remarks", value=str(agg_row["exit_signal"]))
                            fc_ok, fc_cancel = st.columns(2)
                            with fc_ok:
                                if st.form_submit_button("Confirm Exit", type="primary"):
                                    svc.execute_trade(
                                        sym, "EXIT", fe_price,
                                        float(sym_rows["qty"].sum()), fe_rem,
                                        version_id=version_id,
                                    )
                                    st.session_state.pop(fe_key, None)
                                    if "portfolio_positions" in st.session_state:
                                        del st.session_state["portfolio_positions"]
                                    st.success(f"EXIT {sym} @ ₹{fe_price:.2f}")
                                    st.rerun()
                            with fc_cancel:
                                if st.form_submit_button("Cancel"):
                                    st.session_state.pop(fe_key, None)
                                    st.rerun()

                st.markdown("</div>", unsafe_allow_html=True)
