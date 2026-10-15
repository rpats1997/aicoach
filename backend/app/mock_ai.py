"""
Fully hardcoded stand-in for the Gemini Vision analysis engine.

No network calls, no API keys, no tokens. Given a drill's sport/category we pick a
matching template (or fall back to a generic one), then vary the score and copy
slightly using a seeded random derived from the clip id so results feel distinct
per clip but are 100% reproducible and offline.
"""

import random

TEMPLATES: dict[str, dict] = {
    "basketball_free_throw": {
        "drill_type": "Free Throw Shooting Form",
        "strengths": [
            "Consistent pre-shot routine and dribble count",
            "Elbow stays tucked under the ball on release",
            "Good balance and square stance to the rim",
        ],
        "flaws": [
            "Knee bend is shallow, limiting upward power transfer",
            "Follow-through wrist snap is inconsistent between reps",
            "Guide hand thumb is pushing the ball off-line",
        ],
        "joint_notes": "Elbow angle averages 84° at release (target 90°); knee flexion "
        "only reaches 105° at the dip, reducing vertical drive.",
        "steps": [
            ("Reinforce the release", "Practice one-hand form shooting from 3 feet, "
             "focusing on a full wrist snap and holding the follow-through for 2 seconds.",
             ["form shooting", "wrist snap", "follow-through hold"]),
            ("Deepen the load", "Add a rhythm dribble-and-dip drill emphasizing a deeper "
             "knee bend before every rep.", ["knee bend", "rhythm dribble", "BEEF cue"]),
            ("Guide-hand discipline", "Shoot 20 reps with the guide hand held off the ball "
             "until release to remove side-spin.", ["guide hand drill", "one-hand catch and shoot"]),
        ],
    },
    "soccer_dribbling": {
        "drill_type": "Close Control Dribbling",
        "strengths": [
            "Excellent low center of gravity through cone weaves",
            "Uses both inside and outside of the foot naturally",
            "Keeps head up to scan the field between touches",
        ],
        "flaws": [
            "First touch is slightly heavy when changing direction at speed",
            "Weak-foot touches are noticeably slower than strong-foot touches",
            "Shoulders drift open too early before the cut move",
        ],
        "joint_notes": "Ankle lock on contact is inconsistent on the weak foot, causing the "
        "ball to roll 30-40cm further than the strong-foot touches.",
        "steps": [
            ("Tighten the first touch", "Wall-pass touch-and-turn drill, 3 sets of 15, "
             "cushioning the ball within one stride.", ["first touch drill", "wall passes"]),
            ("Balance the weak foot", "Cone weave using only the weak foot for 5 minutes daily.",
             ["weak foot cone weave", "close control"]),
            ("Disguise the cut", "Practice step-overs and body feints keeping shoulders "
             "square until the last moment.", ["step-over drill", "body feint"]),
        ],
    },
    "track_sprint_start": {
        "drill_type": "Sprint Block Start",
        "strengths": [
            "Explosive first two steps out of the blocks",
            "Strong front-side mechanics through acceleration phase",
            "Head and neck stay neutral, avoiding early upright posture",
        ],
        "flaws": [
            "Hips rise too quickly out of the set position",
            "Arm drive is asymmetric, favoring the dominant side",
            "Shin angle on the front leg is too vertical at the gun",
        ],
        "joint_notes": "Hip height at 'set' is elevated roughly 8° above optimal, and front "
        "shin angle measures 61° versus a 45-50° target at the start signal.",
        "steps": [
            ("Lower the hips", "3-point start drills against a resistance band holding hip "
             "height for a 3-count before driving out.", ["resistance band starts", "hip hinge"]),
            ("Even out the arm drive", "Wall drill isolating arm swing symmetry, 4 sets of 10 seconds each side.",
             ["arm drive wall drill", "sprint mechanics"]),
            ("Own the shin angle", "Falling starts emphasizing a flat front shin at push-off.",
             ["falling starts", "block acceleration"]),
        ],
    },
    "generic": {
        "drill_type": "General Movement Assessment",
        "strengths": [
            "Strong overall effort and focus throughout the rep",
            "Good body control through the movement pattern",
            "Consistent tempo across repetitions",
        ],
        "flaws": [
            "Core bracing loosens in the second half of the movement",
            "Landing mechanics could be softer to protect the joints",
            "Movement slows asymmetrically favoring the dominant side",
        ],
        "joint_notes": "Trunk lean increases by roughly 10° in the closing phase, suggesting "
        "fatigue-related core disengagement.",
        "steps": [
            ("Own the brace", "Add a 3x30 second plank series before each training block.",
             ["core bracing", "plank series"]),
            ("Soften the landing", "Depth drop drill focusing on quiet, absorbed landings.",
             ["depth drops", "landing mechanics"]),
            ("Balance both sides", "Unilateral tempo reps on the non-dominant side, 3 sets of 8.",
             ["unilateral training", "tempo reps"]),
        ],
    },
}

CATEGORY_KEY_BY_SPORT_CATEGORY = {
    ("Basketball", "Shooting"): "basketball_free_throw",
    ("Soccer", "Ball Control"): "soccer_dribbling",
    ("Track & Field", "Sprinting"): "track_sprint_start",
}


def generate_feedback(clip_id: str, sport: str, category: str) -> dict:
    key = CATEGORY_KEY_BY_SPORT_CATEGORY.get((sport, category), "generic")
    template = TEMPLATES[key]

    rng = random.Random(clip_id)  # deterministic per clip
    overall_score = rng.randint(62, 94)
    strengths = rng.sample(template["strengths"], k=min(2, len(template["strengths"])))
    primary_flaw = rng.choice(template["flaws"])

    action_plan = [
        {
            "step": i + 1,
            "title": title,
            "description": description,
            "drill_recommendation_keywords": keywords,
        }
        for i, (title, description, keywords) in enumerate(template["steps"])
    ]

    return {
        "drill_type": template["drill_type"],
        "overall_score": overall_score,
        "strengths": strengths,
        "primary_flaw": primary_flaw,
        "joint_angle_notes": template["joint_notes"],
        "action_plan": action_plan,
    }
