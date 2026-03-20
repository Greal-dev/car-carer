"""Generate vehicle report PDF using FPDF-like approach with fitz (PyMuPDF)."""

import logging
from datetime import date

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from app.models import MaintenanceEvent, CTReport

logger = logging.getLogger(__name__)


def generate_vehicle_pdf(vehicle, analysis: dict, db: Session) -> bytes:
    """Generate a PDF report for a vehicle."""
    logger.info("Generating vehicle PDF report — vehicle_id=%s", getattr(vehicle, 'id', '?'))
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    y = 40

    # Title
    vehicle_name = vehicle.name or "N/R"
    y = _text(page, f"Rapport vehicule — {vehicle_name}", 40, y, size=18, bold=True, color=(0.01, 0.23, 0.40))
    y += 5
    info_parts = [
        vehicle.brand or "N/R",
        vehicle.model or "",
        f"({vehicle.year})" if vehicle.year else None,
        vehicle.plate_number,
    ]
    info = " ".join(p for p in info_parts if p)
    if info:
        y = _text(page, info, 40, y, size=10, color=(0.4, 0.4, 0.4))
    y = _text(page, f"Genere le {date.today().strftime('%d/%m/%Y')}", 40, y, size=8, color=(0.6, 0.6, 0.6))
    y += 10

    # Health score
    health = analysis.get("health_score", {})
    score = health.get("score", "?")
    label = health.get("label", "")
    y = _text(page, f"Score de sante : {score}/100 — {label}", 40, y, size=14, bold=True)
    y += 5

    # CT Status
    ct_status = analysis.get("current_ct_status")
    if ct_status:
        y = _section(page, "Dernier controle technique", y)
        ct_result = (ct_status.get('result') or 'N/R').upper()
        y = _text(page, f"Date : {ct_status.get('date', 'N/R')}  —  Resultat : {ct_result}", 50, y, size=10)
        ct_mileage = ct_status.get("mileage")
        if ct_mileage is not None and isinstance(ct_mileage, (int, float)):
            y = _text(page, f"Kilometrage : {ct_mileage:,} km", 50, y, size=10)
        y = _text(page, f"Defauts : {ct_status.get('defect_count', 0)}  —  Prochaine echeance : {ct_status.get('next_due', 'N/A')}", 50, y, size=10)
        y += 5

    # Alerts
    alerts = analysis.get("alerts", [])
    if alerts:
        y = _section(page, f"Alertes ({len(alerts)})", y)
        for a in alerts:
            if y > 780:
                page = doc.new_page(width=595, height=842)
                y = 40
            level = (a.get("level") or "").upper()
            y = _text(page, f"[{level}] {a.get('title', '')}", 50, y, size=9, bold=True)
            detail = a.get("detail")
            if detail:
                for line in str(detail)[:200].split("\n"):
                    y = _text(page, line, 60, y, size=8, color=(0.3, 0.3, 0.3))
            y += 3

    # Maintenance history (last 10)
    events = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.vehicle_id == vehicle.id, MaintenanceEvent.event_type == "invoice")
        .order_by(MaintenanceEvent.date.desc())
        .limit(10)
        .all()
    )
    if events:
        if y > 700:
            page = doc.new_page(width=595, height=842)
            y = 40
        y = _section(page, "Historique entretiens (10 derniers)", y)
        for ev in events:
            if y > 780:
                page = doc.new_page(width=595, height=842)
                y = 40
            cost_str = ""
            if ev.total_cost is not None and isinstance(ev.total_cost, (int, float)):
                cost_str = f"{ev.total_cost:.2f} EUR"
            km_str = ""
            if ev.mileage is not None and isinstance(ev.mileage, (int, float)):
                km_str = f"{ev.mileage:,} km"
            y = _text(page, f"{ev.date}  {km_str}  {ev.garage_name or ''}  {cost_str}", 50, y, size=9)

    logger.info("Vehicle PDF report generated successfully")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _text(page, text: str, x: float, y: float, size: float = 10, bold: bool = False, color=(0, 0, 0)) -> float:
    """Insert text and return new y position."""
    font = "helv" if not bold else "hebo"
    # fitz uses fontname conventions: helv=Helvetica, hebo=Helvetica-Bold
    tw = fitz.TextWriter(page.rect)
    tw.append((x, y), str(text or "")[:120], fontsize=size, font=fitz.Font(font))
    tw.write_text(page, color=color)
    return y + size + 4


def _section(page, title: str, y: float) -> float:
    """Draw a section header with underline."""
    y = _text(page, title, 40, y, size=12, bold=True, color=(0.01, 0.23, 0.40))
    page.draw_line((40, y - 2), (555, y - 2), color=(0.8, 0.8, 0.8), width=0.5)
    return y + 2


