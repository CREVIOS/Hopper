"""Manages kubectl port-forward processes for pod-internal services.

Used for code-server (port 8080) and the in-browser terminal (port 22 / sshd).
NodePort isn't reachable from the api-gateway process in the minikube docker
driver and most kind setups, so we forward into the pod by name instead.

Each (pod, target_port) gets its own forward keyed independently so callers
can request multiple ports for the same pod without trampling each other.
"""

import asyncio
import logging
import socket

logger = logging.getLogger(__name__)

# (pod_name, target_port) -> (local_port, process)
_forwards: dict[tuple[str, int], tuple[int, asyncio.subprocess.Process]] = {}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def start(pod_name: str, namespace: str, target_port: int = 8080) -> int:
    """Start kubectl port-forward for the pod and return the local port."""
    key = (pod_name, target_port)
    if key in _forwards:
        local_port, proc = _forwards[key]
        if proc.returncode is None:
            return local_port
        del _forwards[key]

    local_port = _free_port()

    proc = await asyncio.create_subprocess_exec(
        "kubectl", "port-forward",
        "-n", namespace,
        f"pod/{pod_name}",
        f"{local_port}:{target_port}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Wait up to 15s for the port to become reachable
    for _ in range(15):
        await asyncio.sleep(1)
        if proc.returncode is not None:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=2)
            raise RuntimeError(f"port-forward exited: {stderr.decode().strip()}")
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", local_port)) == 0:
                break
    else:
        proc.terminate()
        raise RuntimeError(f"port-forward for {pod_name}:{target_port} never became ready")

    _forwards[key] = (local_port, proc)
    logger.info("port-forward %s:%d -> 127.0.0.1:%d", pod_name, target_port, local_port)
    return local_port


async def stop(pod_name: str, target_port: int | None = None):
    """Stop a port-forward. If target_port is None, stop every forward for the pod."""
    keys = (
        [(pod_name, target_port)] if target_port is not None
        else [k for k in _forwards if k[0] == pod_name]
    )
    for key in keys:
        if key not in _forwards:
            continue
        _, proc = _forwards.pop(key)
        try:
            proc.terminate()
            await proc.wait()
        except Exception:
            pass


def get_local_port(pod_name: str, target_port: int = 8080) -> int | None:
    entry = _forwards.get((pod_name, target_port))
    if entry and entry[1].returncode is None:
        return entry[0]
    return None
