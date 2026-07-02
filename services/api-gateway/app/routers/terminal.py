"""WebSocket terminal — proxies browser to K8s pod exec via a PTY.

Uses Python's pty.spawn via a thread to create a real pseudo-terminal,
which gives bash proper interactive behavior (prompts, arrow keys, tab completion).
"""

import asyncio
import fcntl
import logging
import os
import pty
import signal
import struct
import subprocess
import termios

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select as sa_select

from app.core.database import async_session
from app.middleware.auth import verify_token
from app.models.session import PodSession

logger = logging.getLogger(__name__)
router = APIRouter()


def _set_winsize(fd: int, rows: int, cols: int):
    """Set terminal window size on a file descriptor."""
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


@router.websocket("/ws/{pod_id}")
async def terminal_ws(websocket: WebSocket, pod_id: str):
    """WebSocket terminal with full PTY support."""
    token = websocket.cookies.get("session_token")
    if not token:
        await websocket.close(code=1008, reason="Not authenticated")
        return

    user = await verify_token(token)
    if not user:
        await websocket.close(code=1008, reason="Invalid token")
        return

    async with async_session() as db:
        result = await db.execute(sa_select(PodSession).where(PodSession.id == pod_id))
        session = result.scalar_one_or_none()

    if not session or session.user_id != user.sub or session.state != "running":
        await websocket.close(code=1008, reason="Pod not available")
        return

    await websocket.accept()

    # Find the actual K8s pod name
    namespace = session.namespace or "hopper"
    find_proc = await asyncio.create_subprocess_exec(
        "kubectl", "get", "pods", "-n", namespace,
        "-l", f"hopper.dev/user-id={session.user_id}",
        "-l", "app=hopper-vm",
        "--field-selector=status.phase=Running",
        "-o", "jsonpath={.items[0].metadata.name}",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await find_proc.communicate()
    k8s_pod_name = stdout.decode().strip()

    if not k8s_pod_name:
        await websocket.send_text("\r\nNo running pod found\r\n")
        await websocket.close()
        return

    # Open PTY pair
    master_fd, slave_fd = pty.openpty()
    _set_winsize(slave_fd, 24, 80)

    # Start kubectl exec with the slave side as its terminal
    proc = subprocess.Popen(
        ["kubectl", "exec", "-it", k8s_pod_name, "-n", namespace, "-c", "vm", "--", "/bin/bash"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=os.setsid,
    )
    os.close(slave_fd)  # Parent doesn't need the slave side

    # Make master non-blocking
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    closed = asyncio.Event()

    async def pty_to_ws():
        """Read from PTY master → send to WebSocket."""
        try:
            while not closed.is_set():
                await asyncio.sleep(0.02)
                try:
                    data = os.read(master_fd, 8192)
                    if not data:
                        break
                    await websocket.send_text(data.decode(errors="replace"))
                except BlockingIOError:
                    continue
                except OSError:
                    break
        except Exception:
            pass
        finally:
            closed.set()

    async def ws_to_pty():
        """Read from WebSocket → write to PTY master."""
        import json as _json
        try:
            while not closed.is_set():
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                text = msg.get("text", "")
                if not text:
                    continue
                # Handle resize
                if text.startswith("{"):
                    try:
                        parsed = _json.loads(text)
                        if parsed.get("type") == "resize":
                            _set_winsize(master_fd, parsed.get("rows", 24), parsed.get("cols", 80))
                            # Signal the process group about the resize
                            os.kill(-proc.pid, signal.SIGWINCH)
                            continue
                    except (_json.JSONDecodeError, KeyError, ProcessLookupError):
                        pass
                os.write(master_fd, text.encode())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            closed.set()

    try:
        await asyncio.gather(pty_to_ws(), ws_to_pty())
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        try:
            await websocket.close()
        except Exception:
            pass
