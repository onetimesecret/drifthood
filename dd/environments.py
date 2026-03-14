"""Environment CRUD routes. Environments are server-synced, encrypted client-side."""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from .auth import get_session_hash
from .store import (
    create_environment, get_environments,
    update_environment, delete_environment
)
from .extid import externalize

router = APIRouter(prefix="/api/environments", tags=["environments"])


def _ext_env(env):
    """Externalize an environment row for API response."""
    return externalize(env, exclude=("id", "session_hash"))


class EnvironmentCreate(BaseModel):
    name: str = ''
    blob_hash: Optional[str] = None
    encrypted_blob: Optional[str] = None
    blob_iv: Optional[str] = None


class EnvironmentUpdate(BaseModel):
    name: Optional[str] = None
    blob_hash: Optional[str] = None
    encrypted_blob: Optional[str] = None
    blob_iv: Optional[str] = None


@router.get("")
async def list_environments(request: Request):
    session_hash = get_session_hash(request)
    envs = get_environments(session_hash)
    return [_ext_env(e) for e in envs]


@router.post("")
async def create_env(request: Request, body: EnvironmentCreate):
    session_hash = get_session_hash(request)
    env = create_environment(
        session_hash=session_hash,
        name=body.name,
        blob_hash=body.blob_hash,
        encrypted_blob=body.encrypted_blob,
        blob_iv=body.blob_iv,
    )
    return _ext_env(env)


@router.put("/{extid}")
async def update_env(extid: str, request: Request, body: EnvironmentUpdate):
    session_hash = get_session_hash(request)
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = update_environment(extid, session_hash, **fields)
    if result is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    if result == 'skipped':
        return {"status": "skipped", "reason": "blob_hash unchanged"}
    return _ext_env(result)


@router.delete("/{extid}")
async def delete_env(extid: str, request: Request):
    session_hash = get_session_hash(request)
    deleted = delete_environment(extid, session_hash)
    if not deleted:
        raise HTTPException(status_code=404, detail="Environment not found")
    return {"status": "deleted"}
