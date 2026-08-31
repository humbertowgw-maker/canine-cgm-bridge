from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.user_auth import (
    get_current_user_id,
    hash_password,
    sign_user_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=schemas.TokenOut, status_code=201)
def signup(body: schemas.SignupRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=409, detail="an account with that email already exists")

    user = models.User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    db.add(models.Subscription(user_id=user.id, status="none"))
    db.commit()
    db.refresh(user)

    return schemas.TokenOut(token=sign_user_token(user.id))


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")

    return schemas.TokenOut(token=sign_user_token(user.id))


@router.get("/me", response_model=schemas.MeOut)
def me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="not found")
    status = user.subscription.status if user.subscription else "none"
    return schemas.MeOut(id=user.id, email=user.email, subscription_status=status)
