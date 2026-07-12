from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services import credit_alerts


class FakeDB:
    """Minimal AsyncSession stand-in. Plan/roster lookups are monkeypatched."""

    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        pass


def _session(**overrides) -> SimpleNamespace:
    defaults = dict(
        id="pod-uuid",
        pod_name="vm-123",
        user_id="stu-1",
        plan="small",
        state="running",
        expires_at=None,
        credit_grace_until=None,
    )
    return SimpleNamespace(**{**defaults, **overrides})


# --- warning bands -----------------------------------------------------------


def test_warning_bands_map_remaining_minutes_to_a_threshold():
    assert credit_alerts.warning_threshold_for_minutes(59.9) == 60
    assert credit_alerts.warning_threshold_for_minutes(30) == 30
    assert credit_alerts.warning_threshold_for_minutes(9.5) == 10
    assert credit_alerts.warning_threshold_for_minutes(4.5) == 5


def test_no_warning_when_plenty_of_credit_or_already_empty():
    assert credit_alerts.warning_threshold_for_minutes(90) is None  # loads of time
    assert credit_alerts.warning_threshold_for_minutes(0) is None   # already exhausted
    assert credit_alerts.warning_threshold_for_minutes(-5) is None


# --- burn rate (now read from the DB plan catalogue) -------------------------


async def test_hourly_rate_comes_from_the_db_plan_catalogue(monkeypatch):
    async def fake_get_plan(db, name):
        return SimpleNamespace(credits_per_hour=7.5) if name == "custom" else None

    monkeypatch.setattr("app.services.plan_service.get_plan", fake_get_plan)

    # Admin-editable price wins over the hardcoded table.
    assert await credit_alerts.hourly_rate_for_plan(FakeDB(), "custom") == 7.5


async def test_hourly_rate_falls_back_to_builtin_table_for_a_deleted_plan(monkeypatch):
    async def fake_get_plan(db, name):
        return None  # plan row gone, but a pod is still running on it

    monkeypatch.setattr("app.services.plan_service.get_plan", fake_get_plan)

    assert await credit_alerts.hourly_rate_for_plan(FakeDB(), "small") == 1.0
    assert await credit_alerts.hourly_rate_for_plan(FakeDB(), "large") == 4.0
    assert await credit_alerts.hourly_rate_for_plan(FakeDB(), "nonexistent") == 0.0


async def test_burn_rate_sums_across_every_live_vm(monkeypatch):
    """Two VMs burn credits twice as fast — the warning must reflect the total."""

    class DB(FakeDB):
        async def scalars(self, stmt):
            return SimpleNamespace(all=lambda: ["small", "large"])

    async def fake_get_plan(db, name):
        return None

    monkeypatch.setattr("app.services.plan_service.get_plan", fake_get_plan)

    assert await credit_alerts.user_hourly_burn_rate(DB(), "stu-1") == 5.0  # 1 + 4


# --- low-credit warnings -----------------------------------------------------


async def test_warning_fires_with_the_right_band_and_dedupe_key(monkeypatch):
    sent = []

    async def fake_burn(db, user_id):
        return 60.0  # 60 credits/hour == 1 credit/minute

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(credit_alerts, "user_hourly_burn_rate", fake_burn)
    monkeypatch.setattr(credit_alerts, "create_notification_safely", fake_notify)

    # 25 credits at 1/minute == 25 minutes left → the 30-minute band.
    await credit_alerts.maybe_warn_low_credits(FakeDB(), session=_session(), balance=25.0)

    assert len(sent) == 1
    assert sent[0]["type"] == "credit_warning"
    assert sent[0]["severity"] == "warning"
    assert sent[0]["metadata"]["threshold_minutes"] == 30
    # Deduped per (VM, band) so a once-a-minute tick can't spam the bell.
    assert sent[0]["dedupe_key"] == "credit-warning:pod-uuid:30"


async def test_no_warning_when_there_is_plenty_of_credit(monkeypatch):
    sent = []

    async def fake_burn(db, user_id):
        return 60.0

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(credit_alerts, "user_hourly_burn_rate", fake_burn)
    monkeypatch.setattr(credit_alerts, "create_notification_safely", fake_notify)

    # 500 minutes remaining — nowhere near a band.
    await credit_alerts.maybe_warn_low_credits(FakeDB(), session=_session(), balance=500.0)

    assert sent == []


async def test_no_warning_when_nothing_is_burning_credits(monkeypatch):
    """Guards a divide-by-zero: a user with no live VM has no burn rate."""
    sent = []

    async def fake_burn(db, user_id):
        return 0.0

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(credit_alerts, "user_hourly_burn_rate", fake_burn)
    monkeypatch.setattr(credit_alerts, "create_notification_safely", fake_notify)

    await credit_alerts.maybe_warn_low_credits(FakeDB(), session=_session(), balance=0.0)

    assert sent == []


# --- grace period ------------------------------------------------------------


