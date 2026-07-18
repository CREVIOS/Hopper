import pytest

from app.core import nats as nats_module


class FakeNatsClient:
    def __init__(self, connected=True):
        self.is_connected = connected
        self.drained = False

    async def drain(self):
        self.drained = True


async def test_connect_stores_and_returns_client(monkeypatch):
    fake_client = FakeNatsClient()

    async def fake_connect(url, max_reconnect_attempts, reconnect_time_wait):
        assert url == nats_module.settings.nats_url
        assert max_reconnect_attempts == -1
        assert reconnect_time_wait == 2
        return fake_client

    monkeypatch.setattr("app.core.nats.nats.connect", fake_connect)
    nats_module.nc = None

    result = await nats_module.connect()

    assert result is fake_client
    assert nats_module.nc is fake_client


async def test_disconnect_drains_connected_client_and_clears_global():
    fake_client = FakeNatsClient(connected=True)
    nats_module.nc = fake_client

    await nats_module.disconnect()

    assert fake_client.drained is True
    assert nats_module.nc is None


async def test_disconnect_skips_drain_for_disconnected_client():
    fake_client = FakeNatsClient(connected=False)
    nats_module.nc = fake_client

    await nats_module.disconnect()

    assert fake_client.drained is False
    assert nats_module.nc is None


def test_get_nc_returns_connected_client():
    fake_client = FakeNatsClient(connected=True)
    nats_module.nc = fake_client

    assert nats_module.get_nc() is fake_client


def test_get_nc_raises_when_not_connected():
    nats_module.nc = None

    with pytest.raises(RuntimeError) as exc_info:
        nats_module.get_nc()

    assert str(exc_info.value) == "NATS not connected"
