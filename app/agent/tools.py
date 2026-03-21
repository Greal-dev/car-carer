"""Agent tools for querying the vehicle maintenance database."""

import logging
from datetime import date
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Vehicle, MaintenanceEvent, MaintenanceItem,
    CTReport, CTDefect, Document,
)
from app.services.analysis import analyze_vehicle

logger = logging.getLogger(__name__)

# Tool definitions for Claude API
TOOL_DEFINITIONS = [
    {
        "name": "get_vehicle_info",
        "description": "Obtenir les informations d'un vehicule et un resume de son historique (dernier km, total depense, nombre d'entretiens, nombre de CT).",
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "integer", "description": "ID du vehicule"}
            },
            "required": ["vehicle_id"],
        },
    },
    {
        "name": "search_maintenance",
        "description": "Rechercher dans l'historique d'entretien. Peut filtrer par mot-cle (piece, travail), categorie, plage de dates, plage de km.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "integer", "description": "ID du vehicule"},
                "keyword": {"type": "string", "description": "Mot-cle a chercher (ex: 'triangle', 'frein', 'vidange')"},
                "category": {"type": "string", "description": "Categorie: moteur, freinage, direction, suspension, transmission, echappement, electricite, carrosserie, climatisation, pneus, vidange, filtres, distribution, embrayage"},
                "date_from": {"type": "string", "description": "Date debut (YYYY-MM-DD)"},
                "date_to": {"type": "string", "description": "Date fin (YYYY-MM-DD)"},
                "event_type": {"type": "string", "description": "'invoice' pour factures, 'quote' pour devis"},
            },
            "required": ["vehicle_id"],
        },
    },
    {
        "name": "get_ct_reports",
        "description": "Obtenir tous les controles techniques d'un vehicule avec leurs defauts, tries par date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "integer", "description": "ID du vehicule"},
            },
            "required": ["vehicle_id"],
        },
    },
    {
        "name": "compare_ct_reports",
        "description": "Comparer deux controles techniques pour detecter les anomalies : nouveaux defauts majeurs, defauts disparus, evolution de severite. Identifie les incoherences suspectes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "integer", "description": "ID du vehicule"},
                "ct_report_id_old": {"type": "integer", "description": "ID du CT le plus ancien"},
                "ct_report_id_new": {"type": "integer", "description": "ID du CT le plus recent"},
            },
            "required": ["vehicle_id", "ct_report_id_old", "ct_report_id_new"],
        },
    },
    {
        "name": "get_mileage_timeline",
        "description": "Obtenir la chronologie des kilometres enregistres (tous les points : entretiens + CT) pour evaluer le rythme d'utilisation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "integer", "description": "ID du vehicule"},
            },
            "required": ["vehicle_id"],
        },
    },
    {
        "name": "get_spending_summary",
        "description": "Obtenir un resume des depenses par categorie de travaux.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "integer", "description": "ID du vehicule"},
                "year": {"type": "integer", "description": "Filtrer par annee (optionnel)"},
            },
            "required": ["vehicle_id"],
        },
    },
    {
        "name": "get_vehicle_analysis",
        "description": "Analyse proactive complete du vehicule : evolution des CT (defauts apparus, aggraves, recurrents), intervalles d'entretien depasses (vidange, distribution, freins, filtres...), defauts CT non resolus. Retourne des alertes classees par priorite.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "integer", "description": "ID du vehicule"},
            },
            "required": ["vehicle_id"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict, db: Session, allowed_vehicle_ids: list[int] | None = None) -> str:
    """Execute a tool and return the result as a string.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Tool input parameters
        db: Database session
        allowed_vehicle_ids: If provided, restrict access to these vehicle IDs only
    """
    # Check vehicle ownership if allowed_vehicle_ids is set
    vehicle_id = tool_input.get("vehicle_id")
    if allowed_vehicle_ids is not None and vehicle_id is not None:
        if vehicle_id not in allowed_vehicle_ids:
            logger.warning("Ownership check failed — tool=%s, vehicle_id=%s, allowed=%s",
                           tool_name, vehicle_id, allowed_vehicle_ids)
            return "Vehicule non autorise."

    handlers = {
        "get_vehicle_info": _get_vehicle_info,
        "search_maintenance": _search_maintenance,
        "get_ct_reports": _get_ct_reports,
        "compare_ct_reports": _compare_ct_reports,
        "get_mileage_timeline": _get_mileage_timeline,
        "get_spending_summary": _get_spending_summary,
        "get_vehicle_analysis": _get_vehicle_analysis,
    }
    handler = handlers.get(tool_name)
    if not handler:
        logger.warning("Unknown tool requested: %s", tool_name)
        return f"Outil inconnu: {tool_name}"

    logger.info("Executing tool — name=%s, input=%s", tool_name, tool_input)
    return handler(db=db, **tool_input)


