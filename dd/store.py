# drift-detector/dd/store.py

"""
SQLite / Turso storage for Drift Detector documents and sessions.

Document = a named container (like a notebook/runbook).
Session  = a numbered snapshot within a document. Each Save appends one.
           Contains the full cumulative state at that point.
           session_type is either 'save' (explicit) or 'autosave' (periodic).

Schema is deliberately flat and simple. JSON goes in as TEXT.

── Turso / libSQL swap ──
The connection factory (_connect) is the single point of change.
Set DD_DB_DRIVER=turso and DD_DB_PATH=libsql://your-db.turso.io
plus DD_DB_AUTH_TOKEN to switch backends. All SQL stays the same
because Turso is wire-compatible with SQLite.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from dd.config import DB_AUTH_TOKEN, DB_DRIVER, DB_PATH


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL DEFAULT 'Untitled',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id     INTEGER NOT NULL REFERENCES documents(id),
            session_number  INTEGER NOT NULL,
            session_type    TEXT NOT NULL DEFAULT 'save',
            endpoint_count  INTEGER NOT NULL DEFAULT 0,
            drift_count     INTEGER NOT NULL DEFAULT 0,
            ok_count        INTEGER NOT NULL DEFAULT 0,
            state_json      TEXT NOT NULL,
            state_hash      TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT,
            deleted_at      TEXT,
            UNIQUE(document_id, session_number)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_doc ON sessions(document_id)"
    )
    conn.commit()

    # Migrations for existing DBs
    cursor = conn.execute("PRAGMA table_info(sessions)")
    columns = [
        row[1] if isinstance(row, tuple) else row["name"]
        for row in cursor.fetchall()
    ]
    migrations = []
    if "session_type" not in columns:
        migrations.append(
            "ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'save'"
        )
    if "endpoint_count" not in columns:
        migrations.append(
            "ALTER TABLE sessions ADD COLUMN endpoint_count INTEGER NOT NULL DEFAULT 0"
        )
    if "drift_count" not in columns:
        migrations.append(
            "ALTER TABLE sessions ADD COLUMN drift_count INTEGER NOT NULL DEFAULT 0"
        )
    if "ok_count" not in columns:
        migrations.append(
            "ALTER TABLE sessions ADD COLUMN ok_count INTEGER NOT NULL DEFAULT 0"
        )
    if "state_hash" not in columns:
        migrations.append("ALTER TABLE sessions ADD COLUMN state_hash TEXT")
    if "updated_at" not in columns:
        migrations.append("ALTER TABLE sessions ADD COLUMN updated_at TEXT")
    if "deleted_at" not in columns:
        migrations.append("ALTER TABLE sessions ADD COLUMN deleted_at TEXT")
    for sql in migrations:
        conn.execute(sql)
    if migrations:
        conn.commit()

    conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash_state(state: dict) -> str:
    """Compute a stable hash of the state, excluding volatile fields."""
    s = {
        k: v
        for k, v in state.items()
        if k not in ("savedAt", "sessionNumber", "version")
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


# ── Documents ──


def create_document(title: str) -> dict:
    now = _now()
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO documents (title, created_at, updated_at) VALUES (?, ?, ?)",
        (title, now, now),
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


def list_documents() -> list[dict]:
    conn = _connect()
    cur = conn.execute("""
        SELECT d.*,
               COUNT(s.id) AS session_count,
               COUNT(CASE WHEN s.session_type = 'save' THEN 1 END) AS save_count,
               COUNT(CASE WHEN s.session_type = 'autosave' THEN 1 END) AS autosave_count
        FROM documents d
        LEFT JOIN sessions s ON s.document_id = d.id AND s.deleted_at IS NULL
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


# ── Sessions ──


