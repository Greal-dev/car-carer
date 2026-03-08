"""Proactive maintenance intelligence — vehicle health analysis."""

from datetime import date
from dateutil.relativedelta import relativedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Vehicle, MaintenanceEvent, MaintenanceItem,
    CTReport, CTDefect,
)
from app.services.mileage import get_last_known_mileage

# --- Maintenance interval thresholds ---
# (category_keywords, max_km, max_months, label)
INTERVALS = [
    (["vidange"], 20_000, 12, "Vidange moteur"),
    (["filtre a air", "filtre air"], 40_000, 24, "Filtre a air"),
    (["filtre habitacle"], 20_000, 12, "Filtre habitacle"),
    (["liquide de frein", "frein"], 40_000, 24, "Liquide de frein"),
    (["distribution", "courroie distribution", "chaine distribution"], 120_000, 72, "Distribution"),
    (["plaquette"], 50_000, None, "Plaquettes de frein"),
    (["pneu", "pneumatique"], 50_000, None, "Pneumatiques"),
    (["liquide refroidissement", "liquide de refroidissement"], 100_000, 60, "Liquide de refroidissement"),
    (["bougie"], 60_000, 48, "Bougies"),
    (["amortisseur"], 80_000, None, "Amortisseurs"),
]

SEVERITY_ORDER = {"a_surveiller": 0, "mineur": 1, "majeur": 2, "critique": 3}


def analyze_vehicle(db: Session, vehicle_id: int) -> dict:
    """Run complete proactive analysis on a vehicle. Returns structured alerts."""
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        return {"error": "Vehicule non trouve"}

    ct_analysis = _analyze_ct_evolution(db, vehicle_id)
    interval_alerts = _check_maintenance_intervals(db, vehicle_id)
    unresolved = _check_unresolved_ct_defects(db, vehicle_id)

    # Collect all alerts sorted by priority
    alerts = []
    alerts.extend(ct_analysis.get("alerts", []))
    alerts.extend(interval_alerts)
    alerts.extend(unresolved)
    alerts.sort(key=lambda a: {"critical": 0, "warning": 1, "info": 2}.get(a["level"], 3))

    health_score = _compute_health_score(ct_analysis, interval_alerts, unresolved)

    return {
        "vehicle_id": vehicle_id,
        "vehicle_name": vehicle.name,
        "ct_evolution": ct_analysis.get("comparisons", []),
        "current_ct_status": ct_analysis.get("current_status"),
        "alerts": alerts,
        "maintenance_intervals": interval_alerts,
        "unresolved_defects": unresolved,
        "health_score": health_score,
    }