def _get_vehicle_info(db: Session, vehicle_id: int) -> str:
    v = db.get(Vehicle, vehicle_id)
    if not v:
        return "Vehicule non trouve."

    last_event = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.vehicle_id == vehicle_id, MaintenanceEvent.mileage.isnot(None))
        .order_by(MaintenanceEvent.date.desc())
        .first()
    )
    last_ct = (
        db.query(CTReport)
        .filter(CTReport.vehicle_id == vehicle_id, CTReport.mileage.isnot(None))
        .order_by(CTReport.date.desc())
        .first()
    )

    last_mileage = None
    last_mileage_date = None
    candidates = []
    if last_event and last_event.mileage:
        candidates.append((last_event.date, last_event.mileage))
    if last_ct and last_ct.mileage:
        candidates.append((last_ct.date, last_ct.mileage))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        last_mileage_date, last_mileage = candidates[0]

    total_spent = db.query(func.sum(MaintenanceEvent.total_cost)).filter(
        MaintenanceEvent.vehicle_id == vehicle_id,
        MaintenanceEvent.event_type == "invoice",
    ).scalar() or 0

    event_count = db.query(func.count(MaintenanceEvent.id)).filter(
        MaintenanceEvent.vehicle_id == vehicle_id
    ).scalar()
    ct_count = db.query(func.count(CTReport.id)).filter(
        CTReport.vehicle_id == vehicle_id
    ).scalar()

    lines = [
        f"Vehicule: {v.name} — {v.brand} {v.model} ({v.year or '?'})",
        f"Plaque: {v.plate_number or 'N/R'} | VIN: {v.vin or 'N/R'}",
        f"Carburant: {v.fuel_type or 'N/R'}",
        f"Km initial (achat): {v.initial_mileage or 'N/R'} | Date achat: {v.purchase_date or 'N/R'}",
        f"Dernier km connu: {last_mileage or 'N/R'} (au {last_mileage_date or '?'})",
        f"Total depense (factures): {total_spent:.2f} EUR",
        f"Nombre d'interventions: {event_count} | Nombre de CT: {ct_count}",
    ]
    return "\n".join(lines)


def _search_maintenance(
    db: Session,
    vehicle_id: int,
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    event_type: Optional[str] = None,
) -> str:
    query = (
        db.query(MaintenanceEvent)
        .options(joinedload(MaintenanceEvent.items))
        .filter(MaintenanceEvent.vehicle_id == vehicle_id)
    )

    if event_type:
        query = query.filter(MaintenanceEvent.event_type == event_type)
    if date_from:
        try:
            query = query.filter(MaintenanceEvent.date >= date.fromisoformat(date_from))
        except ValueError:
            return f"Format de date invalide pour date_from: '{date_from}'. Utilisez le format YYYY-MM-DD."
    if date_to:
        try:
            query = query.filter(MaintenanceEvent.date <= date.fromisoformat(date_to))
        except ValueError:
            return f"Format de date invalide pour date_to: '{date_to}'. Utilisez le format YYYY-MM-DD."

    events = query.order_by(MaintenanceEvent.date.desc()).all()

    results = []
    for ev in events:
        items = ev.items
        if keyword:
            kw = keyword.lower()
            items = [it for it in items if kw in (it.description or "").lower() or kw in (it.part_name or "").lower()]
        if category:
            items = [it for it in items if it.category and it.category.lower() == category.lower()]

        if keyword or category:
            if not items:
                continue

        item_lines = []
        for it in items:
            price_str = f"{it.total_price:.2f} EUR" if it.total_price else "N/R"
            item_lines.append(f"  - {it.description} [{it.category or '?'}] — {price_str}")

        results.append(
            f"[{ev.event_type.upper()}] {ev.date} | {ev.mileage or '?'} km | {ev.garage_name or 'Garage inconnu'} | Total: {ev.total_cost or '?'} EUR\n"
            + "\n".join(item_lines)
        )

    if not results:
        return "Aucun resultat trouve."
    return f"{len(results)} intervention(s) trouvee(s):\n\n" + "\n\n".join(results)


