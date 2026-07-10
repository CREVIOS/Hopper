"""File upload/download for VM pods.

Uses SSH/SCP through a kubectl port-forward to the pod's sshd:22. We don't
go through the K8s NodePort because that path isn't reachable from inside
the api-gateway pod under the minikube docker driver and most kind setups
— the same reason the in-browser terminal port-forwards too.

Upload: multipart form → SCP into pod.
Download: SCP from pod → stream response.
List: SSH `ls -lA --time-style=long-iso` parsed into structured entries.
"""

import asyncio
import logging
import os
import re
import shlex
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.session import PodSession
from app.schemas.user import TokenPayload
from app.services import port_forward

logger = logging.getLogger(__name__)
router = APIRouter()


class MkdirRequest(BaseModel):
    path: str


class RenameRequest(BaseModel):
    path: str
    new_path: str


class DeleteRequest(BaseModel):
    path: str


def _safe_path(path: str) -> str:
    """Reject paths that try to escape via shell injection or null bytes."""
    if not path or "\x00" in path or "\n" in path:
        raise HTTPException(status_code=400, detail="invalid path")
    return path


def _reject_root_delete(path: str) -> None:
    """Refuse to recursively delete the filesystem root.

    The student already has root SSH into their own VM, so this is not a
    privilege boundary — it's a guard against a UI action accidentally wiping
    the whole VM (e.g. an empty/"/" path). normpath collapses ``..`` and
    trailing slashes so "/home/.." and "//" are caught too.
    """
    if os.path.normpath(path) in ("/", "//"):
        raise HTTPException(status_code=400, detail="refusing to delete the filesystem root")


async def _get_user_pod(pod_id: str, user: TokenPayload, db: AsyncSession) -> PodSession:
    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Pod not found")
    if session.user_id != user.sub:
        raise HTTPException(status_code=403, detail="Not your pod")
    if session.state != "running" or not session.pod_name:
        raise HTTPException(status_code=400, detail="Pod not running")
    return session


async def _ssh_endpoint(session: PodSession) -> tuple[str, int]:
    """Resolve (host, port) for a working SSH path into this pod.

    Prefers a kubectl port-forward to pod:22 (works in every cluster setup).
    Falls back to the recorded NodePort only when port-forward fails — that
    path only works on bare-metal clusters where the api-gateway can reach
    node IPs directly.
    """
    port = port_forward.get_local_port(session.pod_name, 22)
    if not port:
        try:
            port = await port_forward.start(session.pod_name, session.namespace, 22)
        except Exception as pf_err:
            logger.warning(
                "ssh port-forward unavailable for %s: %s — trying NodePort",
                session.pod_name, pf_err,
            )
            if not session.ssh_port:
                raise HTTPException(
                    status_code=503,
                    detail="VM SSH is not reachable from the gateway",
                )
            from app.config import settings as cfg
            return (cfg.node_ip, session.ssh_port)
    return ("127.0.0.1", port)


