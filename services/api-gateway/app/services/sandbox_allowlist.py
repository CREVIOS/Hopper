"""Authorized-source allowlist for the Smart Sandbox provisioner.

This module is the guardrail that protects cluster integrity. The sandbox
agent turns a natural-language project description into a *proposed* workspace
spec, but nothing that proposal contains is trusted: every package, extension,
and service is validated against the tables here before it is allowed into a
generated ``provision.sh``. Anything not on an allowlist is dropped and
reported back to the user, never silently installed.

Two independent controls:

1. **Authorized mirrors** — every installer in the generated script is pinned
   to a mirror we control (``AUTHORIZED_PIP_INDEX`` / ``AUTHORIZED_NPM_REGISTRY``
   / ``AUTHORIZED_APT_MIRROR``). A student VM can therefore only pull bytes from
   infrastructure the platform trusts, even for an allowlisted package name.
2. **Name allowlists** — apt packages, pip/npm package *names*, VS Code
   extensions, and background services are each checked against a curated set
   (or, for language ecosystems, a strict name grammar). This blocks
   command-injection-via-package-name (``foo; rm -rf /``), VCS/URL installs
   (``pip install git+http://evil``), and unofficial extensions.

All values are overridable via ``HOPPER_*`` env so an operator can point at an
internal Artifactory/Verdaccio without a code change.
"""
from __future__ import annotations

import re

from app.config import settings

# --------------------------------------------------------------------------- #
# Authorized mirrors (pinned into every generated installer command)
# --------------------------------------------------------------------------- #
AUTHORIZED_PIP_INDEX = settings.sandbox_pip_index_url
AUTHORIZED_NPM_REGISTRY = settings.sandbox_npm_registry
AUTHORIZED_APT_MIRROR = settings.sandbox_apt_mirror  # empty = image default

# --------------------------------------------------------------------------- #
# Base templates — must map 1:1 to VM_TEMPLATE_IMAGES (schemas/pod.py)
# --------------------------------------------------------------------------- #
ALLOWED_BASE_TEMPLATES = {"ubuntu", "python-ml", "cpp", "java"}

# --------------------------------------------------------------------------- #
# apt: an explicit allowlist. apt runs as root inside the VM, so we do NOT
# accept arbitrary names — only vetted dev tooling and language runtimes.
# --------------------------------------------------------------------------- #
APT_ALLOWLIST: frozenset[str] = frozenset({
    # languages / runtimes
    "python3", "python3-pip", "python3-venv", "python3-dev",
    "nodejs", "npm", "golang", "openjdk-17-jdk", "openjdk-21-jdk",
    "ruby", "ruby-dev", "php", "php-cli", "rustc", "cargo",
    # .NET / C# (Ubuntu 22.04 ships these in the archive)
    "dotnet-sdk-8.0", "dotnet-sdk-7.0", "dotnet-sdk-6.0", "dotnet6",
    "aspnetcore-runtime-8.0", "dotnet-runtime-8.0", "mono-complete",
    # build tooling
    "build-essential", "g++", "gcc", "make", "cmake", "pkg-config",
    "clang", "gdb", "valgrind", "ninja-build", "autoconf", "libtool",
    # vcs / net / editors
    "git", "git-lfs", "curl", "wget", "vim", "nano", "jq", "unzip", "zip",
    "ca-certificates", "tmux", "htop", "tree", "ripgrep",
    # common client libs / headers
    "libpq-dev", "libssl-dev", "libffi-dev", "zlib1g-dev", "libsqlite3-dev",
    "sqlite3", "redis-tools", "postgresql-client", "default-libmysqlclient-dev",
})