def _get_ct_reports(db: Session, vehicle_id: int) -> str:
    reports = (
        db.query(CTReport)
        .options(joinedload(CTReport.defects))
        .filter(CTReport.vehicle_id == vehicle_id)
        .order_by(CTReport.date.desc())
        .all()
    )
    if not reports:
        return "Aucun controle technique enregistre."

    lines = []
    for ct in reports:
        defect_lines = []
        for d in ct.defects:
            defect_lines.append(f"  [{d.severity.upper()}] {d.code or '—'} : {d.description} ({d.category or '?'})")

        lines.append(
            f"CT #{ct.id} — {ct.date} | {ct.mileage or '?'} km | {ct.center_name or '?'}\n"
            f"Resultat: {ct.result.upper()}\n"
            + (("\n".join(defect_lines) + "\n") if defect_lines else "Aucun defaut.\n")
        )
    return "\n".join(lines)


def _compare_ct_reports(
    db: Session, vehicle_id: int, ct_report_id_old: int, ct_report_id_new: int
) -> str:
    old = db.query(CTReport).options(joinedload(CTReport.defects)).get(ct_report_id_old)
    new = db.query(CTReport).options(joinedload(CTReport.defects)).get(ct_report_id_new)

    if not old or not new:
        return "Un ou les deux CT sont introuvables."

    km_diff = None
    if old.mileage and new.mileage:
        km_diff = new.mileage - old.mileage

    old_codes = {(d.code or d.description): d for d in old.defects}
    new_codes = {(d.code or d.description): d for d in new.defects}

    new_defects = []
    escalated = []
    resolved = []

    for key, d in new_codes.items():
        if key not in old_codes:
            new_defects.append(d)
        else:
            old_sev = old_codes[key].severity
            new_sev = d.severity
            severity_order = {"a_surveiller": 0, "mineur": 1, "majeur": 2, "critique": 3}
            if severity_order.get(new_sev, 0) > severity_order.get(old_sev, 0):
                escalated.append((old_codes[key], d))

    for key, d in old_codes.items():
        if key not in new_codes:
            resolved.append(d)

    lines = [
        f"Comparaison CT #{old.id} ({old.date}, {old.mileage or '?'} km) vs CT #{new.id} ({new.date}, {new.mileage or '?'} km)",
        f"Km parcourus entre les deux: {km_diff if km_diff is not None else '?'}",
        "",
    ]

    if new_defects:
        lines.append(f"NOUVEAUX DEFAUTS ({len(new_defects)}):")
        for d in new_defects:
            flag = " ⚠ SUSPECT" if d.severity in ("majeur", "critique") else ""
            lines.append(f"  [{d.severity.upper()}] {d.code or '—'} : {d.description}{flag}")
        lines.append("")

    if escalated:
        lines.append(f"DEFAUTS AGGRAVES ({len(escalated)}):")
        for old_d, new_d in escalated:
            lines.append(f"  {old_d.severity} → {new_d.severity} : {new_d.description}")
        lines.append("")

    if resolved:
        lines.append(f"DEFAUTS RESOLUS ({len(resolved)}):")
        for d in resolved:
            lines.append(f"  [{d.severity}] {d.description}")
        lines.append("")

    if not new_defects and not escalated:
        lines.append("Aucune anomalie detectee entre les deux CT.")

    if new_defects and km_diff is not None and km_diff < 10000:
        suspect = [d for d in new_defects if d.severity in ("majeur", "critique")]
        if suspect:
            lines.append(
                f"⚠ ALERTE : {len(suspect)} defaut(s) majeur/critique apparu(s) en seulement {km_diff} km. "
                "C'est inhabituel et merite verification."
            )

    return "\n".join(lines)


