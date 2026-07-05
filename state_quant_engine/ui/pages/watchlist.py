"""Watchlist management page — multiple named watchlists."""
from __future__ import annotations
from typing import Any
import streamlit as st
import pandas as pd
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.watchlist_repository import WatchlistRepository
from state_quant_engine.repositories.watchlist_group_repository import WatchlistGroupRepository


def render(settings: Any, version_id: int = 1) -> None:
    st.title("Watchlists")
    st.caption("Manage multiple watchlists — assign symbols to groups and scan any group")

    session = get_session()
    try:
        grp_repo = WatchlistGroupRepository(session)
        wl_repo  = WatchlistRepository(session)
        groups   = grp_repo.get_all_ordered()

        if not groups:
            st.warning("No watchlist groups found. Click 'Re-seed Defaults' in Settings.")
            return

        # ── Sidebar-style group selector ──────────────────────────────────
        group_names = [g.name for g in groups]
        sel_name    = st.selectbox(
            "Active Watchlist",
            group_names,
            index=next((i for i, g in enumerate(groups) if g.is_default), 0),
            key="wl_active_group",
        )
        sel_group = next(g for g in groups if g.name == sel_name)

        badge = (
            '<span style="background:#00C853;color:#000;padding:2px 8px;border-radius:4px;'
            'font-size:0.8em;font-weight:700">DEFAULT</span>'
            if sel_group.is_default else ""
        )
        st.markdown(
            f'<span style="font-size:1.05em;font-weight:700">{sel_group.name}</span>'
            + (f" &nbsp; {badge}" if badge else "")
            + (f' <span style="color:#777;font-size:0.85em"> — {sel_group.description}</span>'
               if sel_group.description else ""),
            unsafe_allow_html=True,
        )

        tab_view, tab_add, tab_import, tab_manage, tab_scan = st.tabs(
            ["View & Edit", "Add Symbol", "Import / Export", "Manage Groups", "📊 Index Scanner"]
        )

        # ── Tab 1 : View & Edit ───────────────────────────────────────────
        with tab_view:
            items = wl_repo.get_by_group(sel_group.id)
            if not items:
                st.info(f"No symbols in '{sel_group.name}'. Use the Add Symbol tab.")
            else:
                # ── HTML display table with colored Enabled badge ─────────
                rows_html = []
                for i in items:
                    enabled_badge = (
                        '<span style="background:#00C853;color:#000;padding:2px 9px;'
                        'border-radius:4px;font-weight:700;font-size:0.82em">✔ Active</span>'
                        if i.enabled else
                        '<span style="background:#D50000;color:#fff;padding:2px 9px;'
                        'border-radius:4px;font-weight:700;font-size:0.82em">✖ Disabled</span>'
                    )
                    type_color = "#2979FF" if i.asset_type == "ETF" else "#607D8B"
                    rows_html.append(
                        f"<tr>"
                        f"<td><b>{i.symbol}</b></td>"
                        f"<td>{i.name or '—'}</td>"
                        f"<td><span style='color:{type_color};font-weight:700'>{i.asset_type}</span></td>"
                        f"<td>{i.exchange or '—'}</td>"
                        f"<td style='text-align:center'>{i.priority}</td>"
                        f"<td style='text-align:center'>{enabled_badge}</td>"
                        f"</tr>"
                    )
                table_html = """
                <style>
                  .wl-table { width:100%; border-collapse:collapse; font-size:0.9em; }
                  .wl-table th { background:#1e2a3a; color:#aac4e0; padding:7px 10px;
                                 text-align:left; border-bottom:2px solid #2e3f55; }
                  .wl-table td { padding:6px 10px; border-bottom:1px solid #1a2535; vertical-align:middle; }
                  .wl-table tr:hover td { background:#1a2435; }
                </style>
                <table class="wl-table">
                  <thead><tr>
                    <th>Symbol</th><th>Name</th><th>Type</th><th>Exchange</th>
                    <th>Priority</th><th>Status</th>
                  </tr></thead>
                  <tbody>""" + "".join(rows_html) + "</tbody></table>"
                st.markdown(table_html, unsafe_allow_html=True)
                st.caption("Edit values below to update name, type, exchange, priority or toggle enabled.")

                # ── Editable data_editor below the display table ──────────
                data = [{
                    "Symbol": i.symbol, "Name": i.name or "",
                    "Type": i.asset_type, "Exchange": i.exchange or "",
                    "Priority": i.priority, "Enabled": i.enabled,
                } for i in items]
                df = pd.DataFrame(data).set_index("Symbol")
                edited = st.data_editor(
                    df,
                    column_config={
                        "Type":     st.column_config.SelectboxColumn("Type", options=["ETF","STOCK"]),
                        "Priority": st.column_config.NumberColumn("Priority", min_value=1, max_value=10),
                        "Enabled":  st.column_config.CheckboxColumn("Enabled"),
                    },
                    use_container_width=True,
                )

                col_save, col_del = st.columns([1, 5])
                with col_save:
                    if st.button("Save Changes", type="primary"):
                        for symbol, row in edited.iterrows():
                            item = wl_repo.get_by_symbol_and_group(symbol, sel_group.id)
                            if item:
                                item.name       = row["Name"]
                                item.asset_type = row["Type"]
                                item.exchange   = row["Exchange"]
                                item.priority   = int(row["Priority"])
                                item.enabled    = bool(row["Enabled"])
                        session.commit()
                        st.success("Saved!")
                        st.rerun()

                st.divider()
                del_sym = st.selectbox("Remove symbol", [i.symbol for i in items],
                                        key="del_sym_sel")
                if st.button("Remove", type="secondary", key="del_sym_btn"):
                    item = wl_repo.get_by_symbol_and_group(del_sym, sel_group.id)
                    if item:
                        wl_repo.delete(item)
                        st.success(f"Removed {del_sym} from '{sel_group.name}'.")
                        st.rerun()

        # ── Tab 2 : Add Symbol ────────────────────────────────────────────
        with tab_add:
            with st.form("add_symbol_form"):
                c1, c2 = st.columns(2)
                with c1:
                    new_sym  = st.text_input("Symbol (e.g. RELIANCE.NS)").upper()
                    new_name = st.text_input("Name")
                    new_type = st.selectbox("Asset Type", ["STOCK","ETF"])
                with c2:
                    new_exch = st.text_input("Exchange", value="NSE")
                    new_pri  = st.number_input("Priority", min_value=1, max_value=10, value=5)
                    new_ena  = st.checkbox("Enabled", value=True)
                submitted = st.form_submit_button("Add Symbol", type="primary")
                if submitted and new_sym:
                    existing = wl_repo.get_by_symbol_and_group(new_sym, sel_group.id)
                    if existing:
                        st.warning(f"{new_sym} already in '{sel_group.name}'.")
                    else:
                        wl_repo.upsert(
                            symbol=new_sym, name=new_name, exchange=new_exch,
                            asset_type=new_type, priority=int(new_pri),
                            group_id=sel_group.id,
                        )
                        st.success(f"Added {new_sym} to '{sel_group.name}'.")
                        st.rerun()

        # ── Tab 3 : Import / Export ───────────────────────────────────────
        with tab_import:
            st.subheader("Import CSV")
            st.caption("Columns: symbol, name, asset_type, exchange, priority")
            uploaded = st.file_uploader("Upload CSV", type=["csv"], key="wl_csv_upload")
            if uploaded:
                try:
                    df_imp = pd.read_csv(uploaded)
                    st.dataframe(df_imp, use_container_width=True)
                    if st.button("Import into current watchlist", type="primary"):
                        for _, row in df_imp.iterrows():
                            wl_repo.upsert(
                                symbol=str(row["symbol"]).upper(),
                                name=str(row.get("name","")),
                                exchange=str(row.get("exchange","NSE")),
                                asset_type=str(row.get("asset_type","STOCK")),
                                priority=int(row.get("priority",5)),
                                group_id=sel_group.id,
                            )
                        st.success(f"Imported {len(df_imp)} symbols into '{sel_group.name}'.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Import failed: {e}")

            st.divider()
            st.subheader("Export")
            items_exp = wl_repo.get_by_group(sel_group.id)
            if items_exp:
                exp_df = pd.DataFrame([{
                    "symbol": i.symbol, "name": i.name or "",
                    "asset_type": i.asset_type, "exchange": i.exchange or "",
                    "priority": i.priority, "enabled": i.enabled,
                } for i in items_exp])
                st.download_button(
                    f"Download '{sel_group.name}' CSV",
                    data=exp_df.to_csv(index=False),
                    file_name=f"watchlist_{sel_group.name.replace(' ','_').lower()}.csv",
                    mime="text/csv",
                )

        # ── Tab 4 : Manage Groups ─────────────────────────────────────────
        with tab_manage:
            st.subheader("All Watchlists")
            for g in groups:
                cnt = grp_repo.symbol_count(g.id)
                badge_str = " 🟢 **[DEFAULT]**" if g.is_default else ""
                with st.expander(f"{g.name}{badge_str} — {cnt} symbols"):
                    st.caption(g.description or "")
                    col_a, col_b, col_c = st.columns([1, 1, 4])
                    with col_a:
                        if not g.is_default:
                            if st.button("Set Default", key=f"def_{g.id}"):
                                for grp in groups:
                                    grp.is_default = (grp.id == g.id)
                                session.commit()
                                st.success(f"'{g.name}' is now the default watchlist.")
                                st.rerun()
                    with col_b:
                        if not g.is_default and st.button("Delete", key=f"delg_{g.id}",
                                                           type="secondary"):
                            if cnt > 0:
                                st.error(f"Remove all {cnt} symbols first.")
                            else:
                                grp_repo.delete(g)
                                st.success(f"Deleted '{g.name}'.")
                                st.rerun()

            st.divider()
            st.subheader("Create New Watchlist")
            with st.form("new_group_form"):
                ng_name = st.text_input("Watchlist Name")
                ng_desc = st.text_input("Description (optional)")
                clone   = st.selectbox("Clone from (optional)",
                                        ["— blank —"] + group_names)
                if st.form_submit_button("Create", type="primary"):
                    if not ng_name.strip():
                        st.error("Name is required.")
                    elif grp_repo.get_by_name(ng_name.strip()):
                        st.error(f"'{ng_name}' already exists.")
                    else:
                        new_grp = grp_repo.create_group(ng_name.strip(), ng_desc.strip())
                        if clone != "— blank —":
                            src_grp = next((g for g in groups if g.name == clone), None)
                            if src_grp:
                                for item in wl_repo.get_by_group(src_grp.id):
                                    wl_repo.copy_to_group(item, new_grp.id)
                        st.success(f"Created '{new_grp.name}'.")
                        st.rerun()

        # ── Tab 5: Index Scanner ──────────────────────────────────────────
        with tab_scan:
            _render_index_scanner(settings, sel_group, wl_repo, grp_repo, session)

    finally:
        session.close()


