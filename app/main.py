from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.routers import auth, vehicles, documents, chat

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Care of your Car", version="0.1.0")

# API routes
app.include_router(auth.router)
app.include_router(vehicles.router)
app.include_router(documents.router)
app.include_router(chat.router)


# Migrate existing DB: add missing columns
def _migrate_db():
    import sqlalchemy
    insp = sqlalchemy.inspect(engine)
    if "vehicles" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("vehicles")]
        with engine.begin() as conn:
            if "user_id" not in cols:
                conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN user_id INTEGER REFERENCES users(id)"))
            if "photo_path" not in cols:
                conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN photo_path VARCHAR(255)"))

_migrate_db()

@app.get("/api/shared/{token}")
def get_shared_vehicle(token: str, db: Session = Depends(get_db)):
    """Public read-only access to a shared vehicle."""
    from app.models import ShareLink, Vehicle, MaintenanceEvent, CTReport
    from app.services.analysis import analyze_vehicle
    from sqlalchemy.orm import joinedload

    link = db.query(ShareLink).filter(ShareLink.token == token, ShareLink.active == True).first()
    if not link:
        raise HTTPException(404, "Lien de partage invalide ou expire")

    # Check expiration
    if link.expires_at is not None:
        from datetime import datetime
        if link.expires_at < datetime.now():
            raise HTTPException(404, "Lien de partage invalide ou expire")

    vehicle = db.get(Vehicle, link.vehicle_id)
    if not vehicle:
        raise HTTPException(404)

    analysis = analyze_vehicle(db, vehicle.id)
    events = db.query(MaintenanceEvent).filter(MaintenanceEvent.vehicle_id == vehicle.id).order_by(MaintenanceEvent.date.desc()).all()
    cts = db.query(CTReport).options(joinedload(CTReport.defects)).filter(CTReport.vehicle_id == vehicle.id).order_by(CTReport.date.desc()).all()

    return {
        "vehicle": {"name": vehicle.name, "brand": vehicle.brand, "model": vehicle.model, "year": vehicle.year, "plate_number": vehicle.plate_number},
        "health_score": analysis.get("health_score"),
        "current_ct_status": analysis.get("current_ct_status"),
        "alerts_count": len(analysis.get("alerts", [])),
        "maintenance_count": len(events),
        "ct_count": len(cts),
        "maintenance": [{"date": str(e.date), "mileage": e.mileage, "total_cost": float(e.total_cost) if e.total_cost else None, "garage": e.garage_name} for e in events[:20]],
        "ct_reports": [{"date": str(c.date), "result": c.result, "mileage": c.mileage, "defect_count": len(c.defects)} for c in cts],
    }


# Static files (frontend)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def index():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/shared/{token}")
def shared_view(token: str):
    return FileResponse(str(static_dir / "shared.html"))
