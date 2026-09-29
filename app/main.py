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
from app.routes import billing as billing_router
from app.routes import settings_routes as settings_router
from app.routes import notifications as notifications_router
from app.routes import department_routes as department_router
from app.routes import real_estate as real_estate_router
from app.routes import launch_matcher as launch_matcher_router
from app.migrations import run_migrations
from app.services import whatsapp_identity
from app.services.reminder_service import start_scheduler, stop_scheduler
from app.services.messaging_service import subscribe_waba_webhook

# Import models so Base.metadata knows about every table
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create tables on startup, start scheduler, and clean up on shutdown."""
    # --- Startup ---
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created / verified.")
    except Exception:
        logger.exception(
            "FATAL: create_all failed — tables may be missing. "
            "Check DATABASE_URL and PostgreSQL permissions."
        )
        raise

    await run_migrations(engine)

    # One WhatsApp number, one user: prove the unique index migration 037
    # creates is really there, since run_migrations swallows its failure
    # while duplicates exist. Reports rather than raising — see
    # whatsapp_identity.check_uniqueness.
    try:
        await whatsapp_identity.check_uniqueness(engine)
    except Exception:
        logger.exception("WhatsApp routing uniqueness check could not run")

    start_scheduler()
    logger.info("Reminder scheduler started.")

    # ── WABA webhook subscription ─────────────────────────────
    import asyncio as _asyncio
    ok, msg = await _asyncio.to_thread(subscribe_waba_webhook)
    if ok:
        logger.info("WABA subscription: %s", msg)
    else:
        logger.warning("WABA subscription: %s", msg)

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
    title="PhantomPilot",
    description="Backend API that captures WhatsApp messages, extracts tasks via LLM, and tracks them. PhantomPilot - Smart Task Management for Teams",
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
app.include_router(billing_router.router)
app.include_router(settings_router.router)
app.include_router(notifications_router.router)
app.include_router(department_router.router)
app.include_router(real_estate_router.router)
app.include_router(launch_matcher_router.router)

# ── Static files & root redirect ──────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/static/dashboard/index.html")

@app.get("/signup", include_in_schema=False)
def signup_page():
    return RedirectResponse(url="/static/auth.html")

@app.get("/login", include_in_schema=False)
def login_page():
    return RedirectResponse(url="/static/auth.html?tab=login")

@app.get("/dashboard", include_in_schema=False)
def dashboard_page():
    """Convenience redirect — /dashboard → dashboard SPA."""
    return RedirectResponse(url="/static/dashboard/index.html")

@app.get("/privacy", include_in_schema=False)
def privacy_page():
    return RedirectResponse(url="/static/privacy.html")

@app.get("/terms", include_in_schema=False)
def terms_page():
    return RedirectResponse(url="/static/terms.html")


@app.api_route("/health", methods=["GET", "HEAD"], tags=["Health"])
async def health_check():
    """Simple liveness probe — accepts HEAD for UptimeRobot.

    `whatsapp_unique` is the boot-time result of whatsapp_identity.
    check_uniqueness: true once the one-number-one-user index is in force,
    false while it is missing or a duplicate remains, null if the check could
    not run. A boolean only — it says nothing about which numbers."""
    return {"status": "ok", "whatsapp_unique": whatsapp_identity.last_check_ok()}