# ── NIFTY 50 + MIDCAP top constituent tickers (Yahoo Finance .NS format) ─────
_NIFTY50 = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","BHARTIARTL.NS","ICICIBANK.NS",
    "INFOSYS.NS","SBIN.NS","HINDUNILVR.NS","ITC.NS","LT.NS",
    "KOTAKBANK.NS","BAJFINANCE.NS","ASIANPAINT.NS","AXISBANK.NS","MARUTI.NS",
    "NTPC.NS","SUNPHARMA.NS","TATAMOTORS.NS","WIPRO.NS","HCLTECH.NS",
    "POWERGRID.NS","ULTRACEMCO.NS","TITAN.NS","NESTLEIND.NS","BAJAJFINSV.NS",
    "ADANIENT.NS","JSWSTEEL.NS","COALINDIA.NS","TECHM.NS","DRREDDY.NS",
    "APOLLOHOSP.NS","TATASTEEL.NS","ONGC.NS","HINDALCO.NS","GRASIM.NS",
    "CIPLA.NS","ADANIPORTS.NS","TATACONSUM.NS","DIVISLAB.NS","BPCL.NS",
    "SHRIRAMFIN.NS","HEROMOTOCO.NS","EICHERMOT.NS","BAJAJ-AUTO.NS",
    "BEL.NS","TRENT.NS","INDUSINDBK.NS","BRITANNIA.NS","SBILIFE.NS","HDFCLIFE.NS",
]

