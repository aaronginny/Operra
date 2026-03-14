"""Centralized application settings via pydantic-settings.

All environment variables are loaded once at import time.
Every module should use ``from app.config import settings`` instead of
calling ``os.getenv()`` directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration — populated from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./ai_ops.db"

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

    # ── Founder notifications ─────────────────────────────────
    founder_phone: str | None = None
    founder_email: str | None = None

    # ── Daily report ──────────────────────────────────────────
    daily_report_time: str = "09:00"


settings = Settings()
