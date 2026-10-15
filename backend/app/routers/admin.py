import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_role
from app.models import (
    AIFeedback,
    CoachProfile,
    DrillClip,
    Role,
    StudentProfile,
    Team,
    TeamMembership,
    User,
    gen_uuid,
)
from app.schemas import (
    AdminCreateUserRequest,
    AdminCreateUserResponse,
    AdminKpis,
    CoachEngagement,
    SportBreakdown,
    StudentSummary,
    UserOut,
)
from app.security import hash_password
from app.utils import generate_temp_password

router = APIRouter(prefix="/api/admin", tags=["admin"])
require_admin = require_role("admin")


@router.get("/kpis", response_model=AdminKpis)
def kpis(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    total_students = db.query(User).filter(User.role == Role.student, User.school_id == admin.school_id).count()
    total_coaches = db.query(User).filter(User.role == Role.coach, User.school_id == admin.school_id).count()

    month_ago = datetime.utcnow() - timedelta(days=30)
    total_clips_this_month = (
        db.query(DrillClip).filter(DrillClip.recorded_at >= month_ago).count()
    )

    feedback_items = db.query(AIFeedback).filter(AIFeedback.is_published.is_(True)).all()
    if feedback_items:
        turnaround_hours = [
            (f.published_at - f.created_at).total_seconds() / 3600.0
            for f in feedback_items
            if f.published_at
        ]
        avg_turnaround = sum(turnaround_hours) / len(turnaround_hours) if turnaround_hours else 0.0
        avg_score = sum(f.overall_score for f in feedback_items) / len(feedback_items)
    else:
        avg_turnaround = 0.0
        avg_score = 0.0

    return AdminKpis(
        total_students=total_students,
        total_coaches=total_coaches,
        total_clips_this_month=total_clips_this_month,
        avg_review_turnaround_hours=round(avg_turnaround, 1),
        avg_overall_score=round(avg_score, 1),
    )


@router.get("/sports-breakdown", response_model=list[SportBreakdown])
def sports_breakdown(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    profiles = db.query(StudentProfile).join(User, User.id == StudentProfile.user_id).filter(
        User.school_id == admin.school_id
    ).all()
    sport_students: dict[str, list[str]] = {}
    for p in profiles:
        sport_students.setdefault(p.primary_sport, []).append(p.user_id)

    out = []
    for sport, student_ids in sport_students.items():
        scores = (
            db.query(AIFeedback.overall_score)
            .filter(AIFeedback.athlete_id.in_(student_ids), AIFeedback.is_published.is_(True))
            .all()
        )
        avg = sum(s[0] for s in scores) / len(scores) if scores else 0.0
        out.append(SportBreakdown(sport=sport, student_count=len(student_ids), avg_score=round(avg, 1)))
    return out


@router.get("/coach-engagement", response_model=list[CoachEngagement])
def coach_engagement(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    coaches = db.query(User).filter(User.role == Role.coach, User.school_id == admin.school_id).all()
    out = []
    for coach in coaches:
        items = db.query(AIFeedback).filter(
            AIFeedback.coach_id == coach.id, AIFeedback.is_published.is_(True)
        ).all()
        if items:
            turnaround = [
                (f.published_at - f.created_at).total_seconds() / 3600.0 for f in items if f.published_at
            ]
            avg_turnaround = sum(turnaround) / len(turnaround) if turnaround else 0.0
            avg_score = sum(f.overall_score for f in items) / len(items)
        else:
            avg_turnaround = 0.0
            avg_score = 0.0
        out.append(
            CoachEngagement(
                coach_id=coach.id,
                coach_name=coach.full_name,
                clips_reviewed=len(items),
                avg_turnaround_hours=round(avg_turnaround, 1),
                avg_score_given=round(avg_score, 1),
            )
        )
    return out


@router.get("/roster", response_model=list[UserOut])
def roster(
    role: str | None = None, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    q = db.query(User).filter(User.school_id == admin.school_id)
    if role:
        q = q.filter(User.role == role)
    return q.order_by(User.role, User.full_name).all()


@router.post("/users", response_model=AdminCreateUserResponse)
def create_user(
    payload: AdminCreateUserRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    """Provisions a new coach, student, or parent account for this school. There's
    no email delivery in this prototype, so the temporary password is returned
    directly for the admin to share with the new user."""
    if payload.role not in ("coach", "student", "parent"):
        raise HTTPException(status_code=400, detail="Role must be coach, student, or parent")

    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=400, detail="An account with that email already exists")

    if payload.role == "student" and (payload.grade is None or not payload.primary_sport):
        raise HTTPException(status_code=400, detail="Students need a grade and a primary sport")

    temp_password = generate_temp_password()
    user = User(
        school_id=admin.school_id,
        email=email,
        hashed_password=hash_password(temp_password),
        full_name=payload.full_name.strip(),
        role=Role(payload.role),
        avatar_seed=gen_uuid()[:8],
    )
    db.add(user)
    db.flush()

    if payload.role == "coach":
        db.add(CoachProfile(user_id=user.id, sports=[]))
    elif payload.role == "student":
        db.add(
            StudentProfile(
                user_id=user.id,
                grade=payload.grade,
                primary_sport=payload.primary_sport,
                jersey_number=payload.jersey_number,
            )
        )

    db.commit()
    db.refresh(user)
    return AdminCreateUserResponse(user=UserOut.model_validate(user), temporary_password=temp_password)


@router.get("/coaches/{coach_id}/students", response_model=list[StudentSummary])
def coach_students(
    coach_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    """Every student tagged to a given coach's teams, for the admin's view."""
    coach = db.query(User).filter(User.id == coach_id, User.school_id == admin.school_id, User.role == Role.coach).first()
    if coach is None:
        raise HTTPException(status_code=404, detail="Coach not found")

    rows = (
        db.query(User, StudentProfile, Team)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(TeamMembership, TeamMembership.student_id == User.id)
        .join(Team, Team.id == TeamMembership.team_id)
        .filter(Team.coach_id == coach_id)
        .all()
    )
    out = []
    for user, profile, team in rows:
        latest_fb = (
            db.query(AIFeedback)
            .filter(AIFeedback.athlete_id == user.id, AIFeedback.is_published.is_(True))
            .order_by(AIFeedback.published_at.desc())
            .first()
        )
        out.append(
            StudentSummary(
                id=user.id,
                full_name=user.full_name,
                grade=profile.grade,
                primary_sport=profile.primary_sport,
                jersey_number=profile.jersey_number,
                avatar_seed=user.avatar_seed,
                team_name=team.name,
                latest_score=latest_fb.overall_score if latest_fb else None,
            )
        )
    return out


def _student_export_rows(db: Session, school_id: str | None):
    profiles = (
        db.query(StudentProfile, User)
        .join(User, User.id == StudentProfile.user_id)
        .filter(User.school_id == school_id)
        .all()
    )
    rows = []
    for profile, user in profiles:
        avg_score_row = (
            db.query(func.avg(AIFeedback.overall_score))
            .filter(AIFeedback.athlete_id == user.id, AIFeedback.is_published.is_(True))
            .scalar()
        )
        rows.append(
            {
                "name": user.full_name,
                "email": user.email,
                "grade": profile.grade,
                "sport": profile.primary_sport,
                "jersey": profile.jersey_number or "",
                "avg_score": round(avg_score_row, 1) if avg_score_row else "N/A",
            }
        )
    return rows


@router.get("/export/csv")
def export_csv(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = _student_export_rows(db, admin.school_id)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["name", "email", "grade", "sport", "jersey", "avg_score"])
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_athletic_profiles.csv"},
    )


@router.get("/export/pdf")
def export_pdf(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = _student_export_rows(db, admin.school_id)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Student Athletic Profiles", styles["Title"]), Spacer(1, 12)]

    table_data = [["Name", "Email", "Grade", "Sport", "Jersey", "Avg Score"]]
    for r in rows:
        table_data.append([r["name"], r["email"], r["grade"], r["sport"], r["jersey"], r["avg_score"]])

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=student_athletic_profiles.pdf"},
    )