_MIDCAP150 = [
    "PERSISTENT.NS","MPHASIS.NS","COFORGE.NS","LTIM.NS","PIIND.NS",
    "AARTIIND.NS","AUROPHARMA.NS","BANKBARODA.NS","CANBK.NS","IDFCFIRSTB.NS",
    "FEDERALBNK.NS","KAJARINDIA.NS","SUPREMEIND.NS","CUMMINSIND.NS","BHARATFORG.NS",
    "ALKEM.NS","TATAELXSI.NS","POLICYBZR.NS","NAUKRI.NS","IRCTC.NS",
    "OBEROIRLTY.NS","GODREJPROP.NS","PRESTIGE.NS","PHOENIXLTD.NS","SOBHA.NS",
    "ABCAPITAL.NS","MUTHOOTFIN.NS","CHOLAFIN.NS","BAJAJHLDNG.NS","PNBHOUSING.NS",
    "VOLTAS.NS","CROMPTON.NS","HAVELLS.NS","POLYCAB.NS","VGUARD.NS",
    "ASTRAL.NS","KPITTECH.NS","LTTS.NS","CYIENT.NS","HEXAWARE.NS",
    "DELHIVERY.NS","ZOMATO.NS","PAYTM.NS","NYKAA.NS","CARTRADE.NS",
    "SJVN.NS","NHPC.NS","RECLTD.NS","PFC.NS","IRFC.NS",
]

