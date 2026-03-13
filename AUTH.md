# Token-Based Sessions

## Core idea

The token is the identity. No usernames, no passwords, no user table. A `secrets.token_urlsafe(32)` string (256 bits of entropy) is the credential, the partition key, and the recovery mechanism. Lose it, lose your data. Save it, reconnect from anywhere.

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
POST /api/auth/token       -> { token }        # mint a new token
GET  /api/auth/validate    -> { valid, documentCount }  # check via Bearer header
```

1. Client generates token via `POST /api/auth/token`
2. Server returns raw token. Never stores it. Only the `SHA256` hash touches the DB.
3. Client stores token in `sessionStorage` (default) or `localStorage` ("Remember me")
4. Every request sends `Authorization: Bearer <token>`
5. Server hashes it, uses hash to scope all document queries
6. User can re-enter a saved token to reconnect — the hash is deterministic

Browser storage key: `dd_token`

## Data model

```
documents
├── session_hash TEXT (nullable, indexed) ← partition key
├── id, title, created_at, updated_at

testruns  (formerly "sessions")
├── document_id → documents(id)
├── testrun_number, testrun_type ('save'|'autosave')
├── state_json, state_hash, endpoint/drift/ok counts
├── UNIQUE(document_id, testrun_number)
```

Pre-existing documents (before auth was added) have `session_hash = NULL` and remain accessible without a token.

## Naming

"Session" was overloaded — it meant both "numbered snapshot within a document" and "a user's browsing context." Now:

- **testrun** = a numbered snapshot within a document (the old "session")
- **session** = the token-bound browser session (traditional meaning)

The `session.svelte.js` store keeps its name — it holds per-browser-session config (hosts, auth credentials, ignore paths), which is now the correct semantic.

## Frontend gate

`TokenGate.svelte` wraps the entire app. Without a token, it renders a landing page:
- "Start fresh" — mints a token, displays it once, warns to save it
- "I have a token" — paste input, validates against `/api/auth/validate`
- "Remember me" checkbox — localStorage vs sessionStorage

When authenticated, a token bar at the top shows the masked token with copy + sign out.

## Migration

`init_db()` handles both directions automatically on startup:
- Detects old `sessions` table → renames to `testruns`, renames columns
- Adds `session_hash` column to `documents` if missing

## Turso migration path

When ready to switch from local SQLite to Turso:
1. Set `DD_DB_DRIVER=turso`
2. Set `DD_DB_PATH=libsql://your-db.turso.io`
3. Set `DD_DB_AUTH_TOKEN=<token>`

No schema changes needed — the `_connect()` factory in `store.py` already abstracts the driver. Both use DB-API 2.0 compatible connections with identical SQL.
