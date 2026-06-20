"""Resolve VM pod IPs via the in-cluster Kubernetes API.

NetworkPolicy ``api-gateway-egress-to-user-vms`` allows TCP 22/8080 only to
pod endpoints with ``role=user-vm``. Traffic to a Service ClusterIP (10.43.x)
does not match that rule, so the integrated terminal must dial the pod IP
directly—not ``ssh-<pod>.svc.cluster.local``.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_SA_TOKEN = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
_SA_CA = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")

_pod_ip_cache: dict[tuple[str, str], tuple[float, str]] = {}
_CACHE_TTL_S = 20.0


def in_kubernetes_pod() -> bool:
    """True when running as a pod with a projected service-account token."""
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST")) and _SA_TOKEN.is_file()


async def get_pod_ip(namespace: str, pod_name: str) -> str | None:
    """Return ``status.podIP`` for a namespaced pod, or None on failure."""
    if not in_kubernetes_pod():
        return None
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    if not host or not _SA_CA.is_file():
        return None
    url = f"https://{host}:{port}/api/v1/namespaces/{namespace}/pods/{pod_name}"
    try:
        token = _SA_TOKEN.read_text().strip()
    except OSError:
        return None
    try:
        async with httpx.AsyncClient(verify=str(_SA_CA), timeout=5.0) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        logger.warning("k8s get pod %s/%s failed: %s", namespace, pod_name, e)
        return None
    if r.status_code != 200:
        logger.warning(
            "k8s get pod %s/%s: HTTP %s %s",
            namespace,
            pod_name,
            r.status_code,
            (r.text or "")[:200],
        )
        return None
    ip = (r.json().get("status") or {}).get("podIP")
    return ip if isinstance(ip, str) and ip else None


async def get_pod_ip_cached(namespace: str, pod_name: str) -> str | None:
    key = (namespace, pod_name)
    now = time.monotonic()
    hit = _pod_ip_cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return hit[1]
    ip = await get_pod_ip(namespace, pod_name)
    if ip:
        _pod_ip_cache[key] = (now, ip)
    return ip


async def resolve_vm_ssh_socket(namespace: str | None, pod_name: str | None, ssh_port: int) -> tuple[str, int]:
    """(host, port) for SSH: pod IP :22 in-cluster, else node IP + NodePort."""
    if in_kubernetes_pod() and pod_name:
        ns = namespace or "hopper"
        ip = await get_pod_ip_cached(ns, pod_name)
        if ip:
            return ip, 22
        logger.warning(
            "Pod IP lookup failed for %s/%s — falling back to NodePort (may be blocked by policy)",
            ns,
            pod_name,
        )
    return settings.node_ip, int(ssh_port)


async def resolve_vm_vscode_http_base(
    namespace: str | None, pod_name: str | None, vscode_nodeport: int | None
) -> str | None:
    """Base URL for code-server HTTP proxy (pod IP in-cluster)."""
    if in_kubernetes_pod() and pod_name:
        ns = namespace or "hopper"
        ip = await get_pod_ip_cached(ns, pod_name)
        if ip:
            return f"http://{ip}:8080"
    if vscode_nodeport:
        return f"http://{settings.node_ip}:{vscode_nodeport}"
    return None
