"""
Token-based session identity.

A session token is a random string that identifies a user's data partition.
The SHA256 hash of the token is stored as `session_hash` on documents.
The raw token is never stored server-side.

Each session also gets a UUIDv7 extid for use in URLs. The raw token
never appears in URLs — only the extid does (/s/{extid}).
"""

import hashlib
import secrets
from typing import Optional

from fastapi import APIRouter, Request

import dd.store as store

router = APIRouter(prefix="/api/auth", tags=["auth"])


def generate_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Derive the storage key from a raw token."""
    return hashlib.sha256(token.encode()).hexdigest()


def get_session_hash(request: Request) -> Optional[str]:
    """FastAPI dependency: extract session hash from Authorization header.

    Reads `Authorization: Bearer <token>`, hashes the token, returns the hash.
    Returns None if no Authorization header is present.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return hash_token(token)
    return None


@router.post("/token")
async def create_token():
    """Generate a new session token.

    Returns the raw token (shown to user once) and a public extid
    for use in URLs. The token is used for API auth (Bearer header),
    while the extid appears in the URL path (/s/{extid}).
    """
    token = generate_token()
    session_hash = hash_token(token)
    session = store.create_session(session_hash)
    return {"token": token, "extid": session["extid"]}


@router.get("/validate")
async def validate_token(request: Request):
    """Check if a token has any associated data.

    Reads the token from the Authorization header.
    Returns {valid: bool, documentCount: int, extid: str|null}.
    """
    session_hash = get_session_hash(request)
    if not session_hash:
        return {"valid": False, "documentCount": 0, "extid": None}
    docs = store.list_documents(session_hash=session_hash)
    # Look up or create the session to return its extid
    session = store.get_session_by_hash(session_hash)
    if not session:
        session = store.create_session(session_hash)
    return {
        "valid": True,
        "documentCount": len(docs),
        "extid": session["extid"],
    }
