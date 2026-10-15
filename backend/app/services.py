"""
Shared clip -> AI feedback pipeline used by every persona's upload path.

Every clip, regardless of who uploads it (coach, student, or parent), goes
straight to the (mocked) AI analysis engine and the resulting feedback is
published immediately so the athlete and their parents can see it right away.
The coach's job shifts from "trigger analysis" to "review and refine what the
AI already produced" - they can edit the feedback at any time afterward.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.mock_ai import generate_feedback
from app.models import AIFeedback, ActionStepProgress, ClipStatus, DrillClip, NotificationItem, ParentStudentLink


def analyze_and_publish_clip(db: Session, clip: DrillClip) -> AIFeedback:
    drill = clip.drill
    analysis = generate_feedback(clip.id, drill.sport, drill.category)

    feedback = AIFeedback(
        clip_id=clip.id,
        athlete_id=clip.student_id,
        coach_id=clip.coach_id,
        drill_type=analysis["drill_type"],
        overall_score=analysis["overall_score"],
        strengths=analysis["strengths"],
        primary_flaw=analysis["primary_flaw"],
        joint_angle_notes=analysis["joint_angle_notes"],
        action_plan=analysis["action_plan"],
        is_published=True,
        published_at=datetime.utcnow(),
    )
    db.add(feedback)
    clip.status = ClipStatus.published
    db.flush()

    for i, _ in enumerate(analysis["action_plan"]):
        db.add(ActionStepProgress(feedback_id=feedback.id, step_number=i + 1))

    student = clip.student
    db.add(
        NotificationItem(
            user_id=clip.student_id,
            title="New AI feedback ready",
            body=f"Your {feedback.drill_type} review is ready — score {feedback.overall_score}/100.",
            kind="feedback",
            related_feedback_id=feedback.id,
        )
    )
    for link in db.query(ParentStudentLink).filter(ParentStudentLink.student_id == clip.student_id).all():
        db.add(
            NotificationItem(
                user_id=link.parent_id,
                title=f"{student.full_name} has new AI feedback",
                body=f"{feedback.drill_type} — score {feedback.overall_score}/100.",
                kind="feedback",
                related_feedback_id=feedback.id,
            )
        )

    if clip.uploaded_by_id != clip.coach_id:
        uploader_name = clip.uploaded_by.full_name if clip.uploaded_by else "Someone"
        db.add(
            NotificationItem(
                user_id=clip.coach_id,
                title=f"{uploader_name} uploaded a clip for {student.full_name}",
                body=f"AI feedback is ready for your review — score {feedback.overall_score}/100.",
                kind="upload",
                related_feedback_id=feedback.id,
            )
        )

    return feedback
