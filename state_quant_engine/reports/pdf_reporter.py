"""PDF report generator using reportlab."""
from __future__ import annotations
from typing import Any, List
import io
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from state_quant_engine.services.portfolio_service import PortfolioService


def generate_pdf_report(settings: Any, scan_results: List = None) -> bytes:
    """Generate a PDF portfolio report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#1F4E79"))
    heading_style = ParagraphStyle("heading", parent=styles["Heading2"], textColor=colors.HexColor("#2E75B6"))

    story.append(Paragraph("STATE Quant Engine", title_style))
    story.append(Paragraph(f"Report Date: {date.today()}", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))

    svc = PortfolioService(settings)
    summary = svc.get_summary(scan_results)

    story.append(Paragraph("Portfolio Summary", heading_style))
    summary_data = [
        ["Metric", "Value"],
        ["Total Capital", f"Rs {summary.total_capital:,.0f}"],
        ["Allocated", f"Rs {summary.allocated:,.0f}"],
        ["Available", f"Rs {summary.available:,.0f}"],
        ["MTM P&L", f"Rs {summary.mtm:+,.0f} ({summary.mtm_pct:+.2f}%)"],
        ["Open Positions", str(summary.open_positions)],
        ["BUY Signals", str(summary.buy_signals)],
        ["HOLD Signals", str(summary.hold_signals)],
        ["EXIT Signals", str(summary.exit_signals)],
    ]
    t = Table(summary_data, colWidths=[8*cm, 8*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    if scan_results:
        story.append(Paragraph("Scanner Results (Top 20)", heading_style))
        scan_data = [["#", "Symbol", "Type", "Price", "Health %", "Signal", "P&L %"]]
        for r in scan_results[:20]:
            scan_data.append([
                str(r.rank), r.symbol, r.asset_type,
                f"Rs {r.price:.2f}", f"{r.score_pct:.1f}%",
                r.recommendation, f"{r.current_profit:+.2f}%",
            ])
        t2 = Table(scan_data, colWidths=[1*cm, 3.5*cm, 2*cm, 3*cm, 2.5*cm, 2.5*cm, 2.5*cm])
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E75B6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ]))
        story.append(t2)

    doc.build(story)
    buf.seek(0)
    return buf.read()