# --------------------------------------------------------------------------- #
# Background services the agent may request. Each maps to the apt package(s)
# that provide it plus the command that launches it under supervisord-less
# provisioning (started with `service <name> start` where possible, else a
# raw daemon command). Keeping this a closed set means "add a Postgres" is a
# vetted, reproducible action — not an arbitrary root command.
# --------------------------------------------------------------------------- #
SERVICE_CATALOG: dict[str, dict] = {
    "postgresql": {
        "apt": ["postgresql", "postgresql-contrib"],
        "start": "service postgresql start",
        "note": "Postgres 14 on :5432 (default 'postgres' superuser, trust auth on localhost).",
    },
    "redis": {
        "apt": ["redis-server"],
        "start": "service redis-server start",
        "note": "Redis on :6379.",
    },
    "mysql": {
        "apt": ["mariadb-server"],
        "start": "service mariadb start",
        "note": "MariaDB (MySQL-compatible) on :3306.",
    },
    "mongodb": {
        # mongodb is not in Ubuntu main; we only enable it when the operator
        # has added it to the authorized apt mirror. Guarded by name here.
        "apt": ["mongodb"],
        "start": "service mongodb start",
        "note": "MongoDB on :27017 (requires it to be present in the apt mirror).",
    },
}
ALLOWED_SERVICES = frozenset(SERVICE_CATALOG)

# --------------------------------------------------------------------------- #
# VS Code / code-server extensions — official publishers only. code-server
# installs from the Open VSX registry; we still restrict to a vetted set so a
# spec cannot pull an arbitrary (potentially malicious) extension.
# --------------------------------------------------------------------------- #
EXTENSION_ALLOWLIST: frozenset[str] = frozenset({
    # python
    "ms-python.python", "ms-python.debugpy", "ms-python.black-formatter",
    "ms-python.flake8", "ms-toolsai.jupyter", "charliermarsh.ruff",
    # web / js / ts
    "dbaeumer.vscode-eslint", "esbenp.prettier-vscode",
    "bradlc.vscode-tailwindcss", "svelte.svelte-vscode",
    "vue.volar", "dsznajder.es7-react-js-snippets",
    # backend langs
    "golang.go", "rust-lang.rust-analyzer", "redhat.java",
    "vscjava.vscode-java-debug", "ms-vscode.cpptools", "llvm-vscode.vscode-clangd",
    "ms-dotnettools.csharp", "rebornix.ruby",
    # data / infra / misc
    "ms-azuretools.vscode-docker", "redhat.vscode-yaml",
    "editorconfig.editorconfig", "eamodio.gitlens",
    "mtxr.sqltools", "mtxr.sqltools-driver-pg",
})

# pip/npm package *name* grammars (PEP 503 / npm). We validate the shape and
# reject anything carrying a URL, VCS ref, extras with markers, shell meta, or
# a version specifier smuggled into the name — versions are handled separately.
_PIP_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,100})$")
_PIP_PINNED_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,100})(?:==[A-Za-z0-9][A-Za-z0-9.\-_+]{0,40})?$"
)
_NPM_NAME_RE = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._-]{0,60}/)?[a-z0-9][a-z0-9._-]{0,120}(?:@[a-zA-Z0-9][a-zA-Z0-9.\-_^~*]{0,40})?$"
)


class RejectedItem:
    """A single dropped item plus why — surfaced to the user for transparency."""

    __slots__ = ("kind", "value", "reason")

    def __init__(self, kind: str, value: str, reason: str):
        self.kind = kind
        self.value = value
        self.reason = reason

    def as_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "reason": self.reason}


def validate_apt(name: str) -> bool:
    return name in APT_ALLOWLIST


def validate_pip(name: str) -> bool:
    """Accept ``pkg`` or ``pkg==1.2.3`` only. No URLs, VCS, extras, or markers."""
    return bool(_PIP_PINNED_RE.match(name))


def validate_npm(name: str) -> bool:
    """Accept ``pkg``, ``@scope/pkg``, optionally ``@version``. No URLs/tarballs."""
    return bool(_NPM_NAME_RE.match(name))


def validate_extension(ext_id: str) -> bool:
    return ext_id in EXTENSION_ALLOWLIST


def validate_service(name: str) -> bool:
    return name in ALLOWED_SERVICES
