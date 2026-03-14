"""UUIDv7 generation (RFC 9562).

Time-ordered UUIDs with millisecond precision. Used as external
identifiers for all database entities so that primary keys and
auth tokens never leak into URLs, UI, or API responses.
"""

import os
import time
import uuid


def uuid7() -> str:
    """Generate a UUIDv7 string.

    Layout (128 bits):
      48 bits — Unix timestamp in milliseconds
       4 bits — version (0b0111)
      12 bits — random (rand_a)
       2 bits — variant (0b10)
      62 bits — random (rand_b)
    """
    timestamp_ms = int(time.time() * 1000)
    rand = os.urandom(10)

    # Bytes 0-5: 48-bit timestamp (big-endian)
    ts_bytes = timestamp_ms.to_bytes(6, "big")

    # Bytes 6-7: version (4 bits) + rand_a (12 bits)
    rand_a = int.from_bytes(rand[:2], "big")
    ver_rand_a = (0x7 << 12) | (rand_a & 0x0FFF)
    vr_bytes = ver_rand_a.to_bytes(2, "big")

    # Bytes 8-15: variant (2 bits) + rand_b (62 bits)
    rand_b = bytearray(rand[2:])
    rand_b[0] = (rand_b[0] & 0x3F) | 0x80
    rand_b = bytes(rand_b)

    raw = ts_bytes + vr_bytes + rand_b
    return str(uuid.UUID(bytes=raw))


def externalize(row: dict, exclude=("id", "document_id", "session_hash")) -> dict:
    """Remove internal fields from a row before returning via API.

    Strips primary keys, foreign keys, and sensitive hashes so that
    only extid and user-facing fields cross the API boundary.
    """
    if row is None:
        return None
    return {k: v for k, v in row.items() if k not in exclude}
