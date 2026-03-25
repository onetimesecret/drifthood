# tests/test_auth.py

"""
Tests for dd.auth API routes, specifically around session management
and token validation security.

SECURITY TESTS: validate_token must not create orphan sessions for
unknown tokens. This prevents database pollution from random Bearer
tokens sent by unauthenticated callers.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch, tmp_path):
    """Use a temporary database for each test.

    Uses pytest's tmp_path fixture for proper isolation and cleanup.
    Patches the config module attributes directly to avoid importlib.reload().
    """
    db_path = str(tmp_path / "test_auth.db")

    # Patch config attributes before any store operations
    monkeypatch.setattr("dd.config.DB_PATH", db_path)
    monkeypatch.setattr("dd.config.DB_DRIVER", "sqlite")

    # Import store and patch its module-level references
    import dd.store as store_module

    # Patch the store module's cached config values
    monkeypatch.setattr(store_module, "DB_PATH", db_path)
    monkeypatch.setattr(store_module, "DB_DRIVER", "sqlite")
    monkeypatch.setattr(store_module, "DB_AUTH_TOKEN", None)

    # Initialize the database with fresh tables
    store_module.init_db()

    yield db_path
    # tmp_path fixture handles cleanup automatically


@pytest.fixture
def store():
    """Get the store module (after DB patching)."""
    import dd.store as store_module
    return store_module


@pytest.fixture
def client():
    """Create a test client with the auth router."""
    from dd.auth import router as auth_router
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


@pytest.fixture
def clean_db(store):
    """Clean database tables before each test.

    Tables are guaranteed to exist because use_temp_db runs init_db().
    """
    conn = store._connect()
    conn.execute("DELETE FROM testruns")
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()
    yield


# =============================================================================
# validate_token orphan session prevention tests
# =============================================================================


class TestValidateTokenNoOrphanSessions:
    """Tests that validate_token does not create orphan sessions.

    SECURITY: Before the fix (task 35), validate_token would create a new
    session row for any token hash that didn't exist. This allowed attackers
    to pollute the database with unlimited session rows by sending random
    Bearer tokens.

    The fix ensures validate_token returns {valid: False} for unknown tokens
    without creating any session rows.
    """

    def test_validate_unknown_token_returns_invalid(self, client, clean_db):
        """GET /api/auth/validate with unknown token returns valid=False."""
        response = client.get(
            "/api/auth/validate",
            headers={"Authorization": "Bearer unknown_random_token_abc123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["documentCount"] == 0
        assert data["extid"] is None

    def test_validate_unknown_token_creates_no_session(self, client, store, clean_db):
        """GET /api/auth/validate with unknown token does not create session row."""
        # Count sessions before
        conn = store._connect()
        cur = conn.execute("SELECT COUNT(*) FROM sessions")
        count_before = cur.fetchone()[0]
        conn.close()

        # Call validate with random token
        client.get(
            "/api/auth/validate",
            headers={"Authorization": "Bearer some_random_token_xyz789"},
        )

        # Count sessions after - should be unchanged
        conn = store._connect()
        cur = conn.execute("SELECT COUNT(*) FROM sessions")
        count_after = cur.fetchone()[0]
        conn.close()

        assert count_after == count_before, (
            f"Session count changed from {count_before} to {count_after}. "
            "validate_token should not create sessions for unknown tokens."
        )

    def test_validate_multiple_unknown_tokens_creates_no_sessions(
        self, client, store, clean_db
    ):
        """Multiple validate calls with different unknown tokens create no sessions."""
        # Count sessions before
        conn = store._connect()
        cur = conn.execute("SELECT COUNT(*) FROM sessions")
        count_before = cur.fetchone()[0]
        conn.close()

        # Call validate with multiple different random tokens
        for i in range(5):
            client.get(
                "/api/auth/validate",
                headers={"Authorization": f"Bearer random_token_{i}_asdf"},
            )

        # Count sessions after - should be unchanged
        conn = store._connect()
        cur = conn.execute("SELECT COUNT(*) FROM sessions")
        count_after = cur.fetchone()[0]
        conn.close()

        assert count_after == count_before, (
            f"Session count changed from {count_before} to {count_after} after "
            "5 validate calls. No sessions should be created for unknown tokens."
        )

    def test_validate_valid_token_returns_valid(self, client, clean_db):
        """GET /api/auth/validate with valid auth key returns valid=True.

        The /api/auth/token endpoint returns a raw token + extid.
        The client must derive the auth key via HKDF(token, extid, "auth")
        and send that in the Bearer header (not the raw token).
        """
        from dd.auth import derive_auth_key

        # First create a real token via /api/auth/token
        create_response = client.post("/api/auth/token")
        assert create_response.status_code == 200
        token_data = create_response.json()
        token = token_data["token"]
        extid = token_data["extid"]

        # Derive the auth key (as the frontend would)
        auth_key = derive_auth_key(token, extid)

        # Now validate using the derived auth key
        validate_response = client.get(
            "/api/auth/validate",
            headers={"Authorization": f"Bearer {auth_key}"},
        )
        assert validate_response.status_code == 200
        data = validate_response.json()
        assert data["valid"] is True
        assert data["extid"] == extid
        assert data["documentCount"] == 0  # No documents yet

    def test_validate_missing_auth_header_returns_invalid(self, client, clean_db):
        """GET /api/auth/validate without Authorization header returns valid=False."""
        response = client.get("/api/auth/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["documentCount"] == 0
        assert data["extid"] is None

    def test_validate_malformed_auth_header_returns_invalid(self, client, clean_db):
        """GET /api/auth/validate with malformed auth header returns valid=False."""
        # Missing "Bearer " prefix
        response = client.get(
            "/api/auth/validate",
            headers={"Authorization": "some_token_without_bearer"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["documentCount"] == 0
        assert data["extid"] is None
