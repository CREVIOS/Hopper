"""Transactional email for signup verification and password reset.

Uses stdlib smtplib (no extra dependency) run in a threadpool so the blocking
socket work doesn't stall the event loop. If SMTP is not configured
(`settings.smtp_host` empty), we run in DEV mode: the code is written to the app
log instead of being sent, so the whole flow is testable without a mail server.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from starlette.concurrency import run_in_threadpool

from app.config import settings

logger = logging.getLogger(__name__)

# Human copy per purpose: (subject, intro line, action label).
_TEMPLATES = {
    "verify_email": (
        "Verify your Hopper account",
        "Welcome to Hopper! Use the code below to verify your email address.",
    ),
    "password_reset": (
        "Reset your Hopper password",
        "We received a request to reset your Hopper password. Use the code below to continue.",
    ),
}


def smtp_enabled() -> bool:
    return bool(settings.smtp_host)


def _build_message(to: str, purpose: str, code: str) -> EmailMessage:
    subject, intro = _TEMPLATES.get(
        purpose, ("Your Hopper verification code", "Use the code below to continue.")
    )
    ttl_min = max(1, settings.email_code_ttl_seconds // 60)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.set_content(
        f"{intro}\n\n"
        f"    {code}\n\n"
        f"This code expires in {ttl_min} minutes. If you didn't request it, "
        f"you can ignore this email.\n\n— Hopper"
    )
    msg.add_alternative(
        f"""\
<div style="font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:440px;margin:0 auto;color:#0f172a">
  <h2 style="margin:0 0 12px">{subject}</h2>
  <p style="color:#475569;line-height:1.55">{intro}</p>
  <div style="font-size:32px;font-weight:700;letter-spacing:8px;background:#f1f5f9;
              border-radius:10px;padding:18px;text-align:center;margin:20px 0">{code}</div>
  <p style="color:#64748b;font-size:13px">This code expires in {ttl_min} minutes.
     If you didn't request it, you can ignore this email.</p>
  <p style="color:#94a3b8;font-size:12px;margin-top:24px">— Hopper</p>
</div>""",
        subtype="html",
    )
    return msg


def _send_sync(msg: EmailMessage) -> None:
    """Blocking SMTP send — always called via run_in_threadpool."""
    if settings.smtp_starttls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port,
            timeout=15, context=ssl.create_default_context(),
        ) as server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)


async def send_code_email(to: str, purpose: str, code: str) -> None:
    """Email a one-time code. In DEV mode (no SMTP configured) log it instead.

    Never raises to the caller on a send failure — verification/reset endpoints
    stay resilient (and don't leak SMTP errors to the browser). A failure is
    logged; the user can request a resend.
    """
    if not smtp_enabled():
        logger.warning("email DEV: %s code for %s = %s (SMTP not configured)", purpose, to, code)
        return
    try:
        await run_in_threadpool(_send_sync, _build_message(to, purpose, code))
        logger.info("email sent: %s -> %s", purpose, to)
    except Exception as e:  # noqa: BLE001 — resilience: log, don't crash the request
        logger.error("email send failed (%s -> %s): %s", purpose, to, e)
