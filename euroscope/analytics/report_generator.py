"""
PDF Performance Report Generator

Generates a professional, branded PDF tear sheet for subscribers
detailing weekly EuroScope performance, risk metrics, and key trades.
"""

import os
import logging
from datetime import datetime, UTC
from typing import List, Dict

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False
    logging.warning("reportlab not installed. PDF generation will fail. Run: pip install reportlab")

from ..data.storage import Storage
from ..backtest.metrics import BacktestMetrics

logger = logging.getLogger("euroscope.analytics.report_generator")


class PDFReportGenerator:
    """Generates PDF performance reports."""

    def __init__(self, storage: Storage, output_dir: str = "reports"):
        self.storage = storage
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    async def generate_weekly_report(self) -> str:
        """Fetch last 7 days of trades and generate a PDF report."""
        if not _REPORTLAB_AVAILABLE:
            logger.error("Cannot generate PDF report: reportlab is not installed.")
            return ""
        now = datetime.now(UTC)
        start_date = now.strftime("%Y-%m-%d") # simplified logic: just getting today's trades for demo
        
        # In a real scenario, this would fetch the last week's trades:
        # We will fetch all closed trades for this example to ensure data is present.
        trades = await self.storage.get_trade_journal(status="closed", limit=100)
        
        if not trades:
            logger.warning("No closed trades found to generate report.")
            return ""

        # Calculate metrics
        stats = await self.storage.get_trade_journal_stats()
        
        filename = f"EuroScope_Performance_Report_{now.strftime('%Y%m%d')}.pdf"
        filepath = os.path.join(self.output_dir, filename)
        
        self._build_pdf(filepath, trades, stats)
        
        return filepath

    def _build_pdf(self, filepath: str, trades: List[Dict], stats: Dict):
        """Constructs the PDF document using ReportLab Platypus."""
        doc = SimpleDocTemplate(filepath, pagesize=letter,
                                rightMargin=40, leftMargin=40,
                                topMargin=40, bottomMargin=40)
        
        styles = getSampleStyleSheet()
        title_style = styles['Heading1']
        title_style.alignment = 1 # Center
        h2_style = styles['Heading2']
        body_style = styles['Normal']
        
        # Custom styles
        metric_style = ParagraphStyle(
            'Metric',
            parent=body_style,
            fontName='Helvetica-Bold',
            fontSize=12,
            textColor=colors.HexColor("#2C3E50")
        )
        
        elements = []
        
        # Header
        elements.append(Paragraph("EuroScope Institutional Auto-Trader", title_style))
        elements.append(Paragraph(f"Performance Report - {datetime.now(UTC).strftime('%B %d, %Y')}", title_style))
        elements.append(Spacer(1, 20))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey, spaceAfter=20))
        
        # Executive Summary
        elements.append(Paragraph("Executive Summary", h2_style))
        elements.append(Spacer(1, 10))
        
        summary_data = [
            ["Total Trades", str(stats.get('total', 0))],
            ["Win Rate", f"{stats.get('win_rate', 0.0)}%"],
            ["Total PnL (pips)", f"{stats.get('total_pnl', 0.0)}"],
            ["Average PnL/Trade (pips)", f"{stats.get('avg_pnl', 0.0)}"]
        ]
        
        t = Table(summary_data, colWidths=[200, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8F9F9")),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#2C3E50")),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('INNERGRID', (0,0), (-1,-1), 0.25, colors.lightgrey),
            ('BOX', (0,0), (-1,-1), 0.25, colors.lightgrey),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))
        
        # Strategy Breakdown
        valid_strats = stats.get('by_strategy', {})
        if valid_strats:
            elements.append(Paragraph("Strategy Breakdown", h2_style))
            elements.append(Spacer(1, 10))
            
            strat_data = [["Strategy", "Trades", "Win Rate (%)", "PnL (pips)"]]
            for s_name, s_data in valid_strats.items():
                strat_data.append([
                    s_name,
                    str(s_data.get('total', 0)),
                    f"{s_data.get('win_rate', 0.0)}",
                    str(s_data.get('pnl', 0.0))
                ])
                
            t2 = Table(strat_data, colWidths=[150, 70, 80, 80])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#34495E")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,0), 12),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
            ]))
            elements.append(t2)
            elements.append(Spacer(1, 20))
        
        # Recent Trades Log
        elements.append(Paragraph("Recent Trades Log", h2_style))
        elements.append(Spacer(1, 10))
        
        trade_data = [["Date", "Dir", "Entry", "Exit", "PnL", "Strategy"]]
        
        # Limit to last 15 trades for the PDF list
        recent_trades = sorted(trades, key=lambda x: x.get('timestamp', ''), reverse=True)[:15]
        
        for tr in recent_trades:
            # Parse date string
            date_str = tr.get('timestamp', '')[:10]
            
            pnl = tr.get('pnl_pips', 0.0)
            pnl_str = f"+{pnl}" if pnl > 0 else str(pnl)
            
            trade_data.append([
                date_str,
                tr.get('direction', ''),
                str(tr.get('entry_price', '')),
                str(tr.get('exit_price', '')),
                pnl_str,
                tr.get('strategy', '')
            ])
            
        t3 = Table(trade_data, colWidths=[70, 40, 60, 60, 50, 100])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2E86C1")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        
        # Color code the PnL column
        for i, tr in enumerate(recent_trades, start=1):
            pnl = tr.get('pnl_pips', 0.0)
            color = colors.green if pnl > 0 else colors.red if pnl < 0 else colors.black
            t3.setStyle(TableStyle([
                ('TEXTCOLOR', (4, i), (4, i), color)
            ]))
            
        elements.append(t3)
        
        # Build document
        doc.build(elements)
        logger.info(f"Generated PDF Report: {filepath}")
