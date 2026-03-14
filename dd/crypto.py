"""HKDF key derivation (RFC 5869) using stdlib hmac."""

import hmac
import hashlib
import math


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """HKDF-Extract: PRK = HMAC-Hash(salt, IKM)"""
    if not salt:
        salt = b'\x00' * 32  # HashLen zeros for SHA-256
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand: OKM = T(1) || T(2) || ... where T(i) = HMAC-Hash(PRK, T(i-1) || info || i)"""
    hash_len = 32  # SHA-256
    n = math.ceil(length / hash_len)
    if n > 255:
        raise ValueError("Cannot expand to more than 255*HashLen bytes")
    okm = b''
    t = b''
    for i in range(1, n + 1):
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]


def hkdf_derive(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    """Full HKDF: Extract then Expand."""
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)
