import logging

import pytest

from app.config import settings
from app.services import email as email_service


class FakeResponse:
    def __init__(self, status_code=201, text=""):
        self.status_code = status_code
        self.text = text


class FakeAsyncClient:
    def __init__(self, *, post_responses=None, post_exc=None):
        self.post_responses = list(post_responses or [])
        self.post_exc = post_exc
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if self.post_exc is not None:
            raise self.post_exc
        return self.post_responses.pop(0)


@pytest.fixture
def no_transports(monkeypatch):
    """Baseline: neither Brevo nor SMTP configured."""
    monkeypatch.setattr(settings, "brevo_api_key", "")
    monkeypatch.setattr(settings, "smtp_host", "")


async def test_dev_mode_logs_code_when_nothing_configured(no_transports, caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.email"):
        await email_service.send_code_email("student@example.com", "verify_email", "123456")
    assert "email DEV" in caplog.text
    assert "123456" in caplog.text


async def test_brevo_sends_via_https_api(no_transports, monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-test-key")
    monkeypatch.setattr(settings, "smtp_from", "Hopper <no-reply@hopper.farefin.com>")
    fake_client = FakeAsyncClient(post_responses=[FakeResponse(201)])
    monkeypatch.setattr(
        "app.services.email.httpx.AsyncClient", lambda timeout: fake_client
    )

    await email_service.send_code_email("student@example.com", "verify_email", "654321")

    assert len(fake_client.post_calls) == 1
    url, kwargs = fake_client.post_calls[0]
    assert url == email_service.BREVO_API_URL
    assert kwargs["headers"]["api-key"] == "xkeysib-test-key"
    payload = kwargs["json"]
    assert payload["sender"] == {"name": "Hopper", "email": "no-reply@hopper.farefin.com"}
    assert payload["to"] == [{"email": "student@example.com"}]
    assert payload["subject"] == "Verify your Hopper account"
    assert "654321" in payload["textContent"]
    assert "654321" in payload["htmlContent"]


async def test_brevo_sender_without_display_name(no_transports, monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-test-key")
    monkeypatch.setattr(settings, "smtp_from", "no-reply@hopper.farefin.com")
    fake_client = FakeAsyncClient(post_responses=[FakeResponse(201)])
    monkeypatch.setattr(
        "app.services.email.httpx.AsyncClient", lambda timeout: fake_client
    )

    await email_service.send_code_email("student@example.com", "password_reset", "111222")

    payload = fake_client.post_calls[0][1]["json"]
    assert payload["sender"] == {"email": "no-reply@hopper.farefin.com"}
    assert payload["subject"] == "Reset your Hopper password"


async def test_brevo_api_error_falls_back_to_smtp(no_transports, monkeypatch, caplog):
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-test-key")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    fake_client = FakeAsyncClient(
        post_responses=[FakeResponse(401, text='{"code":"unauthorized"}')]
    )
    monkeypatch.setattr(
        "app.services.email.httpx.AsyncClient", lambda timeout: fake_client
    )
    smtp_sends = []
    monkeypatch.setattr(
        "app.services.email._send_sync", lambda msg: smtp_sends.append(msg)
    )

    with caplog.at_level(logging.WARNING, logger="app.services.email"):
        await email_service.send_code_email("student@example.com", "verify_email", "999000")

    assert "brevo send failed" in caplog.text
    assert "falling back to SMTP" in caplog.text
    assert len(smtp_sends) == 1
    assert smtp_sends[0]["To"] == "student@example.com"


async def test_brevo_failure_without_smtp_never_raises(no_transports, monkeypatch, caplog):
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-test-key")
    fake_client = FakeAsyncClient(post_exc=RuntimeError("connect timeout"))
    monkeypatch.setattr(
        "app.services.email.httpx.AsyncClient", lambda timeout: fake_client
    )

    with caplog.at_level(logging.ERROR, logger="app.services.email"):
        await email_service.send_code_email("student@example.com", "verify_email", "424242")

    assert "email send failed" in caplog.text


async def test_smtp_path_used_when_no_brevo_key(no_transports, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    smtp_sends = []
    monkeypatch.setattr(
        "app.services.email._send_sync", lambda msg: smtp_sends.append(msg)
    )

    await email_service.send_code_email("student@example.com", "verify_email", "777888")

    assert len(smtp_sends) == 1
    msg = smtp_sends[0]
    assert msg["Subject"] == "Verify your Hopper account"
    assert "777888" in msg.get_body(("plain",)).get_content()


async def test_smtp_failure_never_raises(no_transports, monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")

    def boom(msg):
        raise OSError("connection refused")

    monkeypatch.setattr("app.services.email._send_sync", boom)

    with caplog.at_level(logging.ERROR, logger="app.services.email"):
        await email_service.send_code_email("student@example.com", "verify_email", "313131")

    assert "email send failed" in caplog.text
