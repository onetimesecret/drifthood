# dd/store.py

"""
SQLite / Turso storage for Drift Detector documents and testruns.

Document = a named container (like a notebook/runbook).
Testrun  = a numbered snapshot within a document. Each Save appends one.
           Contains the full cumulative state at that point.
           testrun_type is either 'save' (explicit) or 'autosave' (periodic).
Session  = a token-based identity. Stores the SHA256 hash of the auth token
           and a public-facing extid (UUIDv7) for URL references.

Schema is deliberately flat and simple. JSON goes in as TEXT.

All entities use UUIDv7 extids as their external identifiers. Primary keys
(integer IDs) and auth tokens never appear in URLs, UI, or API responses.

── Turso / libSQL swap ──
The connection factory (_connect) is the single point of change.
Set DD_DB_DRIVER=turso and DD_DB_PATH=libsql://your-db.turso.io
plus DD_DB_AUTH_TOKEN to switch backends. All SQL stays the same
because Turso is wire-compatible with SQLite.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

from dd.config import DB_AUTH_TOKEN, DB_DRIVER, DB_PATH
from dd.extid import uuid7


def _connect():
    """Return a DB-API 2.0 connection.

    sqlite  -> stdlib sqlite3
    turso   -> libsql_experimental (pip install libsql-experimental)

    Both expose the same cursor/execute/fetchone/fetchall interface,
    so the rest of the module doesn't care which one is active.
    """
    if DB_DRIVER == "turso":
        try:
            import libsql_experimental as libsql
        except ImportError:
            raise RuntimeError(
                "DD_DB_DRIVER=turso requires the libsql-experimental package. "
                "Install it: pip install libsql-experimental"
            )
        conn = libsql.connect(DB_PATH, auth_token=DB_AUTH_TOKEN)
        # libsql doesn't support row_factory the same way; we wrap below
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # Default: local SQLite file
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _row_to_dict(row, description):
    """Convert a raw row tuple + cursor.description to dict.
    Works for both sqlite3.Row and plain tuples (libsql)."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return dict(row)
    # Plain tuple from libsql
    return {description[i][0]: row[i] for i in range(len(description))}


