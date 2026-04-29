"""File upload/download for VM pods.

Uses SSH/SCP via the pod's NodePort to transfer files.
Upload: multipart form → SCP into pod.
Download: SCP from pod → stream response.
"""

import asyncio
import logging
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.session import PodSession
from app.schemas.user import TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_user_pod(pod_id: str, user: TokenPayload, db: AsyncSession) -> PodSession:
    result = await db.execute(select(PodSession).where(PodSession.id == pod_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Pod not found")
    if session.user_id != user.sub:
        raise HTTPException(status_code=403, detail="Not your pod")
    if session.state != "running" or not session.ssh_port:
        raise HTTPException(status_code=400, detail="Pod not running")
    return session


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

    with tempfile.NamedTemporaryFile(delete=True, suffix=f"_{file.filename}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp.flush()

        remote_path = f"{dest_path}/{file.filename}"
        proc = await asyncio.create_subprocess_exec(
            "sshpass", "-p", session.ssh_password or "hopper",
            "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-P", str(session.ssh_port),
            tmp.name, f"root@localhost:{remote_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Upload failed: {stderr.decode()}")

    return {"message": "uploaded", "path": remote_path, "size": len(content)}


@router.get("/{pod_id}/download")
async def download_file(
    pod_id: str,
    path: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a file from the VM via SCP."""
    session = await _get_user_pod(pod_id, current_user, db)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    proc = await asyncio.create_subprocess_exec(
        "sshpass", "-p", session.ssh_password or "hopper",
        "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-P", str(session.ssh_port),
        f"root@localhost:{path}", tmp_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Download failed: {stderr.decode()}")

    import os
    filename = os.path.basename(path)

    async def stream():
        with open(tmp_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk
        os.unlink(tmp_path)

    return StreamingResponse(stream(), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})
