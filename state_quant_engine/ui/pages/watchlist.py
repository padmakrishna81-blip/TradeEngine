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

        tab_view, tab_add, tab_import, tab_manage = st.tabs(
            ["View & Edit", "Add Symbol", "Import / Export", "Manage Groups"]
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
    finally:
        session.close()
