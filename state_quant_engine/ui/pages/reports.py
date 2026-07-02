"""Reports page - Excel and PDF generation."""
from __future__ import annotations
from typing import Any
from datetime import date, timedelta
import streamlit as st
from state_quant_engine.reports.excel_reporter import generate_excel_report
from state_quant_engine.reports.pdf_reporter import generate_pdf_report
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.trade_log_repository import TradeLogRepository
from state_quant_engine.repositories.scan_strategy_repository import ScanHistoryRepository
from state_quant_engine.repositories.version_repository import VersionRepository
import pandas as pd


def render(settings: Any, version_id: int = 1) -> None:
    is_live  = st.session_state.get("version_is_live", True)
    ver_name = st.session_state.get("version_name", "Live")
    ver_badge = (
        '<span style="background:#00C853;color:#000;padding:2px 10px;border-radius:10px;font-size:0.8em;font-weight:700">🟢 LIVE</span>'
        if is_live else
        f'<span style="background:#FF6D00;color:#fff;padding:2px 10px;border-radius:10px;font-size:0.8em;font-weight:700">🧪 {ver_name}</span>'
    )
    st.markdown(f'<h1>Reports &nbsp; {ver_badge}</h1>', unsafe_allow_html=True)
    st.caption("Generate Excel and PDF reports")

    session = get_session()
    try:
        tab_trade, tab_scan, tab_portfolio, tab_generate = st.tabs(
            ["Trade History", "Scan History", "Portfolio Summary", "Generate Reports"]
        )

        with tab_trade:
            st.subheader("Trade History")
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                start_date = st.date_input("From", value=date.today() - timedelta(days=30))
            with col2:
                end_date = st.date_input("To", value=date.today())
            with col3:
                # Allow cross-version view in reports
                ver_repo = VersionRepository(session)
                all_vers = ver_repo.get_all_ordered()
                ver_names = ["Current version"] + [v.name for v in all_vers]
                report_ver_choice = st.selectbox("Version", ver_names, index=0)

            trade_repo = TradeLogRepository(session)
            if report_ver_choice == "Current version":
                trades = trade_repo.get_by_date_range(start_date, end_date, version_id=version_id)
            elif report_ver_choice == "All versions":
                trades = trade_repo.get_all_versions(start_date, end_date)
            else:
                chosen_ver = next((v for v in all_vers if v.name == report_ver_choice), None)
                trades = trade_repo.get_by_date_range(start_date, end_date,
                                                       version_id=chosen_ver.id if chosen_ver else version_id)

            if trades:
                df = pd.DataFrame([{
                    "Date": t.date, "Symbol": t.symbol, "Action": t.action,
                    "Price": f"₹{t.price:.2f}", "Qty": t.quantity,
                    "Version": t.version_id, "Remarks": t.remarks or "",
                } for t in trades])
                st.dataframe(df, use_container_width=True, hide_index=True)
                csv = df.to_csv(index=False)
                st.download_button("Download CSV", data=csv, file_name="trade_history.csv", mime="text/csv")
            else:
                st.info("No trades found in selected date range.")

        with tab_scan:
            st.subheader("Scan History")
            scan_repo = ScanHistoryRepository(session)
            scans = scan_repo.get_by_version(version_id=version_id)
            if scans:
                df = pd.DataFrame([{
                    "Date": s.date, "Symbol": s.symbol,
                    "Score": f"{s.score:.1f}", "Signal": s.recommendation,
                } for s in scans[:200]])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No scan history for this version. Run the Scanner first.")

        with tab_portfolio:
            from state_quant_engine.services.portfolio_service import PortfolioService
            svc = PortfolioService(settings)
            summary = svc.get_summary(version_id=version_id)
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Capital", f"₹{summary.total_capital:,.0f}")
            col2.metric("Allocated",     f"₹{summary.allocated:,.0f}")
            col3.metric("MTM P&L",       f"₹{summary.mtm:+,.0f}")
            if summary.positions:
                st.dataframe(pd.DataFrame(summary.positions), use_container_width=True, hide_index=True)

        with tab_generate:
            st.subheader("Generate Reports")
            report_type = st.radio("Report Type", ["Excel", "PDF"])
            if st.button("Generate Report", type="primary"):
                scan_results = st.session_state.get("scan_results", [])
                with st.spinner("Generating report..."):
                    if report_type == "Excel":
                        buf = generate_excel_report(settings, scan_results, version_id=version_id)
                        st.download_button(
                            "Download Excel Report", data=buf,
                            file_name=f"sqe_report_{ver_name}_{date.today()}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    else:
                        buf = generate_pdf_report(settings, scan_results)
                        st.download_button(
                            "Download PDF Report", data=buf,
                            file_name=f"sqe_report_{ver_name}_{date.today()}.pdf",
                            mime="application/pdf",
                        )
    finally:
        session.close()
