"""
Seeds a fully-formed demo dataset so every persona has something real to look at
the moment they log in. No external calls, no GenAI - pure fixtures.
"""

from datetime import date, datetime, timedelta

from app.database import SessionLocal
from app.mock_ai import generate_feedback
from app.models import (
    ActionStepProgress,
    AIFeedback,
    ClipStatus,
    CoachProfile,
    Drill,
    DrillClip,
    NotificationItem,
    ParentStudentLink,
    ProgressMetric,
    Role,
    School,
    StudentProfile,
    Team,
    TeamMembership,
    User,
)
from app.security import hash_password

SAMPLE_VIDEO_URL = "https://storage.googleapis.com/coachai-demo-assets/sample-drill-clip.mp4"
SAMPLE_THUMB_URL = "https://images.unsplash.com/photo-1546519638-68e109498ffc?w=400"


def seed_if_empty():
    db = SessionLocal()
    try:
        if db.query(School).first() is not None:
            return  # already seeded

        school = School(name="Lincoln High School", district="Lincoln Unified School District")
        db.add(school)
        db.flush()

        admin = User(
            school_id=school.id,
            email="admin@coachai.test",
            hashed_password=hash_password("Admin123!"),
            full_name="Dana Whitfield",
            role=Role.admin,
            avatar_seed="admin1",
        )
        coach_user = User(
            school_id=school.id,
            email="coach@coachai.test",
            hashed_password=hash_password("Coach123!"),
            full_name="Morgan Reyes",
            role=Role.coach,
            avatar_seed="coach1",
        )
        db.add_all([admin, coach_user])
        db.flush()

        db.add(CoachProfile(user_id=coach_user.id, title="Head Athletic Coach", sports=["Basketball", "Track & Field"]))

        student1 = User(
            school_id=school.id,
            email="student1@coachai.test",
            hashed_password=hash_password("Student123!"),
            full_name="Alex Carter",
            role=Role.student,
            avatar_seed="alex1",
        )
        student2 = User(
            school_id=school.id,
            email="student2@coachai.test",
            hashed_password=hash_password("Student123!"),
            full_name="Jamie Lee",
            role=Role.student,
            avatar_seed="jamie1",
        )
        db.add_all([student1, student2])
        db.flush()

        db.add(StudentProfile(user_id=student1.id, grade=10, primary_sport="Basketball", jersey_number=23,
                               date_of_birth=date(2010, 3, 14)))
        db.add(StudentProfile(user_id=student2.id, grade=11, primary_sport="Track & Field", jersey_number=7,
                               date_of_birth=date(2009, 8, 2)))

        parent1 = User(
            school_id=school.id,
            email="parent1@coachai.test",
            hashed_password=hash_password("Parent123!"),
            full_name="Pat Carter",
            role=Role.parent,
            avatar_seed="pat1",
        )
        parent2 = User(
            school_id=school.id,
            email="parent2@coachai.test",
            hashed_password=hash_password("Parent123!"),
            full_name="Robin Lee",
            role=Role.parent,
            avatar_seed="robin1",
        )
        db.add_all([parent1, parent2])
        db.flush()

        db.add(ParentStudentLink(parent_id=parent1.id, student_id=student1.id, relationship_label="Parent"))
        db.add(ParentStudentLink(parent_id=parent2.id, student_id=student2.id, relationship_label="Parent"))

        basketball_team = Team(
            school_id=school.id, coach_id=coach_user.id, name="Varsity Basketball", sport="Basketball",
            grade_level="Varsity",
        )
        track_team = Team(
            school_id=school.id, coach_id=coach_user.id, name="Varsity Track & Field", sport="Track & Field",
            grade_level="Varsity",
        )
        db.add_all([basketball_team, track_team])
        db.flush()

        db.add(TeamMembership(team_id=basketball_team.id, student_id=student1.id))
        db.add(TeamMembership(team_id=track_team.id, student_id=student2.id))

        drills = [
            Drill(title="Free Throw Form Reset", sport="Basketball", category="Shooting",
                  description="Isolated free-throw mechanics work focused on release consistency.",
                  reference_video_url=SAMPLE_VIDEO_URL, thumbnail_url=SAMPLE_THUMB_URL),
            Drill(title="Catch & Shoot Footwork", sport="Basketball", category="Shooting",
                  description="Footwork sequencing into the shot pocket off the catch.",
                  reference_video_url=SAMPLE_VIDEO_URL, thumbnail_url=SAMPLE_THUMB_URL),
            Drill(title="Block Start Acceleration", sport="Track & Field", category="Sprinting",
                  description="Start technique out of the blocks through the first 10 meters.",
                  reference_video_url=SAMPLE_VIDEO_URL, thumbnail_url=SAMPLE_THUMB_URL),
            Drill(title="Cone Weave Close Control", sport="Soccer", category="Ball Control",
                  description="Tight-space dribbling through a cone corridor.",
                  reference_video_url=SAMPLE_VIDEO_URL, thumbnail_url=SAMPLE_THUMB_URL),
            Drill(title="Core Stability Circuit", sport="General", category="Conditioning",
                  description="Trunk bracing and landing mechanics circuit.",
                  reference_video_url=SAMPLE_VIDEO_URL, thumbnail_url=SAMPLE_THUMB_URL),
        ]
        db.add_all(drills)
        db.flush()
        free_throw_drill, catch_shoot_drill, block_start_drill, cone_weave_drill, core_drill = drills

        def make_published_feedback(student, drill, days_ago, edited=False, commentary="", uploaded_by=None):
            uploader = uploaded_by or coach_user
            clip = DrillClip(
                student_id=student.id,
                coach_id=coach_user.id,
                uploaded_by_id=uploader.id,
                drill_id=drill.id,
                video_url=SAMPLE_VIDEO_URL,
                thumbnail_url=SAMPLE_THUMB_URL,
                status=ClipStatus.published,
                recorded_at=datetime.utcnow() - timedelta(days=days_ago),
            )
            db.add(clip)
            db.flush()

            analysis = generate_feedback(clip.id, drill.sport, drill.category)
            created = datetime.utcnow() - timedelta(days=days_ago, hours=6)
            published = datetime.utcnow() - timedelta(days=days_ago, hours=2)
            fb = AIFeedback(
                clip_id=clip.id,
                athlete_id=student.id,
                coach_id=coach_user.id,
                drill_type=analysis["drill_type"],
                overall_score=analysis["overall_score"],
                strengths=analysis["strengths"],
                primary_flaw=analysis["primary_flaw"],
                joint_angle_notes=analysis["joint_angle_notes"],
                action_plan=analysis["action_plan"],
                coach_commentary=commentary,
                is_published=True,
                was_edited_by_coach=edited,
                created_at=created,
                published_at=published,
            )
            db.add(fb)
            db.flush()
            for i, _ in enumerate(analysis["action_plan"]):
                db.add(ActionStepProgress(
                    feedback_id=fb.id, step_number=i + 1,
                    watched=(i == 0), practiced=False,
                ))
            db.add(NotificationItem(
                user_id=student.id, title="New feedback from your coach",
                body=f"Your {fb.drill_type} review is ready — score {fb.overall_score}/100.",
                kind="feedback", related_feedback_id=fb.id, created_at=published,
            ))
            for link in db.query(ParentStudentLink).filter(ParentStudentLink.student_id == student.id).all():
                db.add(NotificationItem(
                    user_id=link.parent_id, title=f"{student.full_name} has new coach feedback",
                    body=f"{fb.drill_type} — score {fb.overall_score}/100.",
                    kind="feedback", related_feedback_id=fb.id, created_at=published,
                ))
            return fb

        make_published_feedback(student1, free_throw_drill, days_ago=14,
                                 commentary="Great improvement on your release, Alex. Keep drilling that knee bend.")
        make_published_feedback(student1, catch_shoot_drill, days_ago=5, edited=True,
                                 commentary="Footwork is coming together — focus on the guide hand this week.")
        make_published_feedback(student2, block_start_drill, days_ago=10,
                                 commentary="Solid start position, Jamie. Let's smooth out that arm drive.")
        make_published_feedback(student2, block_start_drill, days_ago=2, edited=True,
                                 commentary="Noticeable gains on hip height at the set position!")

        # Self-uploaded clips (student / parent), analyzed by the AI the instant
        # they were sent in — the coach hasn't touched these yet.
        make_published_feedback(student2, block_start_drill, days_ago=0, uploaded_by=student2)
        make_published_feedback(student1, core_drill, days_ago=1, uploaded_by=parent1)

        # Multi-term progress trajectories for charts.
        terms = [("Fall 2024", 1), ("Winter 2025", 2), ("Spring 2025", 3), ("Fall 2025", 4)]
        alex_scores = [58, 67, 74, 81]
        jamie_scores = [61, 65, 70, 78]
        for (label, order), score in zip(terms, alex_scores):
            db.add(ProgressMetric(student_id=student1.id, sport="Basketball", skill="Free Throw Shooting",
                                   term_label=label, term_order=order, score=score))
        for (label, order), score in zip(terms, jamie_scores):
            db.add(ProgressMetric(student_id=student2.id, sport="Track & Field", skill="Sprint Start",
                                   term_label=label, term_order=order, score=score))

        db.commit()
    finally:
        db.close()
