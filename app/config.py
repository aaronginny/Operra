"""Centralized application settings via pydantic-settings.

All environment variables are loaded once at import time.
Every module should use ``from app.config import settings`` instead of
calling ``os.getenv()`` directly.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration — populated from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    
    # ── Security ──────────────────────────────────────────────
    secret_key: str = "super_secret_dev_key_operra_123!"
    cors_origins: list[str] = ["*"]
    
    # ── Database ──────────────────────────────────────────────
    # Render sets DATABASE_URL as postgresql:// or postgres://
    # SQLAlchemy asyncpg driver requires postgresql+asyncpg://
    database_url: str = "sqlite+aiosqlite:///./ai_ops_v2.db"

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_async_db_url(cls, v: str) -> str:
        """Rewrite sync postgres:// URLs to the asyncpg driver scheme."""
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # ── OpenAI ────────────────────────────────────────────────
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # ── Twilio WhatsApp ───────────────────────────────────────
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_number: str | None = None

    # ── WhatsApp webhook verification ─────────────────────────
    whatsapp_verify_token: str = ""

    # ── Email / SMTP ──────────────────────────────────────────
    email_host: str = "smtp.gmail.com"
    email_port: int = 587
    email_user: str | None = None
    email_password: str | None = None

    # ── Gmail OTP (for email verification) ───────────────────
    gmail_user: str | None = None        # GMAIL_USER env var
    gmail_app_password: str | None = None  # GMAIL_APP_PASSWORD env var

    # ── Founder notifications ─────────────────────────────────
    founder_phone: str | None = None
    founder_email: str | None = None

    # ── Daily report ──────────────────────────────────────────
    daily_report_time: str = "09:00"

    # ── Payment ───────────────────────────────────────────────
    # Payment handled manually via UPI — aaronginny@okhdfcbank
    # Aaron activates plans after verifying WhatsApp screenshot.


settings = Settings()
