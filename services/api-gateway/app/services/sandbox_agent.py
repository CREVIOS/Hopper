"""Smart Sandbox agent — natural language -> ready-to-run VM workspace.

This is the intelligence layer of the sandbox generator. It has three jobs:

1. **Plan** (``plan_workspace``): turn a free-form project description into a
   structured ``RawWorkspaceSpec``. Real language understanding runs through
   Google Gemini when a ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` is present; with
   no key it falls back to a deterministic keyword planner so the flow works with
   zero API keys (mirroring the SMTP "DEV mode" convention in this codebase).
   There is no Anthropic dependency.

2. **Validate** (``validate_spec``): run the (untrusted) planner output through
   the allowlist in ``sandbox_allowlist``. Anything not authorized is dropped
   and reported — never silently installed.

3. **Render** (``render_provision_script``): emit a deterministic ``provision.sh``
   whose every installer is pinned to an authorized mirror. This is what the
   in-VM provisioner fetches and runs once on first boot.

The per-pod bearer used to fetch the script is the *same* HMAC token the idle
agent already uses (:func:`app.services.idle_agent.make_pod_token`), so a single
``HOPPER_POD_TOKEN`` in the pod env serves both in-VM agents.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shlex

from app.config import settings
from app.schemas.pod import VM_PLAN_RESOURCES, DEFAULT_TEMPLATE, VmPlan
from app.schemas.sandbox import RawWorkspaceSpec, WorkspaceSpec
from app.services import sandbox_allowlist as al
from app.services.pod_token import make_pod_token, verify_pod_token

logger = logging.getLogger(__name__)

# Re-export the shared per-pod token helpers under sandbox names so callers
# don't need to know the idle agent owns them.
make_provision_token = make_pod_token
verify_provision_token = verify_pod_token


def credits_per_hour(plan: VmPlan) -> float:
    return float(VM_PLAN_RESOURCES[plan]["credits_per_hour"])


# --------------------------------------------------------------------------- #
# 1. PLAN — natural language -> RawWorkspaceSpec
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = """You configure development sandboxes for university students.
Given a short project description, produce a workspace spec as JSON.

Rules:
- base_template must be one of: ubuntu, python-ml, cpp, java. Pick python-ml for
  data science / ML / Python-heavy work, cpp for C/C++, java for JVM work, else ubuntu.
- apt_packages: OS packages (compilers, git, client libs). Use plain names.
- For C# / .NET / ASP.NET / Blazor: base_template ubuntu, apt_packages include
  "dotnet-sdk-8.0", and vscode_extensions include "ms-dotnettools.csharp".
- pip_packages / npm_packages: library names only (optionally name==version).
  Never use URLs, git+ specifiers, or shell characters.
- vscode_extensions: official Open VSX / Marketplace extension IDs (publisher.name).
- services: only from [postgresql, redis, mysql, mongodb], and only if the
  project clearly needs a database/cache.
