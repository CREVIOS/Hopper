"""Manages kubectl port-forward processes for VS Code access.

Spawns a kubectl port-forward per pod targeting port 8080 (code-server)
and tracks the assigned local port so the proxy can reach it via localhost.
"""

import asyncio
import logging
import socket

logger = logging.getLogger(__name__)

# pod_name -> (local_port, process)
_forwards: dict[str, tuple[int, asyncio.subprocess.Process]] = {}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def start(pod_name: str, namespace: str) -> int:
    """Start kubectl port-forward for the pod and return the local port."""
    if pod_name in _forwards:
        local_port, proc = _forwards[pod_name]
        if proc.returncode is None:
            return local_port
        del _forwards[pod_name]

    local_port = _free_port()

    proc = await asyncio.create_subprocess_exec(
        "kubectl", "port-forward",
        "-n", namespace,
        f"pod/{pod_name}",
        f"{local_port}:8080",
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
        raise RuntimeError(f"port-forward for {pod_name} never became ready")

    _forwards[pod_name] = (local_port, proc)
    logger.info("port-forward %s:8080 -> 127.0.0.1:%d", pod_name, local_port)
    return local_port


async def stop(pod_name: str):
    if pod_name not in _forwards:
        return
    _, proc = _forwards.pop(pod_name)
    try:
        proc.terminate()
        await proc.wait()
    except Exception:
        pass


def get_local_port(pod_name: str) -> int | None:
    entry = _forwards.get(pod_name)
    if entry and entry[1].returncode is None:
        return entry[0]
    return None
