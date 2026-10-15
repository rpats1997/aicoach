from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_role
from app.models import (
    ActionStepProgress,
    AIFeedback,
    Drill,
    DrillClip,
    NotificationItem,
    ProgressMetric,
    Role,
    StudentProfile,
    Team,
    TeamMembership,
    User,
)
from app.schemas import (
    AIFeedbackOut,
    ClipCreateRequest,
    DrillCreateRequest,
    DrillOut,
    FeedbackEditRequest,
    LinkRequest,
    LinkResult,
    ProgressSeries,
    StudentSummary,
    TeamOut,
    UserOut,
)
from app.services import analyze_and_publish_clip
from app.utils import redeem_link_code

router = APIRouter(prefix="/api/coach", tags=["coach"])
require_coach = require_role("coach")


def _feedback_to_out(fb: AIFeedback, db: Session) -> AIFeedbackOut:
    clip = fb.clip
    drill = clip.drill if clip else None
    steps = db.query(ActionStepProgress).filter(ActionStepProgress.feedback_id == fb.id).all()
    step_progress = {
        s.step_number: {"watched": s.watched, "practiced": s.practiced} for s in steps
    }
    return AIFeedbackOut(
        id=fb.id,
        clip_id=fb.clip_id,
        athlete_id=fb.athlete_id,
        athlete_name=fb.athlete.full_name,
        coach_id=fb.coach_id,
        drill_id=clip.drill_id if clip else "",
        drill_title=drill.title if drill else fb.drill_type,
        drill_type=fb.drill_type,
        overall_score=fb.overall_score,
        strengths=fb.strengths,
        primary_flaw=fb.primary_flaw,
        joint_angle_notes=fb.joint_angle_notes,
        action_plan=fb.action_plan,
        coach_commentary=fb.coach_commentary or "",
        is_published=fb.is_published,
        was_edited_by_coach=fb.was_edited_by_coach,
        created_at=fb.created_at,
        published_at=fb.published_at,
        video_url=clip.video_url if clip else "",
        thumbnail_url=clip.thumbnail_url if clip else None,
        uploaded_by_id=clip.uploaded_by_id if clip else "",
        uploaded_by_name=clip.uploaded_by.full_name if clip and clip.uploaded_by else "",
        uploaded_by_role=clip.uploaded_by.role.value if clip and clip.uploaded_by else "",
        step_progress=step_progress,
    )


@router.get("/teams", response_model=list[TeamOut])
def list_teams(db: Session = Depends(get_db), coach: User = Depends(require_coach)):
    teams = db.query(Team).filter(Team.coach_id == coach.id).all()
    out = []
    for t in teams:
        count = db.query(TeamMembership).filter(TeamMembership.team_id == t.id).count()
        out.append(TeamOut(id=t.id, name=t.name, sport=t.sport, grade_level=t.grade_level, student_count=count))
    return out


