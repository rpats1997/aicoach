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
    ParentStudentLink,
    ProgressMetric,
    Role,
    StudentProfile,
    User,
)
from app.schemas import (
    AIFeedbackOut,
    ClipCreateRequest,
    LinkRequest,
    LinkResult,
    NotificationOut,
    ProgressSeries,
    StudentSummary,
    UserOut,
)
from app.services import analyze_and_publish_clip
from app.utils import redeem_link_code, resolve_coach_for_student

router = APIRouter(prefix="/api/parent", tags=["parent"])
require_parent = require_role("parent")


def _feedback_to_out(fb: AIFeedback, db: Session) -> AIFeedbackOut:
    clip = fb.clip
    drill = clip.drill if clip else None
    steps = db.query(ActionStepProgress).filter(ActionStepProgress.feedback_id == fb.id).all()
    step_progress = {s.step_number: {"watched": s.watched, "practiced": s.practiced} for s in steps}
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


def _assert_linked(db: Session, parent_id: str, student_id: str):
    link = (
        db.query(ParentStudentLink)
        .filter(ParentStudentLink.parent_id == parent_id, ParentStudentLink.student_id == student_id)
        .first()
    )
    if link is None:
        raise HTTPException(status_code=403, detail="Not authorized for this student")


@router.get("/children", response_model=list[StudentSummary])
def list_children(db: Session = Depends(get_db), parent: User = Depends(require_parent)):
    links = db.query(ParentStudentLink).filter(ParentStudentLink.parent_id == parent.id).all()
    out = []
    for link in links:
        student = link.student
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == student.id).first()
        latest_fb = (
            db.query(AIFeedback)
            .filter(AIFeedback.athlete_id == student.id, AIFeedback.is_published.is_(True))
            .order_by(AIFeedback.published_at.desc())
            .first()
        )
        out.append(
            StudentSummary(
                id=student.id,
                full_name=student.full_name,
                grade=profile.grade if profile else 0,
                primary_sport=profile.primary_sport if profile else "",
                jersey_number=profile.jersey_number if profile else None,
                avatar_seed=student.avatar_seed,
                team_name=None,
                latest_score=latest_fb.overall_score if latest_fb else None,
            )
        )
    return out


@router.get("/children/{student_id}/feed", response_model=list[AIFeedbackOut])
def child_feed(student_id: str, db: Session = Depends(get_db), parent: User = Depends(require_parent)):
    _assert_linked(db, parent.id, student_id)
    items = (
        db.query(AIFeedback)
        .filter(AIFeedback.athlete_id == student_id, AIFeedback.is_published.is_(True))
        .order_by(AIFeedback.published_at.desc())
        .all()
    )
    return [_feedback_to_out(f, db) for f in items]


@router.get("/children/{student_id}/progress", response_model=list[ProgressSeries])
def child_progress(student_id: str, db: Session = Depends(get_db), parent: User = Depends(require_parent)):
    _assert_linked(db, parent.id, student_id)
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


@router.post("/children/{student_id}/clips", response_model=AIFeedbackOut, status_code=status.HTTP_201_CREATED)
def upload_clip_for_child(
    student_id: str,
    payload: ClipCreateRequest,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Parent uploads a home-practice clip on behalf of a linked child; the AI
    engine analyzes it immediately and the result is visible to the parent
    (and the student) right away. The coach can review and refine it after."""
    _assert_linked(db, parent.id, student_id)
    drill = db.query(Drill).filter(Drill.id == payload.drill_id).first()
    if drill is None:
        raise HTTPException(status_code=404, detail="Drill not found")

    coach_id = resolve_coach_for_student(db, student_id)
    clip = DrillClip(
        student_id=student_id,
        coach_id=coach_id,
        uploaded_by_id=parent.id,
        drill_id=payload.drill_id,
        video_url=payload.video_url,
        thumbnail_url=payload.thumbnail_url,
    )
    db.add(clip)
    db.flush()

    feedback = analyze_and_publish_clip(db, clip)
    db.commit()
    db.refresh(feedback)
    return _feedback_to_out(feedback, db)


@router.post("/link-student", response_model=LinkResult)
def link_student(
    payload: LinkRequest, db: Session = Depends(get_db), parent: User = Depends(require_parent)
):
    """Links a student to this parent. The student generates the code from
    their own Profile screen and shares it with the parent out-of-band."""
    student = (
        db.query(User)
        .filter(User.email == payload.email.lower().strip(), User.role == Role.student)
        .first()
    )
    if student is None:
        raise HTTPException(status_code=404, detail="No student account found with that email")

    existing = (
        db.query(ParentStudentLink)
        .filter(ParentStudentLink.parent_id == parent.id, ParentStudentLink.student_id == student.id)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="This student is already linked to you")

    redeem_link_code(db, student, payload.code)
    db.add(ParentStudentLink(parent_id=parent.id, student_id=student.id))
    db.add(
        NotificationItem(
            user_id=student.id,
            title=f"{parent.full_name} linked to your account",
            body="They can now see your coach feedback and progress.",
            kind="link",
        )
    )
    db.commit()
    return LinkResult(linked_user=UserOut.model_validate(student), message=f"Linked to {student.full_name}")


@router.get("/notifications", response_model=list[NotificationOut])
def parent_notifications(db: Session = Depends(get_db), parent: User = Depends(require_parent)):
    return (
        db.query(NotificationItem)
        .filter(NotificationItem.user_id == parent.id)
        .order_by(NotificationItem.created_at.desc())
        .all()
    )
