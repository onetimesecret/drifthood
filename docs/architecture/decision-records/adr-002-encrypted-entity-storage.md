---
id: "002"
status: accepted
title: "ADR-002: Encrypted Entity Storage"
---

## Status

Accepted

## Date

2026-03-13

## Context

The drift detector stores session data (environments with credentials, endpoints with API paths, testruns with comparison results) on a server that may be shared or hosted. Even as a testing tool, the data can contain production API credentials, auth tokens, and response bodies that should not be readable by the server operator or anyone with database access.

The identity model from ADR-001 already splits the session token from the public extid. But the server still stores all entity data in cleartext. A compromise of the database (or a curious operator) exposes everything.

The constraint: zero new dependencies on either side. The browser has SubtleCrypto. Python has `hmac` and `hashlib`. The solution has to work within those.

## Decision

**Each entity carries queryable cleartext columns alongside an opaque encrypted blob. The client encrypts sensitive fields before they leave the browser; the server stores only ciphertext it cannot read.**

### Key derivation

A single 32-byte token (from `secrets.token_urlsafe(32)`) is the root secret. Two independent keys are derived via HKDF (RFC 5869, extract-then-expand with HMAC-SHA256):

- `HKDF(ikm=token_bytes, salt=extid, info="auth")` produces a 256-bit **auth key**. This replaces the raw token in `Authorization: Bearer` headers. The server stores `SHA256(auth_key)` for lookup — the raw token and the auth key are never persisted server-side.
- `HKDF(ikm=token_bytes, salt=extid, info="enc")` produces a 256-bit **encryption key** as a non-extractable AES-GCM `CryptoKey`. Used exclusively client-side for encrypt/decrypt. The server never sees this key or any material from which it could be derived.

The extid (UUIDv7) serves double duty: public session identifier in URLs and HKDF salt binding derived keys to a specific session.

### Per-entity encryption

Entities (environments, endpoints, testruns) split their fields into two categories:

- **Cleartext columns** — queryable metadata the server needs for indexing, display, and dedup. Examples: `name` (environments), `label`/`group` (endpoints), `endpoint_count`/`drift_count`/`ok_count` (testruns).
- **Encrypted blob** — a JSON object containing sensitive fields, encrypted with AES-GCM-256. Stored as three columns: `encrypted_blob` (base64 ciphertext), `blob_iv` (base64 96-bit nonce), `blob_hash` (hex SHA-256 of plaintext).

For environments, the sensitive fields are `baseUrl`, `auth`, `memo`, and `metadata`. For endpoints, the sensitive fields include `path`, `body`, and `fieldValues`. For testruns, the encrypted blob carries `endpoint_results` (with full response bodies and credentials); the cleartext `state_json` becomes a manifest of entity references (extids) and summary counts.

### AAD binding

AES-GCM's Additional Authenticated Data is set to the entity's own extid. This prevents an attacker who can rewrite the database from swapping encrypted blobs between entities within the same session — decryption fails if the extid doesn't match the one used during encryption.

### Hash-then-encrypt dedup

Before encrypting, the client computes `SHA256(plaintext)` and sends the hex digest as `blob_hash`. The server compares this hash against the stored value to skip no-op writes (autosaves where nothing changed). This leaks whether the content changed between saves but not what changed — an acceptable tradeoff for a testing tool where save frequency matters more than metadata privacy.

### Two-step re-entry

Resuming a session requires both the raw token and the extid. The extid is the HKDF salt — without it, the client cannot re-derive auth or encryption keys. Two sources:

1. **URL**: navigating to `/s/{extid}` provides the extid; the token comes from browser storage.
2. **Paste**: the format `extid:token` in the token input field supplies both values in one step.

### Testruns as manifests

The testrun `state_json` column transitions from a monolithic state dump to a cleartext manifest: document/testrun extids, environment and endpoint extid arrays, selected A/B references, and summary counts. Sensitive data (comparison results, credentials, UI state) moves into the encrypted blob. Legacy testruns without blobs are still loadable — the restore path falls back to reading everything from `state_json`.

### Token loss is unrecoverable

The server cannot decrypt any entity data without client-supplied key material. If the token is lost and not in browser storage, the session's encrypted data is permanently inaccessible. This is the same tradeoff password managers make: security in exchange for the user's responsibility to retain the secret.

## Trade-offs

- **We lose**: Server-side introspection of entity data. Debugging encrypted blobs requires the client token. Backups are opaque without key material. The `blob_hash` leaks a content-changed signal (though not the content itself).
- **We gain**: Database compromise does not expose credentials or API responses. The server operator is structurally unable to read sensitive fields. Zero new dependencies — SubtleCrypto on the client, stdlib `hmac`/`hashlib` on the server.

## References

- HKDF: RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function.
- AES-GCM: NIST SP 800-38D. 96-bit random IV, 256-bit key. AAD binds ciphertext to entity identity.
- ADR-001 established the token/extid split that this decision extends with key derivation.
