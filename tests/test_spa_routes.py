# tests/test_spa_routes.py

"""
Tests for SPA fallback routes in dd/app.py.

These routes serve index.html for client-side routing paths like:
- /s/{extid} - session detail views
- /e/{extid} - environment detail views
- /t/{extid} - shared testrun views

Each route validates extid format against the UUID regex and returns 404
for invalid formats. Some routes (like /s/{extid}) additionally validate
database existence.
"""

import hashlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch, tmp_path):
    """Use a temporary database for each test.

    Uses pytest's tmp_path fixture for proper isolation and cleanup.
    Patches the config module attributes directly to avoid importlib.reload().
    """
    db_path = str(tmp_path / "test_spa_routes.db")

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
def client(tmp_path):
    """Create a test client with the full app.

    Uses a temporary dist dir with a minimal index.html so tests
    don't depend on a frontend build existing on disk.
    """
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>test</body></html>")

    from dd.app import create_app
    app = create_app(dist_dir=str(dist_dir))
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


# ═══════════════════════════════════════════════════════════════════════════
# Testrun SPA fallback tests (/t/{extid})
# ═══════════════════════════════════════════════════════════════════════════


class TestTestrunSpaFallback:
    """Tests for the /t/{extid} SPA fallback route.

    This route serves index.html for shared testrun views.
    It only validates UUID format; database validation happens
    in the /api/share/{extid} endpoint.
    """

    def test_valid_uuid_returns_200_with_html(self, client):
        """A valid UUID format should return 200 with index.html content."""
        # UUIDv4 format
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        response = client.get(f"/t/{valid_uuid}")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_valid_uuidv7_returns_200(self, client):
        """UUIDv7 format (used by the app) should be accepted."""
        # UUIDv7 example - note the version digit (7) in position 13
        uuidv7 = "01906c73-7a8f-7b3d-8e9f-123456789abc"
        response = client.get(f"/t/{uuidv7}")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_uppercase_uuid_returns_200(self, client):
        """UUID regex uses re.I flag, so uppercase should work."""
        uppercase_uuid = "550E8400-E29B-41D4-A716-446655440000"
        response = client.get(f"/t/{uppercase_uuid}")

        assert response.status_code == 200

    def test_mixed_case_uuid_returns_200(self, client):
        """Mixed case UUIDs should be accepted."""
        mixed_case = "550e8400-E29B-41d4-A716-446655440000"
        response = client.get(f"/t/{mixed_case}")

        assert response.status_code == 200

    def test_invalid_uuid_too_short_returns_404(self, client):
        """UUID that's too short should return 404."""
        too_short = "550e8400-e29b-41d4-a716"
        response = client.get(f"/t/{too_short}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"

    def test_invalid_uuid_too_long_returns_404(self, client):
        """UUID that's too long should return 404."""
        too_long = "550e8400-e29b-41d4-a716-446655440000-extra"
        response = client.get(f"/t/{too_long}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"

    def test_invalid_uuid_wrong_format_returns_404(self, client):
        """String that doesn't match UUID format should return 404."""
        not_uuid = "not-a-valid-uuid-format"
        response = client.get(f"/t/{not_uuid}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"

    def test_invalid_uuid_missing_hyphens_returns_404(self, client):
        """UUID without hyphens should return 404."""
        no_hyphens = "550e8400e29b41d4a716446655440000"
        response = client.get(f"/t/{no_hyphens}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"

    def test_invalid_uuid_extra_hyphens_returns_404(self, client):
        """UUID with extra hyphens should return 404."""
        extra_hyphens = "550e-8400-e29b-41d4-a716-4466-5544-0000"
        response = client.get(f"/t/{extra_hyphens}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"

    def test_invalid_uuid_non_hex_chars_returns_404(self, client):
        """UUID with non-hex characters should return 404."""
        non_hex = "550e8400-e29b-41d4-a716-44665544zzzz"
        response = client.get(f"/t/{non_hex}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"

    def test_empty_extid_returns_404(self, client):
        """Empty extid path should return 404."""
        response = client.get("/t/")

        # FastAPI treats /t/ as a valid path with empty extid
        assert response.status_code == 404

    def test_path_traversal_attempt_returns_404(self, client):
        """Path traversal attempts should return 404."""
        response = client.get("/t/../../../etc/passwd")

        assert response.status_code == 404

    def test_sql_injection_attempt_returns_404(self, client):
        """SQL injection attempts should return 404 (not UUID format)."""
        response = client.get("/t/'; DROP TABLE testruns;--")

        assert response.status_code == 404

    def test_nonexistent_but_valid_uuid_returns_200(self, client):
        """A valid UUID that doesn't exist in DB should still return 200.

        The /t/{extid} route only validates format, not DB existence.
        DB validation happens in /api/share/{extid}.
        """
        # This UUID is valid format but doesn't exist
        nonexistent = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/t/{nonexistent}")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════════════════
# Environment SPA fallback tests (/e/{extid})
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvironmentSpaFallback:
    """Tests for the /e/{extid} SPA fallback route.

    Similar to /t/{extid}, this route only validates UUID format
    and serves index.html for valid UUIDs.
    """

    def test_valid_uuid_returns_200_with_html(self, client):
        """A valid UUID format should return 200 with index.html."""
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        response = client.get(f"/e/{valid_uuid}")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_invalid_uuid_returns_404(self, client):
        """Invalid UUID format should return 404."""
        response = client.get("/e/not-a-uuid")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"


# ═══════════════════════════════════════════════════════════════════════════
# Session SPA fallback tests (/s/{extid})
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionSpaFallback:
    """Tests for the /s/{extid} SPA fallback route.

    Unlike /t/{extid} and /e/{extid}, this route validates both
    UUID format AND database existence before returning index.html.
    """

    def test_valid_uuid_nonexistent_session_returns_404(self, client, clean_db):
        """A valid UUID that doesn't exist in sessions table returns 404."""
        nonexistent = "550e8400-e29b-41d4-a716-446655440000"
        response = client.get(f"/s/{nonexistent}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"

    def test_invalid_uuid_returns_404(self, client):
        """Invalid UUID format should return 404."""
        response = client.get("/s/not-a-uuid")

        assert response.status_code == 404
        assert response.json()["detail"] == "Not found"

    def test_existing_session_returns_200(self, client, store, clean_db):
        """An existing session should return 200 with index.html."""
        # Create a session directly in the database
        token = "test_token_for_session_spa"
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        session = store.create_session(token_hash)
        session_extid = session["extid"]

        response = client.get(f"/s/{session_extid}")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