Keep the lists tight — only what the described project needs. Return JSON only."""


def _gemini_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _gemini_plan(description: str) -> RawWorkspaceSpec:
    """Call Gemini for structured output. Raises on any failure (caller falls back)."""
    from google import genai  # lazy import: no hard dependency on the fallback path
    from google.genai import types

    client = genai.Client()  # reads GEMINI_API_KEY / GOOGLE_API_KEY from env
    resp = client.models.generate_content(
        model=settings.sandbox_agent_model,
        contents=f"Project description:\n{description}",
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RawWorkspaceSpec,
            temperature=0.2,
        ),
    )
    parsed = resp.parsed
    if isinstance(parsed, RawWorkspaceSpec):
        return parsed
    # Some SDK versions return a dict; coerce defensively.
    return RawWorkspaceSpec.model_validate(parsed)


# Keyword -> spec fragments for the deterministic fallback. Order-independent;
# fragments are merged and de-duplicated. Only allowlisted values appear here.
_KEYWORD_RULES: list[tuple[tuple[str, ...], dict]] = [
    (("python", "fastapi", "flask", "django", "pandas", "numpy"),
     {"apt": ["python3", "python3-pip", "python3-venv"],
      "ext": ["ms-python.python", "charliermarsh.ruff"]}),
    (("fastapi",), {"pip": ["fastapi", "uvicorn"]}),
    (("flask",), {"pip": ["flask"]}),
    (("django",), {"pip": ["django"]}),
    (("pytorch", "torch", "ml", "machine learning", "deep learning", "tensorflow"),
     {"template": "python-ml", "pip": ["numpy", "pandas", "scikit-learn"],
      "ext": ["ms-toolsai.jupyter", "ms-python.python"]}),
    (("pytorch", "torch"), {"pip": ["torch"]}),
    (("tensorflow",), {"pip": ["tensorflow"]}),
    (("jupyter", "notebook", "data science", "data-science"),
     {"template": "python-ml", "pip": ["jupyterlab", "pandas", "matplotlib"],
      "ext": ["ms-toolsai.jupyter"]}),
    (("react", "next", "vue", "svelte", "node", "express", "typescript", "frontend", "javascript"),
     {"apt": ["nodejs", "npm"],
      "ext": ["dbaeumer.vscode-eslint", "esbenp.prettier-vscode"]}),
    (("react",), {"npm": ["react", "react-dom"], "ext": ["dsznajder.es7-react-js-snippets"]}),
    (("vue",), {"npm": ["vue"], "ext": ["vue.volar"]}),
    (("svelte",), {"npm": ["svelte"], "ext": ["svelte.svelte-vscode"]}),
    (("express",), {"npm": ["express"]}),
    (("typescript", "next"), {"npm": ["typescript"]}),
    (("tailwind",), {"npm": ["tailwindcss"], "ext": ["bradlc.vscode-tailwindcss"]}),
    (("c++", "cpp", "c programming"),
     {"template": "cpp", "apt": ["build-essential", "g++", "cmake", "gdb"],
      "ext": ["ms-vscode.cpptools"]}),
    (("rust", "cargo"),
     {"apt": ["rustc", "cargo"], "ext": ["rust-lang.rust-analyzer"]}),
    (("go", "golang"),
     {"apt": ["golang"], "ext": ["golang.go"]}),
    (("java", "spring", "maven", "gradle"),
     {"template": "java", "apt": ["openjdk-21-jdk"], "ext": ["redhat.java", "vscjava.vscode-java-debug"]}),
    (("c#", "csharp", "dotnet", ".net", "asp.net", "aspnet", "blazor"),
     {"template": "ubuntu", "apt": ["dotnet-sdk-8.0"], "ext": ["ms-dotnettools.csharp"]}),
    (("postgres", "postgresql", "psql"),
     {"service": ["postgresql"], "apt": ["postgresql-client", "libpq-dev"],
      "ext": ["mtxr.sqltools", "mtxr.sqltools-driver-pg"]}),
    (("redis", "cache"), {"service": ["redis"], "apt": ["redis-tools"]}),
    (("mysql", "mariadb"), {"service": ["mysql"], "apt": ["default-libmysqlclient-dev"]}),
    (("mongo", "mongodb"), {"service": ["mongodb"]}),
    (("docker", "container"), {"ext": ["ms-azuretools.vscode-docker"]}),
]


def _fallback_plan(description: str) -> RawWorkspaceSpec:
    """Deterministic keyword planner used when no LLM key is configured."""
    text = description.lower()
    template = DEFAULT_TEMPLATE
    apt: list[str] = ["git", "curl", "build-essential"]
    pip: list[str] = []
    npm: list[str] = []
    ext: list[str] = ["eamodio.gitlens", "editorconfig.editorconfig"]
    services: list[str] = []

    for keywords, frag in _KEYWORD_RULES:
        if any(k in text for k in keywords):
            if "template" in frag:
                template = frag["template"]
            apt += frag.get("apt", [])
            pip += frag.get("pip", [])
            npm += frag.get("npm", [])
            ext += frag.get("ext", [])
            services += frag.get("service", [])

    def _dedup(xs: list[str]) -> list[str]:
        return list(dict.fromkeys(xs))

    return RawWorkspaceSpec(
        summary=description.strip()[:200],
        base_template=template,
        apt_packages=_dedup(apt),
        pip_packages=_dedup(pip),
        npm_packages=_dedup(npm),
        vscode_extensions=_dedup(ext),
        services=_dedup(services),
    )


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of an LLM reply (handles ``` fences / prose)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j != -1:
            text = text[i : j + 1]
    return json.loads(text)


def _llm_plan(description: str) -> tuple[RawWorkspaceSpec, str]:
    """Interpret *any* project description via the free LLM backend (Groq / HF /
    Ollama, resolved by :mod:`app.agents.free_agents`). This is the general path:
    the model reads the prompt and proposes a full workspace spec — no per-language
    hard-coding. Raises when no backend is reachable so the caller can fall back.
    Returns (spec, backend_name)."""
    from app.agents.free_agents import resolve_provider

    provider = resolve_provider()
    if provider.name == "stub":
        raise RuntimeError("no free LLM backend configured")
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Project description:\n{description}\n\n"
                "Return ONLY a JSON object with keys: summary, base_template, "
                "apt_packages, pip_packages, npm_packages, vscode_extensions, services."
            ),
        },
    ]
    text = provider.chat(messages, temperature=0.2, max_tokens=1024)
    return RawWorkspaceSpec.model_validate(_extract_json(text)), provider.name


def plan_workspace(description: str) -> tuple[RawWorkspaceSpec, bool, list[str]]:
    """Return (raw spec, llm_used, notes). Never raises — always yields a spec.

    Primary path is the free LLM (Groq) reading the prompt and building the spec;
    Gemini is used only if a working key is set; the keyword planner is a
    last-resort fallback when no LLM backend is reachable."""
    notes: list[str] = []

    # 1) Gemini structured output — only when a key is actually configured.
    if _gemini_available():
        try:
            return _gemini_plan(description), True, notes
        except Exception as exc:  # noqa: BLE001 - fall through to the free LLM
            logger.warning("Gemini planner failed (%s); trying the free LLM backend", exc)

    # 2) Free LLM backend (Groq / HF / Ollama) — general prompt understanding.
    try:
        spec, backend = _llm_plan(description)
        notes.append(f"Planned from your prompt by the {backend} LLM.")
        return spec, True, notes
    except Exception as exc:  # noqa: BLE001 - any error -> deterministic fallback
        logger.warning("Free LLM planner failed (%s); using the keyword planner", exc)
        notes.append("No LLM backend reachable; used the built-in keyword planner.")

    return _fallback_plan(description), False, notes


# --------------------------------------------------------------------------- #
# 2. VALIDATE — drop anything not on the allowlist
# --------------------------------------------------------------------------- #
def validate_spec(raw: RawWorkspaceSpec) -> tuple[WorkspaceSpec, list[al.RejectedItem]]:
    rejected: list[al.RejectedItem] = []

    template = raw.base_template if raw.base_template in al.ALLOWED_BASE_TEMPLATES else DEFAULT_TEMPLATE
    if raw.base_template not in al.ALLOWED_BASE_TEMPLATES:
        rejected.append(al.RejectedItem("base_template", raw.base_template, "unknown template; defaulted to ubuntu"))

    def _filter(items: list[str], kind: str, ok) -> list[str]:
        kept: list[str] = []
        for it in items:
            name = (it or "").strip()
            if not name:
                continue
            if ok(name):
                if name not in kept:
                    kept.append(name)
            else:
                rejected.append(al.RejectedItem(kind, name, "not on the authorized allowlist"))
        return kept

    spec = WorkspaceSpec(
        summary=raw.summary,
        base_template=template,
        apt_packages=_filter(raw.apt_packages, "apt", al.validate_apt),
        pip_packages=_filter(raw.pip_packages, "pip", al.validate_pip),
        npm_packages=_filter(raw.npm_packages, "npm", al.validate_npm),
        vscode_extensions=_filter(raw.vscode_extensions, "vscode_extension", al.validate_extension),
        services=_filter(raw.services, "service", al.validate_service),
    )
    return spec, rejected


# --------------------------------------------------------------------------- #
# 3. RENDER — deterministic provision.sh, every installer pinned to a mirror
# --------------------------------------------------------------------------- #
def render_provision_script(spec: WorkspaceSpec) -> str:
    """Render the bootstrap script. Assumes an already-validated spec.

    Values are still shell-quoted defensively so the script is safe even if this
    is ever called on an unvalidated spec.
    """
    lines: list[str] = [
        "#!/usr/bin/env bash",
        "# Generated by the Hopper Smart Sandbox agent. Do not edit by hand.",
        "# Every installer below is pinned to a platform-authorized mirror.",
        "set -euo pipefail",
        "export DEBIAN_FRONTEND=noninteractive",
        f"echo '>>> Provisioning workspace: {spec.summary[:120].replace(chr(39), '')}'",
        "",
    ]

    # Collect apt packages (explicit + those required by services).
    apt_pkgs = list(spec.apt_packages)
    service_starts: list[str] = []
    for svc in spec.services:
        entry = al.SERVICE_CATALOG[svc]
        apt_pkgs += entry["apt"]
        service_starts.append(entry["start"])
    apt_pkgs = list(dict.fromkeys(apt_pkgs))  # de-dup, keep order

    if al.AUTHORIZED_APT_MIRROR:
        lines.append("# Pin apt to the authorized mirror")
        lines.append(
            "sed -i "
            + shlex.quote(f"s|http://archive.ubuntu.com/ubuntu|{al.AUTHORIZED_APT_MIRROR}|g")
            + " /etc/apt/sources.list || true"
        )
    if apt_pkgs:
        lines.append("apt-get update")
        lines.append("apt-get install -y --no-install-recommends " + " ".join(shlex.quote(p) for p in apt_pkgs))
        lines.append("")

    if spec.pip_packages:
        lines.append("# Python packages (pinned index)")
        lines.append(
            "python3 -m pip install --no-cache-dir --index-url "
            + shlex.quote(al.AUTHORIZED_PIP_INDEX)
            + " "
            + " ".join(shlex.quote(p) for p in spec.pip_packages)
        )
        lines.append("")

    if spec.npm_packages:
        lines.append("# Node packages (pinned registry, installed globally)")
        lines.append(
            "npm install -g --registry "
            + shlex.quote(al.AUTHORIZED_NPM_REGISTRY)
            + " "
            + " ".join(shlex.quote(p) for p in spec.npm_packages)
        )
        lines.append("")

    if spec.vscode_extensions:
        lines.append("# VS Code (code-server) extensions — official IDs only")
        for ext in spec.vscode_extensions:
            lines.append(
                "code-server --install-extension " + shlex.quote(ext) + " || true"
            )
        lines.append("")

    if service_starts:
        lines.append("# Start requested background services")
        for cmd in service_starts:
            lines.append(cmd + " || true")
        lines.append("")

    lines.append("echo '>>> Provisioning complete.'")
    lines.append("")
    return "\n".join(lines)


def build_pod_env(pod_id: str) -> dict[str, str]:
    """The HOPPER_* values the orchestrator injects into the pod so the in-VM
    provisioner can fetch its script. Passed via the CreatePod ``labels`` map;
    the orchestrator promotes HOPPER_-prefixed keys to env vars."""
    return {
        "HOPPER_POD_ID": pod_id,
        "HOPPER_API_URL": settings.sandbox_internal_api_url,
        "HOPPER_POD_TOKEN": make_provision_token(pod_id),
        "HOPPER_PROVISION": "1",
    }