async def test_start_grace_stamps_its_own_column_and_never_touches_the_ttl(monkeypatch):
    """The whole point of credit_grace_until: expires_at is the session TTL, and
    the session reaper terminates on it. Grace must not write to it."""
    sent = []

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(credit_alerts, "create_notification_safely", fake_notify)

    ttl = datetime(2026, 1, 1, 20, 0)
    session = _session(expires_at=ttl)
    db = FakeDB()
    now = datetime(2026, 1, 1, 12, 0)

    await credit_alerts.start_credit_grace(db, session=session, now=now)

    assert session.credit_grace_until == now + timedelta(minutes=5)
    assert session.expires_at == ttl  # TTL untouched
    assert db.commits == 1
    assert sent[0]["type"] == "credit_grace"
    assert sent[0]["severity"] == "error"


async def test_start_grace_is_idempotent_and_does_not_extend_the_deadline(monkeypatch):
    """Billing ticks every minute while exhausted — the deadline must not slide."""

    async def fake_notify(db, **kwargs):
        pass

    monkeypatch.setattr(credit_alerts, "create_notification_safely", fake_notify)

    deadline = datetime(2026, 1, 1, 12, 5)
    session = _session(credit_grace_until=deadline)
    db = FakeDB()

    await credit_alerts.start_credit_grace(
        db, session=session, now=datetime(2026, 1, 1, 12, 3)
    )

    assert session.credit_grace_until == deadline  # not pushed out
    assert db.commits == 0


async def test_topping_up_in_time_clears_the_grace_and_spares_the_vm(monkeypatch):
    session = _session(credit_grace_until=datetime(2026, 1, 1, 12, 0))
    published, sent = [], []

    class DB(FakeDB):
        async def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [session])

    async def fake_balance(db, user_id):
        return 50.0  # they paid up

    async def fake_publish(pod_id, user_id):
        published.append(pod_id)

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    async def fake_rate(db, plan):
        return 1.0

    monkeypatch.setattr(credit_alerts, "get_balance", fake_balance)
    monkeypatch.setattr(credit_alerts, "publish_billing_exhausted", fake_publish)
    monkeypatch.setattr(credit_alerts, "create_notification_safely", fake_notify)
    monkeypatch.setattr(credit_alerts, "hourly_rate_for_plan", fake_rate)

    resolved = await credit_alerts.process_expired_graces(
        DB(), now=datetime(2026, 1, 1, 12, 1)
    )

    assert resolved == 1
    assert published == []                    # VM survives
    assert session.credit_grace_until is None  # grace cleared
    assert sent[0]["type"] == "credits_received"


async def test_still_broke_at_the_deadline_terminates_the_vm(monkeypatch):
    session = _session(credit_grace_until=datetime(2026, 1, 1, 12, 0))
    published, sent = [], []

    class DB(FakeDB):
        async def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [session])

    async def fake_balance(db, user_id):
        return 0.0  # still nothing

    async def fake_publish(pod_id, user_id):
        published.append(pod_id)

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    async def fake_rate(db, plan):
        return 1.0

    monkeypatch.setattr(credit_alerts, "get_balance", fake_balance)
    monkeypatch.setattr(credit_alerts, "publish_billing_exhausted", fake_publish)
    monkeypatch.setattr(credit_alerts, "create_notification_safely", fake_notify)
    monkeypatch.setattr(credit_alerts, "hourly_rate_for_plan", fake_rate)

    resolved = await credit_alerts.process_expired_graces(
        DB(), now=datetime(2026, 1, 1, 12, 1)
    )

    assert resolved == 1
    # Terminated via the orchestrator, using the k8s name it knows the pod by.
    assert published == ["vm-123"]
    assert session.credit_grace_until is None
    assert sent[0]["type"] == "vm_terminated"


async def test_a_failed_kill_leaves_the_grace_set_so_the_next_tick_retries(monkeypatch):
    session = _session(credit_grace_until=datetime(2026, 1, 1, 12, 0))

    class DB(FakeDB):
        async def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [session])

    async def fake_balance(db, user_id):
        return 0.0

    async def fake_publish(pod_id, user_id):
        raise RuntimeError("NATS down")

    async def fake_notify(db, **kwargs):
        pass

    async def fake_rate(db, plan):
        return 1.0

    monkeypatch.setattr(credit_alerts, "get_balance", fake_balance)
    monkeypatch.setattr(credit_alerts, "publish_billing_exhausted", fake_publish)
    monkeypatch.setattr(credit_alerts, "create_notification_safely", fake_notify)
    monkeypatch.setattr(credit_alerts, "hourly_rate_for_plan", fake_rate)

    db = DB()
    resolved = await credit_alerts.process_expired_graces(
        db, now=datetime(2026, 1, 1, 12, 1)
    )

    assert resolved == 0
    # Grace still set → the VM gets killed on a later tick rather than running free.
    assert session.credit_grace_until is not None
    assert db.rollbacks == 1