def _fetchone_dict(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    if hasattr(row, "keys"):
        return dict(row)
    return {
        cursor.description[i][0]: row[i] for i in range(len(cursor.description))
    }


def _fetchall_dict(cursor):
    rows = cursor.fetchall()
    if not rows:
        return []
    if hasattr(rows[0], "keys"):
        return [dict(r) for r in rows]
    return [
        {
            cursor.description[i][0]: row[i]
            for i in range(len(cursor.description))
        }
        for row in rows
    ]


def init_db():
    """Create tables if they don't exist. Migrates existing DBs.

    Uses individual execute() calls instead of executescript() because
    libsql_experimental (the Turso driver) doesn't implement executescript().
    """
    conn = _connect()

    # Migration: rename old sessions -> testruns (for existing DBs)
    # Must run BEFORE creating the new sessions table, because the old
    # sessions table (which has state_json/document_id columns) would
    # satisfy the CREATE TABLE IF NOT EXISTS but lacks session_hash,
    # causing the subsequent CREATE INDEX on sessions(session_hash) to fail.
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
    old_sessions = cursor.fetchone()
    if old_sessions:
        cols_cursor = conn.execute("PRAGMA table_info(sessions)")
        col_names = [row[1] if isinstance(row, tuple) else row["name"] for row in cols_cursor.fetchall()]
        if "state_json" in col_names:
            # This is the old sessions table — rename to testruns
            testruns_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='testruns'")
            if not testruns_check.fetchone():
                conn.execute("ALTER TABLE sessions RENAME TO testruns")
                conn.execute("ALTER TABLE testruns RENAME COLUMN session_number TO testrun_number")
                conn.execute("ALTER TABLE testruns RENAME COLUMN session_type TO testrun_type")
                conn.execute("DROP INDEX IF EXISTS idx_sessions_doc")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_testruns_doc ON testruns(document_id)")
                conn.commit()

    # ── Sessions table (new) ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            extid        TEXT NOT NULL UNIQUE,
            session_hash TEXT NOT NULL,
            created_at   TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_hash ON sessions(session_hash)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_extid ON sessions(extid)"
    )

    # ── Documents table ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            extid        TEXT UNIQUE,
            title        TEXT NOT NULL DEFAULT 'Untitled',
            session_hash TEXT,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        )
    """)

    # ── Testruns table ──
    # SECURITY NOTE: Share link visibility
    #
    # The is_public flag provides explicit opt-in for sharing. Without it set,
    # the share endpoint returns 404 (same as non-existent or deleted).
    #
    # UUIDv7 LIMITATION: While UUIDv7 has ~122 bits total, security is weaker
    # than that suggests. The first 48 bits are a millisecond timestamp, leaving
    # only ~74 bits of randomness. An attacker who knows approximately when
    # testruns were created (e.g., within a day) can narrow the search space
    # significantly. The is_public flag provides defense-in-depth: even if an
    # attacker guesses a valid extid, they only see data the owner chose to share.
    #
    # Future enhancements to consider:
    #   - share_token column: shorter, revocable token for sharing
    #   - share_expires_at: time-limited share links
    #   - share_view_count / max_views: limit views before expiry
    conn.execute("""
        CREATE TABLE IF NOT EXISTS testruns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            extid           TEXT UNIQUE,
            document_id     INTEGER NOT NULL REFERENCES documents(id),
            testrun_number  INTEGER NOT NULL,
            testrun_type    TEXT NOT NULL DEFAULT 'save',
            endpoint_count  INTEGER NOT NULL DEFAULT 0,
            drift_count     INTEGER NOT NULL DEFAULT 0,
            ok_count        INTEGER NOT NULL DEFAULT 0,
            is_public       BOOLEAN NOT NULL DEFAULT 0,
            state_json      TEXT NOT NULL,
            state_hash      TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT,
            deleted_at      TEXT,
            UNIQUE(document_id, testrun_number)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_testruns_doc ON testruns(document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_session_hash ON documents(session_hash)"
    )
    conn.commit()

    # Migration: add session_hash column to documents
    cursor = conn.execute("PRAGMA table_info(documents)")
    doc_columns = [row[1] if isinstance(row, tuple) else row["name"] for row in cursor.fetchall()]
    if "session_hash" not in doc_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN session_hash TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_session_hash ON documents(session_hash)")
        conn.commit()

    # Migration: add extid column to documents
    cursor = conn.execute("PRAGMA table_info(documents)")
    doc_columns = [row[1] if isinstance(row, tuple) else row["name"] for row in cursor.fetchall()]
    if "extid" not in doc_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN extid TEXT UNIQUE")
        # Backfill existing rows
        cursor = conn.execute("SELECT id FROM documents WHERE extid IS NULL")
        for row in cursor.fetchall():
            doc_id = row[0] if isinstance(row, tuple) else row["id"]
            conn.execute("UPDATE documents SET extid = ? WHERE id = ?", (uuid7(), doc_id))
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_extid ON documents(extid)")
        conn.commit()

    # Migrations for existing testruns table
    cursor = conn.execute("PRAGMA table_info(testruns)")
    columns = [
        row[1] if isinstance(row, tuple) else row["name"]
        for row in cursor.fetchall()
    ]
    migrations = []
    if "testrun_type" not in columns:
        migrations.append(
            "ALTER TABLE testruns ADD COLUMN testrun_type TEXT NOT NULL DEFAULT 'save'"
        )
    if "endpoint_count" not in columns:
        migrations.append(
            "ALTER TABLE testruns ADD COLUMN endpoint_count INTEGER NOT NULL DEFAULT 0"
        )
    if "drift_count" not in columns:
        migrations.append(
            "ALTER TABLE testruns ADD COLUMN drift_count INTEGER NOT NULL DEFAULT 0"
        )
    if "ok_count" not in columns:
        migrations.append(
            "ALTER TABLE testruns ADD COLUMN ok_count INTEGER NOT NULL DEFAULT 0"
        )
    if "state_hash" not in columns:
        migrations.append("ALTER TABLE testruns ADD COLUMN state_hash TEXT")
    if "updated_at" not in columns:
        migrations.append("ALTER TABLE testruns ADD COLUMN updated_at TEXT")
    if "deleted_at" not in columns:
        migrations.append("ALTER TABLE testruns ADD COLUMN deleted_at TEXT")
    if "extid" not in columns:
        migrations.append("ALTER TABLE testruns ADD COLUMN extid TEXT UNIQUE")
    if "is_public" not in columns:
        migrations.append(
            "ALTER TABLE testruns ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT 0"
        )
    for sql in migrations:
        conn.execute(sql)
    if migrations:
        conn.commit()

    # Backfill extid for testruns
    if "extid" not in columns:
        cursor = conn.execute("SELECT id FROM testruns WHERE extid IS NULL")
        for row in cursor.fetchall():
            tr_id = row[0] if isinstance(row, tuple) else row["id"]
            conn.execute("UPDATE testruns SET extid = ? WHERE id = ?", (uuid7(), tr_id))
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_testruns_extid ON testruns(extid)")
        conn.commit()

    # Migration: add blob columns to testruns
    cursor = conn.execute("PRAGMA table_info(testruns)")
    tr_columns = [
        row[1] if isinstance(row, tuple) else row["name"]
        for row in cursor.fetchall()
    ]
    blob_migrations = []
    if "blob_hash" not in tr_columns:
        blob_migrations.append("ALTER TABLE testruns ADD COLUMN blob_hash TEXT")
    if "encrypted_blob" not in tr_columns:
        blob_migrations.append("ALTER TABLE testruns ADD COLUMN encrypted_blob TEXT")
    if "blob_iv" not in tr_columns:
        blob_migrations.append("ALTER TABLE testruns ADD COLUMN blob_iv TEXT")
    for sql in blob_migrations:
        conn.execute(sql)
    if blob_migrations:
        conn.commit()

    # ── Environments table ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS environments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            extid           TEXT UNIQUE NOT NULL,
            session_hash    TEXT NOT NULL,
            name            TEXT NOT NULL DEFAULT '',
            blob_hash       TEXT,
            encrypted_blob  TEXT,
            blob_iv         TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_environments_session ON environments(session_hash)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_environments_extid ON environments(extid)"
    )

    # ── Endpoints table ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS endpoints (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            extid           TEXT UNIQUE NOT NULL,
            session_hash    TEXT NOT NULL,
            label           TEXT NOT NULL DEFAULT '',
            "group"         TEXT NOT NULL DEFAULT '',
            blob_hash       TEXT,
            encrypted_blob  TEXT,
            blob_iv         TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_endpoints_session ON endpoints(session_hash)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_endpoints_extid ON endpoints(extid)"
    )
    conn.commit()

    conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash_state(state: dict) -> str:
    """Compute a stable hash of the state, excluding volatile fields."""
    s = {
        k: v
        for k, v in state.items()
        if k not in ("savedAt", "sessionNumber", "testrunNumber", "version")
    }
    raw = json.dumps(s, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _summarize_state(state: dict) -> dict:
    endpoints = state.get("endpoints", [])
    endpoint_count = len(endpoints)
    drift_count = sum(1 for ep in endpoints if ep.get("state") == "done-drift")
    ok_count = sum(1 for ep in endpoints if ep.get("state") == "done-ok")
    return {
        "endpoint_count": endpoint_count,
        "drift_count": drift_count,
        "ok_count": ok_count,
    }


# ── Sessions ──


def create_session(session_hash: str, *, extid: str = None) -> dict:
    """Create a new session record. Returns the session row."""
    now = _now()
    if extid is None:
        extid = uuid7()
    conn = _connect()
    conn.execute(
        "INSERT INTO sessions (extid, session_hash, created_at) VALUES (?, ?, ?)",
        (extid, session_hash, now),
    )
    conn.commit()
    cur = conn.execute("SELECT * FROM sessions WHERE extid = ?", (extid,))
    session = _fetchone_dict(cur)
    conn.close()
    return session


def get_session_by_hash(session_hash: str) -> dict | None:
    """Look up a session by its hash. Returns the most recent match."""
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM sessions WHERE session_hash = ? ORDER BY created_at DESC LIMIT 1",
        (session_hash,),
    )
    session = _fetchone_dict(cur)
    conn.close()
    return session


