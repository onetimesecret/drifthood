# tests/test_cors.py

"""
Tests for CORS configuration in dd.app.

Validates that the CORS middleware is configured with restricted origins
rather than the insecure wildcard (*) default.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch, tmp_path):
    """Use a temporary database for each test."""
    db_path = str(tmp_path / "test_cors.db")
    monkeypatch.setattr("dd.config.DB_PATH", db_path)
    monkeypatch.setattr("dd.config.DB_DRIVER", "sqlite")

    import dd.store as store_module
    monkeypatch.setattr(store_module, "DB_PATH", db_path)
    monkeypatch.setattr(store_module, "DB_DRIVER", "sqlite")
    monkeypatch.setattr(store_module, "DB_AUTH_TOKEN", None)
    store_module.init_db()
    yield db_path


@pytest.fixture
def client():
    """Create a test client using the full app with CORS middleware."""
    from dd.app import create_app
    app = create_app()
    return TestClient(app)


class TestCORSConfiguration:
    """Tests for CORS middleware configuration."""

    def test_cors_allows_configured_origin(self, client):
        """Requests from configured origins should include proper CORS headers."""
        # Default CORS_ORIGINS includes localhost:5899
        response = client.options(
            "/api/auth/validate",
            headers={
                "Origin": "http://localhost:5899",
                "Access-Control-Request-Method": "GET",
            }
        )
        # OPTIONS preflight should succeed
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5899"

    def test_cors_rejects_unknown_origin(self, client):
        """Requests from unknown origins should not get CORS headers."""
        response = client.options(
            "/api/auth/validate",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            }
        )
        # The origin should NOT be reflected back
        assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"
        # Should not be a wildcard either
        assert response.headers.get("access-control-allow-origin") != "*"

    def test_cors_credentials_allowed(self, client):
        """CORS should allow credentials for session-based auth."""
        response = client.options(
            "/api/auth/validate",
            headers={
                "Origin": "http://localhost:5899",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_allowed_methods(self, client):
        """CORS should only allow configured HTTP methods."""
        response = client.options(
            "/api/auth/validate",
            headers={
                "Origin": "http://localhost:5899",
                "Access-Control-Request-Method": "GET",
            }
        )
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        # Should include standard REST methods
        assert "GET" in allowed_methods
        assert "POST" in allowed_methods
        assert "PUT" in allowed_methods
        assert "DELETE" in allowed_methods
        assert "OPTIONS" in allowed_methods

    def test_cors_allowed_headers(self, client):
        """CORS should only allow configured headers."""
        response = client.options(
            "/api/auth/validate",
            headers={
                "Origin": "http://localhost:5899",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            }
        )
        allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allowed_headers
        assert "content-type" in allowed_headers

    def test_cors_not_wildcard(self, client):
        """CORS origin should never be a wildcard."""
        response = client.options(
            "/api/auth/validate",
            headers={
                "Origin": "http://localhost:5899",
                "Access-Control-Request-Method": "GET",
            }
        )
        # Even for allowed origins, should not return wildcard
        assert response.headers.get("access-control-allow-origin") != "*"


class TestCORSConfigurable:
    """Tests for DD_CORS_ORIGINS environment variable configuration."""

    def test_custom_cors_origins(self, monkeypatch, tmp_path):
        """Custom CORS origins should be respected."""
        db_path = str(tmp_path / "test_cors_custom.db")
        monkeypatch.setattr("dd.config.DB_PATH", db_path)
        monkeypatch.setattr("dd.config.DB_DRIVER", "sqlite")
        # Set custom CORS origins
        monkeypatch.setattr("dd.config.CORS_ORIGINS", ["https://mydomain.com"])

        import dd.store as store_module
        monkeypatch.setattr(store_module, "DB_PATH", db_path)
        monkeypatch.setattr(store_module, "DB_DRIVER", "sqlite")
        monkeypatch.setattr(store_module, "DB_AUTH_TOKEN", None)
        store_module.init_db()

        # Need to reload app to pick up new CORS config
        from dd.app import create_app
        monkeypatch.setattr("dd.app.CORS_ORIGINS", ["https://mydomain.com"])
        app = create_app()
        client = TestClient(app)

        response = client.options(
            "/api/auth/validate",
            headers={
                "Origin": "https://mydomain.com",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert response.headers.get("access-control-allow-origin") == "https://mydomain.com"

    def test_localhost_5899_in_default_origins(self, monkeypatch, tmp_path):
        """Default CORS origins should include localhost:5899 for dev."""
        from dd.config import CORS_ORIGINS
        assert "http://localhost:5899" in CORS_ORIGINS or any("localhost:5899" in o for o in CORS_ORIGINS)

    def test_localhost_127_in_default_origins(self, monkeypatch, tmp_path):
        """Default CORS origins should include 127.0.0.1:5899 for dev."""
        from dd.config import CORS_ORIGINS
        assert "http://127.0.0.1:5899" in CORS_ORIGINS or any("127.0.0.1:5899" in o for o in CORS_ORIGINS)
