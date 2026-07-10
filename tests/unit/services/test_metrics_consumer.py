import json

from app.services import metrics_consumer as metrics_module


class FakeMessage:
    def __init__(self, data):
        self.data = data


async def test_handle_metrics_ignores_malformed_message():
    msg = FakeMessage(b"{bad json")

    assert await metrics_module._handle_metrics(msg) is None


async def test_handle_metrics_stores_sample(monkeypatch):
    captured = {}

    class FakeDB:
        def add(self, sample):
            captured["sample"] = sample

        async def commit(self):
            captured["committed"] = True

    class FakeSessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.services.metrics_consumer.async_session", lambda: FakeSessionContext())

    msg = FakeMessage(
        json.dumps(
            {
                "pod_id": "pod-1",
                "user_id": "user-1",
                "cpu_percent": 40.5,
                "memory_used_bytes": 2048,
                "memory_limit_bytes": 4096,
            }
        ).encode()
    )

    await metrics_module._handle_metrics(msg)

    assert captured["committed"] is True
    assert captured["sample"].pod_id == "pod-1"
    assert captured["sample"].user_id == "user-1"
    assert captured["sample"].cpu_percent == 40.5


async def test_start_metrics_consumer_subscribes_with_queue_group(monkeypatch):
    captured = {}

    class FakeNC:
        async def subscribe(self, subject, queue, cb):
            captured["subject"] = subject
            captured["queue"] = queue
            captured["callback"] = cb

    monkeypatch.setattr("app.services.metrics_consumer.nats_client.get_nc", lambda: FakeNC())

    await metrics_module.start_metrics_consumer()

    assert captured["subject"] == "metrics.*"
    assert captured["queue"] == "metrics-workers"
    assert captured["callback"] is metrics_module._handle_metrics
