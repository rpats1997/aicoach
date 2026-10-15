from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


# ---------- Auth ----------

class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    avatar_seed: str
    school_id: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Account linking (OTP) ----------

class LinkCodeOut(BaseModel):
    code: str
    expires_at: datetime
    expires_in_seconds: int


class LinkRequest(BaseModel):
    email: str
    code: str


class LinkResult(BaseModel):
    linked_user: UserOut
    message: str


# ---------- Roster / profiles ----------

class StudentSummary(BaseModel):
    id: str
    full_name: str
    grade: int
    primary_sport: str
    jersey_number: int | None = None
    avatar_seed: str
    team_name: str | None = None
    latest_score: int | None = None


class TeamOut(BaseModel):
    id: str
    name: str
    sport: str
    grade_level: str
    student_count: int


# ---------- Drills ----------

class DrillOut(BaseModel):
    id: str
    title: str
    sport: str
    category: str
    description: str
    reference_video_url: str | None = None
    thumbnail_url: str | None = None


class DrillCreateRequest(BaseModel):
    title: str
    sport: str
    category: str
    description: str = ""
    reference_video_url: str | None = None
    thumbnail_url: str | None = None


# ---------- Clips & AI Feedback ----------

class ClipCreateRequest(BaseModel):
    student_id: str
    drill_id: str
    video_url: str
    thumbnail_url: str | None = None
    is_retry_attempt: bool = False
    parent_feedback_id: str | None = None


class ActionPlanStep(BaseModel):
    step: int
    title: str
    description: str
    drill_recommendation_keywords: list[str] = []


class BiomechanicalAnalysis(BaseModel):
    strengths: list[str]
    primary_flaw: str
    joint_angle_notes: str


class AIFeedbackOut(BaseModel):
    id: str
    clip_id: str
    athlete_id: str
    athlete_name: str
    coach_id: str
    drill_id: str
    drill_title: str
    drill_type: str
    overall_score: int
    strengths: list[str]
    primary_flaw: str
    joint_angle_notes: str
    action_plan: list[ActionPlanStep]
    coach_commentary: str
    is_published: bool
    was_edited_by_coach: bool
    created_at: datetime
    published_at: datetime | None = None
    video_url: str
    thumbnail_url: str | None = None
    uploaded_by_id: str
    uploaded_by_name: str
    uploaded_by_role: str
    step_progress: dict[int, dict] = {}


class FeedbackEditRequest(BaseModel):
    overall_score: int | None = None
    strengths: list[str] | None = None
    primary_flaw: str | None = None
    joint_angle_notes: str | None = None
    action_plan: list[ActionPlanStep] | None = None
    coach_commentary: str | None = None


class StepProgressUpdate(BaseModel):
    step_number: int
    watched: bool | None = None
    practiced: bool | None = None


# ---------- Progress ----------

class ProgressPoint(BaseModel):
    term_label: str
    term_order: int
    score: int


class ProgressSeries(BaseModel):
    skill: str
    sport: str
    points: list[ProgressPoint]


# ---------- Admin ----------

class AdminKpis(BaseModel):
    total_students: int
    total_coaches: int
    total_clips_this_month: int
    avg_review_turnaround_hours: float
    avg_overall_score: float


class SportBreakdown(BaseModel):
    sport: str
    student_count: int
    avg_score: float


class CoachEngagement(BaseModel):
    coach_id: str
    coach_name: str
    clips_reviewed: int
    avg_turnaround_hours: float
    avg_score_given: float


class AdminCreateUserRequest(BaseModel):
    role: str  # "coach" | "student" | "parent"
    full_name: str
    email: str
    grade: int | None = None
    primary_sport: str | None = None
    jersey_number: int | None = None


class AdminCreateUserResponse(BaseModel):
    user: UserOut
    temporary_password: str


class NotificationOut(BaseModel):
    id: str
    title: str
    body: str
    kind: str
    is_read: bool
    created_at: datetime
    related_feedback_id: str | None = None
