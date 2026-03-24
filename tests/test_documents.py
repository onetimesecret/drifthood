# drift-detector/tests/test_documents.py

"""
Tests for dd.documents API routes, with focus on security-critical
share endpoint behavior.

SECURITY TESTS: The share endpoint (/api/share/{testrun_extid}) must
return 404 for deleted testruns to prevent information disclosure.
"""

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch, tmp_path):
    """Use a temporary database for each test.

    Uses pytest's tmp_path fixture for proper isolation and cleanup.
    Patches the config module attributes directly to avoid importlib.reload().
    """
    db_path = str(tmp_path / "test_documents.db")

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
    """Create a test client with the documents router."""
    from dd.documents import router as documents_router
    app = FastAPI()
    app.include_router(documents_router)
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


@pytest.fixture
def sample_testrun_state():
    """Minimal testrun state for testing."""
    return {
        "endpoints": [
            {"method": "GET", "path": "/api/status", "state": "done-ok"},
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════
# Share endpoint security tests (/api/share/{testrun_extid})
# ═══════════════════════════════════════════════════════════════════════════


class TestShareEndpointSecurity:
    """Security tests for the share endpoint.

    CRITICAL: These tests verify that deleted testruns cannot be accessed
    via the share endpoint. This prevents information disclosure when a
    user deletes a testrun expecting it to become inaccessible.

    NOTE: Testruns must have is_public=true to be accessible via the share
    endpoint. See test_share.py for comprehensive is_public tests.
    """

    def test_active_testrun_returns_200_with_data(self, client, store, sample_testrun_state, clean_db):
        """An active (non-deleted), public testrun should be accessible via share endpoint."""
        # Create a document and testrun directly in the database
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Make the testrun public (required for share endpoint)
        store.set_testrun_public(testrun_extid, True)

        # Access via share endpoint
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200
        data = response.json()
        assert "testrun" in data
        assert "document" in data
        assert data["testrun"]["extid"] == testrun_extid

    def test_deleted_testrun_returns_404(self, client, store, sample_testrun_state, clean_db):
        """A soft-deleted testrun MUST return 404 via share endpoint.

        SECURITY: This is critical to prevent information disclosure.
        When a user deletes a testrun, they expect it to be inaccessible.
        """
        # Create a document and testrun
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Make it public first
        store.set_testrun_public(testrun_extid, True)

        # Soft-delete the testrun
        deleted = store.soft_delete_testrun_by_extid(testrun_extid)
        assert deleted is True

        # Attempt to access via share endpoint - should be 404
        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Testrun not found"

    def test_nonexistent_extid_returns_404(self, client, clean_db):
        """A non-existent testrun extid should return 404."""
        fake_extid = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/share/{fake_extid}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Testrun not found"

    def test_invalid_extid_format_returns_404(self, client, clean_db):
        """An invalid extid format should return 404."""
        response = client.get("/api/share/not-a-uuid")
        # The route accepts any string, but store.get_active_testrun_by_extid
        # will return None for invalid format, resulting in 404
        assert response.status_code == 404

    def test_share_endpoint_returns_document_metadata(self, client, store, sample_testrun_state, clean_db):
        """Share endpoint should include document metadata (title, extid)."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]
        doc_extid = result["document"]["extid"]

        # Make the testrun public (required for share endpoint)
        store.set_testrun_public(testrun_extid, True)

        # Update document title
        store.update_document_title(result["document"]["id"], "Test Document Title")

        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200
        data = response.json()
        assert data["document"]["extid"] == doc_extid
        assert data["document"]["title"] == "Test Document Title"

    def test_share_endpoint_excludes_internal_ids(self, client, store, sample_testrun_state, clean_db):
        """Share endpoint should NOT expose internal database IDs."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
        )
        testrun_extid = result["testrun"]["extid"]

        # Make the testrun public (required for share endpoint)
        store.set_testrun_public(testrun_extid, True)

        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200
        data = response.json()

        # Internal IDs should be excluded
        assert "id" not in data["testrun"]
        assert "document_id" not in data["testrun"]
        assert "id" not in data["document"]
        assert "session_hash" not in data["document"]

    def test_encrypted_testrun_indicates_encrypted_blob(self, client, store, sample_testrun_state, clean_db):
        """Share endpoint should return encrypted_blob field when testrun is encrypted.

        This allows the frontend to display a notice that the testrun is encrypted
        and cannot be decrypted without the client-side key.
        """
        # Create a testrun with encrypted blob data
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
            blob_hash="abc123hash",
            encrypted_blob="encrypted_data_here",
            blob_iv="iv_value",
        )
        testrun_extid = result["testrun"]["extid"]

        # Make the testrun public (required for share endpoint)
        store.set_testrun_public(testrun_extid, True)

        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200
        data = response.json()

        # Encrypted blob fields should be present in response
        testrun = data["testrun"]
        assert "encrypted_blob" in testrun
        assert testrun["encrypted_blob"] == "encrypted_data_here"
        assert "blob_iv" in testrun or "blobIv" in testrun  # camelCase variant

    def test_unencrypted_testrun_has_state_data(self, client, store, sample_testrun_state, clean_db):
        """Share endpoint returns state data for unencrypted testruns."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="test_session_hash",
            # No blob_* parameters = unencrypted
        )
        testrun_extid = result["testrun"]["extid"]

        # Make the testrun public (required for share endpoint)
        store.set_testrun_public(testrun_extid, True)

        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200
        data = response.json()

        testrun = data["testrun"]
        # State should be accessible for unencrypted testruns
        assert "state" in testrun
        assert testrun["state"]["endpoints"][0]["method"] == "GET"

    def test_share_no_sensitive_session_hash_leaked(self, client, store, sample_testrun_state, clean_db):
        """Share endpoint must never leak session_hash (owner identifier)."""
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="secret_session_hash_value",
        )
        testrun_extid = result["testrun"]["extid"]

        # Make the testrun public (required for share endpoint)
        store.set_testrun_public(testrun_extid, True)

        response = client.get(f"/api/share/{testrun_extid}")
        assert response.status_code == 200
        data = response.json()

        # session_hash must not appear anywhere in the response
        response_text = response.text
        assert "secret_session_hash_value" not in response_text
        assert "session_hash" not in data.get("testrun", {})
        assert "sessionHash" not in data.get("testrun", {})


# ═══════════════════════════════════════════════════════════════════════════
# Diff route security tests (/api/documents/{doc_extid}/diff)
# ═══════════════════════════════════════════════════════════════════════════


class TestDiffRouteSecurity:
    """Security tests for the diff route.

    CRITICAL: These tests verify that deleted testruns cannot be compared
    via the diff route. Both testrun A and testrun B must be active (not
    soft-deleted) for the diff operation to succeed.
    """

    @staticmethod
    def _make_auth_header(token: str) -> dict:
        """Create Authorization header from a raw token."""
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash a token for storage (matches dd.auth.hash_token)."""
        return hashlib.sha256(token.encode()).hexdigest()

    def test_diff_active_testruns_returns_200(self, client, store, sample_testrun_state, clean_db):
        """Diffing two active testruns should succeed."""
        # Use a token and derive session_hash from it
        token = "test_token_for_diff_route"
        session_hash = self._hash_token(token)

        # Create document with two testruns
        result1 = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        doc_extid = result1["document"]["extid"]
        testrun_a_extid = result1["testrun"]["extid"]

        result2 = store.save(
            sample_testrun_state,
            document_extid=doc_extid,
            testrun_type="save",
            session_hash=session_hash,
        )
        testrun_b_extid = result2["testrun"]["extid"]

        # Diff should succeed
        response = client.get(
            f"/api/documents/{doc_extid}/diff?a={testrun_a_extid}&b={testrun_b_extid}",
            headers=self._make_auth_header(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert "diff" in data
        assert "testrun_a" in data
        assert "testrun_b" in data

    def test_diff_deleted_testrun_a_returns_404(self, client, store, sample_testrun_state, clean_db):
        """Diffing with a deleted testrun A MUST return 404.

        SECURITY: Prevents information disclosure about deleted testruns.
        """
        token = "test_token_for_diff_deleted_a"
        session_hash = self._hash_token(token)

        # Create document with two testruns
        result1 = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        doc_extid = result1["document"]["extid"]
        testrun_a_extid = result1["testrun"]["extid"]

        result2 = store.save(
            sample_testrun_state,
            document_extid=doc_extid,
            testrun_type="save",
            session_hash=session_hash,
        )
        testrun_b_extid = result2["testrun"]["extid"]

        # Delete testrun A
        store.soft_delete_testrun_by_extid(testrun_a_extid)

        # Diff should fail with 404
        response = client.get(
            f"/api/documents/{doc_extid}/diff?a={testrun_a_extid}&b={testrun_b_extid}",
            headers=self._make_auth_header(token),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Testrun A not found"

    def test_diff_deleted_testrun_b_returns_404(self, client, store, sample_testrun_state, clean_db):
        """Diffing with a deleted testrun B MUST return 404.

        SECURITY: Prevents information disclosure about deleted testruns.
        """
        token = "test_token_for_diff_deleted_b"
        session_hash = self._hash_token(token)

        # Create document with two testruns
        result1 = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        doc_extid = result1["document"]["extid"]
        testrun_a_extid = result1["testrun"]["extid"]

        result2 = store.save(
            sample_testrun_state,
            document_extid=doc_extid,
            testrun_type="save",
            session_hash=session_hash,
        )
        testrun_b_extid = result2["testrun"]["extid"]

        # Delete testrun B
        store.soft_delete_testrun_by_extid(testrun_b_extid)

        # Diff should fail with 404
        response = client.get(
            f"/api/documents/{doc_extid}/diff?a={testrun_a_extid}&b={testrun_b_extid}",
            headers=self._make_auth_header(token),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Testrun B not found"

    def test_diff_both_deleted_testruns_returns_404(self, client, store, sample_testrun_state, clean_db):
        """Diffing when both testruns are deleted MUST return 404."""
        token = "test_token_for_diff_both_deleted"
        session_hash = self._hash_token(token)

        # Create document with two testruns
        result1 = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        doc_extid = result1["document"]["extid"]
        testrun_a_extid = result1["testrun"]["extid"]

        result2 = store.save(
            sample_testrun_state,
            document_extid=doc_extid,
            testrun_type="save",
            session_hash=session_hash,
        )
        testrun_b_extid = result2["testrun"]["extid"]

        # Delete both testruns
        store.soft_delete_testrun_by_extid(testrun_a_extid)
        store.soft_delete_testrun_by_extid(testrun_b_extid)

        # Diff should fail with 404 (testrun A checked first)
        response = client.get(
            f"/api/documents/{doc_extid}/diff?a={testrun_a_extid}&b={testrun_b_extid}",
            headers=self._make_auth_header(token),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Testrun A not found"

    def test_diff_nonexistent_document_returns_404(self, client, clean_db):
        """Diff with non-existent document returns 404."""
        token = "test_token_for_diff_no_doc"
        fake_doc_extid = "00000000-0000-0000-0000-000000000000"
        fake_testrun_a = "00000000-0000-0000-0000-000000000001"
        fake_testrun_b = "00000000-0000-0000-0000-000000000002"

        response = client.get(
            f"/api/documents/{fake_doc_extid}/diff?a={fake_testrun_a}&b={fake_testrun_b}",
            headers=self._make_auth_header(token),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found"

    def test_diff_testrun_wrong_document_returns_400(self, client, store, sample_testrun_state, clean_db):
        """Testrun belonging to different document returns 400."""
        token = "test_token_for_diff_wrong_doc"
        session_hash = self._hash_token(token)

        # Create two separate documents with testruns
        result1 = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        doc1_extid = result1["document"]["extid"]
        testrun_doc1 = result1["testrun"]["extid"]

        result2 = store.save(
            sample_testrun_state,
            document_extid=None,  # Creates new document
            testrun_type="save",
            session_hash=session_hash,
        )
        testrun_doc2 = result2["testrun"]["extid"]

        # Try to diff testruns from different documents
        response = client.get(
            f"/api/documents/{doc1_extid}/diff?a={testrun_doc1}&b={testrun_doc2}",
            headers=self._make_auth_header(token),
        )
        assert response.status_code == 400
        assert "does not belong to this document" in response.json()["detail"]

    def test_diff_wrong_session_returns_404(self, client, store, sample_testrun_state, clean_db):
        """Diff with wrong session ownership returns 404 (document not found)."""
        token_owner = "owner_token"
        token_other = "other_token"
        owner_hash = self._hash_token(token_owner)

        # Create document with owner's session
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=owner_hash,
        )
        doc_extid = result["document"]["extid"]
        testrun_extid = result["testrun"]["extid"]

        # Different session tries to access - should get 404
        response = client.get(
            f"/api/documents/{doc_extid}/diff?a={testrun_extid}&b={testrun_extid}",
            headers=self._make_auth_header(token_other),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found"

    def test_diff_response_contains_complete_data(self, client, store, clean_db):
        """Successful diff returns complete testrun data and diff results."""
        token = "test_token_complete_data"
        session_hash = self._hash_token(token)

        # Create document with two testruns with different states
        state_a = {
            "endpoints": [
                {"method": "GET", "path": "/api/status", "state": "done-ok"},
                {"method": "POST", "path": "/api/old", "state": "done-drift"},
            ]
        }
        state_b = {
            "endpoints": [
                {"method": "GET", "path": "/api/status", "state": "done-drift"},  # changed
                {"method": "PUT", "path": "/api/new", "state": "done-ok"},  # added
            ]
        }

        result_a = store.save(state_a, document_extid=None, testrun_type="save", session_hash=session_hash)
        doc_extid = result_a["document"]["extid"]
        testrun_a_extid = result_a["testrun"]["extid"]

        result_b = store.save(state_b, document_extid=doc_extid, testrun_type="save", session_hash=session_hash)
        testrun_b_extid = result_b["testrun"]["extid"]

        response = client.get(
            f"/api/documents/{doc_extid}/diff?a={testrun_a_extid}&b={testrun_b_extid}",
            headers=self._make_auth_header(token),
        )
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "diff" in data
        assert "testrun_a" in data
        assert "testrun_b" in data

        # Verify diff contains expected keys
        diff = data["diff"]
        assert "added" in diff
        assert "removed" in diff
        assert "changed" in diff
        assert "unchanged" in diff

        # Verify testrun data excludes internal IDs
        assert "id" not in data["testrun_a"]
        assert "document_id" not in data["testrun_a"]
        assert "extid" in data["testrun_a"]
        assert data["testrun_a"]["extid"] == testrun_a_extid

    def test_diff_same_testrun_twice(self, client, store, sample_testrun_state, clean_db):
        """Diffing same testrun against itself should return no changes."""
        token = "test_token_same_testrun"
        session_hash = self._hash_token(token)

        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash=session_hash,
        )
        doc_extid = result["document"]["extid"]
        testrun_extid = result["testrun"]["extid"]

        response = client.get(
            f"/api/documents/{doc_extid}/diff?a={testrun_extid}&b={testrun_extid}",
            headers=self._make_auth_header(token),
        )
        assert response.status_code == 200
        data = response.json()

        # Same testrun = no changes
        diff = data["diff"]
        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["changed"] == []
        # All endpoints should be unchanged
        assert len(diff["unchanged"]) == len(sample_testrun_state["endpoints"])

    def test_diff_no_auth_header_returns_401_or_422(self, client, store, sample_testrun_state, clean_db):
        """Diff without auth header should fail (401 or 422 depending on auth middleware)."""
        # Create a testrun (doesn't matter for this test)
        result = store.save(
            sample_testrun_state,
            document_extid=None,
            testrun_type="save",
            session_hash="any_hash",
        )
        doc_extid = result["document"]["extid"]
        testrun_extid = result["testrun"]["extid"]

        # No auth header
        response = client.get(
            f"/api/documents/{doc_extid}/diff?a={testrun_extid}&b={testrun_extid}",
        )
        # Should fail - either 401 (unauthorized) or 422/404 (validation/not found)
        assert response.status_code in (401, 404, 422)
