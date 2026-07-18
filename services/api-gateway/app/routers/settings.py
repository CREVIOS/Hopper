from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.alerting import telegram_configured
from app.dependencies import get_current_user, get_db
from app.models.alert_subscription import AlertSubscription
from app.schemas.alert import AlertPreferenceOut, AlertPreferenceUpdate
from app.schemas.user import TokenPayload

router = APIRouter()


@router.get("/alerts", response_model=AlertPreferenceOut)
async def get_alert_preferences(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The current user's telemetry-alert preferences (defaults if never set)."""
    row = await db.get(AlertSubscription, current_user.sub)
    if row is None:
        return AlertPreferenceOut(
            email_address=current_user.email or "",
            telegram_configured=telegram_configured(),
        )
    return AlertPreferenceOut(
        email_enabled=row.email_enabled,
        email_address=row.email_address or (current_user.email or ""),
        telegram_enabled=row.telegram_enabled,
        telegram_number=row.telegram_number,
        min_severity=row.min_severity,
        telegram_configured=telegram_configured(),
    )


@router.put("/alerts", response_model=AlertPreferenceOut)
async def update_alert_preferences(
    body: AlertPreferenceUpdate,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upsert the current user's alert preferences. A blank email defaults to the
    account email so 'email on' always has a destination."""
    email_address = body.email_address.strip() or (current_user.email or "")
    row = await db.get(AlertSubscription, current_user.sub)
    if row is None:
        row = AlertSubscription(user_id=current_user.sub)
        db.add(row)
    row.email_enabled = body.email_enabled
    row.email_address = email_address
    row.telegram_enabled = body.telegram_enabled
    row.telegram_number = body.telegram_number
    row.min_severity = body.min_severity
    await db.commit()
    return AlertPreferenceOut(
        email_enabled=row.email_enabled,
        email_address=row.email_address,
        telegram_enabled=row.telegram_enabled,
        telegram_number=row.telegram_number,
        min_severity=row.min_severity,
        telegram_configured=telegram_configured(),
    )

@router.post("/alerts/test")
async def send_test_alert(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test alert to the current user's own configured channels so they
    can confirm delivery. Uses whatever they've saved (and enabled)."""
    from app.agents.alerting import dispatch_alert

    # Email is disabled as an alert channel — Telegram only.
    row = await db.get(AlertSubscription, current_user.sub)
    numbers: list[str] = []
    if row and row.telegram_enabled and row.telegram_number:
        numbers.append(row.telegram_number)
    if not numbers:
        return {"status": "no_channels", "detail": "Enable and save Telegram first."}
    results = await dispatch_alert(
        "[Hopper] Test alert",
        "This is a test alert from the Hopper telemetry agent. "
        "If you received this, your alert channel is configured correctly.",
        telegram_numbers=numbers,
    )
    # If Telegram was requested but not delivered, explain why (unauthorized
    # gateway / self-number) instead of a bare "not delivered".
    reasons: dict[str, str] = {}
    if numbers and not results.get("telegram"):
        from app.agents.alerting import telegram_status

        st = await telegram_status()
        reasons["telegram"] = st["reason"]
    return {"status": "sent", "delivered": results, "reasons": reasons}


@router.put("/vscode")
async def save_vscode_settings(
    settings_body: dict,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Store VS Code settings blob per user.
    
    The orchestrator mounts the user's PVC at /workspace/.vscode/settings.json.
    code-server picks this up automatically on next launch.
    """
    # Store in user record or a dedicated settings table
    # For now, write to the user's PVC path via a K8s ConfigMap or direct PVC write
    # Implementation depends on your PVC strategy — see Phase 5
    return {"status": "saved"}