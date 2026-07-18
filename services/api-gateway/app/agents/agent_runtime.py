"""Launch a free agent *inside a VM* (Feature 1, Option 1).

The agent-layer chat (``free_agents``) talks to a free LLM from the API gateway.
This module takes the next step the product asks for: when a user *selects an
agent and launches it*, we boot a VM whose first-boot provisioner installs that
same agent as a real in-VM CLI (``hopper-agent``). The agent then runs *inside*
the pod — it can read/write the workspace and run shell commands — and the user
drives it from the existing web terminal / VS Code.

We reuse the Smart Sandbox plumbing wholesale:

* the pod boots with the sandbox env (``HOPPER_PROVISION=1`` + per-pod token),
* the in-VM provisioner fetches ``/sandbox/pods/{id}/provision-script`` and runs
  the script :func:`render_agent_provision_script` produced,
* that script drops a self-contained ``hopper-agent`` (stdlib-only Python) wired
  to whichever *free* backend the gateway resolved (Groq / HuggingFace / Ollama).

So no new VM image, provisioner, or orchestrator change is needed — an "agent
VM" is just a sandbox VM whose provision script installs the agent.
"""
from __future__ import annotations

import base64

from app.agents import free_agents
from app.config import settings
from app.services.pod_token import make_pod_token

# Friendly titles shown in the VM banner / README (keep in sync with the
# frontend AGENT_META labels).
AGENT_TITLES: dict[str, str] = {
    "hermes": "Hermes",
    "clawbot": "Clawbot",
    "opencode": "OpenCode",
}


def agent_title(agent_key: str) -> str:
    return AGENT_TITLES.get(agent_key, agent_key.capitalize())


# --------------------------------------------------------------------------- #
# In-VM agent CLI (stdlib only — no pip install, so it can't fail provisioning).
# Reads its whole config from the HOPPER_AGENT_* pod env injected below.
# --------------------------------------------------------------------------- #
_IN_VM_AGENT_PY = r'''#!/usr/bin/env python3
"""hopper-agent — the selected Hopper agent, running inside this VM.

Chats with a free LLM backend (Groq / HuggingFace / Ollama) and can act on the
VM: when the agent replies with a ```bash fenced block, you're offered to run it
right here, and the output is fed back so the agent can continue the task.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

NAME = os.environ.get("HOPPER_AGENT_TITLE", "Agent")
KIND = os.environ.get("HOPPER_AGENT_API_KIND", "stub")
BASE = os.environ.get("HOPPER_AGENT_BASE_URL", "").rstrip("/")
MODEL = os.environ.get("HOPPER_AGENT_MODEL", "stub")
KEY = os.environ.get("HOPPER_AGENT_KEY", "")
SYSTEM = os.environ.get(
    "HOPPER_AGENT_SYSTEM_PROMPT",
    "You are a helpful assistant running inside a Linux VM.",
)

BOLD, DIM, CYAN, GREEN, RESET = "\033[1m", "\033[2m", "\033[36m", "\033[32m", "\033[0m"
_FENCE = re.compile(r"```(?:bash|sh|shell)\n(.*?)```", re.DOTALL)
# Groq/HuggingFace sit behind Cloudflare, which 403s (error 1010) requests
# carrying urllib's default "Python-urllib" agent — send a real UA.
_UA = "Mozilla/5.0 (X11; Linux x86_64) hopper-agent/1.0"


def _complete(messages):
    """One chat completion against the configured free backend. Returns text."""
    if KIND == "openai":
        url = BASE + "/chat/completions"
        body = {"model": MODEL, "messages": messages, "temperature": 0.3, "stream": False}
        headers = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json",
                   "User-Agent": _UA}
    elif KIND == "ollama":
        url = BASE + "/api/chat"
        body = {"model": MODEL, "messages": messages, "stream": False}
        headers = {"Content-Type": "application/json", "User-Agent": _UA}
    else:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return "[no free LLM backend was configured for this VM] " + last[:400]

    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return "[backend error HTTP %s: %s]" % (exc.code, exc.read().decode()[:300])
    except Exception as exc:  # noqa: BLE001
        return "[backend unreachable: %s]" % exc
    if KIND == "openai":
        return data["choices"][0]["message"]["content"].strip()
    return data["message"]["content"].strip()


def _maybe_run(reply):
    """Offer to run any ```bash blocks in the reply. Returns combined output or None."""
    blocks = [b.strip() for b in _FENCE.findall(reply) if b.strip()]
    if not blocks:
        return None
    out = []
    for cmd in blocks:
        print("%s%s proposes running:%s\n%s" % (DIM, NAME, RESET, cmd))
        try:
            ans = input("%srun it? [y/N] %s" % (BOLD, RESET)).strip().lower()
        except EOFError:
            return None
        if ans != "y":
            out.append("$ (skipped by user)")
            continue
        try:
            p = subprocess.run(cmd, shell=True, cwd="/workspace", capture_output=True,
                               text=True, timeout=600)
            res = (p.stdout + p.stderr).strip()
            print(res)
            out.append("$ %s\n%s (exit %d)" % (cmd, res[:4000], p.returncode))
        except Exception as exc:  # noqa: BLE001
            out.append("$ %s\n[failed: %s]" % (cmd, exc))
    return "\n".join(out)


def main():
    print("%s%s is ready in this VM%s  (%s / %s)" % (BOLD, NAME, RESET, KIND, MODEL))
    print("%sType a task. The agent can run shell commands (it'll ask first)."
          " /reset clears context, /exit quits.%s\n" % (DIM, RESET))
    messages = [{"role": "system", "content": SYSTEM}]
    while True:
        try:
            user = input("%syou>%s " % (CYAN, RESET)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user in ("/exit", "/quit"):
            break
        if user == "/reset":
            messages = [{"role": "system", "content": SYSTEM}]
            print("%scontext cleared%s" % (DIM, RESET))
            continue
        if user == "/help":
            print("Just describe a task. /reset, /exit.")
            continue
        messages.append({"role": "user", "content": user})
        reply = _complete(messages)
        messages.append({"role": "assistant", "content": reply})
        print("%s%s>%s %s\n" % (GREEN, NAME, RESET, reply))
        ran = _maybe_run(reply)
        if ran is not None:
            messages.append({"role": "user",
                             "content": "Output of the commands you asked to run:\n" + ran})
            follow = _complete(messages)
            messages.append({"role": "assistant", "content": follow})
            print("%s%s>%s %s\n" % (GREEN, NAME, RESET, follow))


if __name__ == "__main__":
    main()
'''