def _analyze_ct_evolution(db: Session, vehicle_id: int) -> dict:
    """Compare successive CTs to detect anomalies."""
    reports = (
        db.query(CTReport)
        .options(joinedload(CTReport.defects))
        .filter(CTReport.vehicle_id == vehicle_id)
        .order_by(CTReport.date.asc())
        .all()
    )

    if not reports:
        return {"comparisons": [], "current_status": None, "alerts": []}

    alerts = []
    comparisons = []

    # Current CT status
    latest = reports[-1]
    # Sanity-check next_due_date: if missing or <= CT date, assume +2 years (French standard)
    next_due = latest.next_due_date
    if not next_due or next_due <= latest.date:
        next_due = latest.date + relativedelta(years=2)
    current_status = {
        "date": str(latest.date),
        "result": latest.result,
        "mileage": latest.mileage,
        "center": latest.center_name,
        "defect_count": len(latest.defects),
        "next_due": str(next_due),
    }

    if latest.result in ("defavorable", "contre_visite"):
        alerts.append({
            "level": "critical",
            "category": "ct",
            "title": f"CT defavorable du {latest.date}",
            "detail": f"{len(latest.defects)} defaut(s) releves dont "
                      f"{sum(1 for d in latest.defects if d.severity in ('majeur', 'critique'))} majeur(s)/critique(s). "
                      "Contre-visite necessaire.",
        })

    # Check if CT is overdue (using corrected next_due)
    today = date.today()
    if next_due < today:
        days_overdue = (today - next_due).days
        alerts.append({
            "level": "critical",
            "category": "ct",
            "title": "Controle technique en retard",
            "detail": f"Echeance depassee depuis {days_overdue} jours (date limite: {next_due}).",
        })
    else:
        days_until = (next_due - today).days
        if days_until <= 60:
            alerts.append({
                "level": "warning",
                "category": "ct",
                "title": "Controle technique bientot du",
                "detail": f"Prochaine echeance dans {days_until} jours ({next_due}).",
            })

    # Compare successive CTs
    for i in range(1, len(reports)):
        old_ct = reports[i - 1]
        new_ct = reports[i]

        old_defects = {_defect_key(d): d for d in old_ct.defects}
        new_defects = {_defect_key(d): d for d in new_ct.defects}

        appeared = []
        escalated = []
        resolved = []

        for key, d in new_defects.items():
            if key not in old_defects:
                appeared.append(d)
            else:
                old_sev = SEVERITY_ORDER.get(old_defects[key].severity, 0)
                new_sev = SEVERITY_ORDER.get(d.severity, 0)
                if new_sev > old_sev:
                    escalated.append((old_defects[key], d))

        for key, d in old_defects.items():
            if key not in new_defects:
                resolved.append(d)

        km_between = None
        if old_ct.mileage and new_ct.mileage:
            km_between = new_ct.mileage - old_ct.mileage

        comp = {
            "old_date": str(old_ct.date),
            "new_date": str(new_ct.date),
            "old_mileage": old_ct.mileage,
            "new_mileage": new_ct.mileage,
            "km_between": km_between,
            "appeared": len(appeared),
            "escalated": len(escalated),
            "resolved": len(resolved),
        }
        comparisons.append(comp)

        # Generate alerts for suspicious patterns
        suspect_new = [d for d in appeared if d.severity in ("majeur", "critique")]
        if suspect_new:
            detail_parts = [f"- [{d.severity}] {d.description[:80]}" for d in suspect_new]
            km_note = f" (seulement {km_between:,} km entre les deux)" if km_between and km_between < 15_000 else ""
            alerts.append({
                "level": "warning",
                "category": "ct_anomaly",
                "title": f"{len(suspect_new)} defaut(s) majeur(s) apparu(s) au CT du {new_ct.date}{km_note}",
                "detail": "Defauts majeurs/critiques apparus sans etre mineurs au CT precedent :\n"
                          + "\n".join(detail_parts),
            })

        if escalated:
            detail_parts = [
                f"- {o.severity} -> {n.severity} : {n.description[:80]}"
                for o, n in escalated
            ]
            alerts.append({
                "level": "warning",
                "category": "ct_anomaly",
                "title": f"{len(escalated)} defaut(s) aggrave(s) entre {old_ct.date} et {new_ct.date}",
                "detail": "Defauts dont la severite a augmente :\n" + "\n".join(detail_parts),
            })

        # Recurring defects across many CTs
        if i >= 2:
            prev_prev = reports[i - 2]
            prev_prev_keys = {_defect_key(d) for d in prev_prev.defects}
            recurring = [
                d for key, d in new_defects.items()
                if key in old_defects and key in prev_prev_keys
            ]
            if recurring:
                alerts.append({
                    "level": "info",
                    "category": "ct_recurring",
                    "title": f"{len(recurring)} defaut(s) recurrent(s) depuis 3+ CT",
                    "detail": "Defauts presents sur au moins 3 CT consecutifs :\n"
                              + "\n".join(f"- {d.description[:80]}" for d in recurring),
                })

    return {
        "comparisons": comparisons,
        "current_status": current_status,
        "alerts": alerts,
    }


