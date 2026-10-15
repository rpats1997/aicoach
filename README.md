# Coach.AI (Prototype)

A fully-clickable prototype of the Coach.AI multi-tenant athletic coaching platform
described in the SRS, covering all four personas: **Coach**, **Student-Athlete**,
**Parent**, and **School Admin**.

**No GenAI tokens are used anywhere.** Every "AI analysis" result is generated locally
from hardcoded templates (see [`backend/app/mock_ai.py`](backend/app/mock_ai.py)) that
vary by sport/drill and are seeded per-clip so results are deterministic and reproducible.

**Every clip — from any persona — goes straight to the (mocked) AI engine and is
published immediately.** Coach, student, or parent uploads all run through the same
pipeline ([`backend/app/services.py`](backend/app/services.py)): the clip is analyzed
the instant it's uploaded, and the resulting feedback is visible to the athlete and
their parents right away — no waiting on the coach. The coach's role shifts from
"trigger the analysis" to "review and refine what the AI already produced": they can
edit the score, strengths, flaws, action plan, and add commentary at any time
afterward, and every clip always shows who uploaded it.

## Stack

| Layer | Technology |
|---|---|
| Mobile + Web app | React Native (Expo, Expo Router) — one codebase for iOS, Android, and Web (React Native Web) |
| Backend API | Python FastAPI, JWT auth, RBAC |
| Database | PostgreSQL (SQLAlchemy ORM) |
| Deployment | Single Docker image: PostgreSQL + FastAPI + Nginx, managed by supervisord |

The School Admin "web dashboard" from the SRS is simply the same Expo app running in
Expo Web, gated to the `admin` role — one codebase for every persona instead of a
separate React/Next.js project.

## Quick start (Docker — recommended)

This builds the web app, bundles it with the API and database into **one image**,
and serves everything on port 8080.

```bash
docker build -t coachai:latest .
docker run -d --name coachai-app -p 8080:80 coachai:latest
```

Open **http://localhost:8080** and sign in with any of the [test credentials](#test-credentials)
below (or just tap a demo account card on the login screen).

To persist the database across container restarts, mount a volume:

```bash
docker run -d --name coachai-app -p 8080:80 -v coachai-data:/var/lib/postgresql/data coachai:latest
```

The database is seeded automatically on first boot only (if empty).

### What's inside the container

One image, three supervised processes ([`docker/supervisord.conf`](docker/supervisord.conf)):

- `postgres` — PostgreSQL, initialized on first boot ([`docker/entrypoint.sh`](docker/entrypoint.sh))
- `backend` — FastAPI via uvicorn on `127.0.0.1:8000`
- `nginx` — serves the built web app on port 80 and reverse-proxies `/api/*` to the backend

## Running the mobile app (iOS / Android simulator, or Expo Go)

The Docker container serves the **web** build. To run the actual React Native app on a
simulator/device during development, run the Expo dev server separately, pointed at a
running backend:

```bash
# 1. Start just the backend + database (either the Docker container above, or locally):
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg2://coachai:coachai@localhost:5432/coachai"
export JWT_SECRET="dev-secret"
uvicorn app.main:app --reload --port 8001

# 2. In another terminal, start the Expo app:
cd mobile
npm install
npx expo start
```

`mobile/.env` already points `EXPO_PUBLIC_API_URL` at `http://localhost:8001` for local
development. If testing on a physical device, change it to your machine's LAN IP.

## Test credentials

Seeded automatically: one school (Lincoln High School), one coach, two students, and
one parent per student.

| Role | Email | Password | Notes |
|---|---|---|---|
| Coach | `coach@coachai.test` | `Coach123!` | Morgan Reyes — coaches both Basketball and Track & Field |
| Student | `student1@coachai.test` | `Student123!` | Alex Carter — Grade 10, Basketball, #23 |
| Student | `student2@coachai.test` | `Student123!` | Jamie Lee — Grade 11, Track & Field, #7 |
| Parent | `parent1@coachai.test` | `Parent123!` | Pat Carter — parent of Alex Carter |
| Parent | `parent2@coachai.test` | `Parent123!` | Robin Lee — parent of Jamie Lee |
| School Admin | `admin@coachai.test` | `Admin123!` | Dana Whitfield |

The login screen also has tap-to-sign-in cards for every account above.

## What's implemented per persona

- **Coach**: roster with team/sport filtering, mock camera capture flow (pose-grid
  viewfinder → simulated upload → instant AI analysis), an "AI feedback" queue split
  into Needs your review / Reviewed, always-editable feedback detail (score, strengths,
  flaws, action plan, commentary — no publish step, since it's already live), a drill
  library with the ability to add new drills (and new sports on the fly), per-athlete
  multi-year trajectory chart.
- **Student**: activity feed of AI feedback (own uploads + coach-recorded, all instant),
  full breakdown view, interactive 3-step practice checklist (Watch / Practice / Record
  attempt) per action-plan step, a dedicated Upload tab to send a practice clip straight
  to the AI engine, multi-year progress charts.
- **Parent**: read-only list of linked children, per-child dashboard (trajectory chart +
  feedback history + home practice plan status), and the ability to upload a home-practice
  clip on a child's behalf — also analyzed instantly.
- **School Admin**: department KPIs, sport breakdown, coach engagement/turnaround
  analytics, full user roster with role filtering, one-click CSV and PDF export of
  student athletic profiles.

Every feedback card and list row shows an uploader badge ("Uploaded by Jamie Lee ·
Student", "Uploaded by Pat Carter · Parent", etc.) so it's always clear who recorded
the clip.

## Project structure

```
backend/          FastAPI app (models, routers per persona, mock AI, seed data)
mobile/           Expo (React Native + Web) app
  src/app/        File-based routes (expo-router), grouped by role
  src/components/ Shared UI components (Card, Button, ScoreRing, LineChart, ...)
  src/api/        Typed API client
docker/           nginx.conf, supervisord.conf, entrypoint.sh
Dockerfile        Multi-stage build → single runtime image
```
