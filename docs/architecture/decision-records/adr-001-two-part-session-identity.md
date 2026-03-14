---
id: "001"
status: accepted
title: "ADR-001: Two-Part Session Identity"
---

## Status

Accepted

## Date

2026-03-13

## Context

The drift detector uses token-based sessions to partition user data. Originally, the raw auth token appeared directly in the URL path (`/s/{token}`), served double duty as the bearer credential in API calls, and was the only identifier for a session. This created two problems:

1. **Token leakage via URL.** Browser history, server access logs, referrer headers, and screen-sharing all expose the URL. Anyone who sees it gains full session access.
2. **Internal identifiers in the API surface.** Integer primary keys (`documents.id`, `testruns.id`) and the `session_hash` appeared in API responses and URL paths, coupling the external contract to database internals.

## Decision

**Split session identity into two parts: a secret token for authentication and a public UUIDv7 extid for addressing.**

The token is a `secrets.token_urlsafe(32)` string. It authenticates API calls via `Authorization: Bearer` and is stored client-side in `sessionStorage` (always) or `localStorage` (opt-in via "Remember me"). The server stores only its SHA-256 hash. The token never appears in URLs, UI text, or API response payloads.

The extid is a UUIDv7 generated server-side when the session is created. It appears in the URL path (`/s/{extid}?v=new`), is returned in API responses, and serves as the public name for the session. Knowing the extid does not grant access — the bearer token is still required for every API call.

This same extid convention extends to all database entities. Documents and testruns each carry a UUIDv7 `extid` column. API routes use extids exclusively (`/api/documents/{doc_extid}/testruns/{testrun_extid}`). Integer primary keys and foreign keys are stripped from all API responses by the `externalize()` helper before they cross the boundary.

The `/s/{extid}` route validates both UUID format and existence in the sessions table, returning 404 for anything else.

**localStorage persistence of the auth token is a deliberate convenience tradeoff.** This is primarily a testing tool but we still need to be responsible. The extid/token split prevents casual leakage through URLs; protecting against a compromised browser is out of scope.

## Trade-offs

- We lose: The old simplicity where the token was the only concept. Users now receive both a token (to save) and see a UUID in the URL (which they can ignore). The backend carries a `sessions` table it didn't need before.
- We gain: URLs are safe to share, bookmark, and log. The API contract is decoupled from database internals. UUIDv7 ordering gives natural time-sorting without exposing creation timestamps as integers.

## References

- Selector/validator pattern: Paragon Initiative, "Split Tokens: Token-Based Authentication Protocols without Side Channels" (2015). Adapted here with the validator confined to bearer headers rather than URL parameters.

- Externalized identifiers: OWASP IDOR guidance. UUIDv7 per RFC 9562 provides k-sortability without sequential enumeration.
