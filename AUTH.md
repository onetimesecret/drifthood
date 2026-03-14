# Token-Based Sessions

## Core idea

Two-part session identity: a **token** (the secret) and an **extid** (the public name).

The token is the credential — a `secrets.token_urlsafe(32)` string (256 bits of entropy). It authenticates API calls via `Authorization: Bearer` headers. The server never stores the raw token; only its SHA256 hash touches the database.

The extid is a UUIDv7 that identifies the session in URLs, UI, and API responses. It's not a credential — knowing the extid does not grant access. It exists so the token never appears in the URL bar, browser history, or shared links.

No usernames, no passwords, no user table. Lose the token, lose your data. Save it, reconnect from anywhere.

## Security posture

This is a testing tool. The `localStorage` persistence of the auth token (via "Remember me") is a deliberate convenience tradeoff — the operator chooses whether to point the tool at production targets, and accepts the browser-storage risk that comes with it.

The extid/token split prevents casual leakage of the credential through URLs (copy-pasting, screen sharing, browser history), but does not attempt to defend against a compromised browser environment. If an attacker has access to your browser storage, both the token and extid are already exposed.

## Architecture decision: single DB with partition column

Two partitioning strategies were considered:

### Chosen: single DB with partition column

One database, `session_hash TEXT` column on the `documents` table, all queries filter by it. Works identically on local SQLite and Turso — the only change is the connection string.

- Simpler Turso migration (connection string swap, no schema change)
- Multi-tenant queries possible (admin/debug use)
- No natural isolation — a bug in the WHERE clause leaks data across tokens
- Indexes on `session_hash` required for performance at scale

### Alternative: database-per-token

Locally: `SHA256(token)` as the SQLite filename. On Turso: one database per token via the [Turso Platform API](https://docs.turso.tech/api-reference), which supports creating databases programmatically. Each gets its own `libsql://` URL.

- True data isolation (no WHERE clause bugs can leak across tokens)
- Simpler queries (no partition column, no multi-tenant filtering)
- Clean data deletion (drop the database, no orphan risk)
- But: platform API call on every new token (latency, rate limits, additional auth)
- Managing N database URLs instead of one connection (need a registry/lookup)
- Cross-user queries for admin/debug require iterating databases
- Turso billing may vary by plan for high database counts

This remains a viable path if stronger isolation guarantees are needed. The `_connect()` factory in `store.py` would need to accept a dynamic URL derived from the token hash, and a lightweight registry (or naming convention) would map hashes to Turso database URLs.

**Tradeoffs of the token-as-identity model:**
- Zero friction onboarding — one click, no forms
- Token loss = data loss (orphaned rows, no recovery path without the token)
- No enumeration risk — 256-bit token space is infeasible to brute-force
- Sharing = copying the token (which is fine for a scrappy internal tool)
- No server-side session expiry — the token is valid as long as its data exists

## Token lifecycle

```
POST /api/auth/token       -> { token, extid }        # mint a new token + session
GET  /api/auth/validate    -> { valid, documentCount, extid }  # check via Bearer header
```

1. Client calls `POST /api/auth/token`
2. Server generates token, hashes it, creates a `sessions` row with a UUIDv7 extid
3. Server returns `{ token, extid }` — the token is shown to the user once
4. Client stores the token in `sessionStorage` (default) or `localStorage` ("Remember me")
5. Client stores the extid separately and puts it in the URL: `/s/{extid}`
6. Every API request sends `Authorization: Bearer <token>`
7. Server hashes it, uses the hash to scope all document queries
8. User can re-enter a saved token to reconnect — the hash is deterministic, and the server returns the associated extid

Browser storage keys: `dd_token` (credential), `dd_extid` (URL identifier)

## Extid convention

All database entities use UUIDv7 external identifiers. Integer primary keys, foreign keys, and raw tokens never cross the API boundary — they stay internal to the Python backend.

| Entity   | Internal key          | External reference |
|----------|-----------------------|--------------------|
| Session  | `sessions.id`        | `sessions.extid`   |
| Document | `documents.id`       | `documents.extid`  |
| Testrun  | `testruns.id`        | `testruns.extid`   |

API routes use extids in paths: `/api/documents/{doc_extid}/testruns/{testrun_extid}`

UUIDv7 provides time-ordering (millisecond-precision timestamp in the high bits) which makes them naturally sortable and indexable without sacrificing uniqueness.

## URL structure

```
/                       Landing page (unauthenticated)
/s/{session_extid}      Authenticated session (SPA served if extid is valid, 404 otherwise)
/s/{session_extid}?v=   Vibe param for progressive disclosure (new, fresh)
/e/{environment_extid}  Environment detail page (requires auth in storage)
```

The `/s/` route validates the extid server-side: non-UUID values and unknown extids return 404. This prevents the SPA from loading for garbage paths.

## Data model

```
sessions
├── extid TEXT UNIQUE             ← public session identifier (UUIDv7)
├── session_hash TEXT (indexed)   ← SHA256(token), partition key
├── created_at

documents
├── extid TEXT UNIQUE             ← public document identifier (UUIDv7)
├── session_hash TEXT (indexed)   ← partition key
├── id, title, created_at, updated_at

testruns  (formerly "sessions")
├── extid TEXT UNIQUE             ← public testrun identifier (UUIDv7)
├── document_id → documents(id)  ← internal FK, never exposed
├── testrun_number, testrun_type ('save'|'autosave')
├── state_json, state_hash, endpoint/drift/ok counts
├── UNIQUE(document_id, testrun_number)
```

Pre-existing documents (before auth was added) have `session_hash = NULL` and remain accessible without a token.

## Naming

"Session" was overloaded — it meant both "numbered snapshot within a document" and "a user's browsing context." Now:

- **testrun** = a numbered snapshot within a document (the old "session")
- **session** = the token-bound browser session (traditional meaning), with a `sessions` table

The `session.svelte.js` store keeps its name — it holds per-browser-session config (hosts, auth credentials, ignore paths), which is now the correct semantic.

## Frontend gate

`TokenGate.svelte` wraps the entire app. Without a token, it renders a landing page:
- "Start fresh" — mints a token + extid, displays the token once, warns to save it
- "I have a token" — paste input, validates via `/api/auth/validate`, retrieves the extid
- "Remember me" checkbox — localStorage vs sessionStorage

When authenticated, a token bar at the top shows the masked token with copy + sign out. The URL shows the session extid, never the raw token.

## Migration

`init_db()` handles schema evolution automatically on startup:
- Detects old `sessions` table (with `state_json`) → renames to `testruns`, renames columns
- Creates new `sessions` table (for token identity) if missing
- Adds `session_hash` column to `documents` if missing
- Adds `extid` column to `documents` and `testruns` if missing, backfills with UUIDv7

## Turso migration path

When ready to switch from local SQLite to Turso:
1. Set `DD_DB_DRIVER=turso`
2. Set `DD_DB_PATH=libsql://your-db.turso.io`
3. Set `DD_DB_AUTH_TOKEN=<token>`

No schema changes needed — the `_connect()` factory in `store.py` already abstracts the driver. Both use DB-API 2.0 compatible connections with identical SQL.
