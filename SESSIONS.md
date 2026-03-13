# Token-Based Sessions

Data is partitioned by token. No usernames, no passwords.

## How it works

1. Client hits `POST /api/auth/token` to get a random token (`secrets.token_urlsafe(32)`)
2. Client sends `Authorization: Bearer <token>` on every request
3. Server hashes the token (`SHA256`) and stores the hash as `session_hash` on the `documents` table
4. All queries filter by `session_hash` -- each token sees only its own documents

The raw token is never stored server-side.

## Browser storage

- **sessionStorage** by default (cleared when tab closes)
- **localStorage** if "Remember me" is checked
- Token can be manually re-entered to reconnect to data

Key: `dd_token`

## API

```
POST /api/auth/token          -> { token }
GET  /api/auth/validate       -> { valid, documentCount }  (reads token from header)
```

## Frontend gate

`TokenGate.svelte` wraps the app. No token = landing page with two options:
- "Start fresh" -- generates a new token, shows it once
- "I have a token" -- paste + load

When authenticated, a token bar appears at the top with copy + sign out.

## Naming

The old "session" (numbered snapshots within a document) is now called **testrun**.

| Old | New |
|-----|-----|
| `sessions` table | `testruns` |
| `session_number` | `testrun_number` |
| `session_type` | `testrun_type` |
| `/api/documents/{id}/sessions` | `/api/documents/{id}/testruns` |

"Session" now means the token-bound browser session.

## Files

- `dd/auth.py` -- token generation, hashing, FastAPI dependency
- `dd/store.py` -- `session_hash` column on `documents`, migration from old schema
- `src/stores/auth.svelte.js` -- browser-side token state
- `src/components/TokenGate.svelte` -- auth gate UI
- `lib/api.js` -- `apiFetch()` wrapper injects Bearer header

## Migration

Existing databases migrate automatically on startup:
- `sessions` table renamed to `testruns` (columns too)
- `session_hash` column added to `documents` (nullable -- old docs have NULL, visible without a token)

Designed to work identically on SQLite and Turso (single DB, partition by column).
