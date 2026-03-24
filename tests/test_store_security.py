# tests/test_store_security.py

"""
Security-critical tests for store.py.

These tests verify that soft-deleted resources are properly filtered
to prevent information disclosure via share links and public endpoints.
"""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch, tmp_path):
    """Use a temporary database for each test.

    Uses pytest's tmp_path fixture for proper isolation and cleanup.
    Patches the config module attributes directly to avoid importlib.reload().
    """
    db_path = str(tmp_path / "test_security.db")

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
def session_hash(store):
    """Create a test session and return its hash."""
    import hashlib
    token = "test_token_12345"
    session_hash = hashlib.sha256(token.encode()).hexdigest()
    store.create_session(session_hash)
    return session_hash


@pytest.fixture
def document(store, session_hash):
    """Create a test document."""
    doc = store.create_document(title="Test Document", session_hash=session_hash)
    return doc


class TestGetActiveTestrunByExtid:
    """Tests for get_active_testrun_by_extid security filtering."""

    def test_returns_active_testrun(self, store, document):
        """get_active_testrun_by_extid returns testrun when deleted_at IS NULL."""
        # Create a testrun (not deleted)
        state = {"endpoints": []}
        testrun = store.create_testrun(
            document["id"],
            state,
            testrun_type="save",
        )

        # Should find the active testrun
        result = store.get_active_testrun_by_extid(testrun["extid"])

        assert result is not None
        assert result["extid"] == testrun["extid"]
        assert result["document_id"] == document["id"]

    def test_returns_none_for_deleted_testrun(self, store, document):
        """get_active_testrun_by_extid returns None when deleted_at is set."""
        # Create and then delete a testrun
        state = {"endpoints": []}
        testrun = store.create_testrun(
            document["id"],
            state,
            testrun_type="save",
        )

        # Soft-delete the testrun
        deleted = store.soft_delete_testrun_by_extid(testrun["extid"])
        assert deleted is True

        # Should NOT find the deleted testrun
        result = store.get_active_testrun_by_extid(testrun["extid"])

        assert result is None

    def test_nonexistent_extid_returns_none(self, store):
        """get_active_testrun_by_extid returns None for unknown extid."""
        result = store.get_active_testrun_by_extid("nonexistent-extid-12345")
        assert result is None

    def test_plain_get_testrun_returns_deleted(self, store, document):
        """Contrast: get_testrun_by_extid (plain) returns deleted testruns.

        This test documents the difference between the two functions:
        - get_testrun_by_extid: returns ALL testruns (for admin/audit)
        - get_active_testrun_by_extid: filters deleted_at (for public routes)
        """
        # Create and delete a testrun
        state = {"endpoints": []}
        testrun = store.create_testrun(
            document["id"],
            state,
            testrun_type="save",
        )
        store.soft_delete_testrun_by_extid(testrun["extid"])

        # Plain get_testrun_by_extid SHOULD find it (for audit purposes)
        plain_result = store.get_testrun_by_extid(testrun["extid"])
        assert plain_result is not None
        assert plain_result["extid"] == testrun["extid"]

        # get_active_testrun_by_extid should NOT find it
        active_result = store.get_active_testrun_by_extid(testrun["extid"])
        assert active_result is None


class TestShareEndpointSecurity:
    """Integration tests verifying deleted testruns are not exposed via share endpoint."""

    def test_share_endpoint_rejects_deleted_testrun(self, store, document):
        """The share endpoint uses get_active_testrun_by_extid, so deleted testruns 404."""
        from fastapi.testclient import TestClient

        # Import and create app - store module is already patched by fixture
        import dd.app as app_module

        app = app_module.create_app()
        client = TestClient(app)

        # Create and delete a testrun
        state = {"endpoints": [{"method": "GET", "path": "/test", "state": "done-ok"}]}
        testrun = store.create_testrun(
            document["id"],
            state,
            testrun_type="save",
        )
        store.soft_delete_testrun_by_extid(testrun["extid"])

        # Attempt to access via share endpoint
        response = client.get(f"/api/share/{testrun['extid']}")

        # Should return 404, not the testrun data
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_share_endpoint_returns_active_testrun(self, store, document):
        """The share endpoint returns active, public testruns normally."""
        from fastapi.testclient import TestClient

        import dd.app as app_module

        app = app_module.create_app()
        client = TestClient(app)

        # Create an active testrun
        state = {"endpoints": [{"method": "GET", "path": "/test", "state": "done-ok"}]}
        testrun = store.create_testrun(
            document["id"],
            state,
            testrun_type="save",
        )

        # Make the testrun public (required for share endpoint)
        store.set_testrun_public(testrun["extid"], True)

        # Access via share endpoint
        response = client.get(f"/api/share/{testrun['extid']}")

        # Should return 200 with testrun data
        assert response.status_code == 200
        data = response.json()
        assert data["testrun"]["extid"] == testrun["extid"]
        assert data["document"]["title"] == "Test Document"