def generate_booklet_pdf(vehicle, events: list, cts: list) -> bytes:
    """Generate official-style maintenance booklet."""
    logger.info("Generating booklet PDF — vehicle_id=%s, events=%d, cts=%d",
                getattr(vehicle, 'id', '?'), len(events), len(cts))
    doc = fitz.open()

    # Cover page
    page = doc.new_page(width=595, height=842)
    y = 200
    y = _text(page, "CARNET D'ENTRETIEN", 40, y, size=24, bold=True, color=(0.01, 0.23, 0.40))
    y += 10
    y = _text(page, vehicle.name or "N/R", 40, y, size=18, bold=True)
    info_parts = [
        vehicle.brand or "N/R",
        vehicle.model or "",
        f"({vehicle.year})" if vehicle.year else None,
    ]
    info = " ".join(p for p in info_parts if p)
    if info:
        y = _text(page, info, 40, y, size=14, color=(0.4, 0.4, 0.4))
    if vehicle.plate_number:
        y = _text(page, f"Immatriculation : {vehicle.plate_number}", 40, y, size=12, color=(0.4, 0.4, 0.4))
    if vehicle.vin:
        y = _text(page, f"VIN : {vehicle.vin}", 40, y, size=10, color=(0.5, 0.5, 0.5))
    y += 40
    y = _text(page, f"Document genere le {date.today().strftime('%d/%m/%Y')}", 40, y, size=9, color=(0.6, 0.6, 0.6))
    y = _text(page, f"{len(events)} intervention(s) — {len(cts)} controle(s) technique(s)", 40, y, size=9, color=(0.6, 0.6, 0.6))

    # Maintenance pages
    if events:
        page = doc.new_page(width=595, height=842)
        y = 40
        y = _text(page, "HISTORIQUE DES INTERVENTIONS", 40, y, size=16, bold=True, color=(0.01, 0.23, 0.40))
        y += 5

        for i, ev in enumerate(events):
            if y > 740:
                page = doc.new_page(width=595, height=842)
                y = 40

            # Intervention header
            page.draw_rect(fitz.Rect(40, y - 2, 555, y + 14), color=(0.93, 0.93, 0.93), fill=(0.93, 0.93, 0.93))
            header = f"#{i+1}  {ev.date}"
            if ev.mileage is not None and isinstance(ev.mileage, (int, float)):
                header += f"  —  {ev.mileage:,} km"
            if ev.garage_name:
                header += f"  —  {ev.garage_name}"
            y = _text(page, header, 45, y + 10, size=9, bold=True)
            y += 2

            for item in ev.items:
                if y > 780:
                    page = doc.new_page(width=595, height=842)
                    y = 40
                desc = (item.description or "")[:80]
                price = ""
                if item.total_price is not None and isinstance(item.total_price, (int, float)):
                    price = f"{item.total_price:.2f} EUR"
                y = _text(page, f"  {desc}", 50, y, size=8)
                if price:
                    _text(page, price, 480, y - 12, size=8, color=(0.3, 0.3, 0.3))

            if ev.total_cost is not None and isinstance(ev.total_cost, (int, float)):
                y = _text(page, f"Total : {ev.total_cost:.2f} EUR", 400, y, size=9, bold=True, color=(0.01, 0.23, 0.40))
            y += 5

    # CT pages
    if cts:
        page = doc.new_page(width=595, height=842)
        y = 40
        y = _text(page, "HISTORIQUE DES CONTROLES TECHNIQUES", 40, y, size=16, bold=True, color=(0.01, 0.23, 0.40))
        y += 5

        for ct in cts:
            if y > 700:
                page = doc.new_page(width=595, height=842)
                y = 40

            result = (ct.result or "").upper()
            color = (0.13, 0.55, 0.13) if ct.result == "favorable" else (0.8, 0.1, 0.1)
            y = _text(page, f"{ct.date}  —  {result}", 40, y, size=11, bold=True, color=color)
            if ct.mileage is not None and isinstance(ct.mileage, (int, float)):
                y = _text(page, f"{ct.mileage:,} km  —  {ct.center_name or ''}", 50, y, size=9, color=(0.4, 0.4, 0.4))

            for d in ct.defects:
                if y > 780:
                    page = doc.new_page(width=595, height=842)
                    y = 40
                sev = (d.severity or "").upper()
                y = _text(page, f"  [{sev}] {(d.description or '')[:80]}", 50, y, size=8, color=(0.3, 0.3, 0.3))

            if not ct.defects:
                y = _text(page, "  Aucun defaut", 50, y, size=8, color=(0.13, 0.55, 0.13))
            y += 8

    logger.info("Booklet PDF generated successfully")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
