import random
import secrets
import string
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import LinkCode, Team, TeamMembership, User

LINK_CODE_TTL_MINUTES = 10


def resolve_coach_for_student(db: Session, student_id: str) -> str:
    membership = (
        db.query(TeamMembership)
        .join(Team, Team.id == TeamMembership.team_id)
        .filter(TeamMembership.student_id == student_id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=400, detail="This athlete isn't assigned to a coach yet")
    team = db.query(Team).filter(Team.id == membership.team_id).first()
    return team.coach_id


def generate_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


def generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


def create_link_code(db: Session, user: User) -> LinkCode:
    """Issues a fresh code for this user, invalidating any still-active ones."""
    active = (
        db.query(LinkCode)
        .filter(LinkCode.user_id == user.id, LinkCode.used_at.is_(None))
        .all()
    )
    for c in active:
        c.used_at = datetime.utcnow()

    link_code = LinkCode(
        user_id=user.id,
        code=generate_otp(),
        expires_at=datetime.utcnow() + timedelta(minutes=LINK_CODE_TTL_MINUTES),
    )
    db.add(link_code)
    db.flush()
    return link_code


def redeem_link_code(db: Session, target_user: User, code: str) -> LinkCode:
    """Validates that `code` is a currently-active code belonging to target_user,
    then marks it used. Raises HTTPException on any failure."""
    link_code = (
        db.query(LinkCode)
        .filter(LinkCode.user_id == target_user.id, LinkCode.code == code.strip())
        .order_by(LinkCode.created_at.desc())
        .first()
    )
    if link_code is None:
        raise HTTPException(status_code=400, detail="Invalid code")
    if link_code.used_at is not None:
        raise HTTPException(status_code=400, detail="This code has already been used")
    if link_code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This code has expired")

    link_code.used_at = datetime.utcnow()
    return link_code
