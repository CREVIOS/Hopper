from app.services import vm_scheduler_consumer


class FakeSubscription:
    def __init__(self):
        self.unsubscribed = False

    async def unsubscribe(self):
        self.unsubscribed = True


class FakeNC:
    def __init__(self):
        self.calls = []
        self.subscription = FakeSubscription()

    async def subscribe(self, subject, cb):
        self.calls.append((subject, cb))
        return self.subscription


async def test_on_pod_stopped_nudges_scheduler(monkeypatch):
    called = {}
    monkeypatch.setattr("app.services.vm_scheduler_consumer.nudge", lambda: called.setdefault("nudged", True))

    await vm_scheduler_consumer._on_pod_stopped(object())

    assert called["nudged"] is True


async def test_start_subscribes_to_pod_stopped_subject():
    nc = FakeNC()

    await vm_scheduler_consumer.start(nc, session_factory=None)

    assert nc.calls[0][0] == "pod.stopped"
    assert vm_scheduler_consumer._subscription is nc.subscription


async def test_stop_unsubscribes_and_clears_subscription():
    sub = FakeSubscription()
    vm_scheduler_consumer._subscription = sub

    await vm_scheduler_consumer.stop()

    assert sub.unsubscribed is True
    assert vm_scheduler_consumer._subscription is None


async def test_stop_tolerates_unsubscribe_failure(monkeypatch):
    class BrokenSubscription:
        async def unsubscribe(self):
            raise RuntimeError("boom")

    vm_scheduler_consumer._subscription = BrokenSubscription()

    await vm_scheduler_consumer.stop()

    assert vm_scheduler_consumer._subscription is None