def get_session_by_extid(extid: str) -> dict | None:
    conn = _connect()
    cur = conn.execute("SELECT * FROM sessions WHERE extid = ?", (extid,))
    session = _fetchone_dict(cur)
    conn.close()
    return session


# ── Documents ──


def create_document(title: str, session_hash: str = None) -> dict:
    now = _now()
    extid = uuid7()
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO documents (extid, title, session_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (extid, title, session_hash, now, now),
    )
    doc_id = cur.lastrowid
    conn.commit()
    cur2 = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = _fetchone_dict(cur2)
    conn.close()
    return doc


def get_document(doc_id: int) -> dict | None:
    conn = _connect()
    cur = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = _fetchone_dict(cur)
    conn.close()
    return doc


def get_document_by_extid(extid: str) -> dict | None:
    conn = _connect()
    cur = conn.execute("SELECT * FROM documents WHERE extid = ?", (extid,))
    doc = _fetchone_dict(cur)
    conn.close()
    return doc


def list_documents(session_hash: str = None) -> list[dict]:
    conn = _connect()
    if session_hash is not None:
        cur = conn.execute("""
            SELECT d.*,
                   COUNT(s.id) AS testrun_count,
                   COUNT(CASE WHEN s.testrun_type = 'save' THEN 1 END) AS save_count,
                   COUNT(CASE WHEN s.testrun_type = 'autosave' THEN 1 END) AS autosave_count
            FROM documents d
            LEFT JOIN testruns s ON s.document_id = d.id AND s.deleted_at IS NULL
            WHERE d.session_hash = ?
            GROUP BY d.id
            ORDER BY d.title COLLATE NOCASE ASC
        """, (session_hash,))
    else:
        cur = conn.execute("""
            SELECT d.*,
                   COUNT(s.id) AS testrun_count,
                   COUNT(CASE WHEN s.testrun_type = 'save' THEN 1 END) AS save_count,
                   COUNT(CASE WHEN s.testrun_type = 'autosave' THEN 1 END) AS autosave_count
            FROM documents d
            LEFT JOIN testruns s ON s.document_id = d.id AND s.deleted_at IS NULL
            GROUP BY d.id
            ORDER BY d.title COLLATE NOCASE ASC
        """)
    rows = _fetchall_dict(cur)
    conn.close()
    return rows