def create_session(
    document_id: int, state: dict, session_type: str = "save"
) -> dict:
    assert session_type in ("save", "autosave"), (
        f"Invalid session_type: {session_type}"
    )
    now = _now()
    summary = _summarize_state(state)
    state_hash = _hash_state(state)
    conn = _connect()

    if session_type == "autosave":
        cur = conn.execute(
            "SELECT state_hash FROM sessions WHERE document_id = ? AND deleted_at IS NULL ORDER BY session_number DESC LIMIT 1",
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
        "SELECT COALESCE(MAX(session_number), 0) AS mx FROM sessions WHERE document_id = ?",
        (document_id,),
    )
    row = _fetchone_dict(cur)
    next_num = row["mx"] + 1

    state_json = json.dumps(state)
    conn.execute(
        """INSERT INTO sessions
           (document_id, session_number, session_type, endpoint_count, drift_count, ok_count, state_json, state_hash, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            document_id,
            next_num,
            session_type,
            summary["endpoint_count"],
            summary["drift_count"],
            summary["ok_count"],
            state_json,
            state_hash,
            now,
        ),
    )

    conn.execute(
        "UPDATE documents SET updated_at = ? WHERE id = ?",
        (now, document_id),
    )
    conn.commit()

    cur2 = conn.execute(
        """SELECT id, document_id, session_number, session_type,
                  endpoint_count, drift_count, ok_count, state_hash, created_at, updated_at
           FROM sessions WHERE document_id = ? AND session_number = ?""",
        (document_id, next_num),
    )
    session = _fetchone_dict(cur2)
    conn.close()
    return session


def list_sessions(document_id: int) -> list[dict]:
    conn = _connect()
    cur = conn.execute(
        """SELECT id, document_id, session_number, session_type,
                  endpoint_count, drift_count, ok_count, state_hash, created_at, updated_at
           FROM sessions WHERE document_id = ? AND deleted_at IS NULL
           ORDER BY session_number""",
        (document_id,),
    )
    rows = _fetchall_dict(cur)
    conn.close()
    return rows


def get_session(session_id: int) -> dict | None:
    conn = _connect()
    cur = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def get_session_by_number(document_id: int, session_number: int) -> dict | None:
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM sessions WHERE document_id = ? AND session_number = ?",
        (document_id, session_number),
    )
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def get_latest_session(document_id: int) -> dict | None:
    conn = _connect()
    cur = conn.execute(
        "SELECT * FROM sessions WHERE document_id = ? AND deleted_at IS NULL ORDER BY session_number DESC LIMIT 1",
        (document_id,),
    )
    d = _fetchone_dict(cur)
    conn.close()
    if not d:
        return None
    d["state"] = json.loads(d.pop("state_json"))
    return d


def update_session(
    document_id: int, session_number: int, state: dict
) -> dict | None:
    """Update an existing session's state in-place (for explicit re-saves)."""
    now = _now()
    summary = _summarize_state(state)
    state_hash = _hash_state(state)
    state_json = json.dumps(state)
    conn = _connect()
    cur = conn.execute(
        """UPDATE sessions
           SET state_json = ?, state_hash = ?, endpoint_count = ?,
               drift_count = ?, ok_count = ?, updated_at = ?
           WHERE document_id = ? AND session_number = ? AND deleted_at IS NULL""",
        (
            state_json,
            state_hash,
            summary["endpoint_count"],
            summary["drift_count"],
            summary["ok_count"],
            now,
            document_id,
            session_number,
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
        """SELECT id, document_id, session_number, session_type,
                  endpoint_count, drift_count, ok_count, state_hash, created_at, updated_at
           FROM sessions WHERE document_id = ? AND session_number = ?""",
        (document_id, session_number),
    )
    session = _fetchone_dict(cur2)
    conn.close()
    return session


def soft_delete_session(document_id: int, session_number: int) -> bool:
    conn = _connect()
    cur = conn.execute(
        "UPDATE sessions SET deleted_at = ? WHERE document_id = ? AND session_number = ? AND deleted_at IS NULL",
        (_now(), document_id, session_number),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


# ── Combined save operation ──


def save(
    state: dict,
    document_id: int | None = None,
    session_type: str = "save",
    session_number: int | None = None,
) -> dict:
    title = state.get("title") or "Untitled"

    if document_id is None:
        doc = create_document(title)
    else:
        doc = get_document(document_id)
        if not doc:
            doc = create_document(title)
        else:
            if title != doc["title"]:
                update_document_title(doc["id"], title)
                doc["title"] = title

    # For explicit saves with an existing session, update in-place
    if session_type == "save" and session_number:
        updated = update_session(doc["id"], session_number, state)
        if updated:
            return {"document": doc, "session": updated}
        # Fall through to create_session if update failed (deleted/missing)

    session = create_session(doc["id"], state, session_type)
    return {"document": doc, "session": session}


# Init on import
init_db()
