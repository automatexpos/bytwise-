"""
Application configuration loaded from environment variables.

Mirrors the environment variables consumed by the original TypeScript
project (lib/supabase.ts, lib/envValidation.ts, services/geminiService.ts,
services/storageService.ts, api/cloudinary-delete.ts), but expressed as a
single Python Settings object for the FastAPI backend.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

# Load a local .env file if present. This mirrors Vite's automatic .env
# loading behavior in the original project (does not override real
# environment variables that are already set).
load_dotenv()


class Settings(BaseModel):
    """Container for all environment backed configuration values."""

    supabase_url: str = ""
    supabase_anon_key: str = ""
    # Service role key, only used server-side to reset a user's password
    # after they verify a forgot-password OTP (there is no existing user
    # session to update the password with in that flow). Never sent to
    # the browser and never used for anything else.
    supabase_service_role_key: str = ""

    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    gemini_api_key: str = ""

    session_secret_key: str = ""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    gmail_smtp_user: str = ""
    gmail_smtp_password: str = ""
    # The address emails appear "From" (e.g. a Gmail "Send mail as" alias).
    # Falls back to gmail_smtp_user when not set.
    gmail_smtp_from: str = ""

    @property
    def is_supabase_configured(self) -> bool:
        """Mirrors the isConfigured check in lib/supabase.ts."""
        placeholder_url = "your-supabase-url-here"
        placeholder_key = "your-supabase-anon-key-here"
        return bool(
            self.supabase_url
            and self.supabase_anon_key
            and self.supabase_url != placeholder_url
            and self.supabase_anon_key != placeholder_key
            and self.supabase_url.startswith("http")
        )

    @property
    def is_cloudinary_configured(self) -> bool:
        return bool(
            self.cloudinary_cloud_name
            and self.cloudinary_api_key
            and self.cloudinary_api_secret
        )

    @property
    def is_gemini_configured(self) -> bool:
        placeholder_key = "your-gemini-api-key-here"
        return bool(self.gemini_api_key and self.gemini_api_key != placeholder_key)

    @property
    def is_email_configured(self) -> bool:
        """Whether Gmail SMTP credentials are set, for sending signup OTP codes."""
        return bool(self.gmail_smtp_user and self.gmail_smtp_password)

    @property
    def is_service_role_configured(self) -> bool:
        """Whether a Supabase service role key is set, needed for forgot-password resets."""
        return bool(self.supabase_service_role_key)


def _read_env() -> Settings:
    """
    Reads the environment variables into a Settings instance.

    Accepts both the VITE_ prefixed names used by the original frontend
    build (VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY) and the plain server
    side names (SUPABASE_URL, SUPABASE_ANON_KEY), so the same .env file
    style used by the TypeScript project keeps working.
    """
    supabase_url = os.environ.get("SUPABASE_URL") or os.environ.get("VITE_SUPABASE_URL", "")
    supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get(
        "VITE_SUPABASE_ANON_KEY", ""
    )

    return Settings(
        supabase_url=supabase_url,
        supabase_anon_key=supabase_anon_key,
        supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        cloudinary_cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
        cloudinary_api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
        cloudinary_api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        session_secret_key=os.environ.get("SESSION_SECRET_KEY", "dev-insecure-session-key"),
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        gmail_smtp_user=os.environ.get("GMAIL_SMTP_USER", "").strip(),
        # Google displays app passwords as 4 space separated groups for
        # readability; the real credential has no spaces, so strip them
        # in case one was copied straight from the "App Passwords" page.
        gmail_smtp_password=os.environ.get("GMAIL_SMTP_PASSWORD", "").replace(" ", ""),
        gmail_smtp_from=os.environ.get("GMAIL_SMTP_FROM", "").strip(),
    )


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings instance built from the current environment."""
    return _read_env()


# A module level settings object for convenient importing, e.g.
# `from app.config import settings`.
settings = get_settings()