@router.get("/{pod_id}/list")
async def list_directory(
    pod_id: str,
    path: str = "/home",
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List a directory inside the VM so the UI can render a browser.

    Returned entries: {name, is_dir, size, mtime}. Sorted: dirs first then
    files, both case-insensitive alpha. The path is quoted before being
    inlined into the remote command — never substituted raw — so a filename
    with spaces or quotes can't break out of the ls argument.
    """
    path = _safe_path(path)
    session = await _get_user_pod(pod_id, current_user, db)
    host, port = await _ssh_endpoint(session)

    # `ls -lA --time-style=long-iso` is portable across busybox/coreutils
    # (the hopper-vm image uses coreutils, so we always get the long form).
    remote_cmd = f"ls -lA --time-style=long-iso -- {shlex.quote(path)}"
    proc = await asyncio.create_subprocess_exec(
        "sshpass", "-p", session.ssh_password or "hopper",
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=5",
        "-p", str(port),
        f"root@{host}", remote_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        msg = stderr.decode(errors="replace").strip() or "ls failed"
        # Map common cases to user-friendly errors instead of leaking ssh chatter.
        if "No such file" in msg:
            raise HTTPException(status_code=404, detail=f"Path not found: {path}")
        if "Permission denied" in msg:
            raise HTTPException(status_code=403, detail=f"Permission denied: {path}")
        raise HTTPException(status_code=500, detail=msg)

    entries = []
    # Format: "drwxr-xr-x  2 root root 4096 2024-05-10 12:34 name"
    line_re = re.compile(
        r"^(?P<perm>[\w\-]{10})\s+\d+\s+\S+\s+\S+\s+(?P<size>\d+)\s+"
        r"(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2})\s+(?P<name>.+)$"
    )
    for line in stdout.decode(errors="replace").splitlines():
        if line.startswith("total "):
            continue
        m = line_re.match(line)
        if not m:
            continue
        name = m.group("name")
        # ls -l renders symlinks as "name -> target"; keep just the link name.
        if " -> " in name and m.group("perm").startswith("l"):
            name = name.split(" -> ", 1)[0]
        entries.append({
            "name": name,
            "is_dir": m.group("perm").startswith("d"),
            "size": int(m.group("size")),
            "mtime": f"{m.group('date')}T{m.group('time')}:00",
        })

    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return {"path": path, "entries": entries}


@router.post("/{pod_id}/upload")
async def upload_file(
    pod_id: str,
    dest_path: str = "/home",
    file: UploadFile = File(...),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file to the VM via SCP."""
    session = await _get_user_pod(pod_id, current_user, db)
    host, port = await _ssh_endpoint(session)

    with tempfile.NamedTemporaryFile(delete=True, suffix=f"_{file.filename}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp.flush()

        remote_path = f"{dest_path}/{file.filename}"
        proc = await asyncio.create_subprocess_exec(
            "sshpass", "-p", session.ssh_password or "hopper",
            "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-P", str(port),
            tmp.name, f"root@{host}:{remote_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

    if proc.returncode != 0:
        msg = stderr.decode(errors="replace").strip() or "scp failed"
        if "No such file" in msg or "not a directory" in msg.lower():
            raise HTTPException(status_code=404, detail=f"Destination not found: {dest_path}")
        if "Permission denied" in msg:
            raise HTTPException(status_code=403, detail=f"Permission denied: {dest_path}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {msg}")

    return {"message": "uploaded", "path": remote_path, "size": len(content)}


@router.get("/{pod_id}/download")
async def download_file(
    pod_id: str,
    path: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a file from the VM via SCP."""
    path = _safe_path(path)
    session = await _get_user_pod(pod_id, current_user, db)
    host, port = await _ssh_endpoint(session)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    proc = await asyncio.create_subprocess_exec(
        "sshpass", "-p", session.ssh_password or "hopper",
        "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-P", str(port),
        f"root@{host}:{path}", tmp_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        # Match the list endpoint's error mapping so callers get consistent
        # 404 / 403 instead of a generic 500 they can't act on.
        msg = stderr.decode(errors="replace").strip() or "scp failed"
        if "No such file" in msg or "not a regular file" in msg:
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        if "Permission denied" in msg:
            raise HTTPException(status_code=403, detail=f"Permission denied: {path}")
        raise HTTPException(status_code=500, detail=f"Download failed: {msg}")

    import os
    filename = os.path.basename(path)

    async def stream():
        with open(tmp_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk
        os.unlink(tmp_path)

    return StreamingResponse(stream(), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


async def _ssh_exec(session: PodSession, remote_cmd: str) -> tuple[int, bytes, bytes]:
    """Run a single remote command over SSH; return (returncode, stdout, stderr).

    Shared by mkdir/rename/delete. The caller is responsible for building
    ``remote_cmd`` with ``shlex.quote`` around every user-supplied path.
    """
    host, port = await _ssh_endpoint(session)
    proc = await asyncio.create_subprocess_exec(
        "sshpass", "-p", session.ssh_password or "hopper",
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=5",
        "-p", str(port),
        f"root@{host}", remote_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout, stderr


def _raise_ssh_error(returncode: int, stderr: bytes, path: str, *, exists_conflict: bool = False) -> None:
    """Map a failed remote command to a user-friendly HTTP error.

    Mirrors the list/upload/download error mapping so callers get consistent
    404/403/409 instead of a generic 500 with raw ssh chatter.
    """
    if returncode == 0:
        return
    msg = stderr.decode(errors="replace").strip() or "command failed"
    if "No such file" in msg:
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if "Permission denied" in msg:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")
    if exists_conflict and "File exists" in msg:
        raise HTTPException(status_code=409, detail=f"Already exists: {path}")
    raise HTTPException(status_code=500, detail=msg)


@router.post("/{pod_id}/mkdir")
async def make_directory(
    pod_id: str,
    body: MkdirRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a directory inside the VM. Parent must exist; existing → 409."""
    path = _safe_path(body.path)
    session = await _get_user_pod(pod_id, current_user, db)
    rc, _, stderr = await _ssh_exec(session, f"mkdir -- {shlex.quote(path)}")
    _raise_ssh_error(rc, stderr, path, exists_conflict=True)
    return {"message": "created", "path": path}


@router.post("/{pod_id}/rename")
async def rename_entry(
    pod_id: str,
    body: RenameRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename or move a file/directory inside the VM (mv semantics)."""
    src = _safe_path(body.path)
    dst = _safe_path(body.new_path)
    session = await _get_user_pod(pod_id, current_user, db)
    rc, _, stderr = await _ssh_exec(session, f"mv -- {shlex.quote(src)} {shlex.quote(dst)}")
    _raise_ssh_error(rc, stderr, src)
    return {"message": "renamed", "path": src, "new_path": dst}


@router.post("/{pod_id}/delete")
async def delete_entry(
    pod_id: str,
    body: DeleteRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a file or directory (recursively) inside the VM."""
    path = _safe_path(body.path)
    _reject_root_delete(path)
    session = await _get_user_pod(pod_id, current_user, db)
    rc, _, stderr = await _ssh_exec(session, f"rm -r -- {shlex.quote(path)}")
    _raise_ssh_error(rc, stderr, path)
    return {"message": "deleted", "path": path}
