from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Vehicle, VehicleAccess
from app.models.user import User
from app.schemas.vehicle_access import VehicleAccessCreate, VehicleAccessUpdate, VehicleAccessOut
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/vehicles", tags=["access"])


def _require_owner(vehicle_id: int, user: User, db: Session) -> Vehicle:
    """Verify the user is the owner of the vehicle."""
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(404, "Vehicule non trouve")
    if vehicle.user_id != user.id:
        access = db.query(VehicleAccess).filter(
            VehicleAccess.vehicle_id == vehicle_id,
            VehicleAccess.user_id == user.id,
            VehicleAccess.role == "owner",
        ).first()
        if not access:
            raise HTTPException(403, "Seul le proprietaire peut effectuer cette action")
    return vehicle


def _access_to_out(access: VehicleAccess, db: Session) -> dict:
    """Convert a VehicleAccess to dict with user_email populated."""
    target = db.get(User, access.user_id)
    return VehicleAccessOut(
        id=access.id,
        vehicle_id=access.vehicle_id,
        user_id=access.user_id,
        user_email=target.email if target else None,
        role=access.role,
        granted_by_user_id=access.granted_by_user_id,
        created_at=access.created_at,
    )


@router.post("/{vehicle_id}/share", response_model=VehicleAccessOut, status_code=201)
def share_vehicle(
    vehicle_id: int,
    body: VehicleAccessCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Share a vehicle with another user by email."""
    vehicle = _require_owner(vehicle_id, user, db)

    # Find target user by email
    target_user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not target_user:
        raise HTTPException(404, "Utilisateur non trouve avec cet email")

    if target_user.id == user.id:
        raise HTTPException(400, "Impossible de partager avec vous-meme")

    existing = db.query(VehicleAccess).filter(
        VehicleAccess.vehicle_id == vehicle_id,
        VehicleAccess.user_id == target_user.id,
    ).first()
    if existing:
        raise HTTPException(409, "Cet utilisateur a deja acces a ce vehicule")

    access = VehicleAccess(
        vehicle_id=vehicle_id,
        user_id=target_user.id,
        role=body.role,
        granted_by_user_id=user.id,
    )
    db.add(access)
    db.commit()
    db.refresh(access)
    return _access_to_out(access, db)


@router.get("/{vehicle_id}/access", response_model=list[VehicleAccessOut])
def list_vehicle_access(
    vehicle_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all access entries for a vehicle. Only the owner can see the full list."""
    _require_owner(vehicle_id, user, db)
    entries = (
        db.query(VehicleAccess)
        .filter(VehicleAccess.vehicle_id == vehicle_id)
        .order_by(VehicleAccess.created_at.desc())
        .all()
    )
    return [_access_to_out(a, db) for a in entries]


@router.patch("/{vehicle_id}/access/{access_id}", response_model=VehicleAccessOut)
def update_vehicle_access(
    vehicle_id: int,
    access_id: int,
    body: VehicleAccessUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the role of an existing access entry. Only the owner can modify roles."""
    vehicle = _require_owner(vehicle_id, user, db)

    access = db.get(VehicleAccess, access_id)
    if not access or access.vehicle_id != vehicle_id:
        raise HTTPException(404, "Acces non trouve")

    if access.user_id == vehicle.user_id and access.role == "owner":
        raise HTTPException(400, "Impossible de modifier le role du proprietaire principal")

    access.role = body.role
    db.commit()
    db.refresh(access)
    return _access_to_out(access, db)


@router.delete("/{vehicle_id}/access/{access_id}", status_code=204)
def revoke_vehicle_access(
    vehicle_id: int,
    access_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a shared access. Only the owner can revoke."""
    vehicle = _require_owner(vehicle_id, user, db)

    access = db.get(VehicleAccess, access_id)
    if not access or access.vehicle_id != vehicle_id:
        raise HTTPException(404, "Acces non trouve")

    if access.user_id == vehicle.user_id:
        raise HTTPException(400, "Impossible de revoquer le proprietaire principal")

    owner_count = db.query(VehicleAccess).filter(
        VehicleAccess.vehicle_id == vehicle_id,
        VehicleAccess.role == "owner",
    ).count()
    if access.role == "owner" and owner_count <= 1:
        if vehicle.user_id is None:
            raise HTTPException(400, "Impossible de revoquer le dernier proprietaire")

    db.delete(access)
    db.commit()


@router.get("/shared-with-me", response_model=list[VehicleAccessOut])
def list_shared_with_me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List vehicles shared with the current user (excluding vehicles they directly own)."""
    entries = (
        db.query(VehicleAccess)
        .filter(
            VehicleAccess.user_id == user.id,
            VehicleAccess.role != "owner",
        )
        .order_by(VehicleAccess.created_at.desc())
        .all()
    )
    return [_access_to_out(a, db) for a in entries]
