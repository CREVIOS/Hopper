"""Transactional email for signup verification and password reset.

Two transports, chosen at send time:

- **Brevo HTTPS API** (`settings.brevo_api_key` set) — preferred in prod:
  cluster pods can egress :443 but not SMTP ports, and a domain-authenticated
  Brevo sender (DKIM/SPF-aligned) keeps the codes out of spam.
- **stdlib smtplib** (`settings.smtp_host` set) — the original path, kept as a
  fallback if a Brevo send fails. Blocking socket work runs in a threadpool so
  it doesn't stall the event loop.

If neither is configured we run in DEV mode: the code is written to the app
log instead of being sent, so the whole flow is testable without a mail server.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr

import httpx
from starlette.concurrency import run_in_threadpool

from app.config import settings

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

# Human copy per purpose: (subject, intro line).
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


def brevo_enabled() -> bool:
    return bool(settings.brevo_api_key)


def _render(purpose: str, code: str) -> tuple[str, str, str]:
    """Subject, plain-text body, and HTML body for a one-time-code email."""
    subject, intro = _TEMPLATES.get(
        purpose, ("Your Hopper verification code", "Use the code below to continue.")
    )
    ttl_min = max(1, settings.email_code_ttl_seconds // 60)
    text = (
        f"{intro}\n\n"
        f"    {code}\n\n"
        f"This code expires in {ttl_min} minutes. If you didn't request it, "
        f"you can ignore this email.\n\n— Hopper"
    )
    html = f"""\
<div style="font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:440px;margin:0 auto;color:#0f172a">
  <h2 style="margin:0 0 12px">{subject}</h2>
  <p style="color:#475569;line-height:1.55">{intro}</p>
  <div style="font-size:32px;font-weight:700;letter-spacing:8px;background:#f1f5f9;
              border-radius:10px;padding:18px;text-align:center;margin:20px 0">{code}</div>
  <p style="color:#64748b;font-size:13px">This code expires in {ttl_min} minutes.
     If you didn't request it, you can ignore this email.</p>
  <p style="color:#94a3b8;font-size:12px;margin-top:24px">— Hopper</p>
</div>"""
    return subject, text, html


def _build_message(to: str, purpose: str, code: str) -> EmailMessage:
    subject, text, html = _render(purpose, code)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
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


async def _send_brevo(to: str, purpose: str, code: str) -> None:
    """Send via Brevo's transactional HTTPS API. Raises on any failure."""
    subject, text, html = _render(purpose, code)
    # smtp_from doubles as the sender identity for both transports,
    # e.g. 'Hopper <no-reply@hopper.farefin.com>'.
    name, addr = parseaddr(settings.smtp_from)
    sender: dict[str, str] = {"email": addr}
    if name:
        sender["name"] = name
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            BREVO_API_URL,
            headers={"api-key": settings.brevo_api_key},
            json={
                "sender": sender,
                "to": [{"email": to}],
                "subject": subject,
                "textContent": text,
                "htmlContent": html,
            },
        )
    if resp.status_code >= 400:
        # Surface Brevo's error body (e.g. unauthorized / sender not verified)
        # — raise_for_status alone would hide it.
        raise RuntimeError(f"brevo API {resp.status_code}: {resp.text[:300]}")


async def _send_smtp(to: str, purpose: str, code: str) -> None:
    try:
        await run_in_threadpool(_send_sync, _build_message(to, purpose, code))
        logger.info("email sent: %s -> %s (smtp)", purpose, to)
    except Exception as e:  # noqa: BLE001 — resilience: log, don't crash the request
        logger.error("email send failed (%s -> %s): %s", purpose, to, e)


async def send_code_email(to: str, purpose: str, code: str) -> None:
    """Email a one-time code. In DEV mode (nothing configured) log it instead.

    Never raises to the caller on a send failure — verification/reset endpoints
    stay resilient (and don't leak provider errors to the browser). A failure is
    logged; the user can request a resend.
    """
    if brevo_enabled():
        try:
            await _send_brevo(to, purpose, code)
            logger.info("email sent: %s -> %s (brevo)", purpose, to)
            return
        except Exception as e:  # noqa: BLE001 — resilience: log, don't crash the request
            if not smtp_enabled():
                logger.error("email send failed (%s -> %s): %s", purpose, to, e)
                return
            logger.warning(
                "brevo send failed (%s -> %s): %s — falling back to SMTP", purpose, to, e
            )
    if not smtp_enabled():
        logger.warning(
            "email DEV: %s code for %s = %s (no email transport configured)", purpose, to, code
        )
        return
    await _send_smtp(to, purpose, code)
