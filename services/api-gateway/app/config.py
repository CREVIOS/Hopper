from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Export .env into the real process environment (not just pydantic's private
# read) so SDKs that look at os.environ directly can see it — notably the
# google-genai client, which reads GEMINI_API_KEY / GOOGLE_API_KEY itself. Real
# env vars (e.g. injected by the k8s manifest in prod) always win: override=False.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


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

    # CPU/RAM admission queue. The gateway computes free cluster capacity
    # itself; these reserves cover kube-system pods it cannot see. Kubernetes
    # quantity strings, parsed in app.services.vm_capacity.
    cluster_reserve_cpu: str = "1"
    cluster_reserve_memory: str = "2Gi"
    # Workspace-disk (PVC) pool. Node ephemeral-storage is not reported by
    # ListNodes, so the total is configured; used = sum of live VMs' plan disk.
    cluster_storage_total: str = "150Gi"
    cluster_reserve_storage: str = "10Gi"
    # How often the background admission loop re-checks the queue, in seconds.
    scheduler_tick_seconds: int = 5

    # Brevo transactional-email HTTPS API (https://api.brevo.com, :443). When
    # set, verification/reset emails go out via Brevo instead of SMTP — pods on
    # the prod cluster can egress :443 but not SMTP ports, and a Brevo sender
    # with domain authentication (DKIM/SPF) keeps codes out of spam, which the
    # personal-Gmail SMTP path could not. In prod this comes from the
    # `hopper-brevo` Secret. SMTP below stays as the fallback transport.
    brevo_api_key: str = ""

    # SMTP for email verification + password reset. If neither Brevo nor SMTP
    # is configured the email layer runs in DEV mode: codes are written to the
    # app log instead of being sent (so the flow is testable without a mail
    # server). In prod these come from the `hopper-smtp` Secret / env.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Hopper <no-reply@localhost>"
    smtp_starttls: bool = True  # True=STARTTLS on 587; False+465 = implicit TLS
    # Transport encryption. Empty = derive from smtp_starttls (back-compat).
    # Explicit values: "starttls" (587), "ssl" (implicit TLS, 465),
    # "none" (plain SMTP — for local mail-catchers like Mailpit on :1025).
    smtp_tls: str = ""
    # Verification / reset one-time codes.
    email_code_ttl_seconds: int = 600  # 10 min
    email_code_length: int = 6
    email_code_max_attempts: int = 5

    # --- Idle-detection agent (protects students from credit exhaustion) ----
    # A VM is reclaimed only when it looks abandoned across several dimensions
    # for the whole window AND still holds credits. All values are overridable
    # via HOPPER_* env vars.
    idle_agent_enabled: bool = True
    idle_cpu_threshold_percent: float = 2.0    # CPU >= this counts as "active"
    idle_cpu_window_seconds: int = 1800        # 30 min inactive => idle
    idle_grace_seconds: int = 600              # 10 min warning countdown
    idle_check_interval_seconds: int = 30      # scanner cadence
    idle_metrics_stale_seconds: int = 180      # no metrics this long => blind => never kill
    idle_forget_seconds: int = 3600            # drop tracking rows for long-gone pods
    idle_flush_seconds: int = 60               # throttle metric-driven DB writes per pod
    idle_heartbeat_interval_seconds: int = 60  # advised in-VM agent cadence

    # --- Smart Sandbox provisioner (NL project description -> ready workspace) --
    sandbox_agent_enabled: bool = True
    # LLM planner. Real natural-language parsing runs through Google Gemini when a
    # GEMINI_API_KEY / GOOGLE_API_KEY is present in the environment (the google-genai
    # SDK reads it directly). With no key the agent falls back to a deterministic
    # keyword planner, so the flow works with zero API keys. No Anthropic dependency.
    sandbox_agent_model: str = "gemini-2.5-flash"
    # Authorized package mirrors baked into every generated provision.sh. Point
    # these at an internal Artifactory/Verdaccio/apt mirror in production so a
    # student VM can only pull bytes from infrastructure the platform trusts.
    sandbox_pip_index_url: str = "https://pypi.org/simple"
    sandbox_npm_registry: str = "https://registry.npmjs.org"
    sandbox_apt_mirror: str = ""  # empty = keep the base image's default apt sources
    # Internal URL the in-VM provisioner uses to fetch its script. Injected into
    # the pod env (HOPPER_API_URL) via the orchestrator labels channel.
    sandbox_internal_api_url: str = "http://api-gateway:8000"

    # --- Free open-source agent layer (Hermes / Clawbot / OpenCode) ----------
    # Adapter over FREE LLM backends only — no paid APIs. Provider *secrets*
    # (GROQ_API_KEY, HF_TOKEN) live in .env / env and are read from os.environ,
    # exactly like GEMINI_API_KEY — they are NOT fields here. These are only the
    # non-secret routing knobs.
    #   auto: Groq if GROQ_API_KEY, else HuggingFace if HF_TOKEN, else local
    #   Ollama, else a deterministic stub. Or force: groq | huggingface | ollama.
    agent_provider: str = "auto"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    hf_base_url: str = "https://router.huggingface.co/v1"
    hf_model: str = "meta-llama/Llama-3.1-8B-Instruct"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    agent_temperature: float = 0.3
    agent_timeout_seconds: float = 60.0

    # --- Always-on telemetry / monitoring agent ------------------------------
    # Alert-channel secrets (RESEND_API_KEY, GREEN_API_*) also live in
    # .env / env, not here. These are behaviour + non-secret routing only.
    telemetry_agent_enabled: bool = True
    telemetry_interval_seconds: int = 300      # sample + evaluate cadence
    telemetry_cpu_warn_percent: float = 85.0
    telemetry_mem_warn_percent: float = 85.0
    telemetry_disk_warn_percent: float = 90.0
    telemetry_error_rate_warn: float = 0.05    # 5% VM failures/hour
    telemetry_alert_min_severity: str = "warning"  # info | warning | critical
    telemetry_use_llm_summary: bool = True     # phrase the report via a free LLM
    alert_email_to: str = ""                   # comma-separated recipients
    alert_email_from: str = ""                 # defaults to smtp_from
    # Chat alerts go over Telegram via the Green API Telegram gateway
    # (GREEN_API_ID_INSTANCE / GREEN_API_TOKEN in .env). Optional global
    # recipients, comma-separated phone numbers e.g. +8801XXXXXXXXX.
    telegram_to: str = ""

    # Rate limiting (HOP-19 18.2). Buckets are in-memory per worker process,
    # so the effective ceiling scales with workers × replicas — these are
    # abuse guards, not precise quotas. Format: the `limits` notation, e.g.
    # "5/minute", "3/5minutes".
    #
    # Per-user ceiling on authenticated session traffic, keyed by the
    # verified JWT subject (enforced post-auth in get_current_user).
    rate_limit_user_default: str = "120/minute"
    # Programmatic access via API keys is limited separately from session
    # auth, per key (18.1 "rate limited separately").
    rate_limit_api_key: str = "30/minute"
    # VM creates per user.
    rate_limit_pod_create: str = "5/minute"
    # FAILED sign-in attempts per (client IP, email) before /auth/login
    # returns 429. Counting failures (not calls) means a shared university
    # NAT can't lock out a whole lab, but 3 wrong passwords for one account
    # from one address trips it.
    rate_limit_login_failures: str = "3/5minutes"

    # Low-credit warnings, in minutes of runtime remaining at the user's
    # current burn rate (sum of their running VMs' hourly rates). A warning
    # notification fires once per threshold as the balance crosses it;
    # thresholds re-arm automatically when credits are topped up.
    credit_warning_minutes: list[int] = [60, 30, 10, 5]
    # Grace period after credits hit zero before the VM is terminated. The
    # first failed billing tick starts the countdown and warns the user;
    # termination happens on the first tick after the deadline.
    credit_grace_minutes: int = 5

    # extra="ignore": the .env also holds non-HOPPER_ keys (e.g. GEMINI_API_KEY,
    # read from os.environ by the google-genai SDK, not by this Settings class).
    # Without this, pydantic surfaces them as unknown fields and refuses to load.
    model_config = {
        "env_prefix": "HOPPER_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
