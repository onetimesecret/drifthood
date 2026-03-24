# dd/endpoints_api.py

"""Endpoint CRUD routes. Endpoints are server-synced, encrypted client-side."""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from .auth import get_session_hash
from .store import (
    create_endpoint, get_endpoints,
    update_endpoint, delete_endpoint
)
from .extid import externalize

router = APIRouter(prefix="/api/endpoints", tags=["endpoints"])


def _ext_endpoint(ep):
    """Externalize an endpoint row for API response."""
    return externalize(ep, exclude=("id", "session_hash"))


class EndpointCreate(BaseModel):
    label: str = ''
    group: str = ''
    blob_hash: Optional[str] = None
    encrypted_blob: Optional[str] = None
    blob_iv: Optional[str] = None


class EndpointUpdate(BaseModel):
    label: Optional[str] = None
    group: Optional[str] = None
    blob_hash: Optional[str] = None
    encrypted_blob: Optional[str] = None
    blob_iv: Optional[str] = None


@router.get("")
async def list_endpoints(request: Request):
    session_hash = get_session_hash(request)
    endpoints = get_endpoints(session_hash)
    return [_ext_endpoint(ep) for ep in endpoints]


@router.post("")
async def create_ep(request: Request, body: EndpointCreate):
    session_hash = get_session_hash(request)
    ep = create_endpoint(
        session_hash=session_hash,
        label=body.label,
        group=body.group,
        blob_hash=body.blob_hash,
        encrypted_blob=body.encrypted_blob,
        blob_iv=body.blob_iv,
    )
    return _ext_endpoint(ep)


@router.put("/{extid}")
async def update_ep(extid: str, request: Request, body: EndpointUpdate):
    session_hash = get_session_hash(request)
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = update_endpoint(extid, session_hash, **fields)
    if result is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    if result == 'skipped':
        return {"status": "skipped", "reason": "blob_hash unchanged"}
    return _ext_endpoint(result)


@router.delete("/{extid}")
async def delete_ep(extid: str, request: Request):
    session_hash = get_session_hash(request)
    deleted = delete_endpoint(extid, session_hash)
    if not deleted:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return {"status": "deleted"}