def update_document_title(doc_id: int, title: str):
    conn = _connect()
    conn.execute(
        "UPDATE documents SET title = ?, updated_at = ? WHERE id = ?",
        (title, _now(), doc_id),
    )
    conn.commit()
    conn.close()


def update_document_title_by_extid(extid: str, title: str):
    conn = _connect()
    conn.execute(
        "UPDATE documents SET title = ?, updated_at = ? WHERE extid = ?",
        (title, _now(), extid),
    )
    conn.commit()
    conn.close()


# ── Testruns ──


def create_testrun(
    document_id: int,
    state: dict,
    testrun_type: str = "save",
    blob_hash: str | None = None,
    encrypted_blob: str | None = None,
    blob_iv: str | None = None,
    endpoint_count: int | None = None,
    drift_count: int | None = None,
    ok_count: int | None = None,
) -> dict:
    assert testrun_type in ("save", "autosave"), (
        f"Invalid testrun_type: {testrun_type}"
    )
    now = _now()
    extid = uuid7()
    state_hash = _hash_state(state)

    # Use client-provided counts when available (manifest doesn't have endpoints inline),
    # otherwise fall back to computing from state (legacy path)
    if endpoint_count is not None:
        summary = {
            "endpoint_count": endpoint_count,
            "drift_count": drift_count or 0,
            "ok_count": ok_count or 0,
        }
    else:
        summary = _summarize_state(state)

    conn = _connect()

    if testrun_type == "autosave":
        # Dedup: prefer blob_hash (client-provided SHA256 of encrypted content)
        # over state_hash (server-computed from plaintext state) for dedup.
        # blob_hash is more accurate because it covers the sensitive data
        # that the server can't inspect.
        if blob_hash:
            cur = conn.execute(
                "SELECT blob_hash FROM testruns WHERE document_id = ? AND deleted_at IS NULL ORDER BY testrun_number DESC LIMIT 1",
                (document_id,),
            )
            last = _fetchone_dict(cur)
            if last and last.get("blob_hash") == blob_hash:
                conn.close()
                return {
                    "skipped": True,
                    "reason": "blob unchanged",
                    "blob_hash": blob_hash,
                }
        else:
            cur = conn.execute(
                "SELECT state_hash FROM testruns WHERE document_id = ? AND deleted_at IS NULL ORDER BY testrun_number DESC LIMIT 1",
                (document_id,),
            )
            last = _fetchone_dict(cur)
            if last and last["state_hash"] == state_hash:
                conn.close()
                return {
                    "skipped": True,
                    "reason": "state unchanged",
                    "state_hash": state_hash,
                }

    cur = conn.execute(
        "SELECT COALESCE(MAX(testrun_number), 0) AS mx FROM testruns WHERE document_id = ?",
        (document_id,),
    )
    row = _fetchone_dict(cur)
    next_num = row["mx"] + 1

    state_json = json.dumps(state)
    conn.execute(
        """INSERT INTO testruns
           (extid, document_id, testrun_number, testrun_type, endpoint_count, drift_count, ok_count,
            state_json, state_hash, blob_hash, encrypted_blob, blob_iv, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            extid,
            document_id,
            next_num,
            testrun_type,
            summary["endpoint_count"],
            summary["drift_count"],
            summary["ok_count"],
            state_json,
            state_hash,
            blob_hash,
            encrypted_blob,
            blob_iv,
            now,
        ),
    )

    conn.execute(
        "UPDATE documents SET updated_at = ? WHERE id = ?",
        (now, document_id),
    )
    conn.commit()

    cur2 = conn.execute(
        """SELECT id, extid, document_id, testrun_number, testrun_type,
                  endpoint_count, drift_count, ok_count, state_hash, created_at, updated_at
           FROM testruns WHERE document_id = ? AND testrun_number = ?""",
        (document_id, next_num),
    )
    testrun = _fetchone_dict(cur2)
    conn.close()
    return testrun


def list_testruns(document_id: int) -> list[dict]:
    conn = _connect()
    cur = conn.execute(
        """SELECT id, extid, document_id, testrun_number, testrun_type,
                  endpoint_count, drift_count, ok_count, state_hash, created_at, updated_at
           FROM testruns WHERE document_id = ? AND deleted_at IS NULL
           ORDER BY testrun_number""",
        (document_id,),
    )
    rows = _fetchall_dict(cur)
    conn.close()
    return rows


def get_testrun(testrun_id: int) -> dict | None:
    conn = _connect()
    cur = conn.execute("SELECT * FROM testruns WHERE id = ?", (testrun_id,))
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def get_testrun_by_number(document_id: int, testrun_number: int) -> dict | None:
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM testruns WHERE document_id = ? AND testrun_number = ?",
        (document_id, testrun_number),
    )
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def get_testrun_by_extid(extid: str) -> dict | None:
    conn = _connect()
    cur = conn.execute("SELECT * FROM testruns WHERE extid = ?", (extid,))
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def _normalize_path(path: str) -> str:
    """Normalize path parameters to canonical form for endpoint identity.

    Handles:
    - OpenAPI-style templates: /users/{id} -> /users/{param}
    - Literal numeric segments: /users/123 -> /users/{param}
    - UUIDs: /users/550e8400-e29b-41d4-a716-446655440000 -> /users/{param}

    This ensures /users/1 and /users/2 are treated as the same endpoint.
    """
    import re
    segments = path.split("/")
    normalized = []
    # UUID pattern (8-4-4-4-12 hex)
    uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    for seg in segments:
        if not seg:
            normalized.append(seg)
        elif seg.startswith("{") and seg.endswith("}"):
            # Already a template param, normalize to {param}
            normalized.append("{param}")
        elif seg.isdigit():
            # Numeric ID
            normalized.append("{param}")
        elif uuid_re.match(seg):
            # UUID
            normalized.append("{param}")
        else:
            normalized.append(seg)
    return "/".join(normalized)


def diff_testruns(run_a: dict, run_b: dict) -> dict:
    """Compute endpoint-level delta between two testruns.

    Pure function: does not access the database.

    Returns dict with:
        added: list of endpoints in B but not A (keyed by METHOD:path)
        removed: list of endpoints in A but not B
        changed: list of endpoints present in both but with different state
        unchanged: list of endpoints present in both with same state
    """
    def _endpoint_key(ep: dict) -> str:
        path = ep.get("path", "")
        normalized = _normalize_path(path)
        return f"{ep.get('method', 'GET')}:{normalized}"

    endpoints_a = run_a.get("state", {}).get("endpoints", [])
    endpoints_b = run_b.get("state", {}).get("endpoints", [])

    # Build lookup dicts keyed by METHOD:path
    a_by_key = {_endpoint_key(ep): ep for ep in endpoints_a}
    b_by_key = {_endpoint_key(ep): ep for ep in endpoints_b}

    keys_a = set(a_by_key.keys())
    keys_b = set(b_by_key.keys())

    added = [b_by_key[k] for k in (keys_b - keys_a)]
    removed = [a_by_key[k] for k in (keys_a - keys_b)]
    changed = []
    unchanged = []

    for k in keys_a & keys_b:
        ep_a = a_by_key[k]
        ep_b = b_by_key[k]
        # Compare state field (done-drift, done-ok, idle, etc.)
        if ep_a.get("state") != ep_b.get("state"):
            changed.append({"key": k, "a": ep_a, "b": ep_b})
        else:
            unchanged.append({"key": k, "a": ep_a, "b": ep_b})

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
    }


def get_active_testrun_by_extid(extid: str) -> dict | None:
    """Get a testrun by extid, excluding soft-deleted testruns.

    Use this for public-facing routes (e.g., share links) where deleted
    testruns should return 404. The plain get_testrun_by_extid() does NOT
    filter deleted_at and should only be used for admin/audit purposes.
    """
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM testruns WHERE extid = ? AND deleted_at IS NULL", (extid,)
    )
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def get_public_testrun_by_extid(extid: str) -> dict | None:
    """Get a testrun by extid, only if it's public and not deleted.

    Use this for the share endpoint. Returns None (which routes translate
    to 404) if:
      - testrun doesn't exist
      - testrun is soft-deleted (deleted_at IS NOT NULL)
      - testrun is private (is_public = FALSE)

    SECURITY: All three conditions produce identical 404 responses to prevent
    information leakage about whether a given extid exists or its visibility state.
    """
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM testruns WHERE extid = ? AND deleted_at IS NULL AND is_public = 1",
        (extid,),
    )
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def set_testrun_public(extid: str, is_public: bool) -> bool:
    """Toggle the is_public flag on a testrun.

    Returns True if the testrun was found and updated, False otherwise.
    Only operates on non-deleted testruns.

    NOTE: The frontend share button should call this endpoint to set
    is_public=True before copying the share link. See App.svelte.
    """
    conn = _connect()
    cur = conn.execute(
        "UPDATE testruns SET is_public = ?, updated_at = ? WHERE extid = ? AND deleted_at IS NULL",
        (1 if is_public else 0, _now(), extid),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def get_latest_testrun(document_id: int) -> dict | None:
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM testruns WHERE document_id = ? AND deleted_at IS NULL ORDER BY testrun_number DESC LIMIT 1",
        (document_id,),
    )
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def update_testrun(
    document_id: int,
    testrun_number: int,
    state: dict,
    blob_hash: str | None = None,
    encrypted_blob: str | None = None,
    blob_iv: str | None = None,
    endpoint_count: int | None = None,
    drift_count: int | None = None,
    ok_count: int | None = None,
) -> dict | None:
    """Update an existing testrun's state in-place (for explicit re-saves)."""
    now = _now()
    state_hash = _hash_state(state)
    state_json = json.dumps(state)

    # Use client-provided counts when available, otherwise compute from state
    if endpoint_count is not None:
        summary = {
            "endpoint_count": endpoint_count,
            "drift_count": drift_count or 0,
            "ok_count": ok_count or 0,
        }
    else:
        summary = _summarize_state(state)

    conn = _connect()

    if blob_hash is not None:
        cur = conn.execute(
            """UPDATE testruns
               SET state_json = ?, state_hash = ?, endpoint_count = ?,
                   drift_count = ?, ok_count = ?,
                   blob_hash = ?, encrypted_blob = ?, blob_iv = ?,
                   updated_at = ?
               WHERE document_id = ? AND testrun_number = ? AND deleted_at IS NULL""",
            (
                state_json,
                state_hash,
                summary["endpoint_count"],
                summary["drift_count"],
                summary["ok_count"],
                blob_hash,
                encrypted_blob,
                blob_iv,
                now,
                document_id,
                testrun_number,
            ),
        )
    else:
        cur = conn.execute(
            """UPDATE testruns
               SET state_json = ?, state_hash = ?, endpoint_count = ?,
                   drift_count = ?, ok_count = ?, updated_at = ?
               WHERE document_id = ? AND testrun_number = ? AND deleted_at IS NULL""",
            (
                state_json,
                state_hash,
                summary["endpoint_count"],
                summary["drift_count"],
                summary["ok_count"],
                now,
                document_id,
                testrun_number,
            ),
        )
    if cur.rowcount == 0:
        conn.close()
        return None

    conn.execute(
        "UPDATE documents SET updated_at = ? WHERE id = ?",
        (now, document_id),
    )
    conn.commit()

    cur2 = conn.execute(
        """SELECT id, extid, document_id, testrun_number, testrun_type,
                  endpoint_count, drift_count, ok_count, state_hash, created_at, updated_at
           FROM testruns WHERE document_id = ? AND testrun_number = ?""",
        (document_id, testrun_number),
    )
    testrun = _fetchone_dict(cur2)
    conn.close()
    return testrun


def update_testrun_by_extid(
    testrun_extid: str,
    state: dict,
    blob_hash: str | None = None,
    encrypted_blob: str | None = None,
    blob_iv: str | None = None,
    endpoint_count: int | None = None,
    drift_count: int | None = None,
    ok_count: int | None = None,
) -> dict | None:
    """Update a testrun identified by extid."""
    now = _now()
    state_hash = _hash_state(state)
    state_json = json.dumps(state)

    # Use client-provided counts when available, otherwise compute from state
    if endpoint_count is not None:
        summary = {
            "endpoint_count": endpoint_count,
            "drift_count": drift_count or 0,
            "ok_count": ok_count or 0,
        }
    else:
        summary = _summarize_state(state)

    conn = _connect()

    if blob_hash is not None:
        cur = conn.execute(
            """UPDATE testruns
               SET state_json = ?, state_hash = ?, endpoint_count = ?,
                   drift_count = ?, ok_count = ?,
                   blob_hash = ?, encrypted_blob = ?, blob_iv = ?,
                   updated_at = ?
               WHERE extid = ? AND deleted_at IS NULL""",
            (
                state_json,
                state_hash,
                summary["endpoint_count"],
                summary["drift_count"],
                summary["ok_count"],
                blob_hash,
                encrypted_blob,
                blob_iv,
                now,
                testrun_extid,
            ),
        )
    else:
        cur = conn.execute(
            """UPDATE testruns
               SET state_json = ?, state_hash = ?, endpoint_count = ?,
                   drift_count = ?, ok_count = ?, updated_at = ?
               WHERE extid = ? AND deleted_at IS NULL""",
            (
                state_json,
                state_hash,
                summary["endpoint_count"],
                summary["drift_count"],
                summary["ok_count"],
                now,
                testrun_extid,
            ),
        )
    if cur.rowcount == 0:
        conn.close()
        return None

    # Get the testrun to find its document_id and update document timestamp
    cur2 = conn.execute(
        "SELECT document_id FROM testruns WHERE extid = ?", (testrun_extid,)
    )
    tr = _fetchone_dict(cur2)
    if tr:
        conn.execute(
            "UPDATE documents SET updated_at = ? WHERE id = ?",
            (now, tr["document_id"]),
        )
    conn.commit()

    cur3 = conn.execute(
        """SELECT id, extid, document_id, testrun_number, testrun_type,
                  endpoint_count, drift_count, ok_count, state_hash, created_at, updated_at
           FROM testruns WHERE extid = ?""",
        (testrun_extid,),
    )
    testrun = _fetchone_dict(cur3)
    conn.close()
    return testrun


def soft_delete_testrun(document_id: int, testrun_number: int) -> bool:
    conn = _connect()
    cur = conn.execute(
        "UPDATE testruns SET deleted_at = ? WHERE document_id = ? AND testrun_number = ? AND deleted_at IS NULL",
        (_now(), document_id, testrun_number),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def soft_delete_testrun_by_extid(testrun_extid: str) -> bool:
    conn = _connect()
    cur = conn.execute(
        "UPDATE testruns SET deleted_at = ? WHERE extid = ? AND deleted_at IS NULL",
        (_now(), testrun_extid),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


# ── Combined save operation ──


def save(
    state: dict,
    document_id: int | None = None,
    document_extid: str | None = None,
    testrun_type: str = "save",
    testrun_number: int | None = None,
    testrun_extid: str | None = None,
    session_hash: str = None,
    blob_hash: str | None = None,
    encrypted_blob: str | None = None,
    blob_iv: str | None = None,
    endpoint_count: int | None = None,
    drift_count: int | None = None,
    ok_count: int | None = None,
) -> dict:
    title = state.get("title") or "Untitled"

    # Resolve document by extid if provided
    doc = None
    if document_extid:
        doc = get_document_by_extid(document_extid)
    elif document_id is not None:
        doc = get_document(document_id)

    if doc is None:
        doc = create_document(title, session_hash=session_hash)
    else:
        if title != doc["title"]:
            update_document_title(doc["id"], title)
            doc["title"] = title

    blob_kwargs = dict(
        blob_hash=blob_hash,
        encrypted_blob=encrypted_blob,
        blob_iv=blob_iv,
        endpoint_count=endpoint_count,
        drift_count=drift_count,
        ok_count=ok_count,
    )

    # For explicit saves with an existing testrun, update in-place
    if testrun_type == "save":
        if testrun_extid:
            updated = update_testrun_by_extid(testrun_extid, state, **blob_kwargs)
            if updated:
                return {"document": doc, "testrun": updated}
        elif testrun_number:
            updated = update_testrun(doc["id"], testrun_number, state, **blob_kwargs)
            if updated:
                return {"document": doc, "testrun": updated}
        # Fall through to create_testrun if update failed (deleted/missing)

    testrun = create_testrun(doc["id"], state, testrun_type, **blob_kwargs)
    return {"document": doc, "testrun": testrun}


# ── Environments ──


def create_environment(session_hash, extid=None, name='', blob_hash=None, encrypted_blob=None, blob_iv=None):
    """Create a new environment. Server generates extid if not provided.
    Each environment is uniquely identified by its extid only."""
    conn = _connect()
    now = _now()
    if extid is None:
        extid = uuid7()
    conn.execute(
        """INSERT INTO environments (extid, session_hash, name, blob_hash, encrypted_blob, blob_iv, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (extid, session_hash, name, blob_hash, encrypted_blob, blob_iv, now, now),
    )
    conn.commit()
    cur = conn.execute("SELECT * FROM environments WHERE extid = ?", (extid,))
    env = _fetchone_dict(cur)
    conn.close()
    return env


def get_environments(session_hash):
    """Get all environments for a session."""
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM environments WHERE session_hash = ? ORDER BY created_at ASC",
        (session_hash,),
    )
    rows = _fetchall_dict(cur)
    conn.close()
    return rows


def get_environment_by_extid(extid, session_hash):
    """Get a single environment by extid, scoped to session."""
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM environments WHERE extid = ? AND session_hash = ?",
        (extid, session_hash),
    )
    env = _fetchone_dict(cur)
    conn.close()
    return env


def update_environment(extid, session_hash, **fields):
    """Update environment. Returns None if not found. Returns 'skipped' if blob_hash unchanged."""
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM environments WHERE extid = ? AND session_hash = ?",
        (extid, session_hash),
    )
    existing = _fetchone_dict(cur)
    if not existing:
        conn.close()
        return None

    # Dedup: if blob_hash unchanged, skip blob fields but keep metadata updates
    blob_keys = {"blob_hash", "encrypted_blob", "blob_iv"}
    if "blob_hash" in fields and fields["blob_hash"] is not None:
        if existing.get("blob_hash") == fields["blob_hash"]:
            fields = {k: v for k, v in fields.items() if k not in blob_keys}
            if not fields:
                conn.close()
                return "skipped"

    set_parts = []
    values = []
    for key in ("name", "blob_hash", "encrypted_blob", "blob_iv"):
        if key in fields:
            set_parts.append(f"{key} = ?")
            values.append(fields[key])

    if not set_parts:
        conn.close()
        return existing

    set_parts.append("updated_at = ?")
    values.append(_now())
    values.extend([extid, session_hash])

    conn.execute(
        f"UPDATE environments SET {', '.join(set_parts)} WHERE extid = ? AND session_hash = ?",
        values,
    )
    conn.commit()
    cur2 = conn.execute("SELECT * FROM environments WHERE extid = ?", (extid,))
    env = _fetchone_dict(cur2)
    conn.close()
    return env


def delete_environment(extid, session_hash):
    """Delete environment. Returns True if deleted, False if not found."""
    conn = _connect()
    cur = conn.execute(
        "DELETE FROM environments WHERE extid = ? AND session_hash = ?",
        (extid, session_hash),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


# ── Endpoints ──


def create_endpoint(session_hash, extid=None, label='', group='', blob_hash=None, encrypted_blob=None, blob_iv=None):
    """Create a new endpoint. Server generates extid if not provided."""
    now = _now()
    if extid is None:
        extid = uuid7()
    conn = _connect()
    conn.execute(
        """INSERT INTO endpoints (extid, session_hash, label, "group", blob_hash, encrypted_blob, blob_iv, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (extid, session_hash, label, group, blob_hash, encrypted_blob, blob_iv, now, now),
    )
    conn.commit()
    cur = conn.execute("SELECT * FROM endpoints WHERE extid = ?", (extid,))
    ep = _fetchone_dict(cur)
    conn.close()
    return ep


def get_endpoints(session_hash):
    """Get all endpoints for a session."""
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM endpoints WHERE session_hash = ? ORDER BY created_at ASC",
        (session_hash,),
    )
    rows = _fetchall_dict(cur)
    conn.close()
    return rows


def get_endpoint_by_extid(extid, session_hash):
    """Get a single endpoint by extid, scoped to session."""
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM endpoints WHERE extid = ? AND session_hash = ?",
        (extid, session_hash),
    )
    ep = _fetchone_dict(cur)
    conn.close()
    return ep


def update_endpoint(extid, session_hash, **fields):
    """Update endpoint. Returns None if not found. Returns 'skipped' if blob_hash unchanged."""
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM endpoints WHERE extid = ? AND session_hash = ?",
        (extid, session_hash),
    )
    existing = _fetchone_dict(cur)
    if not existing:
        conn.close()
        return None

    # Dedup: if blob_hash unchanged, skip blob fields but keep metadata updates
    blob_keys = {"blob_hash", "encrypted_blob", "blob_iv"}
    if "blob_hash" in fields and fields["blob_hash"] is not None:
        if existing.get("blob_hash") == fields["blob_hash"]:
            fields = {k: v for k, v in fields.items() if k not in blob_keys}
            if not fields:
                conn.close()
                return "skipped"

    set_parts = []
    values = []
    for key in ("label", "group", "blob_hash", "encrypted_blob", "blob_iv"):
        if key in fields:
            col = f'"{key}"' if key == "group" else key
            set_parts.append(f"{col} = ?")
            values.append(fields[key])

    if not set_parts:
        conn.close()
        return existing

    set_parts.append("updated_at = ?")
    values.append(_now())
    values.extend([extid, session_hash])

    conn.execute(
        f"UPDATE endpoints SET {', '.join(set_parts)} WHERE extid = ? AND session_hash = ?",
        values,
    )
    conn.commit()
    cur2 = conn.execute("SELECT * FROM endpoints WHERE extid = ?", (extid,))
    ep = _fetchone_dict(cur2)
    conn.close()
    return ep


def delete_endpoint(extid, session_hash):
    """Delete endpoint. Returns True if deleted, False if not found."""
    conn = _connect()
    cur = conn.execute(
        "DELETE FROM endpoints WHERE extid = ? AND session_hash = ?",
        (extid, session_hash),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


# Init on import
init_db()