def _llm_env() -> dict[str, str]:
    """Resolve the same free backend the gateway would use and describe it for
    the in-VM agent. Groq/HuggingFace -> OpenAI-compatible; Ollama -> native."""
    provider = free_agents.resolve_provider()
    if isinstance(provider, free_agents._OpenAICompatProvider):  # noqa: SLF001
        return {
            "HOPPER_AGENT_API_KIND": "openai",
            "HOPPER_AGENT_BASE_URL": provider.base_url,
            "HOPPER_AGENT_MODEL": provider.model,
            "HOPPER_AGENT_KEY": provider.api_key,
        }
    if isinstance(provider, free_agents.OllamaProvider):
        return {
            "HOPPER_AGENT_API_KIND": "ollama",
            "HOPPER_AGENT_BASE_URL": provider.base_url,
            "HOPPER_AGENT_MODEL": provider.model,
            "HOPPER_AGENT_KEY": "",
        }
    return {"HOPPER_AGENT_API_KIND": "stub", "HOPPER_AGENT_MODEL": "stub"}


def _system_prompt(agent_key: str) -> str:
    """The agent's chat persona, extended for autonomous work inside the VM."""
    base = free_agents.get_agent(agent_key).system_prompt
    return (
        base
        + "\n\nYou are running inside a dedicated Linux VM (Ubuntu, working "
        "directory /workspace) that belongs to the user. You may act on it: when "
        "a step requires running a command, put exactly that command in a fenced "
        "```bash block and the user will be asked to run it, then the output is "
        "returned to you. Keep commands minimal and safe; explain what each does."
    )


def build_agent_pod_env(pod_id: str, agent_key: str) -> dict[str, str]:
    """HOPPER_* values the orchestrator injects into the pod env. Includes the
    sandbox provisioning handshake plus the agent + backend config."""
    env = {
        "HOPPER_POD_ID": pod_id,
        "HOPPER_API_URL": settings.sandbox_internal_api_url,
        "HOPPER_POD_TOKEN": make_pod_token(pod_id),
        "HOPPER_PROVISION": "1",
        "HOPPER_AGENT_NAME": agent_key,
        "HOPPER_AGENT_TITLE": agent_title(agent_key),
        "HOPPER_AGENT_SYSTEM_PROMPT": _system_prompt(agent_key),
    }
    env.update(_llm_env())
    return env


def render_agent_provision_script(agent_key: str) -> str:
    """provision.sh that installs the in-VM ``hopper-agent`` for this agent.

    The agent source is base64-embedded so no quoting in the shell script can
    corrupt it. Runs once at first boot via the standard in-VM provisioner.
    """
    title = agent_title(agent_key)
    b64 = base64.b64encode(_IN_VM_AGENT_PY.encode()).decode()
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "# Generated by the Hopper agent launcher. Installs the selected",
            f"# agent ({title}) as an in-VM CLI. Do not edit by hand.",
            "set -euo pipefail",
            f"echo '>>> Installing {title} agent into this VM'",
            "install -d /workspace",
            f"echo '{b64}' | base64 -d > /usr/local/bin/hopper-agent",
            "chmod +x /usr/local/bin/hopper-agent",
            "# Convenience: a short alias too.",
            "ln -sf /usr/local/bin/hopper-agent /usr/local/bin/agent || true",
            "# sshd does NOT inherit the pod env, so an SSH/web-terminal login shell",
            "# would see no HOPPER_AGENT_* vars and hopper-agent would fall back to the",
            "# stub backend. Persist the backend config for login shells.",
            "{ for v in HOPPER_AGENT_TITLE HOPPER_AGENT_NAME HOPPER_AGENT_API_KIND "
            "HOPPER_AGENT_BASE_URL HOPPER_AGENT_MODEL HOPPER_AGENT_KEY "
            "HOPPER_AGENT_SYSTEM_PROMPT; do printf 'export %s=%q\\n' \"$v\" \"${!v:-}\"; "
            "done; } > /etc/profile.d/hopper-agent.sh",
            "chmod 644 /etc/profile.d/hopper-agent.sh",
            "cat > /workspace/AGENT.md <<'EOF'",
            f"# {title} — your agent in this VM",
            "",
            f"{title} is installed and ready. Start it from the terminal with:",
            "",
            "    hopper-agent",
            "",
            "Describe a task; the agent can run shell commands here (it asks first)",
            "and works in /workspace.",
            "EOF",
            f"echo '>>> {title} agent installed. Run: hopper-agent'",
            "",
        ]
    )