def _check_maintenance_intervals(db: Session, vehicle_id: int) -> list[dict]:
    """Check if key maintenance items are overdue by km or time."""
    # Get latest mileage
    latest_km = get_last_known_mileage(db, vehicle_id)
    today = date.today()
    alerts = []

    events = (
        db.query(MaintenanceEvent)
        .options(joinedload(MaintenanceEvent.items))
        .filter(
            MaintenanceEvent.vehicle_id == vehicle_id,
            MaintenanceEvent.event_type == "invoice",
        )
        .order_by(MaintenanceEvent.date.desc())
        .all()
    )

    for keywords, max_km, max_months, label in INTERVALS:
        last_date = None
        last_km = None

        # Search for most recent matching maintenance
        for ev in events:
            for item in ev.items:
                desc = (item.description or "").lower()
                cat = (item.category or "").lower()
                part = (item.part_name or "").lower()
                text = f"{desc} {cat} {part}"

                if any(kw in text for kw in keywords):
                    if last_date is None or ev.date > last_date:
                        last_date = ev.date
                        last_km = ev.mileage
                    break

        if last_date is None:
            alerts.append({
                "level": "info",
                "category": "interval",
                "title": f"{label} — aucun historique",
                "detail": f"Aucune trace de {label.lower()} dans l'historique. "
                          "Verifiez si c'est a jour.",
                "maintenance_type": label,
                "last_date": None,
                "last_km": None,
                "km_since": None,
                "months_since": None,
            })
            continue

        km_since = (latest_km - last_km) if latest_km and last_km else None
        months_since = _months_between(last_date, today)

        overdue_km = max_km and km_since and km_since > max_km
        overdue_time = max_months and months_since > max_months

        if overdue_km or overdue_time:
            parts = []
            if overdue_km:
                parts.append(f"{km_since:,} km depuis le dernier (seuil: {max_km:,} km)")
            if overdue_time:
                parts.append(f"{months_since} mois depuis le dernier (seuil: {max_months} mois)")
            alerts.append({
                "level": "warning",
                "category": "interval",
                "title": f"{label} — en retard",
                "detail": f"Dernier {label.lower()} le {last_date} a {last_km or '?'} km. "
                          + " | ".join(parts),
                "maintenance_type": label,
                "last_date": str(last_date),
                "last_km": last_km,
                "km_since": km_since,
                "months_since": months_since,
            })
        else:
            # Not overdue, but include as info for completeness
            alerts.append({
                "level": "ok",
                "category": "interval",
                "title": f"{label} — a jour",
                "detail": f"Dernier {label.lower()} le {last_date} a {last_km or '?'} km"
                          + (f" ({km_since:,} km depuis)" if km_since else "")
                          + (f" ({months_since} mois)" if months_since else ""),
                "maintenance_type": label,
                "last_date": str(last_date),
                "last_km": last_km,
                "km_since": km_since,
                "months_since": months_since,
            })

    return alerts


