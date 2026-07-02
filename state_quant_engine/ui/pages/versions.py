"""Versions management page."""
from __future__ import annotations
from typing import Any
import streamlit as st
import pandas as pd
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.version_repository import VersionRepository
from state_quant_engine.repositories.position_repository import PositionRepository
from state_quant_engine.repositories.trade_log_repository import TradeLogRepository


def render(settings: Any, version_id: int = 1) -> None:
    st.title("Versions")
    st.caption("Manage live and paper-trade versions for isolated testing")

    session = get_session()
    try:
        repo     = VersionRepository(session)
        pos_repo = PositionRepository(session)
        tl_repo  = TradeLogRepository(session)
        versions = repo.get_all_ordered()

        # ── Version list ─────────────────────────────────────────────────
        st.subheader("All Versions")
        rows = []
        for v in versions:
            open_pos   = len(pos_repo.get_open_positions(version_id=v.id))
            trade_cnt  = tl_repo.count_by_version(v.id)
            badge = "🟢 Live" if v.is_live else "🧪 Paper"
            rows.append({
                "ID": v.id, "Name": v.name, "Type": badge,
                "Description": v.description or "",
                "Open Positions": open_pos, "Total Trades": trade_cnt,
                "Created": str(v.created_at),
            })
        df = pd.DataFrame(rows)

        def color_type(val):
            if "Live" in str(val):
                return "background-color:#00C853;color:#000;font-weight:700"
            return "background-color:#FF6D00;color:#fff;font-weight:700"

        st.dataframe(
            df.style.map(color_type, subset=["Type"]),
            use_container_width=True, hide_index=True,
        )

        st.divider()

        # ── Create paper version ─────────────────────────────────────────
        st.subheader("Create Paper-Trade Version")
        with st.form("create_version_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Version Name", placeholder="e.g. Momentum Test Q3")
            with col2:
                new_desc = st.text_input("Description", placeholder="Optional description")
            submitted = st.form_submit_button("Create Version", type="primary")
            if submitted:
                if not new_name.strip():
                    st.error("Version name is required.")
                elif repo.get_by_name(new_name.strip()):
                    st.error(f"A version named '{new_name}' already exists.")
                else:
                    repo.create_paper(new_name.strip(), new_desc.strip())
                    st.success(f"Paper version '{new_name}' created. Select it from the sidebar to start testing.")
                    st.rerun()

        st.divider()

        # ── Delete paper version ─────────────────────────────────────────
        st.subheader("Delete Paper Version")
        paper_versions = [v for v in versions if not v.is_live]
        if not paper_versions:
            st.info("No paper versions exist yet.")
        else:
            del_name = st.selectbox("Select version to delete", [v.name for v in paper_versions])
            del_ver  = next((v for v in paper_versions if v.name == del_name), None)

            if del_ver:
                open_cnt = len(pos_repo.get_open_positions(version_id=del_ver.id))
                if open_cnt > 0:
                    st.warning(
                        f"**{del_name}** has {open_cnt} open position(s). "
                        "Close all positions before deleting this version."
                    )
                else:
                    if st.button(f"Delete '{del_name}'", type="secondary"):
                        from state_quant_engine.models.orm_models import TradeLog, ScanHistory, Position
                        session.query(TradeLog).filter(TradeLog.version_id == del_ver.id).delete()
                        session.query(ScanHistory).filter(ScanHistory.version_id == del_ver.id).delete()
                        session.query(Position).filter(Position.version_id == del_ver.id).delete()
                        repo.delete(del_ver)
                        st.success(f"Version '{del_name}' and all its data deleted.")
                        st.rerun()

        st.divider()
        st.info(
            "**How versioning works:**\n\n"
            "- Select **Live** in the sidebar for real trading — positions and trades are recorded under Live.\n"
            "- Create a **Paper** version to simulate a strategy without affecting live data.\n"
            "- The Scanner, Trade Engine, Portfolio, and Reports all filter by the selected version.\n"
            "- Paper versions can be deleted once you're done testing."
        )
    finally:
        session.close()
