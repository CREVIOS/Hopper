import hashlib
import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.ssh_key import SSHKey
from app.schemas.user import TokenPayload

router = APIRouter()


class AddKeyRequest(BaseModel):
    name: str
    public_key: str


def _compute_fingerprint(public_key: str) -> str:
    """Compute SHA256 fingerprint of an SSH public key."""
    parts = public_key.strip().split()
    if len(parts) < 2:
        raise ValueError("Invalid SSH public key format")
    key_data = base64.b64decode(parts[1])
    digest = hashlib.sha256(key_data).digest()
    return "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode()


@router.get("/")
async def list_keys(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's SSH public keys."""
    result = await db.execute(
        select(SSHKey)
        .where(SSHKey.user_id == current_user.sub)
        .order_by(SSHKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "fingerprint": k.fingerprint,
            "public_key": k.public_key[:50] + "...",
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_key(
    request: AddKeyRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an SSH public key."""
    # Validate key format
    pk = request.public_key.strip()
    valid_prefixes = ("ssh-rsa", "ssh-ed25519", "ecdsa-sha2", "ssh-dss")
    if not any(pk.startswith(p) for p in valid_prefixes):
        raise HTTPException(status_code=400, detail="Invalid SSH public key format")

    try:
        fingerprint = _compute_fingerprint(pk)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse SSH public key")

    # Limit to 10 keys per user
    count = await db.scalar(
        select(func.count()).select_from(SSHKey).where(SSHKey.user_id == current_user.sub)
    )
    if (count or 0) >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 SSH keys allowed")

    key = SSHKey(
        id=str(uuid.uuid4()),
        user_id=current_user.sub,
        name=request.name,
        public_key=pk,
        fingerprint=fingerprint,
    )
    db.add(key)
    await db.commit()
    return {"id": key.id, "fingerprint": fingerprint}


@router.delete("/{key_id}")
async def delete_key(
    key_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an SSH key."""
    result = await db.execute(
        select(SSHKey).where(SSHKey.id == key_id, SSHKey.user_id == current_user.sub)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="SSH key not found")
    await db.delete(key)
    await db.commit()
    return {"message": "deleted"}
