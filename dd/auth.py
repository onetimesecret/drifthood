# dd/auth.py

"""
Token-based session identity.

A session token is a random string that identifies a user's data partition.
The SHA256 hash of the token is stored as `session_hash` on documents.
The raw token is never stored server-side.

Each session also gets a UUIDv7 extid for use in URLs. The raw token
never appears in URLs — only the extid does (/s/{extid}).
"""

import base64
import hashlib
import secrets

from fastapi import APIRouter, HTTPException, Request

import dd.store as store
from .crypto import hkdf_derive
from .extid import uuid7

router = APIRouter(prefix="/api/auth", tags=["auth"])


def generate_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Derive the storage key from a raw token."""
    return hashlib.sha256(token.encode()).hexdigest()


def derive_auth_key(token: str, extid: str) -> str:
    """Derive an auth key from token + extid via HKDF.

    The raw token (base64url from secrets.token_urlsafe) is decoded to bytes
    and used as IKM. The extid (UUIDv7 string) is the salt. Info is b"auth".
    Returns a base64url-encoded (no padding) string matching token_urlsafe format.
    """
    # Pad base64url token for decoding (token_urlsafe strips padding)
    padded = token + '=' * (-len(token) % 4)
    token_bytes = base64.urlsafe_b64decode(padded)
    salt = extid.encode('utf-8')
    info = b"auth"
    auth_key_bytes = hkdf_derive(token_bytes, salt, info, 32)
    return base64.urlsafe_b64encode(auth_key_bytes).rstrip(b'=').decode('ascii')


def get_session_hash(request: Request) -> str:
    """Extract session hash from Authorization: Bearer header.

    Raises 401 if the header is missing or malformed.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth[7:]
    return hash_token(token)


@router.post("/token")
async def create_token():
    """Generate a new session token.

    Returns the raw token (shown to user once) and a public extid
    for use in URLs. The token is used for API auth (Bearer header),
    while the extid appears in the URL path (/s/{extid}).
    """
    token = generate_token()
    extid = uuid7()
    auth_key = derive_auth_key(token, extid)
    session_hash = hash_token(auth_key)
    session = store.create_session(session_hash, extid=extid)
    return {"token": token, "extid": session["extid"]}


@router.get("/validate")
async def validate_token(request: Request):
    """Check if a token has any associated data.

    Reads the token from the Authorization header.
    Returns {valid: bool, documentCount: int, extid: str|null}.
    """
    try:
        session_hash = get_session_hash(request)
    except HTTPException:
        return {"valid": False, "documentCount": 0, "extid": None}
    session = store.get_session_by_hash(session_hash)
    if not session:
        # No session exists for this token - don't create one.
        # Sessions should only be created via /token endpoint.
        return {"valid": False, "documentCount": 0, "extid": None}
    docs = store.list_documents(session_hash=session_hash)
    return {
        "valid": True,
        "documentCount": len(docs),
        "extid": session["extid"],
    }
