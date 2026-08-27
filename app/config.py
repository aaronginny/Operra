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
    # No fallback: if SECRET_KEY isn't set, the app refuses to start in
    # production. The dev-only default is gated by the validator below so
    # a missing prod env var can never silently use a known-public secret.
    secret_key: str = ""
    cors_origins: list[str] = ["*"]
    # Set to "production" on Render / live deploys to enforce strict checks
    # (currently: refuse to start with empty SECRET_KEY).
    app_env: str = "development"

    # ── TEMPORARY: one-off account provisioning ───────────────
    # Shared secret guarding POST /internal/provision-accounts. Empty by
    # default, and the endpoint refuses to do anything while it is empty, so
    # the route is inert unless this is deliberately set.
    #
    # DELETE THIS FIELD, the route module, and the env var in Render once the
    # accounts have been created. It exists only because Render's shell is
    # gated behind a paid plan.
    provision_secret: str = ""

    @field_validator("secret_key", mode="after")
    @classmethod
    def _require_secret_in_prod(cls, v: str, info) -> str:
        env = (info.data.get("app_env") or "development").lower()
        if env == "production" and not v:
            raise ValueError(
                "SECRET_KEY env var is required in production. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        if not v:
            # Dev-only ephemeral default — different per process, so leaked
            # tokens from one local run don't carry to another.
            import secrets as _secrets
            return _secrets.token_urlsafe(48)
        return v
    
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

    # ── Meta WhatsApp Cloud API ───────────────────────────────
    meta_phone_number_id: str | None = None
    meta_access_token: str | None = None
    meta_waba_id: str | None = None

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

    # ── Cashfree Payment Gateway ──────────────────────────────
    cashfree_app_id: str | None = None
    cashfree_secret_key: str | None = None
    # "sandbox" or "production"
    cashfree_env: str = "sandbox"

    @property
    def cashfree_base_url(self) -> str:
        if self.cashfree_env == "production":
            return "https://api.cashfree.com/pg"
        return "https://sandbox.cashfree.com/pg"


settings = Settings()
