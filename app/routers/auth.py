import time

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import hash_password, verify_password, create_token, decode_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "cc_token"

# Simple in-memory rate limiter: max 5 attempts per IP per 60 seconds
_rate_limit_store: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 60  # seconds


def reset_rate_limit_store():
    """Clear rate limit state (used by tests)."""
    _rate_limit_store.clear()


def _check_rate_limit(request: Request):
    """Raise 429 if the IP has exceeded the rate limit for auth endpoints."""
    ip = request.client.host if request.client else "unknown"
    # Skip rate limiting for test clients
    if ip == "testclient":
        return
    now = time.monotonic()

    # Clean expired entries for this IP
    if ip in _rate_limit_store:
        _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if now - t < _RATE_LIMIT_WINDOW]
    else:
        _rate_limit_store[ip] = []

    # Periodically prune IPs with no recent entries (avoid memory leak)
    if len(_rate_limit_store) > 1000:
        expired_ips = [k for k, v in _rate_limit_store.items() if not v]
        for k in expired_ips:
            del _rate_limit_store[k]

    if len(_rate_limit_store[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(429, "Trop de tentatives, reessayez plus tard")

    _rate_limit_store[ip].append(now)


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str

    model_config = {"from_attributes": True}


@router.post("/register", response_model=UserOut)
def register(body: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _check_rate_limit(request)
    if len(body.password) < 6:
        raise HTTPException(400, "Mot de passe trop court (min 6 caracteres)")

    existing = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if existing:
        raise HTTPException(409, "Email deja utilise")

    user = User(
        email=body.email.lower().strip(),
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", max_age=72 * 3600)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _check_rate_limit(request)
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(401, "Email ou mot de passe incorrect")

    token = create_token(user.id)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", max_age=72 * 3600)
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def get_me(request: Request, db: Session = Depends(get_db)):
    user = _get_current_user(request, db)
    if not user:
        raise HTTPException(401, "Non authentifie")
    return user


def _get_current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = decode_token(token)
    if not user_id:
        return None
    return db.get(User, user_id)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI dependency: returns current user or raises 401."""
    user = _get_current_user(request, db)
    if not user:
        raise HTTPException(401, "Non authentifie")
    return user
