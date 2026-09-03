"""
Email OTP verification for the signup flow.

Generates a 6 digit OTP, emails it via Gmail SMTP, and stores the code
(plus its expiry/resend timestamps) in the signed session cookie rather
than a database table, since the code is short lived and single use.
"""

import random
import smtplib
import time
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Optional

from app.config import get_settings

OTP_EXPIRY_SECONDS = 10 * 60
RESEND_COOLDOWN_SECONDS = 60


def generate_otp() -> str:
    """Returns a random 6 digit numeric code, zero padded."""
    return f"{random.randint(0, 999999):06d}"


def send_otp_email(to_email: str, otp: str, username: str = "") -> None:
    """Sends the OTP code to to_email using Gmail SMTP credentials from settings."""
    settings = get_settings()
    if not settings.is_email_configured:
        raise RuntimeError(
            "Email sending is not configured. Set GMAIL_SMTP_USER and "
            "GMAIL_SMTP_PASSWORD (a Gmail app password) in your .env file."
        )

    greeting = f"Hi {username}," if username else "Hi,"
    body = (
        f"{greeting}\n\n"
        f"Your Bytwise verification code is: {otp}\n\n"
        "This code expires in 10 minutes. If you didn't request this, "
        "you can safely ignore this email.\n"
    )
    from_address = settings.gmail_smtp_from or settings.gmail_smtp_user
    message = MIMEText(body)
    message["Subject"] = "Your Bytwise verification code"
    message["From"] = from_address
    message["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        # Login must use the real Gmail account that owns the app password;
        # from_address may be a "Send mail as" alias of that same account.
        server.login(settings.gmail_smtp_user, settings.gmail_smtp_password)
        # sendmail's envelope sender must be a bare address ("MAIL FROM"),
        # not the "Display Name <email>" form used in the From header.
        envelope_from = parseaddr(from_address)[1] or settings.gmail_smtp_user
        server.sendmail(envelope_from, [to_email], message.as_string())


def store_otp(session: dict, otp: str) -> None:
    """Stores the OTP and its sent/expiry timestamps in the session."""
    now = time.time()
    session["signup_otp"] = otp
    session["signup_otp_sent_at"] = now
    session["signup_otp_expires_at"] = now + OTP_EXPIRY_SECONDS


def can_resend(session: dict) -> tuple[bool, int]:
    """Returns (allowed, seconds_to_wait) based on the resend cooldown."""
    sent_at = session.get("signup_otp_sent_at")
    if not sent_at:
        return True, 0
    elapsed = time.time() - sent_at
    if elapsed >= RESEND_COOLDOWN_SECONDS:
        return True, 0
    return False, int(RESEND_COOLDOWN_SECONDS - elapsed)


def verify_otp(session: dict, entered_otp: str) -> tuple[bool, Optional[str]]:
    """Checks entered_otp against the session's stored OTP and expiry.

    Returns (True, None) on success, otherwise (False, reason) where
    reason is "missing", "expired", or "mismatch".
    """
    stored_otp = session.get("signup_otp")
    expires_at = session.get("signup_otp_expires_at")

    if not stored_otp or not expires_at:
        return False, "missing"
    if time.time() >= expires_at:
        return False, "expired"
    if entered_otp != stored_otp:
        return False, "mismatch"
    return True, None


def clear_signup_session(session: dict) -> None:
    """Removes all signup/OTP keys from the session after success or cancel."""
    for key in (
        "signup_email",
        "signup_username",
        "signup_password",
        "signup_otp",
        "signup_otp_sent_at",
        "signup_otp_expires_at",
    ):
        session.pop(key, None)
