# drift-detector/tests/test_share.py

"""
Tests for is_public share visibility feature.

SECURITY MODEL:
Share links rely on UUIDv7 extids being unguessable. However, UUIDv7 has a
48-bit timestamp (predictable for an attacker who knows when testruns were
created) plus only ~74 bits of randomness. The is_public flag provides
explicit opt-in rather than security-through-obscurity: even if an attacker
guesses a valid extid, they only see data the owner chose to share.

Test coverage:
- Private testrun (is_public=false) returns 404 on share route
- Public testrun (is_public=true) returns data on share route
- Toggling is_public requires authentication
- Deleted testrun stays 404 even if is_public=true
- Non-owner cannot toggle is_public
"""

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch, tmp_path):
    """Use a temporary database for each test."""
    db_path = str(tmp_path / "test_share.db")

    monkeypatch.setattr("dd.config.DB_PATH", db_path)
    monkeypatch.setattr("dd.config.DB_DRIVER", "sqlite")

    import dd.store as store_module

    monkeypatch.setattr(store_module, "DB_PATH", db_path)
    monkeypatch.setattr(store_module, "DB_DRIVER", "sqlite")
    monkeypatch.setattr(store_module, "DB_AUTH_TOKEN", None)

    store_module.init_db()

    yield db_path


@pytest.fixture
def store():
    """Get the store module (after DB patching)."""
    import dd.store as store_module
    return store_module


@pytest.fixture
def client():
    """Create a test client with the documents router."""
    from dd.documents import router as documents_router
    app = FastAPI()
    app.include_router(documents_router)
    return TestClient(app)


@pytest.fixture
def clean_db(store):
    """Clean database tables before each test."""
    conn = store._connect()
    conn.execute("DELETE FROM testruns")
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()
    yield


@pytest.fixture
def sample_testrun_state():
    """Minimal testrun state for testing."""
    return {
        "endpoints": [
            {"method": "GET", "path": "/api/status", "state": "done-ok"},
        ]
    }


def _hash_token(token: str) -> str:
    """Hash a token for storage (matches dd.auth.hash_token)."""
    return hashlib.sha256(token.encode()).hexdigest()


def _make_auth_header(token: str) -> dict:
    """Create Authorization header from a raw token."""
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# Share endpoint with is_public flag
# =============================================================================