_SMALLCAP = [
    "RAILVIKAS.NS","RVNL.NS","HUDCO.NS","IRCON.NS","NBCC.NS",
    "HFCL.NS","RAILTEL.NS","MAZDA.NS","RITES.NS","TITAGARH.NS",
    "ELGIEQUIP.NS","GRINDWELL.NS","SUPRAJIT.NS","GABRIEL.NS","ENDURANCE.NS",
    "LAXMIMACH.NS","GREAVESCOT.NS","JINDALSAW.NS","NMDC.NS","MOIL.NS",
    "NATCOPHARM.NS","GRANULES.NS","IOLCP.NS","LAURUSLABS.NS","SEQUENT.NS",
    "MAHINDCIE.NS","RAMKRISHNA.NS","GRAPHITE.NS","NAVNETEDUL.NS","PCBL.NS",
    "SUVENPHAR.NS","SUDARSCHEM.NS","FINEORG.NS","GALAXYSURF.NS","ALKYLAMINE.NS",
    "INDIGOPNTS.NS","EPIGRAL.NS","TATACHEM.NS","DEEPAKNITR.NS","AAVAS.NS",
    "HOMEFIRST.NS","CREDITACC.NS","SPANDANA.NS","UJJIVANLSF.NS","EQUITASBNK.NS",
    "SHOPERSTOP.NS","DMART.NS","VSTIND.NS","RADICO.NS","MCDOWELL-N.NS",
]