def _get_mileage_timeline(db: Session, vehicle_id: int) -> str:
    points = []

    events = db.query(MaintenanceEvent).filter(
        MaintenanceEvent.vehicle_id == vehicle_id,
        MaintenanceEvent.mileage.isnot(None),
    ).all()
    for ev in events:
        points.append((ev.date, ev.mileage, f"Entretien ({ev.garage_name or '?'})"))

    cts = db.query(CTReport).filter(
        CTReport.vehicle_id == vehicle_id,
        CTReport.mileage.isnot(None),
    ).all()
    for ct in cts:
        points.append((ct.date, ct.mileage, f"CT ({ct.center_name or '?'})"))

    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle and vehicle.initial_mileage and vehicle.purchase_date:
        points.append((vehicle.purchase_date, vehicle.initial_mileage, "Achat"))

    points.sort(key=lambda x: x[0])

    if not points:
        return "Aucun point de kilometrage enregistre."

    lines = ["Chronologie kilometrique:"]
    prev_km = None
    prev_date = None
    for d, km, label in points:
        diff = ""
        if prev_km is not None:
            km_delta = km - prev_km
            days_delta = (d - prev_date).days
            if days_delta > 0:
                km_per_year = km_delta / days_delta * 365
                diff = f" (+{km_delta} km en {days_delta}j, ~{km_per_year:.0f} km/an)"
            else:
                diff = f" (+{km_delta} km)"
        lines.append(f"  {d} — {km:,} km — {label}{diff}")
        prev_km = km
        prev_date = d

    if len(points) >= 2:
        total_km = points[-1][1] - points[0][1]
        total_days = (points[-1][0] - points[0][0]).days
        if total_days > 0:
            avg = total_km / total_days * 365
            lines.append(f"\nMoyenne globale: ~{avg:.0f} km/an")

    return "\n".join(lines)


def _get_spending_summary(db: Session, vehicle_id: int, year: Optional[int] = None) -> str:
    query = (
        db.query(MaintenanceItem.category, func.sum(MaintenanceItem.total_price))
        .join(MaintenanceEvent)
        .filter(
            MaintenanceEvent.vehicle_id == vehicle_id,
            MaintenanceEvent.event_type == "invoice",
        )
    )
    if year:
        query = query.filter(func.extract("year", MaintenanceEvent.date) == year)

    results = query.group_by(MaintenanceItem.category).all()

    if not results:
        return "Aucune depense enregistree."

    total = sum(amount or 0 for _, amount in results)
    lines = [f"Depenses par categorie{f' ({year})' if year else ''} :"]
    for cat, amount in sorted(results, key=lambda x: x[1] or 0, reverse=True):
        pct = ((amount or 0) / total * 100) if total else 0
        lines.append(f"  {cat or 'Non categorise'}: {amount or 0:.2f} EUR ({pct:.0f}%)")
    lines.append(f"\nTotal: {total:.2f} EUR")
    return "\n".join(lines)


def _get_vehicle_analysis(db: Session, vehicle_id: int) -> str:
    result = analyze_vehicle(db, vehicle_id)
    if "error" in result:
        return result["error"]

    lines = ["=== ANALYSE PROACTIVE ===\n"]

    # Current CT status
    ct = result.get("current_ct_status")
    if ct:
        lines.append(f"Dernier CT: {ct['date']} | {ct['result'].upper()} | {ct['defect_count']} defaut(s)")
        if ct.get("next_due"):
            lines.append(f"Prochaine echeance CT: {ct['next_due']}")
        lines.append("")

    # Alerts by level
    alerts = result.get("alerts", [])
    critical = [a for a in alerts if a["level"] == "critical"]
    warning = [a for a in alerts if a["level"] == "warning"]
    info = [a for a in alerts if a["level"] == "info"]

    if critical:
        lines.append(f"!!! ALERTES CRITIQUES ({len(critical)}) !!!")
        for a in critical:
            lines.append(f"  [CRITIQUE] {a['title']}")
            lines.append(f"    {a['detail']}")
        lines.append("")

    if warning:
        lines.append(f"AVERTISSEMENTS ({len(warning)}):")
        for a in warning:
            lines.append(f"  [ATTENTION] {a['title']}")
            lines.append(f"    {a['detail']}")
        lines.append("")

    if info:
        lines.append(f"INFORMATIONS ({len(info)}):")
        for a in info:
            lines.append(f"  [INFO] {a['title']}")
            lines.append(f"    {a['detail']}")
        lines.append("")

    # Maintenance intervals summary
    intervals = [a for a in alerts if a.get("category") == "interval"]
    ok_count = sum(1 for a in intervals if a["level"] == "ok")
    warn_count = sum(1 for a in intervals if a["level"] == "warning")
    lines.append(f"Intervalles d'entretien: {ok_count} a jour, {warn_count} en retard")

    return "\n".join(lines)