class TestShareVisibility:
    """Tests for is_public-based share visibility."""

    def test_private_testrun_returns_404(self, client, store, sample_testrun_state, clean_db):
        """A private testrun (is_public=false, the default) returns 404 on share route.

        This is the core security test: testruns are private by default.
        """
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Default is_public=false, so share endpoint should return 404
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Testrun not found"

    def test_public_testrun_returns_200(self, client, store, sample_testrun_state, clean_db):
        """A public testrun (is_public=true) returns data on share route."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Make the testrun public
        store.set_testrun_public(testrun_extid, True)

        # Now share endpoint should return 200 with data
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200
        data = response.json()
        assert "testrun" in data
        assert "document" in data
        assert data["testrun"]["extid"] == testrun_extid

    def test_deleted_testrun_returns_404_even_if_public(
        self, client, store, sample_testrun_state, clean_db
    ):
        """A deleted testrun returns 404 even if is_public=true.

        Deletion takes precedence over visibility.
        """
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Make the testrun public
        store.set_testrun_public(testrun_extid, True)

        # Verify it's accessible
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200

        # Now soft-delete it
        deleted = store.soft_delete_testrun_by_extid(testrun_extid)
        assert deleted is True

        # Should now return 404
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Testrun not found"

    def test_nonexistent_extid_returns_404(self, client, clean_db):
        """A non-existent testrun extid returns 404."""
        fake_extid = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/share/{fake_extid}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Testrun not found"

    def test_toggle_public_to_private(self, client, store, sample_testrun_state, clean_db):
        """A testrun can be toggled from public back to private."""
        token = "owner_token"
        session_hash = _hash_token(token)

        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        testrun_extid = result["testrun"]["extid"]

        # Make it public
        store.set_testrun_public(testrun_extid, True)

        # Verify accessible
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200

        # Toggle back to private via API
        response = client.patch(
            f"/api/testruns/{testrun_extid}/public",
            json={"isPublic": False},
            headers=_make_auth_header(token),
        )
        assert response.status_code == 200
        assert response.json()["isPublic"] is False

        # Now share endpoint should return 404
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 404


# =============================================================================
# Toggle endpoint authentication
# =============================================================================


class TestTogglePublicAuth:
    """Tests for authentication on the toggle public endpoint."""

    def test_toggle_requires_auth(self, client, store, sample_testrun_state, clean_db):
        """Toggling is_public requires authentication (no auth = 401)."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Attempt to toggle without auth header
        response = client.patch(
            f"/api/testruns/{testrun_extid}/public",
            json={"isPublic": True},
        )
        assert response.status_code == 401

    def test_non_owner_cannot_toggle(self, client, store, sample_testrun_state, clean_db):
        """A non-owner cannot toggle is_public (returns 404 to prevent info leak)."""
        owner_token = "owner_token"
        owner_session_hash = _hash_token(owner_token)

        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=owner_session_hash,
        )
        testrun_extid = result["testrun"]["extid"]

        # Different user tries to toggle
        attacker_token = "attacker_token"
        response = client.patch(
            f"/api/testruns/{testrun_extid}/public",
            json={"isPublic": True},
            headers=_make_auth_header(attacker_token),
        )
        # Returns 404 (not 403) to avoid confirming the extid exists
        assert response.status_code == 404

    def test_owner_can_toggle_public_true(self, client, store, sample_testrun_state, clean_db):
        """The owner can toggle is_public to true via API."""
        token = "owner_token"
        session_hash = _hash_token(token)

        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        testrun_extid = result["testrun"]["extid"]

        # Owner toggles to public
        response = client.patch(
            f"/api/testruns/{testrun_extid}/public",
            json={"isPublic": True},
            headers=_make_auth_header(token),
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["isPublic"] is True

        # Verify share endpoint now works
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200

    def test_toggle_nonexistent_testrun_returns_404(self, client, clean_db):
        """Toggling a non-existent testrun returns 404."""
        token = "some_token"
        fake_extid = "00000000-0000-0000-0000-000000000000"

        response = client.patch(
            f"/api/testruns/{fake_extid}/public",
            json={"isPublic": True},
            headers=_make_auth_header(token),
        )
        assert response.status_code == 404

    def test_toggle_deleted_testrun_returns_404(self, client, store, sample_testrun_state, clean_db):
        """Toggling a deleted testrun returns 404."""
        token = "owner_token"
        session_hash = _hash_token(token)

        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        testrun_extid = result["testrun"]["extid"]

        # Delete the testrun
        store.soft_delete_testrun_by_extid(testrun_extid)

        # Try to toggle - should fail
        response = client.patch(
            f"/api/testruns/{testrun_extid}/public",
            json={"isPublic": True},
            headers=_make_auth_header(token),
        )
        assert response.status_code == 404


# =============================================================================
# Store-level tests for is_public
# =============================================================================


class TestStoreIsPublic:
    """Direct tests for store.py is_public functions."""

    def test_set_testrun_public_returns_true_on_success(
        self, store, sample_testrun_state, clean_db
    ):
        """set_testrun_public returns True when successful."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        ok = store.set_testrun_public(testrun_extid, True)
        assert ok is True

    def test_set_testrun_public_returns_false_for_nonexistent(self, store, clean_db):
        """set_testrun_public returns False for non-existent extid."""
        fake_extid = "00000000-0000-0000-0000-000000000000"
        ok = store.set_testrun_public(fake_extid, True)
        assert ok is False

    def test_set_testrun_public_returns_false_for_deleted(
        self, store, sample_testrun_state, clean_db
    ):
        """set_testrun_public returns False for deleted testrun."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        store.soft_delete_testrun_by_extid(testrun_extid)

        ok = store.set_testrun_public(testrun_extid, True)
        assert ok is False

    def test_get_public_testrun_returns_none_for_private(
        self, store, sample_testrun_state, clean_db
    ):
        """get_public_testrun_by_extid returns None for private testrun."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Default is private
        testrun = store.get_public_testrun_by_extid(testrun_extid)
        assert testrun is None

    def test_get_public_testrun_returns_data_for_public(
        self, store, sample_testrun_state, clean_db
    ):
        """get_public_testrun_by_extid returns data for public testrun."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        store.set_testrun_public(testrun_extid, True)

        testrun = store.get_public_testrun_by_extid(testrun_extid)
        assert testrun is not None
        assert testrun["extid"] == testrun_extid
        assert testrun["is_public"] == 1

    def test_get_public_testrun_returns_none_for_deleted_public(
        self, store, sample_testrun_state, clean_db
    ):
        """get_public_testrun_by_extid returns None for deleted public testrun."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        store.set_testrun_public(testrun_extid, True)
        store.soft_delete_testrun_by_extid(testrun_extid)

        testrun = store.get_public_testrun_by_extid(testrun_extid)
        assert testrun is None

    def test_is_public_defaults_to_false(self, store, sample_testrun_state, clean_db):
        """New testruns have is_public=0 by default."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Use get_active (not get_public) to check the raw value
        testrun = store.get_active_testrun_by_extid(testrun_extid)
        assert testrun is not None
        assert testrun.get("is_public") == 0
