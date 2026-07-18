"""Alert dispatch for the telemetry agent — Email + Telegram, all free tiers.

The *sending* accounts are global platform config (one Resend account, one Green
API Telegram instance); the *recipients* are passed in per call so a single alert
fans out to every subscribed user (see ``app.models.alert_subscription``).

Channels:
  Email     — Resend (``RESEND_API_KEY``; ``resend`` lib if installed, else REST)
              or the project's SMTP settings as a fallback.
  Telegram  — Green API Telegram gateway (``GREEN_API_ID_INSTANCE`` /
              ``GREEN_API_TOKEN``), delivering to a recipient phone number.

DEV-safe: with no recipients / no channel configured, :func:`dispatch_alert`
just logs the report and never raises into the monitoring loop.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from starlette.concurrency import run_in_threadpool

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _env(*names: str) -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return ""


# --------------------------------------------------------------------------- #
# Email
# --------------------------------------------------------------------------- #
async def _send_email_resend(subject: str, body: str, api_key: str, recipients: list[str]) -> bool:
    sender = settings.alert_email_from or settings.smtp_from or "Hopper <onboarding@resend.dev>"
    payload = {"from": sender, "to": recipients, "subject": subject, "text": body}
    try:
        import resend  # type: ignore

        resend.api_key = api_key
        await run_in_threadpool(resend.Emails.send, payload)
        return True
    except ModuleNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error("alerting: resend lib send failed: %s", exc)

    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("alerting: resend REST send failed: %s", exc)
        return False


def _send_email_smtp_sync(subject: str, body: str, recipients: list[str]) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.alert_email_from or settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    mode = (settings.smtp_tls or ("starttls" if settings.smtp_starttls else "ssl")).lower()
    if mode == "ssl":
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15,
                              context=ssl.create_default_context()) as s:
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
        if mode == "starttls":
            s.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_email_alert(subject: str, body: str, recipients: list[str]) -> bool:
    """Send to ``recipients`` via Resend if a key exists, else SMTP."""
    recipients = [r for r in recipients if r]
    if not recipients:
        return False
    resend_key = _env("RESEND_API_KEY")
    if resend_key:
        return await _send_email_resend(subject, body, resend_key, recipients)
    if settings.smtp_host:
        try:
            await run_in_threadpool(_send_email_smtp_sync, subject, body, recipients)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("alerting: SMTP send failed: %s", exc)
    return False


# --------------------------------------------------------------------------- #
# Telegram (Green API Telegram gateway)
# --------------------------------------------------------------------------- #
def telegram_configured() -> bool:
    """True when the Green API Telegram gateway credentials are present."""
    return bool(_env("GREEN_API_ID_INSTANCE") and _env("GREEN_API_TOKEN"))


def _tg_chat_id(num: str) -> str:
    """Green API addresses a recipient phone number as ``<digits>@c.us``."""
    digits = num.strip().lstrip("+").strip()
    return f"{digits}@c.us"


async def telegram_status() -> dict[str, str]:
    """Live status of the Green API Telegram gateway.

    Returns ``{"ok": "1"|"0", "state": <stateInstance>, "wid": <bot wid>,
    "reason": <human message>}``. Never raises — a gateway that's down is itself
    the information we want to surface, not an exception.
    """
    inst = _env("GREEN_API_ID_INSTANCE")
    tok = _env("GREEN_API_TOKEN")
    if not (inst and tok):
        return {"ok": "0", "state": "unconfigured", "wid": "",
                "reason": "Telegram gateway credentials are not set on the server."}
    base = f"https://api.green-api.com/waInstance{inst}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            st = (await client.get(f"{base}/getStateInstance/{tok}")).json()
            state = str(st.get("stateInstance", "unknown"))
            wid = ""
            try:
                wid = str((await client.get(f"{base}/getSettings/{tok}")).json().get("wid", ""))
            except Exception:  # noqa: BLE001 - wid is advisory
                pass
    except Exception as exc:  # noqa: BLE001
        return {"ok": "0", "state": "error", "wid": "",
                "reason": f"Could not reach the Telegram gateway: {exc}"}
    if state != "authorized":
        return {"ok": "0", "state": state, "wid": wid,
                "reason": ("Telegram gateway is not authorized "
                           f"(state={state}). Re-authorize the instance in the "
                           "Green API console (log the bot's Telegram back in).")}
    return {"ok": "1", "state": state, "wid": wid, "reason": "authorized"}


async def send_telegram_alert(body: str, numbers: list[str]) -> bool:
    """Send ``body`` to each recipient phone number over the Green API Telegram
    instance. Returns True if at least one message was accepted.

    Preflights the instance state so an unauthorized gateway fails loudly (with a
    logged reason) instead of silently accepting a message that never arrives,
    and warns when a recipient is the bot's *own* number (that just lands in the
    bot's Telegram "Saved Messages", never a real chat)."""
    numbers = [n for n in numbers if n and n.strip()]
    inst = _env("GREEN_API_ID_INSTANCE")
    tok = _env("GREEN_API_TOKEN")
    if not (inst and tok and numbers):
        return False

    status = await telegram_status()
    if status["ok"] != "1":
        logger.error("alerting: telegram not sending — %s", status["reason"])
        return False
    own_wid = status.get("wid", "")

    url = f"https://api.green-api.com/waInstance{inst}/sendMessage/{tok}"
    ok = False
    async with httpx.AsyncClient(timeout=15.0) as client:
        for num in numbers:
            chat_id = _tg_chat_id(num)
            if own_wid and chat_id == own_wid:
                logger.warning(
                    "alerting: telegram recipient %s is the gateway's OWN number; "
                    "Telegram routes self-messages to 'Saved Messages', not a chat. "
                    "Use a different recipient's phone number.", num,
                )
            try:
                resp = await client.post(url, json={"chatId": chat_id, "message": body})
                resp.raise_for_status()
                ok = True
            except Exception as exc:  # noqa: BLE001
                logger.error("alerting: telegram send to %s failed: %s", num, exc)
    return ok


# --------------------------------------------------------------------------- #
# Fan-out
# --------------------------------------------------------------------------- #
async def dispatch_alert(
    subject: str,
    body: str,
    *,
    emails: list[str] | None = None,
    telegram_numbers: list[str] | None = None,
) -> dict[str, bool]:
    """Send to the given recipients on every configured channel. Never raises.
    Logs the report when nothing was delivered (DEV mode)."""
    emails = sorted({e.strip() for e in (emails or []) if e and e.strip()})
    numbers = sorted({n.strip() for n in (telegram_numbers or []) if n and n.strip()})

    results = {
        "email": await send_email_alert(subject, body, emails),
        "telegram": await send_telegram_alert(body, numbers),
    }
    if not any(results.values()):
        logger.warning("alerting DEV (no channel delivered): %s\n%s", subject, body)
    else:
        logger.info(
            "alerting: delivered %s to %d email + %d telegram recipient(s)",
            [k for k, v in results.items() if v], len(emails), len(numbers),
        )
    return results
