from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://hopper:hopper_dev@localhost:5433/hopper"
    nats_url: str = "nats://localhost:4222"
    keycloak_url: str = "http://localhost:8080"
    keycloak_external_url: str = "http://localhost:8080"
    keycloak_realm: str = "hopper"
    keycloak_client_id: str = "hopper-api"
    # Optional confidential-client secret. If empty, the client is public and
    # PKCE alone authenticates the auth-code exchange.
    keycloak_client_secret: str = ""
    # Service-account client used for admin-API calls (role changes, logout).
    keycloak_admin_client_id: str = "hopper-admin"
    keycloak_admin_client_secret: str = ""

    orchestrator_url: str = "localhost:50051"
    frontend_url: str = "http://localhost:5173"
    callback_url: str = "http://localhost:5173/api/auth/callback"
    cors_origins: list[str] = ["http://localhost:5173"]
    jwt_algorithm: str = "RS256"
    debug: bool = False
    node_ip: str = "127.0.0.1"

    # Self-registration is gated to these email domains. Use lowercase, no @.
    # Empty list = allow any (dev only). Includes hopper.dev for Keycloak demo users (e.g. admin@hopper.dev).
    allowed_email_domains: list[str] = ["cs.du.ac.bd", "hopper.dev"]
    # If true, /auth/callback rejects users whose Keycloak `email_verified`
    # claim is false. Keycloak should also enforce verification at signup.
    require_email_verified: bool = True

    # HMAC secret used to sign per-pod code-server access URLs. Must be ≥32
    # bytes of cryptographic random in production. Loaded from a Secret.
    code_url_signing_secret: str = "change-me-in-production-32bytes-or-more"
    code_url_ttl_seconds: int = 600

    model_config = {"env_prefix": "HOPPER_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