@router.get("/roster", response_model=list[StudentSummary])
def get_roster(
    team_id: str | None = None,
    sport: str | None = None,
    db: Session = Depends(get_db),
    coach: User = Depends(require_coach),
):
    q = (
        db.query(User, StudentProfile, Team)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(TeamMembership, TeamMembership.student_id == User.id)
        .join(Team, Team.id == TeamMembership.team_id)
        .filter(Team.coach_id == coach.id)
    )
    if team_id:
        q = q.filter(Team.id == team_id)
    if sport:
        q = q.filter(Team.sport == sport)

    results = []
    for user, profile, team in q.all():
        latest_fb = (
            db.query(AIFeedback)
            .filter(AIFeedback.athlete_id == user.id, AIFeedback.is_published.is_(True))
            .order_by(AIFeedback.published_at.desc())
            .first()
        )
        results.append(
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
    return results


@router.get("/athletes/{student_id}/progress", response_model=list[ProgressSeries])
def athlete_progress(
    student_id: str, db: Session = Depends(get_db), coach: User = Depends(require_coach)
):
    metrics = (
        db.query(ProgressMetric)
        .filter(ProgressMetric.student_id == student_id)
        .order_by(ProgressMetric.term_order)
        .all()
    )
    series: dict[str, ProgressSeries] = {}
    for m in metrics:
        if m.skill not in series:
            series[m.skill] = ProgressSeries(skill=m.skill, sport=m.sport, points=[])
        series[m.skill].points.append(
            {"term_label": m.term_label, "term_order": m.term_order, "score": m.score}
        )
    return list(series.values())


@router.post("/clips", response_model=AIFeedbackOut, status_code=status.HTTP_201_CREATED)
def create_and_analyze_clip(
    payload: ClipCreateRequest,
    db: Session = Depends(get_db),
    coach: User = Depends(require_coach),
):
    """Mocks: direct cloud upload already happened client-side -> we register the
    clip, run the (mocked) AI analysis synchronously, and publish the result
    immediately so the athlete and parents see it right away. The coach can
    still edit/refine it afterward from the review queue."""
    drill = db.query(Drill).filter(Drill.id == payload.drill_id).first()
    if drill is None:
        raise HTTPException(status_code=404, detail="Drill not found")

    clip = DrillClip(
        student_id=payload.student_id,
        coach_id=coach.id,
        uploaded_by_id=coach.id,
        drill_id=payload.drill_id,
        video_url=payload.video_url,
        thumbnail_url=payload.thumbnail_url,
        is_retry_attempt=payload.is_retry_attempt,
        parent_feedback_id=payload.parent_feedback_id,
    )
    db.add(clip)
    db.flush()

    feedback = analyze_and_publish_clip(db, clip)
    db.commit()
    db.refresh(feedback)
    return _feedback_to_out(feedback, db)


@router.get("/feedback", response_model=list[AIFeedbackOut])
def list_feedback(
    edited: bool | None = None,
    athlete_id: str | None = None,
    db: Session = Depends(get_db),
    coach: User = Depends(require_coach),
):
    q = db.query(AIFeedback).filter(AIFeedback.coach_id == coach.id)
    if edited is not None:
        q = q.filter(AIFeedback.was_edited_by_coach.is_(edited))
    if athlete_id:
        q = q.filter(AIFeedback.athlete_id == athlete_id)
    items = q.order_by(AIFeedback.created_at.desc()).all()
    return [_feedback_to_out(f, db) for f in items]


@router.get("/feedback/{feedback_id}", response_model=AIFeedbackOut)
def get_feedback(feedback_id: str, db: Session = Depends(get_db), coach: User = Depends(require_coach)):
    fb = db.query(AIFeedback).filter(AIFeedback.id == feedback_id, AIFeedback.coach_id == coach.id).first()
    if fb is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return _feedback_to_out(fb, db)


@router.patch("/feedback/{feedback_id}", response_model=AIFeedbackOut)
def edit_feedback(
    feedback_id: str,
    payload: FeedbackEditRequest,
    db: Session = Depends(get_db),
    coach: User = Depends(require_coach),
):
    """The AI feedback is already visible to the athlete/parents the moment it's
    generated, so editing here just refines what they're already seeing -
    there's no separate publish step."""
    fb = db.query(AIFeedback).filter(AIFeedback.id == feedback_id, AIFeedback.coach_id == coach.id).first()
    if fb is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    data = payload.model_dump(exclude_unset=True)
    if "action_plan" in data and data["action_plan"] is not None:
        data["action_plan"] = [step for step in data["action_plan"]]

    changed = False
    for field, value in data.items():
        if getattr(fb, field) != value:
            setattr(fb, field, value)
            changed = True
    if changed:
        fb.was_edited_by_coach = True

    db.commit()
    db.refresh(fb)
    return _feedback_to_out(fb, db)


@router.get("/drill-library", response_model=list[DrillOut])
def drill_library(db: Session = Depends(get_db), coach: User = Depends(require_coach)):
    return db.query(Drill).order_by(Drill.sport, Drill.title).all()


@router.get("/sports", response_model=list[str])
def list_sports(db: Session = Depends(get_db), coach: User = Depends(require_coach)):
    """All sports currently in use, so the coach can reuse one or type a brand-new one."""
    drill_sports = {row[0] for row in db.query(Drill.sport).distinct().all()}
    team_sports = {row[0] for row in db.query(Team.sport).distinct().all()}
    return sorted(drill_sports | team_sports)


@router.post("/drills", response_model=DrillOut, status_code=status.HTTP_201_CREATED)
def create_drill(
    payload: DrillCreateRequest,
    db: Session = Depends(get_db),
    coach: User = Depends(require_coach),
):
    drill = Drill(
        title=payload.title.strip(),
        sport=payload.sport.strip(),
        category=payload.category.strip(),
        description=payload.description.strip(),
        reference_video_url=payload.reference_video_url,
        thumbnail_url=payload.thumbnail_url,
        created_by=coach.id,
    )
    db.add(drill)
    db.commit()
    db.refresh(drill)
    return drill


@router.post("/link-student", response_model=LinkResult)
def link_student(
    payload: LinkRequest, db: Session = Depends(get_db), coach: User = Depends(require_coach)
):
    """Adds a student to this coach's roster. The student generates the code
    from their own Profile screen and shares it with the coach out-of-band."""
    student = (
        db.query(User)
        .filter(User.email == payload.email.lower().strip(), User.role == Role.student)
        .first()
    )
    if student is None:
        raise HTTPException(status_code=404, detail="No student account found with that email")

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == student.id).first()
    if profile is None:
        raise HTTPException(status_code=400, detail="This student doesn't have a completed profile yet")

    already_rostered = (
        db.query(TeamMembership)
        .join(Team, Team.id == TeamMembership.team_id)
        .filter(Team.coach_id == coach.id, TeamMembership.student_id == student.id)
        .first()
    )
    if already_rostered is not None:
        raise HTTPException(status_code=400, detail="This student is already on your roster")

    redeem_link_code(db, student, payload.code)

    team = (
        db.query(Team)
        .filter(Team.coach_id == coach.id, Team.sport == profile.primary_sport)
        .first()
    )
    if team is None:
        team = Team(
            school_id=coach.school_id,
            coach_id=coach.id,
            name=f"{profile.primary_sport} Team",
            sport=profile.primary_sport,
        )
        db.add(team)
        db.flush()

    db.add(TeamMembership(team_id=team.id, student_id=student.id))
    db.add(
        NotificationItem(
            user_id=student.id,
            title=f"You've been added to {coach.full_name}'s roster",
            body=f"You're now on {team.name}.",
            kind="link",
        )
    )
    db.commit()
    return LinkResult(linked_user=UserOut.model_validate(student), message=f"Added {student.full_name} to {team.name}")
