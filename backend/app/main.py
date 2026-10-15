from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import admin, auth, coach, drills, parent, student

app = FastAPI(title="Coach.AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    # Seed demo data if the database is empty (safe to call on every boot).
    from app.seed import seed_if_empty

    seed_if_empty()


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(coach.router)
app.include_router(student.router)
app.include_router(parent.router)
app.include_router(admin.router)
app.include_router(drills.router)
