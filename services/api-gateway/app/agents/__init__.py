"""Agent layer for Hopper.

Two features live here:

* ``free_agents``  — a provider-agnostic adapter over *free* LLM backends
  (Groq free tier, HuggingFace serverless inference, or a local Ollama) exposing
  ``HermesAgent`` / ``ClawbotAgent`` / ``OpenCodeAgent``. No paid APIs.
* ``telemetry_agent`` — an always-on background monitor that samples system /
  application telemetry, decides whether things look healthy, and dispatches a
  summary to email / WhatsApp via ``alerting``.

Every external dependency (Groq, HuggingFace, Ollama, LangGraph, Resend, Twilio,
APScheduler, psutil) is imported lazily and degrades gracefully when absent, so
importing this package never hard-fails and the API gateway boots with zero
extra config.
"""
