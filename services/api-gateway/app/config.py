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
    # Set the `Secure` flag on auth cookies. Must stay true in production (HTTPS).
    # For local dev over http://localhost, browsers (notably Safari) drop Secure
    # cookies, so set HOPPER_COOKIE_SECURE=false to log in locally.
    cookie_secure: bool = True
    node_ip: str = "127.0.0.1"
    # Credits granted automatically on signup so a new student can launch a first
    # VM without waiting for an admin/teacher allocation. Set to 0 to disable
    # (accounts then start at 0 and must be funded before launching anything).
    signup_grant_credits: float = 10.0

    # Self-registration email-domain allowlist. Use lowercase, no @.
    # Empty list = allow any valid email (the default). Set a non-empty list
    # (e.g. via HOPPER_ALLOWED_EMAIL_DOMAINS) to restrict signup/login to
    # specific domains.
    allowed_email_domains: list[str] = []
    # If true, /auth/callback rejects users whose Keycloak `email_verified`
    # claim is false. Keycloak should also enforce verification at signup.
    require_email_verified: bool = True

    # HMAC secret used to sign per-pod code-server access URLs. Must be ≥32
    # bytes of cryptographic random in production. Loaded from a Secret.
    code_url_signing_secret: str = "change-me-in-production-32bytes-or-more"
    code_url_ttl_seconds: int = 600

    # SMTP for email verification + password reset. If smtp_host is empty the
    # email layer runs in DEV mode: codes are written to the app log instead of
    # being sent (so the flow is testable without a mail server). In prod these
    # come from the `hopper-smtp` Secret / env.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Hopper <no-reply@localhost>"
    smtp_starttls: bool = True  # True=STARTTLS on 587; False+465 = implicit TLS
    # Verification / reset one-time codes.
    email_code_ttl_seconds: int = 600  # 10 min
    email_code_length: int = 6
    email_code_max_attempts: int = 5

    model_config = {"env_prefix": "HOPPER_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
