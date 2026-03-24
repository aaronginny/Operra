"""FastAPI application entry-point.

Run with:  uvicorn app.main:app --reload
"""

import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routes import tasks as tasks_router
from app.routes import whatsapp_webhook as webhook_router
from app.routes import twilio_webhook as twilio_router
from app.routes import analytics as analytics_router
from app.routes import employee_routes as employee_router
from app.routes import dashboard_api as dashboard_api_router
from app.routes import auth_routes as auth_router
from app.services.reminder_service import start_scheduler, stop_scheduler

# Import models so Base.metadata knows about every table
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create tables on startup, start scheduler, and clean up on shutdown."""
    # --- Startup ---
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified.")

    start_scheduler()
    logger.info("Reminder scheduler started.")

    yield

    # --- Shutdown ---
    await stop_scheduler()
    logger.info("Reminder scheduler stopped.")


app = FastAPI(
    title="Operra",
    description="Backend API that captures WhatsApp messages, extracts tasks via LLM, and tracks them. Operra - AI Operations Assistant for Teams",
    version="0.2.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.models.user import User
from app.services.auth_service import verify_password, create_access_token
from app.database import get_db

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@app.post("/auth/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    logger.info("[Operra] Login attempt for: %s", payload.email)

    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not verify_password(payload.password, user.password_hash):
        logger.warning("[Operra] Login FAILED for: %s", payload.email)
        return {"success": False, "error": "Invalid email or password"}

    token = create_access_token(
        {"sub": user.email, "user_id": user.id, "company_id": user.company_id, "role": user.role.value}
    )
    
    logger.info("[Operra] Login OK for: %s  |  company_id=%s", payload.email, user.company_id)
    return {"success": True, "access_token": token, "company_id": user.company_id}

app.include_router(auth_router.router)
app.include_router(webhook_router.router)
app.include_router(twilio_router.router)
app.include_router(tasks_router.router)
app.include_router(analytics_router.router)
app.include_router(employee_router.router)
app.include_router(dashboard_api_router.router)

# ── Static files & root redirect ──────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", include_in_schema=False)
def root():
    """Redirect bare root to the login page."""
    return RedirectResponse(url="/static/login.html")

@app.get("/login", include_in_schema=False)
def login_page():
    """Convenience redirect — /login → login page."""
    return RedirectResponse(url="/static/login.html")


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}
