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
    # Initial VM session lifetime (hours) from launch; expires_at = started_at +
    # this. Extendable up to SESSION_MAX_WALLCLOCK_HOURS (see routers/pods.py).
    session_ttl_hours: float = 4.0

    # Audit-log retention (NFR-NF-014). A background job periodically deletes
    # audit_logs rows older than this many days. Set to 0 to disable (retain
    # forever). The purge runs every audit_retention_interval_hours.
    audit_retention_days: int = 90
    audit_retention_interval_hours: float = 24.0

    # Session-expiry reaper (FR-HC-27): a background job terminates VMs whose
    # expires_at TTL has passed. Set enabled=false to turn it off (e.g. local
    # dev without an orchestrator).
    session_reaper_enabled: bool = True
    session_reaper_interval_seconds: float = 60.0

    # Credit-exhaustion grace period (FR-HC-18). When a billing tick fails for
    # lack of credits the VM is not killed outright: the user gets a grace
    # window to top up, and a background monitor terminates the VM only if the
    # balance is still short when the window closes. Set grace_minutes to 0 to
    # terminate immediately on exhaustion (the pre-notification behaviour).
    credit_grace_minutes: float = 5.0
    credit_grace_monitor_enabled: bool = True
    credit_grace_monitor_interval_seconds: float = 15.0

    # Idle auto-shutdown. A VM whose CPU stays below idle_cpu_percent for
    # idle_window_minutes is considered idle: the user is warned and the VM is
    # terminated idle_grace_minutes later unless activity resumes. CPU is the
    # only activity signal we collect, and a student reading code in VS Code
    # looks idle by that measure — hence the warning + grace rather than an
    # immediate kill. Set enabled=false to turn the whole thing off.
    idle_shutdown_enabled: bool = True
    idle_cpu_percent: float = 5.0
    idle_window_minutes: float = 30.0
    idle_grace_minutes: float = 10.0
    idle_monitor_interval_seconds: float = 60.0

    # Default per-user quotas (FR-QUOTA-001/002). Applied to any user without a
    # user_quotas override row. Admins can override per user.
    default_max_concurrent_vms: int = 3
    default_max_workspace_gb: int = 100

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
