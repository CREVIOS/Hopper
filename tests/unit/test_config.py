from app.config import Settings


def test_settings_uses_expected_defaults():
    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://hopper:hopper_dev@localhost:5433/hopper"
    assert settings.nats_url == "nats://localhost:4222"
    assert settings.keycloak_realm == "hopper"
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.allowed_email_domains == []
    assert settings.require_email_verified is True
    assert settings.debug is False
    assert settings.code_url_ttl_seconds == 600


def test_settings_reads_prefixed_environment_overrides(monkeypatch):
    monkeypatch.setenv("HOPPER_DEBUG", "true")
    monkeypatch.setenv("HOPPER_NODE_IP", "10.0.0.15")
    monkeypatch.setenv("HOPPER_CODE_URL_TTL_SECONDS", "900")
    monkeypatch.setenv("HOPPER_KEYCLOAK_CLIENT_SECRET", "super-secret")

    settings = Settings(_env_file=None)

    assert settings.debug is True
    assert settings.node_ip == "10.0.0.15"
    assert settings.code_url_ttl_seconds == 900
    assert settings.keycloak_client_secret == "super-secret"


def test_settings_parses_list_fields_from_environment(monkeypatch):
    monkeypatch.setenv(
        "HOPPER_CORS_ORIGINS",
        '["http://localhost:5173","https://hopper.example.com"]',
    )
    monkeypatch.setenv(
        "HOPPER_ALLOWED_EMAIL_DOMAINS",
        '["cs.du.ac.bd","example.edu"]',
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "http://localhost:5173",
        "https://hopper.example.com",
    ]
    assert settings.allowed_email_domains == [
        "cs.du.ac.bd",
        "example.edu",
    ]


def test_settings_allows_empty_domain_list_for_dev_mode(monkeypatch):
    monkeypatch.setenv("HOPPER_ALLOWED_EMAIL_DOMAINS", "[]")

    settings = Settings(_env_file=None)

    assert settings.allowed_email_domains == []


def test_settings_model_config_uses_expected_env_settings():
    assert Settings.model_config["env_prefix"] == "HOPPER_"
    assert Settings.model_config["env_file"] == ".env"
    assert Settings.model_config["env_file_encoding"] == "utf-8"
