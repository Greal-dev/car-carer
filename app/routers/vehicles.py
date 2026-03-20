import csv
import io
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import Response as RawResponse, FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import UPLOAD_PATH
from app.database import get_db
from app.models import Vehicle, MaintenanceEvent, MaintenanceItem, CTReport, CTDefect, Document
from app.models.user import User
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleOut, VehicleSummary
from app.services.analysis import analyze_vehicle
from app.routers.auth import get_current_user

PHOTO_DIR = UPLOAD_PATH / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


# --- Dashboard (multi-vehicle overview) ---

@router.get("/dashboard")
def get_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Multi-vehicle dashboard with health scores and key stats."""
    vehicles = (
        db.query(Vehicle)
        .filter((Vehicle.user_id == user.id) | (Vehicle.user_id.is_(None)))
        .order_by(Vehicle.name)
        .all()
    )
    results = []
    total_spent_all = 0
    for v in vehicles:
        analysis = analyze_vehicle(db, v.id)
        hs = analysis.get("health_score", {})

        spent = db.query(func.sum(MaintenanceEvent.total_cost)).filter(
            MaintenanceEvent.vehicle_id == v.id, MaintenanceEvent.event_type == "invoice"
        ).scalar() or 0
        total_spent_all += float(spent)

        critical_count = len([a for a in analysis.get("alerts", []) if a["level"] == "critical"])
        warning_count = len([a for a in analysis.get("alerts", []) if a["level"] == "warning"])

        last_mileage = None
        last_ev = db.query(MaintenanceEvent).filter(
            MaintenanceEvent.vehicle_id == v.id, MaintenanceEvent.mileage.isnot(None)
        ).order_by(MaintenanceEvent.date.desc()).first()
        if last_ev:
            last_mileage = last_ev.mileage

        results.append({
            "id": v.id, "name": v.name, "brand": v.brand, "model": v.model, "year": v.year,
            "plate_number": v.plate_number,
            "health_score": hs.get("score"), "health_label": hs.get("label"), "health_color": hs.get("color"),
            "critical_alerts": critical_count, "warning_alerts": warning_count,
            "total_spent": round(float(spent), 2), "last_mileage": last_mileage,
        })

    avg_score = round(sum(r["health_score"] or 0 for r in results) / len(results), 1) if results else 0
    return {
        "vehicles": results,
        "summary": {
            "vehicle_count": len(results),
            "avg_health_score": avg_score,
            "total_spent": round(total_spent_all, 2),
            "total_critical": sum(r["critical_alerts"] for r in results),
            "total_warnings": sum(r["warning_alerts"] for r in results),
        },
    }


def _get_vehicle_or_404(vehicle_id: int, user: User, db: Session) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle or (vehicle.user_id and vehicle.user_id != user.id):
        raise HTTPException(404, "Vehicule non trouve")
    return vehicle


@router.get("", response_model=list[VehicleSummary])
def list_vehicles(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from sqlalchemy import select, and_

    # Subquery: last maintenance date per vehicle
    last_event_sq = (
        db.query(
            MaintenanceEvent.vehicle_id,
            func.max(MaintenanceEvent.date).label("last_maintenance_date"),
        )
        .group_by(MaintenanceEvent.vehicle_id)
        .subquery()
    )

    # Subquery: max date with non-null mileage from maintenance events (for join below)
    max_mileage_date_sq = (
        db.query(
            MaintenanceEvent.vehicle_id,
            func.max(MaintenanceEvent.date).label("max_date"),
        )
        .filter(MaintenanceEvent.mileage.isnot(None))
        .group_by(MaintenanceEvent.vehicle_id)
        .subquery()
    )
    # Subquery: get the actual mileage for that max date (SQLite-compatible, no DISTINCT ON)
    last_mileage_event_sq = (
        db.query(
            MaintenanceEvent.vehicle_id,
            MaintenanceEvent.mileage.label("last_event_mileage"),
            MaintenanceEvent.date.label("last_event_mileage_date"),
        )
        .join(
            max_mileage_date_sq,
            and_(
                MaintenanceEvent.vehicle_id == max_mileage_date_sq.c.vehicle_id,
                MaintenanceEvent.date == max_mileage_date_sq.c.max_date,
            ),
        )
        .filter(MaintenanceEvent.mileage.isnot(None))
        .subquery()
    )

    # Subquery: max date with non-null mileage from CT reports
    max_ct_mileage_date_sq = (
        db.query(
            CTReport.vehicle_id,
            func.max(CTReport.date).label("max_date"),
        )
        .filter(CTReport.mileage.isnot(None))
        .group_by(CTReport.vehicle_id)
        .subquery()
    )
    last_mileage_ct_sq = (
        db.query(
            CTReport.vehicle_id,
            CTReport.mileage.label("last_ct_mileage"),
            CTReport.date.label("last_ct_mileage_date"),
        )
        .join(
            max_ct_mileage_date_sq,
            and_(
                CTReport.vehicle_id == max_ct_mileage_date_sq.c.vehicle_id,
                CTReport.date == max_ct_mileage_date_sq.c.max_date,
            ),
        )
        .filter(CTReport.mileage.isnot(None))
        .subquery()
    )

    # Subquery: total spent per vehicle (invoices only)
    spent_sq = (
        db.query(
            MaintenanceEvent.vehicle_id,
            func.sum(MaintenanceEvent.total_cost).label("total_spent"),
        )
        .filter(MaintenanceEvent.event_type == "invoice")
        .group_by(MaintenanceEvent.vehicle_id)
        .subquery()
    )

    # Subquery: document count per vehicle
    doc_count_sq = (
        db.query(
            Document.vehicle_id,
            func.count(Document.id).label("doc_count"),
        )
        .group_by(Document.vehicle_id)
        .subquery()
    )

    # Subquery: CT count per vehicle
    ct_count_sq = (
        db.query(
            CTReport.vehicle_id,
            func.count(CTReport.id).label("ct_count"),
        )
        .group_by(CTReport.vehicle_id)
        .subquery()
    )

    # Main query with all joins — 1 query instead of 4N+1
    rows = (
        db.query(
            Vehicle,
            last_event_sq.c.last_maintenance_date,
            last_mileage_event_sq.c.last_event_mileage,
            last_mileage_event_sq.c.last_event_mileage_date,
            last_mileage_ct_sq.c.last_ct_mileage,
            last_mileage_ct_sq.c.last_ct_mileage_date,
            spent_sq.c.total_spent,
            doc_count_sq.c.doc_count,
            ct_count_sq.c.ct_count,
        )
        .outerjoin(last_event_sq, Vehicle.id == last_event_sq.c.vehicle_id)
        .outerjoin(last_mileage_event_sq, Vehicle.id == last_mileage_event_sq.c.vehicle_id)
        .outerjoin(last_mileage_ct_sq, Vehicle.id == last_mileage_ct_sq.c.vehicle_id)
        .outerjoin(spent_sq, Vehicle.id == spent_sq.c.vehicle_id)
        .outerjoin(doc_count_sq, Vehicle.id == doc_count_sq.c.vehicle_id)
        .outerjoin(ct_count_sq, Vehicle.id == ct_count_sq.c.vehicle_id)
        .filter((Vehicle.user_id == user.id) | (Vehicle.user_id.is_(None)))
        .order_by(Vehicle.name)
        .all()
    )

    results = []
    for (v, last_maint_date, ev_mileage, ev_mileage_date,
         ct_mileage, ct_mileage_date, total_spent, doc_count, ct_count) in rows:
        # Determine last mileage: pick the one from the most recent source
        last_mileage = None
        if ev_mileage is not None and ct_mileage is not None:
            if ct_mileage_date and ev_mileage_date and ct_mileage_date > ev_mileage_date:
                last_mileage = ct_mileage
            else:
                last_mileage = ev_mileage
        elif ev_mileage is not None:
            last_mileage = ev_mileage
        elif ct_mileage is not None:
            last_mileage = ct_mileage

        results.append(VehicleSummary(
            id=v.id, name=v.name, brand=v.brand, model=v.model, year=v.year,
            plate_number=v.plate_number, last_mileage=last_mileage,
            last_maintenance_date=last_maint_date, total_spent=total_spent or 0,
            document_count=doc_count or 0, ct_count=ct_count or 0,
        ))
    return results


@router.post("", response_model=VehicleOut, status_code=201)
def create_vehicle(data: VehicleCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    vehicle = Vehicle(**data.model_dump(), user_id=user.id)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_vehicle_or_404(vehicle_id, user, db)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: int, data: VehicleUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    vehicle = _get_vehicle_or_404(vehicle_id, user, db)
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(vehicle, key, val)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    vehicle = _get_vehicle_or_404(vehicle_id, user, db)
    db.delete(vehicle)
    db.commit()


@router.get("/{vehicle_id}/analysis")
def get_vehicle_analysis(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    return analyze_vehicle(db, vehicle_id)


@router.get("/{vehicle_id}/stats")
def get_vehicle_stats(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return spending and mileage data for charts."""
    _get_vehicle_or_404(vehicle_id, user, db)

    # Spending by month (invoices only)
    events = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.vehicle_id == vehicle_id, MaintenanceEvent.event_type == "invoice")
        .order_by(MaintenanceEvent.date)
        .all()
    )
    spending_by_month = {}
    for ev in events:
        if ev.date and ev.total_cost:
            key = ev.date.strftime("%Y-%m")
            spending_by_month[key] = spending_by_month.get(key, 0) + float(ev.total_cost)

    # Mileage timeline (from events + CTs)
    mileage_points = []
    for ev in events:
        if ev.date and ev.mileage:
            mileage_points.append({"date": str(ev.date), "km": ev.mileage, "source": "entretien"})
    cts = (
        db.query(CTReport)
        .filter(CTReport.vehicle_id == vehicle_id)
        .order_by(CTReport.date)
        .all()
    )
    for ct in cts:
        if ct.date and ct.mileage:
            mileage_points.append({"date": str(ct.date), "km": ct.mileage, "source": "CT"})
    mileage_points.sort(key=lambda x: x["date"])

    # Spending by category
    items = (
        db.query(MaintenanceItem)
        .join(MaintenanceEvent)
        .filter(MaintenanceEvent.vehicle_id == vehicle_id, MaintenanceEvent.event_type == "invoice")
        .all()
    )
    spending_by_cat = {}
    for item in items:
        cat = item.category or "autre"
        spending_by_cat[cat] = spending_by_cat.get(cat, 0) + float(item.total_price or 0)

    return {
        "spending_by_month": [{"month": k, "amount": round(v, 2)} for k, v in sorted(spending_by_month.items())],
        "mileage_timeline": mileage_points,
        "spending_by_category": [{"category": k, "amount": round(v, 2)} for k, v in sorted(spending_by_cat.items(), key=lambda x: -x[1])],
    }


