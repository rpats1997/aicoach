from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Drill, User
from app.schemas import DrillOut

router = APIRouter(prefix="/api/drills", tags=["drills"])


@router.get("", response_model=list[DrillOut])
def list_drills(
    sport: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Drill)
    if sport:
        query = query.filter(Drill.sport == sport)
    return query.order_by(Drill.sport, Drill.title).all()
