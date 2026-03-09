"""Shared mileage service — single source of truth for last known mileage."""

from sqlalchemy.orm import Session

from app.models import MaintenanceEvent, CTReport


def get_last_known_mileage(db: Session, vehicle_id: int) -> int | None:
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

    return max(sources) if sources else None
