from datetime import datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.services import idle_monitor


NOW = datetime(2026, 7, 13, 12, 0)
# Defaults: idle below 5% CPU for 30 min, then a 10-min grace before shutdown.
LONG_AGO = NOW - timedelta(hours=5)


class FakeDB:
    def __init__(self, sessions=None):
        self.sessions = sessions or []
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def scalars(self, stmt):
        return SimpleNamespace(all=lambda: self.sessions)


def _session(**overrides) -> SimpleNamespace:
    defaults = dict(
        id="pod-uuid",
        pod_name="vm-123",
        user_id="stu-1",
        plan="small",
        state="running",
        started_at=LONG_AGO,
        expires_at=NOW + timedelta(hours=4),
        idle_shutdown_at=None,
    )
    return SimpleNamespace(**{**defaults, **overrides})


def _patch_peak(monkeypatch, peak):
    """Stub the metrics query: `peak` is the highest CPU% seen, or None for no data."""

    async def fake_peak(db, session, since):
        return peak

    monkeypatch.setattr(idle_monitor, "peak_cpu_since", fake_peak)


# --- is_idle: the safety-critical predicate -----------------------------------


async def test_quiet_vm_is_idle(monkeypatch):
    _patch_peak(monkeypatch, 1.2)  # well under the 5% threshold

    assert await idle_monitor.is_idle(FakeDB(), _session(), NOW) is True


async def test_busy_vm_is_not_idle(monkeypatch):
    _patch_peak(monkeypatch, 42.0)

    assert await idle_monitor.is_idle(FakeDB(), _session(), NOW) is False


async def test_a_single_cpu_spike_in_the_window_keeps_the_vm_alive(monkeypatch):
    """We take the PEAK over the window, not the average — one burst of real work
    is enough to prove someone is there."""
    _patch_peak(monkeypatch, 80.0)

    assert await idle_monitor.is_idle(FakeDB(), _session(), NOW) is False


async def test_vm_with_no_telemetry_is_never_idle(monkeypatch):
    """A dead metrics pipeline looks exactly like an idle VM. Never kill on
    missing data — that would take out every running VM at once."""
    _patch_peak(monkeypatch, None)

    assert await idle_monitor.is_idle(FakeDB(), _session(), NOW) is False


async def test_a_freshly_booted_vm_is_never_idle(monkeypatch):
    """A VM that has not been up for a full window has no evidence against it —
    new VMs are quiet before the user connects."""
    _patch_peak(monkeypatch, 0.0)
    young = _session(started_at=NOW - timedelta(minutes=5))

    assert await idle_monitor.is_idle(FakeDB(), young, NOW) is False


async def test_cpu_exactly_at_the_threshold_is_not_idle(monkeypatch):
    _patch_peak(monkeypatch, settings.idle_cpu_percent)

    assert await idle_monitor.is_idle(FakeDB(), _session(), NOW) is False


# --- the warn -> grace -> shutdown lifecycle ---------------------------------


async def test_an_idle_vm_is_warned_not_killed(monkeypatch):
    """First contact is always a warning — we never shut down without notice."""
    sent = []
    killed = []

    _patch_peak(monkeypatch, 0.5)

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    async def fake_terminate(session):
        killed.append(session.id)

    monkeypatch.setattr(idle_monitor, "create_notification_safely", fake_notify)
    monkeypatch.setattr(idle_monitor, "_terminate", fake_terminate)

    session = _session()
    result = await idle_monitor.process_idle_sessions(FakeDB([session]), now=NOW)

    assert result == {"warned": 1, "shutdown": 0, "reprieved": 0}
    assert killed == []  # still running
    assert session.idle_shutdown_at == NOW + timedelta(minutes=10)
    assert sent[0]["type"] == "vm_idle"
    assert sent[0]["severity"] == "warning"


async def test_a_warned_vm_is_not_warned_again_every_tick(monkeypatch):
    """idle_shutdown_at doubles as the 'already warned' flag."""
    sent = []
    _patch_peak(monkeypatch, 0.5)

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    async def fake_terminate(session):
        pass

    monkeypatch.setattr(idle_monitor, "create_notification_safely", fake_notify)
    monkeypatch.setattr(idle_monitor, "_terminate", fake_terminate)

    # Warned a minute ago; the deadline is still 9 minutes out.
    session = _session(idle_shutdown_at=NOW + timedelta(minutes=9))
    result = await idle_monitor.process_idle_sessions(FakeDB([session]), now=NOW)

    assert result == {"warned": 0, "shutdown": 0, "reprieved": 0}
    assert sent == []  # no second warning


