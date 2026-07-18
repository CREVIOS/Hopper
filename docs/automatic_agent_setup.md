# Agent Layer — Setup & Deployment

Implements `docs/automatic_agent.md`: a **free open-source agent layer** and an
**always-on telemetry agent**. Everything lives under
`services/api-gateway/app/agents/` and is wired into the existing FastAPI gateway.

Both features follow this repo's "configured → real, unconfigured → graceful
fallback" convention: with **zero** keys installed, nothing breaks — agents use a
local Ollama (or a deterministic stub) and the telemetry agent logs its report
instead of sending it.

---

## Files

| File | Role |
|------|------|
| `app/agents/free_agents.py` | Provider adapter (Groq / HuggingFace / Ollama / stub) + `HermesAgent`, `ClawbotAgent`, `OpenCodeAgent` |
| `app/agents/alerting.py` | Email (Resend or SMTP) + WhatsApp (Twilio / Green API) dispatch |
| `app/agents/telemetry_agent.py` | Collect → analyse → alert loop; LangGraph or sequential; APScheduler or asyncio loop |
| `app/routers/agents.py` | REST API (`/agents/*`) |
| Config: `app/config.py` | Non-secret knobs (`HOPPER_AGENT_*`, `HOPPER_TELEMETRY_*`) |
| Secrets: `services/api-gateway/.env` | `GROQ_API_KEY`, `HF_TOKEN`, `RESEND_API_KEY`, `TWILIO_*`, `GREEN_API_*` |

---

## Feature 1 — Free agents

### Configure a backend (pick one; or none = local/stub)
Secrets go in `services/api-gateway/.env` (read from the environment, no
`HOPPER_` prefix — same as `GEMINI_API_KEY`):

```dotenv
# Groq free tier — fastest hosted option
GROQ_API_KEY=gsk_...
# or HuggingFace serverless inference
HF_TOKEN=hf_...
```

No key? Run models locally for free with **Ollama**:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2         # matches HOPPER_OLLAMA_MODEL
ollama serve                 # serves http://localhost:11434
```

Provider/model selection (non-secret) via env, all optional:
```dotenv
HOPPER_AGENT_PROVIDER=auto            # auto | groq | huggingface | ollama
HOPPER_GROQ_MODEL=llama-3.3-70b-versatile
HOPPER_HF_MODEL=meta-llama/Llama-3.1-8B-Instruct
HOPPER_OLLAMA_MODEL=llama3.2
```

### Use it
In code:
```python
from app.agents.free_agents import HermesAgent, ClawbotAgent, OpenCodeAgent
reply = await OpenCodeAgent().arun("Write a Python function to reverse a linked list")
```

Over HTTP (any logged-in user; rate-limited 20/min):
```bash
curl -X POST http://localhost:8000/agents/hermes/chat \
  -H 'Content-Type: application/json' --cookie "session_token=$TOKEN" \
  -d '{"prompt":"Explain eventual consistency in 3 sentences"}'
# GET /agents/  → lists agents + the resolved provider/model
```

---

## Feature 2 — Always-on telemetry agent

Runs automatically on gateway startup (`HOPPER_TELEMETRY_AGENT_ENABLED=true`,
default). Each cycle samples host CPU/mem/disk + app health (VM pods by state,
failure rate from Postgres), scores a severity, and — when severity ≥
`HOPPER_TELEMETRY_ALERT_MIN_SEVERITY` — dispatches a report.

### Behaviour knobs (non-secret)
```dotenv
HOPPER_TELEMETRY_AGENT_ENABLED=true
HOPPER_TELEMETRY_INTERVAL_SECONDS=300
HOPPER_TELEMETRY_DISK_WARN_PERCENT=90
HOPPER_TELEMETRY_CPU_WARN_PERCENT=85
HOPPER_TELEMETRY_MEM_WARN_PERCENT=85
HOPPER_TELEMETRY_ERROR_RATE_WARN=0.05
HOPPER_TELEMETRY_ALERT_MIN_SEVERITY=warning   # info | warning | critical
HOPPER_TELEMETRY_USE_LLM_SUMMARY=true         # phrase report via a free agent
```

### Alert channels
Secrets in `.env`, routing in `HOPPER_*`. Any subset works; none = log-only.

**Email — Resend** (else falls back to the existing `HOPPER_SMTP_*` / Gmail App Password):
```dotenv
RESEND_API_KEY=re_...
HOPPER_ALERT_EMAIL_TO=you@example.com,oncall@example.com
HOPPER_ALERT_EMAIL_FROM=Hopper <alerts@yourdomain.com>
```

**WhatsApp — Twilio Sandbox:**
```dotenv
HOPPER_WHATSAPP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
HOPPER_TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
HOPPER_WHATSAPP_TO=whatsapp:+8801XXXXXXXXX
```

**WhatsApp — Green API:**
```dotenv
HOPPER_WHATSAPP_PROVIDER=greenapi
GREEN_API_ID_INSTANCE=1101...
GREEN_API_TOKEN=...
HOPPER_WHATSAPP_TO=+8801XXXXXXXXX
```

### Endpoints (admin/professor)
```bash
curl --cookie "session_token=$TOKEN" http://localhost:8000/agents/telemetry/latest
curl -X POST --cookie "session_token=$TOKEN" http://localhost:8000/agents/telemetry/run
```

---

## Optional dependencies (enhanced paths)

The feature runs with the current dependency set via fallbacks. Install these to
enable the richer implementations (the code auto-detects them):

```bash
cd services/api-gateway
poetry run pip install psutil apscheduler          # accurate host metrics + robust scheduler
poetry run pip install langgraph                   # stateful graph orchestration (else sequential)
poetry run pip install resend                      # official Resend client (else raw REST via httpx)
```

| Package | Without it |
|---------|-----------|
| `psutil` | CPU/mem from `/proc` + `os.getloadavg` (coarser); disk exact |
| `apscheduler` | plain `asyncio` interval loop |
| `langgraph` | sequential collect→analyse→alert (identical output) |
| `resend` | raw httpx POST to the Resend REST API |

---

## Deploying the telemetry agent as a standalone worker / cron

It ships with an embedded scheduler (starts with the gateway), **or** run it as
its own process — handy on a free tier (Render/Railway background worker) or a
cron box:

```bash
cd services/api-gateway
# long-running worker (loops every HOPPER_TELEMETRY_INTERVAL_SECONDS)
poetry run python -m app.agents.telemetry_agent
```

Cron (one cycle per invocation — set the interval via crontab, not the env):
```cron
*/5 * * * * cd /path/services/api-gateway && poetry run python -c "import asyncio; from app.agents.telemetry_agent import run_once; print(asyncio.run(run_once())['report'])"
```

To avoid double-alerting, set `HOPPER_TELEMETRY_AGENT_ENABLED=false` on the API
gateway when running the monitor as a separate worker.
