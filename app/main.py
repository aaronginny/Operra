"""FastAPI application entry-point.

Run with:  uvicorn app.main:app --reload
"""

import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI 
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routes import tasks as tasks_router
from app.routes import whatsapp_webhook as webhook_router
from app.routes import twilio_webhook as twilio_router
from app.routes import analytics as analytics_router
from app.routes import employee_routes as employee_router
from app.routes import dashboard_api as dashboard_api_router
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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(webhook_router.router)
app.include_router(twilio_router.router)
app.include_router(tasks_router.router)
app.include_router(analytics_router.router)
app.include_router(employee_router.router)
app.include_router(dashboard_api_router.router)

# ── Static dashboard ──────────────────────────────────────────
_static_dir = pathlib.Path(__file__).resolve().parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/dashboard", StaticFiles(directory=_static_dir, html=True), name="dashboard")


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect the root URL to the dashboard."""
    return RedirectResponse(url="/dashboard/")


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}
