import csv
import io
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import Response as RawResponse, FileResponse
from sqlalchemy import func, extract
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Vehicle, MaintenanceEvent, MaintenanceItem, CTReport, CTDefect, Document, ShareLink, FuelEntry, Warranty
from app.models.user import User
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleOut, VehicleSummary, FuelEntryCreate, FuelEntryOut, WarrantyCreate, WarrantyOut
from app.services.analysis import analyze_vehicle
from app.routers.auth import get_current_user

PHOTO_DIR = Path("./uploads/photos")
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

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
    vehicles = (
        db.query(Vehicle)
        .filter((Vehicle.user_id == user.id) | (Vehicle.user_id.is_(None)))
        .order_by(Vehicle.name)
        .all()
    )
    results = []
    for v in vehicles:
        last_mileage = None
        last_maintenance_date = None

        last_event = (
            db.query(MaintenanceEvent)
            .filter(MaintenanceEvent.vehicle_id == v.id)
            .order_by(MaintenanceEvent.date.desc())
            .first()
        )
        if last_event:
            last_maintenance_date = last_event.date
            if last_event.mileage:
                last_mileage = last_event.mileage

        last_ct = (
            db.query(CTReport)
            .filter(CTReport.vehicle_id == v.id)
            .order_by(CTReport.date.desc())
            .first()
        )
        if last_ct and last_ct.mileage:
            if last_mileage is None or (last_ct.date and last_event and last_ct.date > last_event.date):
                last_mileage = last_ct.mileage

        total_spent = db.query(func.sum(MaintenanceEvent.total_cost)).filter(
            MaintenanceEvent.vehicle_id == v.id,
            MaintenanceEvent.event_type == "invoice",
        ).scalar() or 0

        doc_count = db.query(func.count(Document.id)).filter(Document.vehicle_id == v.id).scalar()
        ct_count = db.query(func.count(CTReport.id)).filter(CTReport.vehicle_id == v.id).scalar()

        results.append(VehicleSummary(
            id=v.id, name=v.name, brand=v.brand, model=v.model, year=v.year,
            plate_number=v.plate_number, last_mileage=last_mileage,
            last_maintenance_date=last_maintenance_date, total_spent=total_spent,
            document_count=doc_count, ct_count=ct_count,
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


# --- Share links ---

@router.post("/{vehicle_id}/share")
def create_share_link(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate a share token for read-only access to a vehicle's history."""
    import secrets
    _get_vehicle_or_404(vehicle_id, user, db)
    token = secrets.token_urlsafe(32)
    link = ShareLink(vehicle_id=vehicle_id, token=token)
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"token": token, "id": link.id}


@router.delete("/{vehicle_id}/share/{link_id}", status_code=204)
def revoke_share_link(vehicle_id: int, link_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    link = db.get(ShareLink, link_id)
    if not link or link.vehicle_id != vehicle_id:
        raise HTTPException(404)
    db.delete(link)
    db.commit()


@router.get("/{vehicle_id}/shares")
def list_share_links(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    links = db.query(ShareLink).filter(ShareLink.vehicle_id == vehicle_id, ShareLink.active == True).all()
    return [{"id": l.id, "token": l.token, "created_at": str(l.created_at)} for l in links]


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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search and filter maintenance events."""
    _get_vehicle_or_404(vehicle_id, user, db)
    query = (
        db.query(MaintenanceEvent)
        .options(joinedload(MaintenanceEvent.items))
        .filter(MaintenanceEvent.vehicle_id == vehicle_id)
    )
    if event_type:
        query = query.filter(MaintenanceEvent.event_type == event_type)
    if date_from:
        query = query.filter(MaintenanceEvent.date >= date_from)
    if date_to:
        query = query.filter(MaintenanceEvent.date <= date_to)
    events = query.order_by(MaintenanceEvent.date.desc()).all()

    # Text search in items
    if q.strip():
        q_lower = q.lower()
        filtered = []
        for ev in events:
            match = q_lower in (ev.garage_name or "").lower()
            if not match:
                for item in ev.items:
                    if q_lower in (item.description or "").lower() or q_lower in (item.category or "").lower():
                        match = True
                        break
            if match:
                filtered.append(ev)
        events = filtered

    return [
        {
            "id": ev.id, "date": str(ev.date) if ev.date else None, "event_type": ev.event_type,
            "garage_name": ev.garage_name, "mileage": ev.mileage,
            "total_cost": float(ev.total_cost) if ev.total_cost else None,
            "items": [{"id": i.id, "description": i.description, "category": i.category, "total_price": float(i.total_price) if i.total_price else None} for i in ev.items],
        }
        for ev in events
    ]


# --- Calendar (upcoming maintenance) ---

@router.get("/{vehicle_id}/calendar")
def get_maintenance_calendar(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Predict upcoming maintenance based on intervals."""
    _get_vehicle_or_404(vehicle_id, user, db)
    analysis = analyze_vehicle(db, vehicle_id)
    from datetime import date
    from dateutil.relativedelta import relativedelta

    upcoming = []

    # CT due date
    ct_status = analysis.get("current_ct_status")
    if ct_status and ct_status.get("next_due"):
        upcoming.append({
            "type": "Controle technique",
            "due_date": ct_status["next_due"],
            "priority": "high" if ct_status["next_due"] < str(date.today()) else "normal",
            "source": "CT",
        })

    # Maintenance intervals overdue or coming up
    for interval in analysis.get("maintenance_intervals", []):
        if interval["level"] == "warning":
            upcoming.append({
                "type": interval.get("maintenance_type", interval.get("title", "")),
                "due_date": str(date.today()),  # Already overdue
                "priority": "overdue",
                "detail": interval.get("detail", ""),
                "source": "interval",
            })
        elif interval["level"] == "ok" and interval.get("last_date"):
            # Estimate next due
            from app.services.analysis import INTERVALS
            for keywords, max_km, max_months, label in INTERVALS:
                if label == interval.get("maintenance_type"):
                    if max_months and interval["last_date"]:
                        try:
                            last = date.fromisoformat(interval["last_date"])
                            next_due = last + relativedelta(months=max_months)
                            upcoming.append({
                                "type": label,
                                "due_date": str(next_due),
                                "priority": "normal",
                                "source": "interval",
                            })
                        except (ValueError, TypeError):
                            pass
                    break

    upcoming.sort(key=lambda x: x.get("due_date", "9999"))
    return upcoming


# --- Quote comparator ---

@router.get("/{vehicle_id}/compare-quotes")
def compare_quotes(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compare quotes (devis) for the same vehicle."""
    _get_vehicle_or_404(vehicle_id, user, db)
    quotes = (
        db.query(MaintenanceEvent)
        .options(joinedload(MaintenanceEvent.items))
        .filter(MaintenanceEvent.vehicle_id == vehicle_id, MaintenanceEvent.event_type == "quote")
        .order_by(MaintenanceEvent.date.desc())
        .all()
    )
    if not quotes:
        return {"quotes": [], "comparison": None}

    # Build comparison: group items by category across quotes
    all_categories = set()
    quote_data = []
    for q in quotes:
        items_by_cat = {}
        for item in q.items:
            cat = item.category or item.description or "autre"
            if cat not in items_by_cat:
                items_by_cat[cat] = 0
            items_by_cat[cat] += float(item.total_price or 0)
            all_categories.add(cat)
        quote_data.append({
            "id": q.id, "date": str(q.date) if q.date else None, "garage": q.garage_name,
            "total": float(q.total_cost) if q.total_cost else 0, "items_by_category": items_by_cat,
        })

    return {
        "quotes": quote_data,
        "categories": sorted(all_categories),
    }


# --- Budget forecast ---

@router.get("/{vehicle_id}/budget-forecast")
def get_budget_forecast(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Predict annual spending based on historical data and upcoming maintenance."""
    from datetime import date
    from dateutil.relativedelta import relativedelta

    _get_vehicle_or_404(vehicle_id, user, db)

    # Historical: average yearly spending over past years
    events = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.vehicle_id == vehicle_id, MaintenanceEvent.event_type == "invoice")
        .order_by(MaintenanceEvent.date)
        .all()
    )

    if not events:
        return {"historical_avg": 0, "forecast": 0, "breakdown": [], "yearly_history": []}

    # Yearly spending history
    yearly = {}
    for ev in events:
        if ev.date and ev.total_cost:
            year = ev.date.year
            yearly[year] = yearly.get(year, 0) + float(ev.total_cost)

    yearly_history = [{"year": y, "amount": round(a, 2)} for y, a in sorted(yearly.items())]
    historical_avg = round(sum(yearly.values()) / len(yearly), 2) if yearly else 0

    # Category-based forecast: average cost per category per year
    category_yearly = {}
    for ev in events:
        if ev.date and ev.total_cost:
            for item in ev.items:
                cat = item.category or "autre"
                year = ev.date.year
                key = (cat, year)
                category_yearly[key] = category_yearly.get(key, 0) + float(item.total_price or 0)

    categories = set(k[0] for k in category_yearly)
    years_count = len(yearly) or 1
    breakdown = []
    for cat in sorted(categories):
        total = sum(v for (c, y), v in category_yearly.items() if c == cat)
        avg = round(total / years_count, 2)
        breakdown.append({"category": cat, "yearly_avg": avg})

    breakdown.sort(key=lambda x: -x["yearly_avg"])
    forecast = round(sum(b["yearly_avg"] for b in breakdown), 2)

    return {
        "historical_avg": historical_avg,
        "forecast": forecast,
        "breakdown": breakdown,
        "yearly_history": yearly_history,
    }


# --- Price history (cost tracking by operation type) ---

@router.get("/{vehicle_id}/price-history")
def get_price_history(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Track how prices for common operations have changed over time."""
    _get_vehicle_or_404(vehicle_id, user, db)
    items = (
        db.query(MaintenanceItem, MaintenanceEvent.date, MaintenanceEvent.garage_name)
        .join(MaintenanceEvent)
        .filter(MaintenanceEvent.vehicle_id == vehicle_id, MaintenanceEvent.event_type == "invoice")
        .order_by(MaintenanceEvent.date)
        .all()
    )

    # Group by category
    by_category = {}
    for item, ev_date, garage in items:
        cat = item.category or "autre"
        if cat not in by_category:
            by_category[cat] = []
        if item.total_price:
            by_category[cat].append({
                "date": str(ev_date) if ev_date else None,
                "description": item.description,
                "price": round(float(item.total_price), 2),
                "garage": garage,
            })

    # Only categories with 2+ data points are interesting
    history = {}
    for cat, points in by_category.items():
        if len(points) >= 2:
            history[cat] = points

    return {"categories": history}


# --- Official maintenance booklet PDF ---

@router.get("/{vehicle_id}/export-booklet")
def export_maintenance_booklet(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate an official-style maintenance booklet PDF."""
    vehicle = _get_vehicle_or_404(vehicle_id, user, db)
    events = (
        db.query(MaintenanceEvent)
        .options(joinedload(MaintenanceEvent.items))
        .filter(MaintenanceEvent.vehicle_id == vehicle_id, MaintenanceEvent.event_type == "invoice")
        .order_by(MaintenanceEvent.date)
        .all()
    )
    cts = (
        db.query(CTReport)
        .options(joinedload(CTReport.defects))
        .filter(CTReport.vehicle_id == vehicle_id)
        .order_by(CTReport.date)
        .all()
    )

    from app.services.pdf_export import generate_booklet_pdf
    pdf_bytes = generate_booklet_pdf(vehicle, events, cts)
    filename = f"carnet_entretien_{vehicle.name.replace(' ', '_')}.pdf"
    return RawResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Mileage validation helper ---

def _get_last_known_mileage(db: Session, vehicle_id: int) -> int | None:
    """Get the highest known mileage for a vehicle from all sources."""
    sources = []
    last_ev = db.query(MaintenanceEvent.mileage).filter(
        MaintenanceEvent.vehicle_id == vehicle_id, MaintenanceEvent.mileage.isnot(None)
    ).order_by(MaintenanceEvent.mileage.desc()).first()
    if last_ev:
        sources.append(last_ev[0])

    last_ct = db.query(CTReport.mileage).filter(
        CTReport.vehicle_id == vehicle_id, CTReport.mileage.isnot(None)
    ).order_by(CTReport.mileage.desc()).first()
    if last_ct:
        sources.append(last_ct[0])

    last_fuel = db.query(FuelEntry.mileage).filter(
        FuelEntry.vehicle_id == vehicle_id
    ).order_by(FuelEntry.mileage.desc()).first()
    if last_fuel:
        sources.append(last_fuel[0])

    return max(sources) if sources else None


def _validate_mileage(db: Session, vehicle_id: int, new_mileage: int) -> dict | None:
    """Return a warning dict if mileage seems wrong, None if OK."""
    last = _get_last_known_mileage(db, vehicle_id)
    if last is None:
        return None
    if new_mileage < last:
        return {"type": "mileage_regression", "message": f"Kilometrage {new_mileage} inferieur au dernier connu ({last} km)", "last_known": last}
    if new_mileage - last > 50000:
        return {"type": "mileage_jump", "message": f"Ecart de {new_mileage - last} km depuis le dernier releve ({last} km)", "last_known": last}
    return None


# --- Fuel tracking ---

@router.post("/{vehicle_id}/fuel", status_code=201)
def add_fuel_entry(vehicle_id: int, data: FuelEntryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add a fuel entry with mileage validation."""
    _get_vehicle_or_404(vehicle_id, user, db)
    warning = _validate_mileage(db, vehicle_id, data.mileage)

    # Auto-calculate total_cost if missing
    entry_data = data.model_dump()
    if entry_data.get("price_per_liter") and not entry_data.get("total_cost"):
        entry_data["total_cost"] = round(entry_data["liters"] * entry_data["price_per_liter"], 2)

    entry = FuelEntry(vehicle_id=vehicle_id, **entry_data)
    db.add(entry)
    db.commit()
    db.refresh(entry)

    result = FuelEntryOut.model_validate(entry).model_dump()
    result["mileage_warning"] = warning
    return result


@router.get("/{vehicle_id}/fuel", response_model=list[FuelEntryOut])
def list_fuel_entries(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    return db.query(FuelEntry).filter(FuelEntry.vehicle_id == vehicle_id).order_by(FuelEntry.date.desc()).all()


@router.delete("/{vehicle_id}/fuel/{entry_id}", status_code=204)
def delete_fuel_entry(vehicle_id: int, entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    entry = db.get(FuelEntry, entry_id)
    if not entry or entry.vehicle_id != vehicle_id:
        raise HTTPException(404, "Entree carburant non trouvee")
    db.delete(entry)
    db.commit()


@router.get("/{vehicle_id}/fuel-stats")
def get_fuel_stats(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compute fuel consumption stats (L/100km, cost/km, monthly evolution)."""
    _get_vehicle_or_404(vehicle_id, user, db)
    entries = (
        db.query(FuelEntry)
        .filter(FuelEntry.vehicle_id == vehicle_id)
        .order_by(FuelEntry.date)
        .all()
    )

    if len(entries) < 2:
        return {"avg_consumption": None, "avg_cost_per_km": None, "total_liters": sum(e.liters for e in entries), "total_fuel_cost": sum(e.total_cost or 0 for e in entries), "monthly": [], "entries_count": len(entries)}

    # Consumption: only between consecutive full-tank fills
    consumptions = []
    total_liters = 0
    total_cost = 0
    for e in entries:
        total_liters += e.liters
        total_cost += e.total_cost or 0

    # Calculate L/100km between consecutive entries with full_tank
    full_entries = [e for e in entries if e.full_tank]
    liters_between = 0
    for i, e in enumerate(entries):
        if i == 0:
            continue
        liters_between += e.liters
        if e.full_tank and entries[i-1].full_tank if i == 1 else e.full_tank:
            # Find last full tank before this one
            prev_full = None
            for j in range(i - 1, -1, -1):
                if entries[j].full_tank:
                    prev_full = entries[j]
                    break
            if prev_full and e.mileage > prev_full.mileage:
                km = e.mileage - prev_full.mileage
                liters_sum = sum(entries[k].liters for k in range(entries.index(prev_full) + 1, i + 1))
                if km > 0:
                    consumptions.append({"l100": round(liters_sum / km * 100, 2), "km": km, "date": str(e.date)})

    avg_consumption = round(sum(c["l100"] for c in consumptions) / len(consumptions), 2) if consumptions else None

    # Cost per km
    total_km = entries[-1].mileage - entries[0].mileage
    avg_cost_per_km = round(total_cost / total_km, 3) if total_km > 0 else None

    # Monthly aggregation
    monthly = {}
    for e in entries:
        key = e.date.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {"liters": 0, "cost": 0, "fills": 0}
        monthly[key]["liters"] += e.liters
        monthly[key]["cost"] += e.total_cost or 0
        monthly[key]["fills"] += 1

    return {
        "avg_consumption": avg_consumption,
        "avg_cost_per_km": avg_cost_per_km,
        "total_liters": round(total_liters, 2),
        "total_fuel_cost": round(total_cost, 2),
        "entries_count": len(entries),
        "consumptions": consumptions,
        "monthly": [{"month": k, **v} for k, v in sorted(monthly.items())],
    }


# --- Vehicle photo ---

@router.post("/{vehicle_id}/photo")
def upload_vehicle_photo(vehicle_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Upload a photo for the vehicle."""
    vehicle = _get_vehicle_or_404(vehicle_id, user, db)
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, "Format non supporte (JPEG, PNG ou WebP)")

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    filename = f"{vehicle_id}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = PHOTO_DIR / filename

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

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


# --- Warranties ---

@router.post("/{vehicle_id}/warranties", status_code=201)
def add_warranty(vehicle_id: int, data: WarrantyCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add a warranty for a maintenance item."""
    _get_vehicle_or_404(vehicle_id, user, db)
    item = db.get(MaintenanceItem, data.item_id)
    if not item:
        raise HTTPException(404, "Item non trouve")
    # Verify item belongs to this vehicle
    event = db.get(MaintenanceEvent, item.event_id)
    if not event or event.vehicle_id != vehicle_id:
        raise HTTPException(404, "Item non trouve pour ce vehicule")

    end_date = data.end_date
    if not end_date and data.duration_months and data.start_date:
        from dateutil.relativedelta import relativedelta
        end_date = data.start_date + relativedelta(months=data.duration_months)

    warranty = Warranty(
        item_id=data.item_id, vehicle_id=vehicle_id,
        description=data.description, duration_months=data.duration_months,
        max_km=data.max_km, start_date=data.start_date, end_date=end_date,
    )
    db.add(warranty)
    db.commit()
    db.refresh(warranty)
    return WarrantyOut.model_validate(warranty)


@router.get("/{vehicle_id}/warranties", response_model=list[WarrantyOut])
def list_warranties(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    return db.query(Warranty).filter(Warranty.vehicle_id == vehicle_id).order_by(Warranty.end_date).all()


@router.delete("/{vehicle_id}/warranties/{warranty_id}", status_code=204)
def delete_warranty(vehicle_id: int, warranty_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    w = db.get(Warranty, warranty_id)
    if not w or w.vehicle_id != vehicle_id:
        raise HTTPException(404, "Garantie non trouvee")
    db.delete(w)
    db.commit()


# --- Reminders (consolidated) ---

@router.get("/{vehicle_id}/reminders")
def get_reminders(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Consolidated reminders: maintenance intervals + CT + expiring warranties."""
    from datetime import date as dt_date
    from dateutil.relativedelta import relativedelta

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

    # 3. Warranty expiration reminders
    today = dt_date.today()
    soon = today + relativedelta(months=2)
    last_mileage = _get_last_known_mileage(db, vehicle_id)

    warranties = db.query(Warranty).filter(Warranty.vehicle_id == vehicle_id).all()
    for w in warranties:
        expired_date = w.end_date and w.end_date < today
        expired_km = w.max_km and last_mileage and last_mileage > w.max_km
        expiring_soon_date = w.end_date and today <= w.end_date <= soon
        expiring_soon_km = w.max_km and last_mileage and (w.max_km - last_mileage) < 5000

        if expired_date or expired_km:
            reminders.append({
                "type": "warranty_expired",
                "priority": "low",
                "title": f"Garantie expiree : {w.description}",
                "detail": f"Fin : {w.end_date}" + (f" ou {w.max_km:,} km" if w.max_km else ""),
                "source": "warranty",
            })
        elif expiring_soon_date or expiring_soon_km:
            reminders.append({
                "type": "warranty_expiring",
                "priority": "medium",
                "title": f"Garantie bientot expiree : {w.description}",
                "detail": f"Fin : {w.end_date}" + (f" ou {w.max_km:,} km" if w.max_km else ""),
                "source": "warranty",
            })

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
