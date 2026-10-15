import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    coach = "coach"
    student = "student"
    parent = "parent"
    admin = "admin"


class ClipStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    ready_for_review = "ready_for_review"
    published = "published"


class School(Base):
    __tablename__ = "schools"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    district = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="school")
    teams = relationship("Team", back_populates="school")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False)
    avatar_seed = Column(String, default="1")
    created_at = Column(DateTime, default=datetime.utcnow)

    school = relationship("School", back_populates="users")

    student_profile = relationship(
        "StudentProfile", back_populates="user", uselist=False, foreign_keys="StudentProfile.user_id"
    )
    coach_profile = relationship(
        "CoachProfile", back_populates="user", uselist=False, foreign_keys="CoachProfile.user_id"
    )


class CoachProfile(Base):
    __tablename__ = "coach_profiles"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    title = Column(String, default="Coach")
    sports = Column(JSON, default=list)  # list[str]

    user = relationship("User", back_populates="coach_profile", foreign_keys=[user_id])


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    grade = Column(Integer, nullable=False)
    primary_sport = Column(String, nullable=False)
    jersey_number = Column(Integer, nullable=True)
    date_of_birth = Column(Date, nullable=True)

    user = relationship("User", back_populates="student_profile", foreign_keys=[user_id])


class LinkCode(Base):
    """A short-lived, single-use OTP a user generates and shares out-of-band so
    someone else can link to their account (a parent linking to a student, a
    coach adding a student to their roster, etc.)."""

    __tablename__ = "link_codes"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    code = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])


class ParentStudentLink(Base):
    __tablename__ = "parent_student_links"

    id = Column(String, primary_key=True, default=gen_uuid)
    parent_id = Column(String, ForeignKey("users.id"), nullable=False)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)
    relationship_label = Column(String, default="Parent/Guardian")

    parent = relationship("User", foreign_keys=[parent_id])
    student = relationship("User", foreign_keys=[student_id])


class Team(Base):
    __tablename__ = "teams"

    id = Column(String, primary_key=True, default=gen_uuid)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    coach_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    grade_level = Column(String, default="Varsity")

    school = relationship("School", back_populates="teams")
    coach = relationship("User", foreign_keys=[coach_id])


class TeamMembership(Base):
    __tablename__ = "team_memberships"

    id = Column(String, primary_key=True, default=gen_uuid)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)

    team = relationship("Team")
    student = relationship("User", foreign_keys=[student_id])


class Drill(Base):
    __tablename__ = "drills"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, default="")
    reference_video_url = Column(String, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)


class DrillClip(Base):
    __tablename__ = "drill_clips"

    id = Column(String, primary_key=True, default=gen_uuid)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)
    coach_id = Column(String, ForeignKey("users.id"), nullable=False)
    uploaded_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    drill_id = Column(String, ForeignKey("drills.id"), nullable=False)
    video_url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    status = Column(Enum(ClipStatus), default=ClipStatus.uploaded)
    is_retry_attempt = Column(Boolean, default=False)
    parent_feedback_id = Column(String, ForeignKey("ai_feedback.id"), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("User", foreign_keys=[student_id])
    coach = relationship("User", foreign_keys=[coach_id])
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])
    drill = relationship("Drill")


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id = Column(String, primary_key=True, default=gen_uuid)
    clip_id = Column(String, ForeignKey("drill_clips.id"), nullable=False)
    athlete_id = Column(String, ForeignKey("users.id"), nullable=False)
    coach_id = Column(String, ForeignKey("users.id"), nullable=False)
    drill_type = Column(String, nullable=False)
    overall_score = Column(Integer, nullable=False)
    strengths = Column(JSON, default=list)  # list[str]
    primary_flaw = Column(String, default="")
    joint_angle_notes = Column(Text, default="")
    action_plan = Column(JSON, default=list)  # list[{step,title,description,drill_recommendation_keywords}]
    coach_commentary = Column(Text, default="")
    is_published = Column(Boolean, default=False)
    was_edited_by_coach = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)

    clip = relationship("DrillClip", foreign_keys=[clip_id])
    athlete = relationship("User", foreign_keys=[athlete_id])
    coach = relationship("User", foreign_keys=[coach_id])


class ActionStepProgress(Base):
    __tablename__ = "action_step_progress"

    id = Column(String, primary_key=True, default=gen_uuid)
    feedback_id = Column(String, ForeignKey("ai_feedback.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    watched = Column(Boolean, default=False)
    practiced = Column(Boolean, default=False)
    retry_clip_id = Column(String, ForeignKey("drill_clips.id"), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    feedback = relationship("AIFeedback")


class ProgressMetric(Base):
    __tablename__ = "progress_metrics"

    id = Column(String, primary_key=True, default=gen_uuid)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)
    sport = Column(String, nullable=False)
    skill = Column(String, nullable=False)
    term_label = Column(String, nullable=False)  # e.g. "Fall 2024"
    term_order = Column(Integer, nullable=False)  # sortable
    score = Column(Integer, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("User", foreign_keys=[student_id])


class NotificationItem(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    body = Column(String, default="")
    kind = Column(String, default="feedback")
    is_read = Column(Boolean, default=False)
    related_feedback_id = Column(String, ForeignKey("ai_feedback.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