def _render_index_scanner(settings: Any, sel_group: Any, wl_repo: Any, grp_repo: Any, session: Any) -> None:
    """Scan NIFTY50 top 20 + MIDCAP top 10 against a strategy and show qualifying stocks."""

    # Show banner if symbols were just added
    if st.session_state.get("idx_scan_last_added") is not None:
        n   = st.session_state.pop("idx_scan_last_added")
        grp = st.session_state.pop("idx_scan_last_group", "watchlist")
        errs = st.session_state.pop("idx_scan_errors", [])
        if n > 0:
            st.success(f"✅ **{n} symbol(s) saved to '{grp}'** — check the View & Edit tab.")
        if errs:
            for e in errs:
                st.error(f"⚠ {e}")

    import json
    from state_quant_engine.repositories.scan_strategy_repository import StrategyRepository
    from state_quant_engine.engine.health_score_engine import EntryHealthEngine
    from state_quant_engine.engine.indicators.data_fetcher import fetch_ohlcv, fetch_price_with_change
    from state_quant_engine.engine.indicators.technical import compute_indicators

    st.subheader("Index Scanner")
    st.caption(
        "Scans **NIFTY 50 top 20** and **MIDCAP top 10** constituents against the selected strategy. "
        "Qualifying BUY signals can be imported directly into the active watchlist group."
    )

    strat_repo = StrategyRepository(session)
    strategies = strat_repo.get_all()
    active     = strat_repo.get_active()

    if not strategies:
        st.warning("No strategies found. Create strategies in Strategy Lab first.")
        return

    strat_names = [s.name for s in strategies]
    default_idx = next((i for i, s in enumerate(strategies) if active and s.id == active.id), 0)

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        sel_strat_name = st.selectbox("Strategy", strat_names, index=default_idx,
                                       key="idx_scan_strategy")
    with col2:
        index_choices = st.multiselect(
            "Index",
            ["NIFTY 50", "MIDCAP 150", "SMALLCAP"],
            default=["NIFTY 50"],
            key="idx_scan_index",
        )
    with col3:
        top_n = st.number_input(
            "Top N per index",
            min_value=1, max_value=50, value=20, step=1,
            key="idx_scan_topn",
            help="How many stocks to scan from each selected index",
        )
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        run_scan = st.button("🔍 Scan Now", type="primary", key="idx_scan_run")

    # Always compute target group (needed whether scan runs or not)
    all_groups_import = grp_repo.get_all_ordered()
    group_names_import = [g.name for g in all_groups_import]
    group_map = {g.name: int(g.id) for g in all_groups_import}
    default_grp_idx = next((i for i, g in enumerate(all_groups_import) if g.id == sel_group.id), 0)

    if not run_scan:
        # Show previous scan results if available
        cached = st.session_state.get("idx_scan_results")
        if cached:
            st.caption("Showing last scan results. Click **Scan Now** to refresh.")
            _show_results_and_import(cached, group_names_import, group_map, default_grp_idx, wl_repo, grp_repo)
        else:
            total_est = len(index_choices) * int(top_n)
            st.info(f"Will scan **{total_est}** stocks. Click **Scan Now**.")
        return

    sel_strat = next(s for s in strategies if s.name == sel_strat_name)
    raw_params = json.loads(sel_strat.parameters) if sel_strat.parameters else {}
    param_list = [
        {"parameter_name": k, "weight": float(v), "enabled": float(v) > 0, "threshold": 0}
        for k, v in raw_params.items() if float(v) > 0
    ]

    pr = getattr(settings, "portfolio_rules", None)
    engine = EntryHealthEngine(
        parameters=param_list,
        buy_threshold=pr.entry_buy_threshold if pr else 75.0,
        hard_gate_above_200dma=pr.hard_gate_above_200dma if pr else True,
        hard_gate_no_strong_bear_macd=pr.hard_gate_no_strong_bear_macd if pr else True,
        hard_gate_max_drawdown=pr.hard_gate_max_drawdown if pr else -15.0,
    )

    # Build symbol list from chosen indices
    n = int(top_n)
    symbols: list = []
    if "NIFTY 50"    in index_choices: symbols += [(s, "STOCK", "N50")  for s in _NIFTY50[:n]]
    if "MIDCAP 150"  in index_choices: symbols += [(s, "STOCK", "MID")  for s in _MIDCAP150[:n]]
    if "SMALLCAP"    in index_choices: symbols += [(s, "STOCK", "SML")  for s in _SMALLCAP[:n]]
    # Deduplicate keeping order
    seen: set = set()
    unique_symbols = []
    for item in symbols:
        if item[0] not in seen:
            seen.add(item[0])
            unique_symbols.append(item)
    symbols = unique_symbols

    results = []
    progress = st.progress(0, text="Scanning…")
    for i, (sym, atype, idx_label) in enumerate(symbols):
        progress.progress((i + 1) / len(symbols), text=f"Scanning {sym}…")
        try:
            df  = fetch_ohlcv(sym, period=settings.data.download_period)
            ind = compute_indicators(df, sym,
                                     drawdown_days=settings.data.drawdown_days)
            cmp, _, day_chg = fetch_price_with_change(sym)
            if cmp > 0:
                ind.price = cmp
            health = engine.compute(ind)
            results.append({
                "symbol":       sym,
                "name":         sym.replace(".NS", ""),
                "index":        idx_label,
                "cmp":          ind.price,
                "day_chg":      day_chg,
                "health":       health.score_pct,
                "signal":       health.recommendation,
                "reasons":      health.reasons,
                "in_watchlist": wl_repo.get_by_symbol_and_group(sym, sel_group.id) is not None,
            })
        except Exception:
            pass
    progress.empty()

    buy_results = [r for r in results if r["signal"] == "BUY"]
    # Persist results so they survive rerun after import
    st.session_state["idx_scan_results"] = buy_results
    wait_results = [r for r in results if r["signal"] != "BUY"]

    st.markdown(
        f'<div style="display:flex;gap:12px;margin:8px 0">'
        f'<div style="background:#00C853;color:#000;padding:10px 20px;border-radius:8px;font-weight:700">'
        f'{len(buy_results)} BUY</div>'
        f'<div style="background:#607D8B;color:#fff;padding:10px 20px;border-radius:8px;font-weight:700">'
        f'{len(wait_results)} WAIT</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _show_results_and_import(buy_results, group_names_import, group_map, default_grp_idx, wl_repo, grp_repo)


def _show_results_and_import(buy_results, group_names, group_map, default_grp_idx, wl_repo, grp_repo):
    """Display qualifying BUY stocks and the import-to-watchlist UI."""
    if not buy_results:
        st.info("No stocks qualify for BUY. Try a different strategy or index.")
        return

    # ── Results table ────────────────────────────────────────────────────
    _idx_colors = {"N50": "#2979FF", "MID": "#FF6D00", "SML": "#9C27B0"}
    rows_html = []
    for r in sorted(buy_results, key=lambda x: x["health"], reverse=True):
        chg_col   = "#00C853" if r["day_chg"] >= 0 else "#D50000"
        arrow     = "▲" if r["day_chg"] >= 0 else "▼"
        idx_col   = _idx_colors.get(r.get("index", "N50"), "#607D8B")
        idx_badge = (
            f'<span style="background:{idx_col};color:#fff;padding:1px 5px;'
            f'border-radius:3px;font-size:0.74em">{r.get("index","")}</span>'
        )
        reasons_short = " · ".join(r["reasons"][:2]) if r["reasons"] else ""
        rows_html.append(
            f"<tr>"
            f"<td style='padding:6px 10px'><b>{r['symbol']}</b>&nbsp;{idx_badge}</td>"
            f"<td style='padding:6px 10px'>₹{r['cmp']:.2f}"
            f"<br><small style='color:{chg_col}'>{arrow}{r['day_chg']:+.1f}%</small></td>"
            f"<td style='padding:6px 10px;text-align:center;color:#00C853;font-weight:700'>"
            f"{r['health']:.0f}%</td>"
            f"<td style='padding:6px 10px;font-size:0.8em;color:#999'>{reasons_short[:90]}</td>"
            f"</tr>"
        )

    table_html = (
        "<table style='width:100%;border-collapse:collapse;font-size:0.9em'>"
        "<thead><tr>"
        + "".join(
            f"<th style='background:#1e2a3a;color:#aac4e0;padding:7px 10px;"
            f"text-align:left;border-bottom:2px solid #2e3f55'>{h}</th>"
            for h in ["Symbol", "CMP / Day%", "Health %", "Key Reasons"]
        )
        + "</tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table>"
    )
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Import to watchlist ───────────────────────────────────────────────
    st.divider()
    st.write("**Add to Watchlist**")

    col_grp, col_sel = st.columns([1, 2])
    with col_grp:
        target_grp_name = st.selectbox(
            "Target watchlist", group_names,
            index=default_grp_idx,
            key="idx_scan_target_grp",
        )
    target_grp_id = int(group_map[target_grp_name])

    all_syms = [r["symbol"] for r in buy_results]
    already_in = set()
    for sym in all_syms:
        if wl_repo.get_by_symbol_and_group(sym, target_grp_id) is not None:
            already_in.add(sym)
    new_syms = [s for s in all_syms if s not in already_in]

    with col_sel:
        to_import = st.multiselect(
            "Select symbols to import",
            all_syms, default=new_syms,
            key="idx_scan_import",
            help="Pre-selected: not yet in target watchlist",
        )

    if already_in:
        st.caption(f"Already in '{target_grp_name}': {', '.join(sorted(already_in))}")

    if st.button(
        f"Add {len(to_import)} symbol(s) to '{target_grp_name}'",
        type="primary", key="idx_scan_add",
        disabled=len(to_import) == 0,
    ):
        from state_quant_engine.database.connection import get_engine
        from sqlalchemy import text as sqla_text

        errors = []
        added  = 0
        engine = get_engine()

        with engine.connect() as conn:
            for sym in to_import:
                r = next((x for x in buy_results if x["symbol"] == sym), None)
                if not r:
                    continue
                try:
                    existing = conn.execute(sqla_text(
                        "SELECT id FROM watchlist WHERE symbol=:s AND watchlist_group_id=:g"
                    ), {"s": sym, "g": target_grp_id}).fetchone()

                    if existing:
                        conn.execute(sqla_text(
                            "UPDATE watchlist SET name=:n, exchange='NSE', "
                            "asset_type='STOCK', priority=3, enabled=1 WHERE id=:id"
                        ), {"n": r["name"], "id": existing[0]})
                    else:
                        conn.execute(sqla_text(
                            "INSERT INTO watchlist "
                            "(symbol, name, exchange, asset_type, priority, enabled, watchlist_group_id) "
                            "VALUES (:s,:n,'NSE','STOCK',3,1,:g)"
                        ), {"s": sym, "n": r["name"], "g": target_grp_id})
                    conn.commit()
                    added += 1
                except Exception as e:
                    errors.append(f"{sym}: {e}")
                    try: conn.rollback()
                    except Exception: pass

        st.session_state["idx_scan_last_added"] = added
        st.session_state["idx_scan_last_group"]  = target_grp_name
        if errors:
            st.session_state["idx_scan_errors"] = errors
        st.rerun()

