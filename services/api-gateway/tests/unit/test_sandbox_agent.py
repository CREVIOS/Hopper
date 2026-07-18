"""Unit tests for the Smart Sandbox agent (planner + allowlist + renderer).

These exercise the pure, offline path — the deterministic keyword planner, the
allowlist guardrail, and the provision.sh renderer — with no LLM key, DB, or
cluster required.
"""
from app.schemas.sandbox import RawWorkspaceSpec
from app.services import sandbox_agent as agent
from app.services import sandbox_allowlist as al


def test_fallback_plan_fullstack():
    """'React + FastAPI + Postgres' -> node + python toolchains + a Postgres service."""
    raw, llm_used, _notes = agent.plan_workspace(
        "React frontend with a FastAPI backend and a Postgres database"
    )
    assert llm_used is False  # no GEMINI_API_KEY in the test env
    spec, rejected = agent.validate_spec(raw)

    assert "nodejs" in spec.apt_packages
    assert "python3" in spec.apt_packages
    assert "fastapi" in spec.pip_packages
    assert "react" in spec.npm_packages
    assert "postgresql" in spec.services
    assert rejected == []  # the fallback only emits allowlisted items


def test_fallback_plan_picks_ml_template():
    raw, _u, _n = agent.plan_workspace("PyTorch deep learning course for students")
    spec, _rej = agent.validate_spec(raw)
    assert spec.base_template == "python-ml"
    assert "torch" in spec.pip_packages


def test_allowlist_rejects_malicious_items():
    """The guardrail drops command-injection, VCS/URL installs, and unofficial extensions."""
    raw = RawWorkspaceSpec(
        base_template="ubuntu",
        apt_packages=["git", "foo; rm -rf /", "curl && wget evil"],
        pip_packages=["requests", "git+http://evil/repo", "torch==2.1.0"],
        npm_packages=["express", "http://evil.tgz"],
        vscode_extensions=["ms-python.python", "evilpublisher.malware"],
        services=["postgresql", "cryptominer"],
    )
    spec, rejected = agent.validate_spec(raw)

    assert spec.apt_packages == ["git"]
    assert spec.pip_packages == ["requests", "torch==2.1.0"]  # pinned version ok
    assert spec.npm_packages == ["express"]
    assert spec.vscode_extensions == ["ms-python.python"]
    assert spec.services == ["postgresql"]

    rejected_values = {r.value for r in rejected}
    assert "foo; rm -rf /" in rejected_values
    assert "git+http://evil/repo" in rejected_values
    assert "evilpublisher.malware" in rejected_values
    assert "cryptominer" in rejected_values


def test_unknown_base_template_defaults_to_ubuntu():
    raw = RawWorkspaceSpec(base_template="gentoo-hardened")
    spec, rejected = agent.validate_spec(raw)
    assert spec.base_template == "ubuntu"
    assert any(r.kind == "base_template" for r in rejected)


def test_render_pins_every_installer_to_authorized_mirror():
    raw, _u, _n = agent.plan_workspace(
        "FastAPI backend with a React frontend and Postgres and Redis"
    )
    spec, _rej = agent.validate_spec(raw)
    script = agent.render_provision_script(spec)

    assert script.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in script
    # pip and npm installers must be pinned to the authorized mirrors.
    if spec.pip_packages:
        assert f"--index-url {al.AUTHORIZED_PIP_INDEX}" in script or \
               al.AUTHORIZED_PIP_INDEX in script
    if spec.npm_packages:
        assert al.AUTHORIZED_NPM_REGISTRY in script
    # services pull in their vetted start command
    assert "service postgresql start" in script
    assert "service redis-server start" in script
    # extensions installed via code-server, never a raw curl
    for ext in spec.vscode_extensions:
        assert f"code-server --install-extension {ext}" in script


def test_pod_token_roundtrip():
    tok = agent.make_provision_token("abc-123")
    assert agent.verify_provision_token("abc-123", tok) is True
    assert agent.verify_provision_token("abc-123", "wrong") is False
    assert agent.verify_provision_token("other", tok) is False
