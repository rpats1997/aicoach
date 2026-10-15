from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LinkCodeOut, LoginRequest, LoginResponse, UserOut
from app.security import create_access_token, verify_password
from app.utils import create_link_code

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(subject=user.id, role=user.role.value)
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.post("/link-code", response_model=LinkCodeOut)
def generate_link_code(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Generates a short-lived code the user can share out-of-band so someone
    else (a parent, student, or coach) can link to their account."""
    link_code = create_link_code(db, current_user)
    db.commit()
    return LinkCodeOut(
        code=link_code.code,
        expires_at=link_code.expires_at,
        expires_in_seconds=int((link_code.expires_at - datetime.utcnow()).total_seconds()),
    )