@router.get("/{vehicle_id}/export-pdf")
def export_vehicle_pdf(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate a PDF report for the vehicle."""
    vehicle = _get_vehicle_or_404(vehicle_id, user, db)
    analysis = analyze_vehicle(db, vehicle_id)

    from app.services.pdf_export import generate_vehicle_pdf
    pdf_bytes = generate_vehicle_pdf(vehicle, analysis, db)

    filename = f"rapport_{vehicle.name.replace(' ', '_')}_{vehicle_id}.pdf"
    return RawResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- CRUD for maintenance events and CT reports ---

@router.delete("/{vehicle_id}/maintenance/{event_id}", status_code=204)
def delete_maintenance_event(vehicle_id: int, event_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    event = db.get(MaintenanceEvent, event_id)
    if not event or event.vehicle_id != vehicle_id:
        raise HTTPException(404, "Entretien non trouve")
    db.delete(event)
    db.commit()


@router.delete("/{vehicle_id}/ct/{ct_id}", status_code=204)
def delete_ct_report(vehicle_id: int, ct_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    ct = db.get(CTReport, ct_id)
    if not ct or ct.vehicle_id != vehicle_id:
        raise HTTPException(404, "CT non trouve")
    db.delete(ct)
    db.commit()


# --- CSV Export ---

@router.get("/{vehicle_id}/export-csv")
def export_vehicle_csv(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Export full maintenance history as CSV."""
    vehicle = _get_vehicle_or_404(vehicle_id, user, db)
    events = (
        db.query(MaintenanceEvent)
        .options(joinedload(MaintenanceEvent.items))
        .filter(MaintenanceEvent.vehicle_id == vehicle_id)
        .order_by(MaintenanceEvent.date.desc())
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Date", "Type", "Garage", "Km", "Description", "Categorie", "Montant HT", "Montant TTC", "Total facture"])
    for ev in events:
        for item in ev.items:
            writer.writerow([
                str(ev.date) if ev.date else "",
                ev.event_type or "",
                ev.garage_name or "",
                ev.mileage or "",
                item.description or "",
                item.category or "",
                f"{item.unit_price:.2f}" if item.unit_price else "",
                f"{item.total_price:.2f}" if item.total_price else "",
                f"{ev.total_cost:.2f}" if ev.total_cost else "",
            ])
    content = output.getvalue().encode("utf-8-sig")  # BOM for Excel
    filename = f"historique_{vehicle.name.replace(' ', '_')}.csv"
    return RawResponse(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Maintenance search ---

@router.get("/{vehicle_id}/maintenance-search")
def search_maintenance(
    vehicle_id: int,
    q: str = Query("", description="Recherche dans descriptions"),
    event_type: Optional[str] = Query(None, description="invoice or quote"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search and filter maintenance events with pagination."""
    from sqlalchemy import or_, exists, select

    _get_vehicle_or_404(vehicle_id, user, db)
    query = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.vehicle_id == vehicle_id)
    )
    if event_type:
        query = query.filter(MaintenanceEvent.event_type == event_type)
    if date_from:
        query = query.filter(MaintenanceEvent.date >= date_from)
    if date_to:
        query = query.filter(MaintenanceEvent.date <= date_to)

    # SQL-level text search using ilike
    if q.strip():
        pattern = f"%{q.strip()}%"
        item_match = (
            select(MaintenanceItem.id)
            .where(
                MaintenanceItem.event_id == MaintenanceEvent.id,
                or_(
                    MaintenanceItem.description.ilike(pattern),
                    MaintenanceItem.category.ilike(pattern),
                ),
            )
            .correlate(MaintenanceEvent)
            .exists()
        )
        query = query.filter(
            or_(
                MaintenanceEvent.garage_name.ilike(pattern),
                item_match,
            )
        )

    # Get total count before pagination
    total = query.count()

    # Apply pagination at DB level
    offset = (page - 1) * limit
    events = (
        query
        .options(joinedload(MaintenanceEvent.items))
        .order_by(MaintenanceEvent.date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Deduplicate events that may appear multiple times due to joinedload
    seen = set()
    unique_events = []
    for ev in events:
        if ev.id not in seen:
            seen.add(ev.id)
            unique_events.append(ev)

    items = [
        {
            "id": ev.id, "date": str(ev.date) if ev.date else None, "event_type": ev.event_type,
            "garage_name": ev.garage_name, "mileage": ev.mileage,
            "total_cost": float(ev.total_cost) if ev.total_cost else None,
            "items": [{"id": i.id, "description": i.description, "category": i.category, "total_price": float(i.total_price) if i.total_price else None} for i in ev.items],
        }
        for ev in unique_events
    ]
    return {"items": items, "total": total, "page": page, "pages": (total + limit - 1) // limit if total else 0}


# --- Mileage validation helper ---

# --- Vehicle photo ---

@router.post("/{vehicle_id}/photo")
def upload_vehicle_photo(vehicle_id: int, request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Upload a photo for the vehicle."""
    vehicle = _get_vehicle_or_404(vehicle_id, user, db)

    # 1. Validate file extension BEFORE reading any content
    ext = ""
    if file.filename and "." in file.filename:
        ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_PHOTO_EXTS:
        raise HTTPException(
            400,
            f"Extension non supportee ({ext or 'aucune'}). "
            f"Extensions acceptees: {', '.join(sorted(ALLOWED_PHOTO_EXTS))}",
        )

    # 2. Check Content-Length header if available (reject early)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_PHOTO_SIZE:
        raise HTTPException(413, f"Fichier trop volumineux. Maximum: {MAX_PHOTO_SIZE // (1024 * 1024)} MB")

    # 3. Read in streaming with size limit (protects against missing/lying Content-Length)
    chunks = []
    total_read = 0
    chunk_size = 64 * 1024  # 64 KB chunks
    while True:
        chunk = file.file.read(chunk_size)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > MAX_PHOTO_SIZE:
            raise HTTPException(413, f"Photo trop volumineuse. Maximum: {MAX_PHOTO_SIZE // (1024 * 1024)} MB")
        chunks.append(chunk)
    contents = b"".join(chunks)

    safe_ext = ext.lstrip(".")
    filename = f"{vehicle_id}_{uuid.uuid4().hex[:8]}.{safe_ext}"
    filepath = PHOTO_DIR / filename

    with open(filepath, "wb") as f:
        f.write(contents)

    # Delete old photo if exists
    if vehicle.photo_path:
        old = PHOTO_DIR / vehicle.photo_path
        if old.exists():
            old.unlink()

    vehicle.photo_path = filename
    db.commit()
    return {"photo_path": filename}


@router.get("/{vehicle_id}/photo")
def get_vehicle_photo(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Serve the vehicle photo."""
    vehicle = _get_vehicle_or_404(vehicle_id, user, db)
    if not vehicle.photo_path:
        raise HTTPException(404, "Pas de photo")
    filepath = PHOTO_DIR / vehicle.photo_path
    if not filepath.exists():
        raise HTTPException(404, "Fichier photo introuvable")
    return FileResponse(str(filepath))


# --- Reminders (consolidated) ---

@router.get("/{vehicle_id}/reminders")
def get_reminders(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Consolidated reminders: maintenance intervals + CT."""
    from datetime import date as dt_date

    _get_vehicle_or_404(vehicle_id, user, db)
    reminders = []

    # 1. Maintenance interval reminders (from analysis)
    analysis = analyze_vehicle(db, vehicle_id)
    for interval in analysis.get("maintenance_intervals", []):
        if interval["level"] in ("warning", "info"):
            reminders.append({
                "type": "maintenance",
                "priority": "high" if interval["level"] == "warning" else "medium",
                "title": interval.get("maintenance_type", ""),
                "detail": interval.get("detail", ""),
                "source": "interval",
            })

    # 2. CT reminders
    ct_status = analysis.get("current_ct_status")
    if ct_status and ct_status.get("next_due"):
        try:
            due = dt_date.fromisoformat(ct_status["next_due"])
            days_left = (due - dt_date.today()).days
            if days_left < 0:
                priority = "critical"
                detail = f"En retard de {abs(days_left)} jours"
            elif days_left < 30:
                priority = "high"
                detail = f"Dans {days_left} jours"
            elif days_left < 90:
                priority = "medium"
                detail = f"Dans {days_left} jours ({ct_status['next_due']})"
            else:
                priority = "low"
                detail = f"Le {ct_status['next_due']}"
            reminders.append({
                "type": "ct",
                "priority": priority,
                "title": "Controle technique",
                "detail": detail,
                "due_date": ct_status["next_due"],
                "source": "ct",
            })
        except (ValueError, TypeError):
            pass

    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    reminders.sort(key=lambda r: priority_order.get(r["priority"], 9))

    return {
        "reminders": reminders,
        "counts": {
            "critical": len([r for r in reminders if r["priority"] == "critical"]),
            "high": len([r for r in reminders if r["priority"] == "high"]),
            "medium": len([r for r in reminders if r["priority"] == "medium"]),
            "low": len([r for r in reminders if r["priority"] == "low"]),
            "total": len(reminders),
        },
    }
