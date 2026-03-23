import asyncio
import json
import logging
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import UPLOAD_PATH, settings
from app.database import get_db, SessionLocal
from app.models import Document, Vehicle, MaintenanceEvent, MaintenanceItem, CTReport, CTDefect
from app.models import FuelRecord, TaxInsuranceRecord
from app.models.user import User
from app.schemas.document import DocumentOut, ExtractionResult, DateConfirmation
from app.schemas.maintenance import MaintenanceEventOut
from app.schemas.ct_report import CTReportOut
from app.services.extraction import extract_document
from app.routers.auth import get_current_user
from app.routers.vehicles import _get_vehicle_or_404

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/webp"}

# In-memory batch job tracker
_batch_jobs: dict[str, dict] = {}
_batch_lock = asyncio.Lock()
_BATCH_TTL_SECONDS = 3600  # 1 hour


async def _cleanup_expired_batch_jobs():
    """Remove batch jobs older than TTL."""
    now = time.monotonic()
    expired = [bid for bid, job in _batch_jobs.items() if now - job.get("created_at", now) > _BATCH_TTL_SECONDS]
    for bid in expired:
        del _batch_jobs[bid]


@router.post("/upload", response_model=ExtractionResult)
async def upload_and_extract(
    vehicle_id: int = Form(...),
    doc_type: str = Form("auto"),  # invoice, ct_report, quote, auto
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _get_vehicle_or_404(vehicle_id, user, db, require_role="editor")

    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME:
        raise HTTPException(400, f"Type de fichier non supporte: {mime}")

    # Save file
    ext = Path(file.filename).suffix if file.filename else ".bin"
    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_PATH / filename
    content = await file.read()
    file_path.write_bytes(content)

    # Create document record
    doc = Document(
        vehicle_id=vehicle_id,
        doc_type=doc_type if doc_type != "auto" else "unknown",
        file_path=str(file_path),
        original_filename=file.filename or "unknown",
        mime_type=mime,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Extract with Gemini
    try:
        data = await extract_document(str(file_path), doc_type)
    except Exception as e:
        return ExtractionResult(
            success=False, doc_type=doc.doc_type, message=f"Erreur d'extraction: {e}"
        )

    if "error" in data:
        doc.extraction_raw = json.dumps(data, ensure_ascii=False)
        db.commit()
        return ExtractionResult(
            success=False, doc_type=doc.doc_type, message=data["error"], data=data
        )

    # Store raw extraction
    doc.extraction_raw = json.dumps(data, ensure_ascii=False)

    # Enrich vehicle info from extracted data
    _enrich_vehicle(vehicle, data.get("vehicle_info"))

    # Check date confidence
    date_confidence = data.get("date_confidence", "high")

    if date_confidence == "low":
        # Don't finalize — ask user to confirm/correct the date
        db.commit()
        actual_type = _detect_actual_type(data, doc_type)
        doc.doc_type = actual_type
        db.commit()
        return ExtractionResult(
            success=True,
            doc_type=actual_type,
            message=f"Date incertaine ({data.get('date', '?')}) — confirmation requise",
            data=data,
            needs_clarification=True,
            document_id=doc.id,
            extracted_date=data.get("date"),
        )

    # Date is confident — finalize normally
    return _finalize_document(db, doc, vehicle, data, doc_type)


@router.post("/{document_id}/confirm", response_model=ExtractionResult)
def confirm_document_date(
    document_id: int,
    body: DateConfirmation,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm or correct the date of a pending document, then finalize extraction."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document non trouve")

    # Verify the user has access to the vehicle associated with this document
    vehicle = _get_vehicle_or_404(doc.vehicle_id, user, db, require_role="editor")

    if doc.extracted:
        raise HTTPException(400, "Document deja finalise")

    if not doc.extraction_raw:
        raise HTTPException(400, "Aucune donnee d'extraction disponible")

    data = json.loads(doc.extraction_raw)

    # Override date with user-confirmed value
    data["date"] = body.date.isoformat()
    data["date_confidence"] = "confirmed"
    doc.extraction_raw = json.dumps(data, ensure_ascii=False)

    return _finalize_document(db, doc, vehicle, data, doc.doc_type)


@router.post("/batch-upload")
async def batch_upload(
    vehicle_id: int = Form(...),
    doc_type: str = Form("auto"),
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload multiple files at once. Returns a batch_id to track progress via SSE."""
    if len(files) > settings.batch_max_files:
        raise HTTPException(413, "Trop de fichiers (max 100)")

    vehicle = _get_vehicle_or_404(vehicle_id, user, db, require_role="editor")

    batch_id = uuid.uuid4().hex[:12]
    saved_files = []

    for f in files:
        mime = f.content_type or "application/octet-stream"
        if mime not in ALLOWED_MIME:
            continue
        ext = Path(f.filename).suffix if f.filename else ".bin"
        filename = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_PATH / filename
        content = await f.read()
        file_path.write_bytes(content)
        saved_files.append({
            "file_path": str(file_path),
            "original_filename": f.filename or "unknown",
            "mime_type": mime,
        })

    async with _batch_lock:
        await _cleanup_expired_batch_jobs()
        _batch_jobs[batch_id] = {
            "user_id": user.id,
            "vehicle_id": vehicle_id,
            "doc_type": doc_type,
            "files": saved_files,
            "total": len(saved_files),
            "processed": 0,
            "results": [],
            "done": False,
            "created_at": time.monotonic(),
        }

    # Launch processing in background
    asyncio.get_event_loop().create_task(_process_batch(batch_id))

    return {"batch_id": batch_id, "total": len(saved_files)}


async def _process_batch(batch_id: str):
    """Process all files in a batch concurrently (up to 3 at a time)."""
    job = _batch_jobs[batch_id]
    vehicle_id = job["vehicle_id"]
    doc_type = job["doc_type"]
    sem = asyncio.Semaphore(settings.batch_max_concurrent)

    async def _worker(file_info):
        async with sem:
            db = SessionLocal()
            try:
                vehicle = db.get(Vehicle, vehicle_id)
                return await _process_single_file(db, vehicle, file_info, doc_type)
            except Exception as e:
                logger.error(f"Batch processing error: {e}", exc_info=True)
                return {
                    "filename": file_info["original_filename"],
                    "success": False,
                    "message": "Erreur de traitement",
                }
            finally:
                db.close()

    tasks = [asyncio.create_task(_worker(f)) for f in job["files"]]

    for coro in asyncio.as_completed(tasks):
        result = await coro
        job["results"].append(result)
        job["processed"] = len(job["results"])

    job["done"] = True


async def _process_single_file(db: Session, vehicle: Vehicle, file_info: dict, doc_type: str) -> dict:
    """Process a single file: create document, extract, enrich."""
    doc = Document(
        vehicle_id=vehicle.id,
        doc_type=doc_type if doc_type != "auto" else "unknown",
        file_path=file_info["file_path"],
        original_filename=file_info["original_filename"],
        mime_type=file_info["mime_type"],
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        data = await extract_document(file_info["file_path"], doc_type)
    except Exception as e:
        logger.error(f"Batch extraction error for {file_info['original_filename']}: {e}", exc_info=True)
        return {"filename": file_info["original_filename"], "success": False, "message": "Erreur de traitement"}

    if "error" in data:
        doc.extraction_raw = json.dumps(data, ensure_ascii=False)
        db.commit()
        return {"filename": file_info["original_filename"], "success": False, "message": data["error"]}

    doc.extraction_raw = json.dumps(data, ensure_ascii=False)
    _enrich_vehicle(vehicle, data.get("vehicle_info"))

    actual_type = _detect_actual_type(data, doc_type)
    date_confidence = data.get("date_confidence", "high")

    if date_confidence == "low":
        doc.doc_type = actual_type
        db.commit()
        return {
            "filename": file_info["original_filename"],
            "success": True,
            "doc_type": actual_type,
            "message": f"Date incertaine ({data.get('date', '?')}) — a confirmer",
            "needs_clarification": True,
            "document_id": doc.id,
            "extracted_date": data.get("date"),
        }

    # Check for duplicates before creating records
    duplicate = _check_duplicate(db, vehicle.id, actual_type, data)
    if duplicate:
        doc.doc_type = actual_type
        doc.extracted = True
        db.commit()
        return {
            "filename": file_info["original_filename"],
            "success": True,
            "doc_type": actual_type,
            "message": f"Doublon detecte (existant du {duplicate}), document ignore",
            "duplicate": True,
        }

    if actual_type in ("invoice", "quote"):
        doc.doc_type = actual_type
        doc.extracted = True
        _create_maintenance_event(db, vehicle.id, doc.id, data)
        db.commit()
        label = "Facture" if actual_type == "invoice" else "Devis"
        return {
            "filename": file_info["original_filename"],
            "success": True,
            "doc_type": actual_type,
            "message": f"{label}: {len(data.get('items', []))} lignes",
        }
    elif actual_type == "ct_report":
        doc.doc_type = "ct_report"
        doc.extracted = True
        _create_ct_report(db, vehicle.id, doc.id, data)
        db.commit()
        return {
            "filename": file_info["original_filename"],
            "success": True,
            "doc_type": "ct_report",
            "message": f"CT: {data.get('result', '?')}, {len(data.get('defects', []))} defaut(s)",
        }
    elif actual_type == "fuel":
        doc.doc_type = "fuel"
        doc.extracted = True
        _create_fuel_record(db, vehicle.id, doc.id, data)
        db.commit()
        return {
            "filename": file_info["original_filename"],
            "success": True,
            "doc_type": "fuel",
            "message": f"Carburant: {data.get('liters', '?')}L a {data.get('price_total', '?')} EUR",
        }
    elif actual_type == "tax_insurance":
        doc.doc_type = "tax_insurance"
        doc.extracted = True
        _create_tax_insurance_record(db, vehicle.id, doc.id, data)
        db.commit()
        return {
            "filename": file_info["original_filename"],
            "success": True,
            "doc_type": "tax_insurance",
            "message": f"Taxe/assurance: {data.get('name', '?')} — {data.get('cost', '?')} EUR",
        }
    else:
        doc.extracted = True
        db.commit()
        return {"filename": file_info["original_filename"], "success": True, "doc_type": "unknown", "message": "Type non identifie"}


@router.get("/batch-status/{batch_id}")
async def batch_status_sse(batch_id: str, user: User = Depends(get_current_user)):
    """SSE endpoint to stream batch processing progress."""
    async with _batch_lock:
        await _cleanup_expired_batch_jobs()
    if batch_id not in _batch_jobs:
        raise HTTPException(404, "Batch non trouve")
    if _batch_jobs[batch_id].get("user_id") != user.id:
        raise HTTPException(404, "Batch non trouve")

    async def event_stream():
        job = _batch_jobs[batch_id]
        last_sent = -1
        while True:
            current = job["processed"]
            if current > last_sent:
                # Send progress update with latest result
                payload = {
                    "processed": current,
                    "total": job["total"],
                    "result": job["results"][-1] if job["results"] else None,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                last_sent = current
            if job["done"]:
                # Send final summary
                success_count = sum(1 for r in job["results"] if r.get("success"))
                clarify_count = sum(1 for r in job["results"] if r.get("needs_clarification"))
                duplicate_count = sum(1 for r in job["results"] if r.get("duplicate"))
                summary = {
                    "done": True,
                    "processed": job["total"],
                    "total": job["total"],
                    "success_count": success_count,
                    "error_count": job["total"] - success_count,
                    "clarification_count": clarify_count,
                    "duplicate_count": duplicate_count,
                }
                yield f"data: {json.dumps(summary, ensure_ascii=False)}\n\n"
                del _batch_jobs[batch_id]
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/pending/{vehicle_id}")
def list_pending_documents(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List documents that need date clarification (extracted=False with extraction_raw)."""
    _get_vehicle_or_404(vehicle_id, user, db)
    docs = (
        db.query(Document)
        .filter(
            Document.vehicle_id == vehicle_id,
            Document.extracted == False,
            Document.extraction_raw.isnot(None),
        )
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    results = []
    for doc in docs:
        try:
            data = json.loads(doc.extraction_raw)
        except json.JSONDecodeError:
            continue
        if "error" in data:
            continue
        results.append({
            "id": doc.id,
            "original_filename": doc.original_filename,
            "doc_type": doc.doc_type,
            "extracted_date": data.get("date"),
            "garage_name": data.get("garage_name") or data.get("center_name"),
            "mileage": data.get("mileage"),
            "total_cost": data.get("total_cost"),
            "items_count": len(data.get("items", data.get("defects", []))),
        })
    return results


def _detect_actual_type(data: dict, doc_type_hint: str) -> str:
    """Determine actual document type from extraction data."""
    actual = data.get("doc_type", doc_type_hint)
    if actual in ("invoice", "quote"):
        return actual
    if actual == "fuel" or doc_type_hint == "fuel":
        return "fuel"
    if actual == "tax_insurance" or doc_type_hint == "tax_insurance":
        return "tax_insurance"
    if "defects" in data or actual == "ct_report":
        return "ct_report"
    return "unknown"


def _check_duplicate(db: Session, vehicle_id: int, doc_type: str, data: dict) -> str | None:
    """Check if a similar record already exists. Returns date string if duplicate found."""
    extracted_date = data.get("date")
    if not extracted_date:
        return None

    try:
        d = date.fromisoformat(extracted_date)
    except ValueError:
        return None

    if doc_type in ("invoice", "quote"):
        garage = data.get("garage_name")
        total = data.get("total_cost")
        query = db.query(MaintenanceEvent).filter(
            MaintenanceEvent.vehicle_id == vehicle_id,
            MaintenanceEvent.date == d,
            MaintenanceEvent.event_type == doc_type,
        )
        if garage:
            query = query.filter(MaintenanceEvent.garage_name == garage)
        if total:
            query = query.filter(MaintenanceEvent.total_cost == total)
        if query.first():
            return extracted_date

    elif doc_type == "ct_report":
        result = data.get("result")
        mileage = data.get("mileage")
        defect_count = len(data.get("defects", []))
        query = db.query(CTReport).filter(
            CTReport.vehicle_id == vehicle_id,
            CTReport.date == d,
        )
        if result:
            query = query.filter(CTReport.result == result)
        if mileage:
            query = query.filter(CTReport.mileage == mileage)
        existing = query.first()
        if existing and len(existing.defects) == defect_count:
            return extracted_date

    return None


def _finalize_document(db: Session, doc: Document, vehicle: Vehicle, data: dict, doc_type_hint: str) -> ExtractionResult:
    """Create maintenance event or CT report from extraction data and finalize the document."""
    actual_type = _detect_actual_type(data, doc_type_hint)

    # Check for duplicates
    duplicate = _check_duplicate(db, vehicle.id, actual_type, data)
    if duplicate:
        doc.doc_type = actual_type
        doc.extracted = True
        db.commit()
        return ExtractionResult(
            success=True,
            doc_type=actual_type,
            message=f"Doublon detecte (existant du {duplicate}), document ignore",
            data=data,
        )

    if actual_type in ("invoice", "quote"):
        doc.doc_type = actual_type
        doc.extracted = True
        _create_maintenance_event(db, vehicle.id, doc.id, data)
        db.commit()
        return ExtractionResult(
            success=True,
            doc_type=actual_type,
            message=f"{'Facture' if actual_type == 'invoice' else 'Devis'} extrait(e): {len(data.get('items', []))} lignes",
            data=data,
        )
    elif actual_type == "ct_report":
        doc.doc_type = "ct_report"
        doc.extracted = True
        _create_ct_report(db, vehicle.id, doc.id, data)
        db.commit()
        return ExtractionResult(
            success=True,
            doc_type="ct_report",
            message=f"CT extrait: {data.get('result', '?')}, {len(data.get('defects', []))} defaut(s)",
            data=data,
        )
    elif actual_type == "fuel":
        doc.doc_type = "fuel"
        doc.extracted = True
        _create_fuel_record(db, vehicle.id, doc.id, data)
        db.commit()
        return ExtractionResult(
            success=True,
            doc_type="fuel",
            message=f"Carburant extrait: {data.get('liters', '?')}L a {data.get('price_total', '?')} EUR",
            data=data,
        )
    elif actual_type == "tax_insurance":
        doc.doc_type = "tax_insurance"
        doc.extracted = True
        _create_tax_insurance_record(db, vehicle.id, doc.id, data)
        db.commit()
        return ExtractionResult(
            success=True,
            doc_type="tax_insurance",
            message=f"Taxe/assurance extrait: {data.get('name', '?')} — {data.get('cost', '?')} EUR",
            data=data,
        )
    else:
        doc.extracted = True
        db.commit()
        return ExtractionResult(
            success=True, doc_type="unknown", message="Document extrait mais type non identifie", data=data
        )


def _enrich_vehicle(vehicle: Vehicle, vehicle_info: dict | None) -> None:
    """Update vehicle fields from extracted document data (only fills blanks)."""
    if not vehicle_info:
        return
    field_map = {
        "brand": "brand",
        "model": "model",
        "year": "year",
        "plate_number": "plate_number",
        "vin": "vin",
        "fuel_type": "fuel_type",
        "owner_count": "owner_count",
    }
    for src_key, dest_attr in field_map.items():
        value = vehicle_info.get(src_key)
        if value and not getattr(vehicle, dest_attr):
            setattr(vehicle, dest_attr, value)


def _create_maintenance_event(db: Session, vehicle_id: int, doc_id: int, data: dict) -> MaintenanceEvent:
    event_date = date.fromisoformat(data["date"]) if data.get("date") else date.today()
    event = MaintenanceEvent(
        vehicle_id=vehicle_id,
        document_id=doc_id,
        date=event_date,
        mileage=data.get("mileage"),
        garage_name=data.get("garage_name"),
        total_cost=data.get("total_cost"),
        notes=data.get("notes"),
        event_type=data.get("doc_type", "invoice"),
        work_type=data.get("work_type"),
    )
    db.add(event)
    db.flush()

    for item_data in data.get("items", []):
        item = MaintenanceItem(
            event_id=event.id,
            description=item_data.get("description", ""),
            category=item_data.get("category"),
            part_name=item_data.get("part_name"),
            quantity=item_data.get("quantity"),
            unit_price=item_data.get("unit_price"),
            labor_cost=item_data.get("labor_cost"),
            total_price=item_data.get("total_price"),
        )
        db.add(item)
    return event


def _create_ct_report(db: Session, vehicle_id: int, doc_id: int, data: dict) -> CTReport:
    ct_date = date.fromisoformat(data["date"]) if data.get("date") else date.today()
    next_due = date.fromisoformat(data["next_due_date"]) if data.get("next_due_date") else None
    ct = CTReport(
        vehicle_id=vehicle_id,
        document_id=doc_id,
        date=ct_date,
        mileage=data.get("mileage"),
        center_name=data.get("center_name"),
        result=data.get("result", "favorable"),
        next_due_date=next_due,
        notes=data.get("notes"),
    )
    db.add(ct)
    db.flush()

    for defect_data in data.get("defects", []):
        defect = CTDefect(
            ct_report_id=ct.id,
            code=defect_data.get("code"),
            description=defect_data.get("description", ""),
            severity=defect_data.get("severity", "mineur"),
            category=defect_data.get("category"),
        )
        db.add(defect)
    return ct


def _create_fuel_record(db: Session, vehicle_id: int, doc_id: int, data: dict) -> FuelRecord:
    """Create a FuelRecord from extracted document data."""
    fuel_date = date.fromisoformat(data["date"]) if data.get("date") else date.today()
    liters = data.get("liters", 0)
    price_total = data.get("price_total", 0)
    price_per_liter = data.get("price_per_liter")
    if price_per_liter is None and liters > 0:
        price_per_liter = round(price_total / liters, 3)
    record = FuelRecord(
        vehicle_id=vehicle_id,
        document_id=doc_id,
        date=fuel_date,
        mileage=data.get("mileage"),
        liters=liters,
        price_total=price_total,
        price_per_liter=price_per_liter,
        station_name=data.get("station_name"),
        fuel_type=data.get("fuel_type"),
        is_full_tank=data.get("is_full_tank", True),
        notes=data.get("notes"),
    )
    db.add(record)
    db.flush()
    return record


def _create_tax_insurance_record(db: Session, vehicle_id: int, doc_id: int, data: dict) -> TaxInsuranceRecord:
    """Create a TaxInsuranceRecord from extracted document data."""
    record_date = date.fromisoformat(data["date"]) if data.get("date") else date.today()
    next_renewal = None
    if data.get("next_renewal_date"):
        try:
            next_renewal = date.fromisoformat(data["next_renewal_date"])
        except (ValueError, TypeError):
            pass
    record = TaxInsuranceRecord(
        vehicle_id=vehicle_id,
        document_id=doc_id,
        date=record_date,
        record_type=data.get("record_type", "other"),
        name=data.get("name", "Document extrait"),
        provider=data.get("provider"),
        cost=data.get("cost", 0),
        next_renewal_date=next_renewal,
        renewal_frequency=data.get("renewal_frequency"),
        notes=data.get("notes"),
    )
    db.add(record)
    db.flush()
    return record


@router.get("/{vehicle_id}", response_model=list[DocumentOut])
def list_documents(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    return (
        db.query(Document)
        .filter(Document.vehicle_id == vehicle_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )


@router.get("/{vehicle_id}/maintenance", response_model=list[MaintenanceEventOut])
def list_maintenance(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    from sqlalchemy.orm import joinedload
    return (
        db.query(MaintenanceEvent)
        .options(joinedload(MaintenanceEvent.items))
        .filter(MaintenanceEvent.vehicle_id == vehicle_id)
        .order_by(MaintenanceEvent.date.desc())
        .all()
    )


@router.get("/{vehicle_id}/ct-reports", response_model=list[CTReportOut])
def list_ct_reports(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_vehicle_or_404(vehicle_id, user, db)
    from sqlalchemy.orm import joinedload
    return (
        db.query(CTReport)
        .options(joinedload(CTReport.defects))
        .filter(CTReport.vehicle_id == vehicle_id)
        .order_by(CTReport.date.desc())
        .all()
    )