def _check_unresolved_ct_defects(db: Session, vehicle_id: int) -> list[dict]:
    """Check if defects from the latest CT have been addressed by subsequent maintenance."""
    latest_ct = (
        db.query(CTReport)
        .options(joinedload(CTReport.defects))
        .filter(CTReport.vehicle_id == vehicle_id)
        .order_by(CTReport.date.desc())
        .first()
    )

    if not latest_ct or not latest_ct.defects:
        return []

    # Get maintenance after the CT date
    post_ct_events = (
        db.query(MaintenanceEvent)
        .options(joinedload(MaintenanceEvent.items))
        .filter(
            MaintenanceEvent.vehicle_id == vehicle_id,
            MaintenanceEvent.date >= latest_ct.date,
            MaintenanceEvent.event_type == "invoice",
        )
        .all()
    )

    post_ct_items_text = ""
    for ev in post_ct_events:
        for item in ev.items:
            post_ct_items_text += f" {(item.description or '')} {(item.category or '')} {(item.part_name or '')} "
    post_ct_items_text = post_ct_items_text.lower()

    alerts = []
    # Map CT defect categories to maintenance keywords
    defect_keywords = {
        "eclairage": ["phare", "ampoule", "feu", "optique", "eclairage"],
        "freinage": ["frein", "plaquette", "disque", "liquide de frein"],
        "direction": ["direction", "timonerie", "rotule", "biellette direction", "ripage"],
        "liaison_sol": ["amortisseur", "triangle", "silentbloc", "suspension", "bras"],
        "pollution": ["antipollution", "obd", "catalyseur", "fap", "egr", "sonde"],
        "structure": ["carrosserie", "panneau", "porte", "capot"],
        "equipements": ["support moteur", "moteur", "ouvrant"],
        "visibilite": ["essuie-glace", "balai", "pare-brise"],
    }

    for defect in latest_ct.defects:
        cat = (defect.category or "").lower()
        keywords = defect_keywords.get(cat, [cat] if cat else [])

        addressed = any(kw in post_ct_items_text for kw in keywords)

        if not addressed and defect.severity in ("majeur", "critique"):
            alerts.append({
                "level": "critical",
                "category": "unresolved",
                "title": f"Defaut CT non resolu : {defect.description[:60]}",
                "detail": f"[{defect.severity.upper()}] {defect.description}\n"
                          f"Releve au CT du {latest_ct.date}. "
                          "Aucune intervention correspondante trouvee dans l'historique.",
            })
        elif not addressed and defect.severity == "mineur":
            alerts.append({
                "level": "info",
                "category": "unresolved",
                "title": f"Defaut CT mineur non traite : {defect.description[:60]}",
                "detail": f"[MINEUR] {defect.description}\n"
                          f"Releve au CT du {latest_ct.date}.",
            })

    return alerts


def _defect_key(defect: CTDefect) -> str:
    """Create a comparable key for a defect (code or description-based)."""
    if defect.code:
        return defect.code.strip()
    # Normalize description for comparison
    desc = (defect.description or "").lower().strip()
    # Remove minor variations
    for noise in [",", ".", "avg", "avd", "arg", "ard"]:
        desc = desc.replace(noise, "")
    return desc[:60]


def _months_between(d1: date, d2: date) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def _compute_health_score(ct_analysis: dict, intervals: list[dict], unresolved: list[dict]) -> dict:
    """Compute a 0-100 health score based on vehicle state."""
    score = 100
    details = []

    # CT status (max -40)
    status = ct_analysis.get("current_status")
    if not status:
        score -= 10
        details.append(("Aucun CT enregistre", -10))
    else:
        if status["result"] in ("defavorable", "contre_visite"):
            score -= 30
            details.append(("CT defavorable", -30))
        ct_alerts = [a for a in ct_analysis.get("alerts", []) if a["category"] == "ct"]
        for a in ct_alerts:
            if "en retard" in a["title"].lower():
                score -= 20
                details.append(("CT en retard", -20))
                break
            elif "bientot" in a["title"].lower():
                score -= 5
                details.append(("CT bientot du", -5))
                break

    # Maintenance intervals (max -30)
    overdue = [i for i in intervals if i["level"] == "warning"]
    unknown = [i for i in intervals if i["level"] == "info"]
    if overdue:
        penalty = min(len(overdue) * 5, 30)
        score -= penalty
        details.append((f"{len(overdue)} entretien(s) en retard", -penalty))
    if unknown:
        penalty = min(len(unknown) * 2, 10)
        score -= penalty
        details.append((f"{len(unknown)} entretien(s) sans historique", -penalty))

    # Unresolved defects (max -30)
    critical_unresolved = [u for u in unresolved if u["level"] == "critical"]
    if critical_unresolved:
        penalty = min(len(critical_unresolved) * 10, 30)
        score -= penalty
        details.append((f"{len(critical_unresolved)} defaut(s) CT non resolu(s)", -penalty))

    score = max(0, min(100, score))
    label = "Excellent" if score >= 80 else "Bon" if score >= 60 else "Moyen" if score >= 40 else "Critique"
    color = "green" if score >= 80 else "blue" if score >= 60 else "orange" if score >= 40 else "red"

    return {"score": score, "label": label, "color": color, "details": details}