async def test_activity_before_the_deadline_cancels_the_shutdown(monkeypatch):
    """The whole point of the grace window: coming back rescues the VM."""
    killed = []
    _patch_peak(monkeypatch, 65.0)  # the user is working again

    async def fake_terminate(session):
        killed.append(session.id)

    monkeypatch.setattr(idle_monitor, "_terminate", fake_terminate)

    session = _session(idle_shutdown_at=NOW + timedelta(minutes=2))
    result = await idle_monitor.process_idle_sessions(FakeDB([session]), now=NOW)

    assert result == {"warned": 0, "shutdown": 0, "reprieved": 1}
    assert killed == []
    assert session.idle_shutdown_at is None  # countdown called off


async def test_still_idle_at_the_deadline_shuts_the_vm_down(monkeypatch):
    sent = []
    killed = []
    _patch_peak(monkeypatch, 0.1)

    async def fake_notify(db, **kwargs):
        sent.append(kwargs)

    async def fake_terminate(session):
        killed.append(session.pod_name)
        session.state = "terminated"

    monkeypatch.setattr(idle_monitor, "create_notification_safely", fake_notify)
    monkeypatch.setattr(idle_monitor, "_terminate", fake_terminate)

    session = _session(idle_shutdown_at=NOW - timedelta(minutes=1))  # deadline passed
    result = await idle_monitor.process_idle_sessions(FakeDB([session]), now=NOW)

    assert result == {"warned": 0, "shutdown": 1, "reprieved": 0}
    assert killed == ["vm-123"]
    assert session.state == "terminated"
    assert session.idle_shutdown_at is None
    assert sent[0]["type"] == "vm_terminated"


async def test_a_rescued_vm_can_be_warned_again_in_a_later_idle_spell(monkeypatch):
    """Clearing the stamp on reprieve must not make the VM immune afterwards."""
    _patch_peak(monkeypatch, 90.0)

    async def fake_notify(db, **kwargs):
        pass

    async def fake_terminate(session):
        pass

    monkeypatch.setattr(idle_monitor, "create_notification_safely", fake_notify)
    monkeypatch.setattr(idle_monitor, "_terminate", fake_terminate)

    session = _session(idle_shutdown_at=NOW + timedelta(minutes=3))
    await idle_monitor.process_idle_sessions(FakeDB([session]), now=NOW)
    assert session.idle_shutdown_at is None

    # It goes quiet again later — it must be warned afresh.
    _patch_peak(monkeypatch, 0.2)
    later = NOW + timedelta(hours=1)
    result = await idle_monitor.process_idle_sessions(FakeDB([session]), now=later)

    assert result["warned"] == 1
    assert session.idle_shutdown_at == later + timedelta(minutes=10)


# --- resilience ---------------------------------------------------------------


async def test_a_failed_kill_leaves_the_deadline_set_so_the_next_tick_retries(monkeypatch):
    _patch_peak(monkeypatch, 0.1)

    async def fake_notify(db, **kwargs):
        pass

    async def fake_terminate(session):
        raise RuntimeError("orchestrator unreachable")

    monkeypatch.setattr(idle_monitor, "create_notification_safely", fake_notify)
    monkeypatch.setattr(idle_monitor, "_terminate", fake_terminate)

    deadline = NOW - timedelta(minutes=1)
    session = _session(idle_shutdown_at=deadline)
    db = FakeDB([session])

    result = await idle_monitor.process_idle_sessions(db, now=NOW)

    assert result["shutdown"] == 0
    assert session.idle_shutdown_at == deadline  # retried next tick, not forgotten
    assert db.rollbacks == 1


async def test_one_broken_pod_does_not_stop_the_sweep(monkeypatch):
    """A single bad pod must not leave every other idle VM unprocessed."""
    good = _session(id="good", pod_name="vm-good")
    bad = _session(id="bad", pod_name="vm-bad")

    async def fake_is_idle(db, session, now):
        if session.id == "bad":
            raise RuntimeError("metrics query blew up")
        return True

    async def fake_notify(db, **kwargs):
        pass

    monkeypatch.setattr(idle_monitor, "is_idle", fake_is_idle)
    monkeypatch.setattr(idle_monitor, "create_notification_safely", fake_notify)

    result = await idle_monitor.process_idle_sessions(FakeDB([bad, good]), now=NOW)

    assert result["warned"] == 1  # the healthy pod was still handled
    assert good.idle_shutdown_at is not None
