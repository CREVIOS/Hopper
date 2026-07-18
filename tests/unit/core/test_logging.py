from app.core.logging import setup_logging


def test_setup_logging_configures_structlog(monkeypatch):
    captured = {}

    def fake_configure(*, processors, logger_factory):
        captured["processors"] = processors
        captured["logger_factory"] = logger_factory

    monkeypatch.setattr("app.core.logging.structlog.configure", fake_configure)

    setup_logging()

    assert len(captured["processors"]) == 4
    assert captured["processors"][0].__name__ == "merge_contextvars"
    assert captured["processors"][1].__name__ == "add_log_level"
    assert captured["processors"][2].__class__.__name__ == "TimeStamper"
    assert captured["processors"][3].__class__.__name__ == "ConsoleRenderer"
    assert captured["logger_factory"].__class__.__name__ == "PrintLoggerFactory"
