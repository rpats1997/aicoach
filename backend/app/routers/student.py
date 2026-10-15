from datetime import datetime

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
    User,
)
from app.schemas import (
    AIFeedbackOut,
    ClipCreateRequest,
    LinkRequest,
    LinkResult,
    NotificationOut,
    ProgressSeries,
    StepProgressUpdate,
    UserOut,
)
from app.services import analyze_and_publish_clip
from app.utils import redeem_link_code, resolve_coach_for_student

router = APIRouter(prefix="/api/student", tags=["student"])
require_student = require_role("student")


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


@router.get("/feed", response_model=list[AIFeedbackOut])
def get_feed(db: Session = Depends(get_db), student: User = Depends(require_student)):
    items = (
        db.query(AIFeedback)
        .filter(AIFeedback.athlete_id == student.id, AIFeedback.is_published.is_(True))
        .order_by(AIFeedback.published_at.desc())
        .all()
    )
    return [_feedback_to_out(f, db) for f in items]


@router.get("/feedback/{feedback_id}", response_model=AIFeedbackOut)
def get_feedback_detail(
    feedback_id: str, db: Session = Depends(get_db), student: User = Depends(require_student)
):
    fb = (
        db.query(AIFeedback)
        .filter(AIFeedback.id == feedback_id, AIFeedback.athlete_id == student.id)
        .first()
    )
    if fb is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return _feedback_to_out(fb, db)


@router.patch("/feedback/{feedback_id}/steps", response_model=AIFeedbackOut)
def update_step_progress(
    feedback_id: str,
    payload: StepProgressUpdate,
    db: Session = Depends(get_db),
    student: User = Depends(require_student),
):
    fb = (
        db.query(AIFeedback)
        .filter(AIFeedback.id == feedback_id, AIFeedback.athlete_id == student.id)
        .first()
    )
    if fb is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    step = (
        db.query(ActionStepProgress)
        .filter(
            ActionStepProgress.feedback_id == feedback_id,
            ActionStepProgress.step_number == payload.step_number,
        )
        .first()
    )
    if step is None:
        step = ActionStepProgress(feedback_id=feedback_id, step_number=payload.step_number)
        db.add(step)

    if payload.watched is not None:
        step.watched = payload.watched
    if payload.practiced is not None:
        step.practiced = payload.practiced
    if step.watched and step.practiced and step.completed_at is None:
        step.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(fb)
    return _feedback_to_out(fb, db)


@router.post("/feedback/{feedback_id}/retry-clip", response_model=AIFeedbackOut)
def submit_retry_clip(
    feedback_id: str,
    payload: ClipCreateRequest,
    db: Session = Depends(get_db),
    student: User = Depends(require_student),
):
    """A retry attempt is itself a clip, so it goes straight through the AI
    engine like any other upload and returns fresh feedback immediately."""
    original = (
        db.query(AIFeedback)
        .filter(AIFeedback.id == feedback_id, AIFeedback.athlete_id == student.id)
        .first()
    )
    if original is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    clip = DrillClip(
        student_id=student.id,
        coach_id=original.coach_id,
        uploaded_by_id=student.id,
        drill_id=payload.drill_id,
        video_url=payload.video_url,
        thumbnail_url=payload.thumbnail_url,
        is_retry_attempt=True,
        parent_feedback_id=feedback_id,
    )
    db.add(clip)
    db.flush()

    feedback = analyze_and_publish_clip(db, clip)
    db.commit()
    db.refresh(feedback)
    return _feedback_to_out(feedback, db)


@router.post("/clips", response_model=AIFeedbackOut, status_code=status.HTTP_201_CREATED)
def upload_practice_clip(
    payload: ClipCreateRequest,
    db: Session = Depends(get_db),
    student: User = Depends(require_student),
):
    """Student proactively uploads a practice clip; the AI engine analyzes it
    immediately and the result is visible to the student (and their parents)
    right away. The coach can review and refine it afterward."""
    drill = db.query(Drill).filter(Drill.id == payload.drill_id).first()
    if drill is None:
        raise HTTPException(status_code=404, detail="Drill not found")

    coach_id = resolve_coach_for_student(db, student.id)
    clip = DrillClip(
        student_id=student.id,
        coach_id=coach_id,
        uploaded_by_id=student.id,
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


@router.post("/link-parent", response_model=LinkResult)
def link_parent(
    payload: LinkRequest, db: Session = Depends(get_db), student: User = Depends(require_student)
):
    """Links a parent to this student. The parent generates the code from their
    own Profile screen and shares it with the student out-of-band."""
    parent = (
        db.query(User)
        .filter(User.email == payload.email.lower().strip(), User.role == Role.parent)
        .first()
    )
    if parent is None:
        raise HTTPException(status_code=404, detail="No parent account found with that email")

    existing = (
        db.query(ParentStudentLink)
        .filter(ParentStudentLink.parent_id == parent.id, ParentStudentLink.student_id == student.id)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="This parent is already linked to you")

    redeem_link_code(db, parent, payload.code)
    db.add(ParentStudentLink(parent_id=parent.id, student_id=student.id))
    db.add(
        NotificationItem(
            user_id=parent.id,
            title=f"You're now linked to {student.full_name}",
            body="You can view their coach feedback and progress in the Coach.AI app.",
            kind="link",
        )
    )
    db.commit()
    return LinkResult(linked_user=UserOut.model_validate(parent), message=f"Linked to {parent.full_name}")


@router.get("/progress", response_model=list[ProgressSeries])
def student_progress(db: Session = Depends(get_db), student: User = Depends(require_student)):
    metrics = (
        db.query(ProgressMetric)
        .filter(ProgressMetric.student_id == student.id)
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


@router.get("/notifications", response_model=list[NotificationOut])
def student_notifications(db: Session = Depends(get_db), student: User = Depends(require_student)):
    return (
        db.query(NotificationItem)
        .filter(NotificationItem.user_id == student.id)
        .order_by(NotificationItem.created_at.desc())
        .all()
    )
