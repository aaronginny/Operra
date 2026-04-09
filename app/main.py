"""FastAPI application entry-point.

Run with:  uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
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
from app.routes import enquiries as enquiries_router
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

    # ── Twilio config check ───────────────────────────────────
    from app.config import settings as _s
    logger.info(
        "Twilio config: SID=%s  TOKEN=%s  NUMBER=%s",
        "set" if _s.twilio_account_sid else "MISSING",
        "set" if _s.twilio_auth_token else "MISSING",
        _s.twilio_whatsapp_number or "MISSING",
    )

    yield

    # --- Shutdown ---
    await stop_scheduler()
    logger.info("Reminder scheduler stopped.")


app = FastAPI(
    title="Foreman AI",
    description="Backend API that captures WhatsApp messages, extracts tasks via LLM, and tracks them. Foreman AI - Smart Task Management for Teams",
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
app.include_router(auth_router.router)
app.include_router(webhook_router.router)
app.include_router(twilio_router.router)
app.include_router(tasks_router.router)
app.include_router(analytics_router.router)
app.include_router(employee_router.router)
app.include_router(dashboard_api_router.router)
app.include_router(enquiries_router.router)

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
