"""Report generation — on-demand PDF / CSV download."""
import io
import csv
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.server import Server, MetricsSnapshot
from app.models.intelligence import RiskScore, Recommendation
from app.models.alerts import Alert, AlertState

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

REPORT_TITLES = {
    "daily-ops": "Daily Operations Report",
    "weekly-health": "Weekly Health Report",
    "monthly-capacity": "Monthly Capacity Report",
    "exec": "Executive Fleet Report",
}


async def _gather(db: AsyncSession):
    servers = (await db.execute(select(Server))).scalars().all()
    snaps = {snap.server_id: snap for snap in (await db.execute(
        select(MetricsSnapshot).distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )).scalars().all()}
    risks = {r.server_id: r for r in (await db.execute(
        select(RiskScore).distinct(RiskScore.server_id)
        .order_by(RiskScore.server_id, RiskScore.scored_at.desc())
    )).scalars().all()}
    alerts = (await db.execute(select(Alert).where(Alert.state == AlertState.FIRING))).scalars().all()
    recos = (await db.execute(select(Recommendation).where(Recommendation.dismissed == False))).scalars().all()  # noqa: E712
    return servers, snaps, risks, alerts, recos


@router.get("/{report_type}")
async def generate_report(report_type: str, format: str = "pdf", db: AsyncSession = Depends(get_db)):
    if report_type not in REPORT_TITLES:
        raise HTTPException(400, f"Unknown report type. Options: {list(REPORT_TITLES)}")

    servers, snaps, risks, alerts, recos = await _gather(db)
    title = REPORT_TITLES[report_type]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if format == "csv":
        return _csv_report(servers, snaps, risks, report_type)
    return _pdf_report(title, generated, servers, snaps, risks, alerts, recos)


def _csv_report(servers, snaps, risks, report_type):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Hostname", "Status", "Health", "Risk", "RiskLevel", "CPU%", "Mem%", "CPUTemp", "PowerW"])
    for s in servers:
        snap = snaps.get(s.id)
        risk = risks.get(s.id)
        w.writerow([
            s.hostname, s.status.value if s.status else "unknown", s.health_score or "",
            risk.overall_risk if risk else "", risk.risk_level if risk else "",
            snap.cpu_usage_avg if snap else "", snap.memory_usage_pct if snap else "",
            snap.cpu_temp_max if snap else "", snap.power_consumed_watts if snap else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={report_type}-{datetime.now().date()}.csv"},
    )


def _pdf_report(title, generated, servers, snaps, risks, alerts, recos):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], textColor=colors.HexColor("#ED1C24"))
    elements = []

    elements.append(Paragraph("Helios — AMD Fleet Intelligence", title_style))
    elements.append(Paragraph(title, styles["Heading2"]))
    elements.append(Paragraph(f"Generated: {generated}", styles["Normal"]))
    elements.append(Spacer(1, 0.2 * inch))

    # Fleet summary
    total = len(servers)
    healthy = sum(1 for s in servers if s.status and s.status.value == "healthy")
    critical = sum(1 for s in servers if s.status and s.status.value == "critical")
    high_risk = sum(1 for r in risks.values() if r.risk_level == "high")
    total_power = sum(s.power_consumed_watts for s in snaps.values() if s.power_consumed_watts)

    summary = [
        ["Metric", "Value"],
        ["Total Servers", str(total)],
        ["Healthy", str(healthy)],
        ["Critical", str(critical)],
        ["High Risk", str(high_risk)],
        ["Active Alerts", str(len(alerts))],
        ["Open Recommendations", str(len(recos))],
        ["Total Power", f"{total_power:.0f} W"],
        ["Est. Monthly Cost", f"${(total_power/1000)*24*30*1.5*0.12:,.2f}"],
        ["Est. Monthly Carbon", f"{(total_power/1000)*24*30*1.5*0.37:,.1f} kg CO2"],
    ]
    t = Table(summary, colWidths=[2.5 * inch, 2.5 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3 * inch))

    # Top risk servers
    elements.append(Paragraph("Top Risk Servers", styles["Heading3"]))
    risk_rows = [["Server", "Health", "Risk", "Level"]]
    ranked = sorted(risks.values(), key=lambda r: r.overall_risk, reverse=True)[:10]
    srv_map = {s.id: s for s in servers}
    for r in ranked:
        s = srv_map.get(r.server_id)
        risk_rows.append([s.hostname if s else "—", str(s.health_score if s else ""), f"{r.overall_risk:.0f}", r.risk_level])
    rt = Table(risk_rows, colWidths=[2.2 * inch, 1 * inch, 1 * inch, 1 * inch])
    rt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elements.append(rt)
    elements.append(Spacer(1, 0.3 * inch))

    # Recommendations
    if recos:
        elements.append(Paragraph("Key Recommendations", styles["Heading3"]))
        for r in recos[:12]:
            elements.append(Paragraph(f"<b>[{r.severity.upper()}]</b> {r.title} — {r.body}", styles["Normal"]))
            elements.append(Spacer(1, 0.05 * inch))

    doc.build(elements)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=fleet-report-{datetime.now().date()}.pdf"},
    )
