from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import hash_password, verify_password, create_token, decode_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "cc_token"


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
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
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
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
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
