"""FEATURE 1 — Free open-source agent layer (Hermes / Clawbot / OpenCode).

Goal: talk to open-weight models (Llama, Mixtral, Nous-Hermes, Qwen-Coder, …)
without any paid API. We do that behind a small provider adapter so the same
agent code runs against whichever *free* backend is available:

    Groq free tier   ── OpenAI-compatible /chat/completions  (needs GROQ_API_KEY)
    HuggingFace      ── serverless inference router           (needs HF_TOKEN)
    Ollama (local)   ── http://localhost:11434/api/chat       (no key, no cost)

Selection is controlled by ``settings.agent_provider``:

  * ``auto`` (default): use Groq if GROQ_API_KEY is set, else HuggingFace if
    HF_TOKEN is set, else a local Ollama, else a deterministic stub (so callers
    never crash when no backend is reachable — mirrors the Gemini/SMTP DEV mode
    convention used elsewhere in this codebase).
  * ``groq`` / ``huggingface`` / ``ollama``: force one backend.

Everything is plain ``httpx`` (already a project dependency) — no vendor SDKs to
install. Keys are read straight from the process environment (the same way the
sandbox agent reads GEMINI_API_KEY), so ``GROQ_API_KEY`` / ``HF_TOKEN`` in the
api-gateway ``.env`` just work.

Deliverable entry points: :class:`HermesAgent`, :class:`ClawbotAgent`,
:class:`OpenCodeAgent` plus :func:`get_agent` / :func:`resolve_provider`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

Message = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": ...}


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
class LLMProvider:
    """Base provider. Subclasses implement :meth:`achat` (async) — the sync
    :meth:`chat` wrapper is provided for standalone/cron use."""

    name: str = "base"

    def __init__(self, model: str) -> None:
        self.model = model

    def available(self) -> bool:  # pragma: no cover - trivial
        return True

    async def achat(self, messages: list[Message], *, temperature: float, max_tokens: int) -> str:
        raise NotImplementedError

    def chat(self, messages: list[Message], *, temperature: float, max_tokens: int) -> str:
        # Real implementation is attached below (``LLMProvider.chat = _sync_chat``)
        # once the async subclasses exist; this body is never reached.
        raise NotImplementedError


class _OpenAICompatProvider(LLMProvider):
    """Groq and HuggingFace both expose an OpenAI-style /chat/completions API,
    so they share one implementation differing only in base URL + auth header."""

    def __init__(self, *, base_url: str, model: str, api_key: str, name: str) -> None:
        super().__init__(model)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = name

    def available(self) -> bool:
        return bool(self.api_key)

    async def achat(self, messages: list[Message], *, temperature: float, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=settings.agent_timeout_seconds) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class OllamaProvider(LLMProvider):
    """Local, fully-free backend. Assumes ``ollama serve`` on :11434 with the
    model already pulled (``ollama pull llama3.2``)."""

    name = "ollama"

    def __init__(self, *, base_url: str, model: str) -> None:
        super().__init__(model)
        self.base_url = base_url.rstrip("/")

    def available(self) -> bool:
        # Cheap reachability probe; keep it short so `auto` selection is snappy.
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=1.5)
            return resp.status_code == 200
        except Exception:  # noqa: BLE001 - unreachable Ollama is a normal case
            return False

    async def achat(self, messages: list[Message], *, temperature: float, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=settings.agent_timeout_seconds) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


class StubProvider(LLMProvider):
    """Zero-dependency fallback when no free backend is reachable. Returns a
    deterministic echo so callers (e.g. the telemetry summariser) still work."""

    name = "stub"

    def available(self) -> bool:
        return True

    async def achat(self, messages: list[Message], *, temperature: float, max_tokens: int) -> str:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"[no free LLM backend configured] {user[:400]}"


# Give LLMProvider.chat a working sync path now that subclasses exist.
def _sync_chat(self: LLMProvider, messages: list[Message], *, temperature: float, max_tokens: int) -> str:
    import asyncio

    return asyncio.run(self.achat(messages, temperature=temperature, max_tokens=max_tokens))


LLMProvider.chat = _sync_chat  # type: ignore[assignment]


def _env(*names: str) -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return ""


def resolve_provider(force: str | None = None) -> LLMProvider:
    """Pick a provider honouring ``settings.agent_provider`` (or ``force``).

    ``auto`` prefers a hosted free tier (fast, no local GPU) then falls back to
    a local Ollama, then the stub. Selection never raises.
    """
    choice = (force or settings.agent_provider or "auto").lower()

    def groq() -> LLMProvider:
        return _OpenAICompatProvider(
            base_url=settings.groq_base_url, model=settings.groq_model,
            api_key=_env("GROQ_API_KEY"), name="groq",
        )

    def hf() -> LLMProvider:
        return _OpenAICompatProvider(
            base_url=settings.hf_base_url, model=settings.hf_model,
            api_key=_env("HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACEHUB_API_TOKEN"),
            name="huggingface",
        )

    def ollama() -> LLMProvider:
        return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)

    if choice == "groq":
        return groq()
    if choice == "huggingface":
        return hf()
    if choice == "ollama":
        return ollama()

    # auto
    for candidate in (groq(), hf(), ollama()):
        if candidate.available():
            logger.info("free_agents: selected provider %s (%s)", candidate.name, candidate.model)
            return candidate
    logger.warning("free_agents: no free LLM backend available; using stub")
    return StubProvider(model="stub")


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
@dataclass
class Agent:
    """A named agent = a system prompt + a resolved free provider."""

    name: str
    system_prompt: str
    provider: LLMProvider = field(default_factory=resolve_provider)
    max_tokens: int = 1024

    async def arun(self, prompt: str, *, temperature: float | None = None) -> str:
        messages: list[Message] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        temp = settings.agent_temperature if temperature is None else temperature
        try:
            return await self.provider.achat(messages, temperature=temp, max_tokens=self.max_tokens)
        except Exception as exc:  # noqa: BLE001 - resilience: never crash the caller
            logger.warning("%s: provider %s failed (%s)", self.name, self.provider.name, exc)
            return f"[{self.name} unavailable: {self.provider.name} error]"

    def run(self, prompt: str, *, temperature: float | None = None) -> str:
        temp = settings.agent_temperature if temperature is None else temperature
        messages: list[Message] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        try:
            return self.provider.chat(messages, temperature=temp, max_tokens=self.max_tokens)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: provider %s failed (%s)", self.name, self.provider.name, exc)
            return f"[{self.name} unavailable: {self.provider.name} error]"


_HERMES_PROMPT = (
    "You are Hermes, a helpful open-source reasoning assistant. Answer clearly "
    "and concisely, think step by step when a question is analytical, and admit "
    "uncertainty rather than inventing facts."
)
_CLAWBOT_PROMPT = (
    "You are Clawbot, a robotics-and-systems reasoning agent. You reason about "
    "control loops, planning, sensors, and infrastructure. Prefer precise, "
    "actionable, engineering-grade answers with explicit assumptions."
)
_OPENCODE_PROMPT = (
    "You are OpenCode, an expert programming assistant. Produce correct, minimal, "
    "idiomatic code. Explain only what's non-obvious. When given an error, "
    "diagnose the root cause before proposing a fix."
)


def HermesAgent(provider: LLMProvider | None = None) -> Agent:
    """General reasoning agent (Nous-Hermes-style) on a free backend."""
    return Agent("HermesAgent", _HERMES_PROMPT, provider or resolve_provider())


def ClawbotAgent(provider: LLMProvider | None = None) -> Agent:
    """Robotics / systems reasoning agent on a free backend."""
    return Agent("ClawbotAgent", _CLAWBOT_PROMPT, provider or resolve_provider())


def OpenCodeAgent(provider: LLMProvider | None = None) -> Agent:
    """Coding agent (Qwen-Coder / CodeLlama-style) on a free backend."""
    return Agent("OpenCodeAgent", _OPENCODE_PROMPT, provider or resolve_provider(), max_tokens=2048)


_REGISTRY = {
    "hermes": HermesAgent,
    "clawbot": ClawbotAgent,
    "opencode": OpenCodeAgent,
}


def get_agent(name: str, provider: LLMProvider | None = None) -> Agent:
    """Factory by short name: ``hermes`` | ``clawbot`` | ``opencode``."""
    key = name.lower().strip()
    if key not in _REGISTRY:
        raise ValueError(f"unknown agent '{name}'; choices: {sorted(_REGISTRY)}")
    return _REGISTRY[key](provider)


def available_agents() -> list[str]:
    return sorted(_REGISTRY)
