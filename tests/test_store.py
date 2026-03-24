# tests/test_store.py

"""
Tests for store.py functions, with focus on diff_testruns and _normalize_path.
"""

import pytest
from dd.store import diff_testruns, _normalize_path


# ═══════════════════════════════════════════════════════════════════════════
# _normalize_path tests
# ═══════════════════════════════════════════════════════════════════════════


class TestNormalizePath:
    """Tests for _normalize_path which normalizes path params for endpoint identity.

    This function ensures that semantically identical endpoints are recognized
    as the same regardless of how path parameters are represented.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # OpenAPI template parameters
    # ─────────────────────────────────────────────────────────────────────────

    def test_template_param_id_normalized(self):
        """Template param {id} becomes {param}."""
        assert _normalize_path("/users/{id}") == "/users/{param}"

    def test_template_param_custom_name_normalized(self):
        """Template params with any name become {param}."""
        assert _normalize_path("/users/{user_id}") == "/users/{param}"
        assert _normalize_path("/orders/{order_uuid}") == "/orders/{param}"
        assert _normalize_path("/items/{itemKey}") == "/items/{param}"

    def test_multiple_template_params(self):
        """Multiple template params all become {param}."""
        assert _normalize_path("/users/{id}/posts/{post_id}") == "/users/{param}/posts/{param}"

    def test_template_param_already_param(self):
        """Template {param} stays {param}."""
        assert _normalize_path("/users/{param}") == "/users/{param}"

    # ─────────────────────────────────────────────────────────────────────────
    # Numeric segments
    # ─────────────────────────────────────────────────────────────────────────

    def test_numeric_segment_normalized(self):
        """Numeric segments like /123 become /{param}."""
        assert _normalize_path("/users/123") == "/users/{param}"

    def test_zero_is_numeric(self):
        """0 is treated as numeric."""
        assert _normalize_path("/items/0") == "/items/{param}"

    def test_long_numeric_id(self):
        """Long numeric IDs are normalized."""
        assert _normalize_path("/items/1234567890") == "/items/{param}"

    def test_numeric_with_leading_zeros(self):
        """Numeric with leading zeros is normalized."""
        assert _normalize_path("/items/007") == "/items/{param}"

    def test_negative_number_not_numeric(self):
        """Negative numbers are NOT recognized as numeric (no leading -)."""
        # isdigit() returns False for "-123"
        assert _normalize_path("/items/-123") == "/items/-123"

    def test_floating_point_not_numeric(self):
        """Floating point is NOT recognized as numeric."""
        assert _normalize_path("/items/3.14") == "/items/3.14"

    # ─────────────────────────────────────────────────────────────────────────
    # UUID segments
    # ─────────────────────────────────────────────────────────────────────────

    def test_uuid_standard_format_normalized(self):
        """Standard UUID (8-4-4-4-12 hex) becomes {param}."""
        assert _normalize_path("/users/550e8400-e29b-41d4-a716-446655440000") == "/users/{param}"

    def test_uuid_lowercase(self):
        """Lowercase UUID is normalized."""
        assert _normalize_path("/items/abcd1234-abcd-abcd-abcd-abcd12345678") == "/items/{param}"

    def test_uuid_uppercase(self):
        """Uppercase UUID is normalized."""
        assert _normalize_path("/items/ABCD1234-ABCD-ABCD-ABCD-ABCD12345678") == "/items/{param}"

    def test_uuid_mixed_case(self):
        """Mixed case UUID is normalized."""
        assert _normalize_path("/items/AbCd1234-aBcD-AbCd-aBcD-AbCd12345678") == "/items/{param}"

    def test_uuid_without_dashes_not_matched(self):
        """UUID without dashes is NOT recognized as UUID."""
        # 32 hex chars without dashes is just a long hex string
        assert _normalize_path("/items/550e8400e29b41d4a716446655440000") == "/items/550e8400e29b41d4a716446655440000"

    def test_uuid_with_extra_chars_not_matched(self):
        """UUID with extra characters is not matched."""
        assert _normalize_path("/items/550e8400-e29b-41d4-a716-446655440000X") == "/items/550e8400-e29b-41d4-a716-446655440000X"

    # ─────────────────────────────────────────────────────────────────────────
    # Mixed paths
    # ─────────────────────────────────────────────────────────────────────────

    def test_mixed_template_and_numeric(self):
        """Template and numeric params in same path."""
        assert _normalize_path("/api/v1/users/{id}/posts/42") == "/api/v1/users/{param}/posts/{param}"

    def test_mixed_template_and_uuid(self):
        """Template and UUID params in same path."""
        path = "/orgs/{org}/users/550e8400-e29b-41d4-a716-446655440000"
        assert _normalize_path(path) == "/orgs/{param}/users/{param}"

    def test_complex_path_with_all_types(self):
        """Path with template, numeric, UUID, and static segments."""
        path = "/api/v1/tenants/{tenant_id}/users/123/sessions/550e8400-e29b-41d4-a716-446655440000/details"
        expected = "/api/v1/tenants/{param}/users/{param}/sessions/{param}/details"
        assert _normalize_path(path) == expected

    # ─────────────────────────────────────────────────────────────────────────
    # Empty segments and edge cases
    # ─────────────────────────────────────────────────────────────────────────

    def test_empty_path(self):
        """Empty path returns empty."""
        assert _normalize_path("") == ""

    def test_root_path(self):
        """Root path / stays /."""
        assert _normalize_path("/") == "/"

    def test_trailing_slash_preserved(self):
        """Trailing slash is preserved (empty segment)."""
        assert _normalize_path("/users/") == "/users/"

    def test_double_slash_preserved(self):
        """Double slashes (empty segments) are preserved."""
        assert _normalize_path("/api//users") == "/api//users"

    def test_leading_slash_preserved(self):
        """Leading slash is preserved."""
        assert _normalize_path("/api/status") == "/api/status"

    def test_no_leading_slash(self):
        """Path without leading slash works."""
        assert _normalize_path("api/users/123") == "api/users/{param}"

    # ─────────────────────────────────────────────────────────────────────────
    # Non-param segments preserved
    # ─────────────────────────────────────────────────────────────────────────

    def test_static_segments_preserved(self):
        """Static path segments are not normalized."""
        assert _normalize_path("/api/v1/status") == "/api/v1/status"

    def test_alphanumeric_segment_preserved(self):
        """Alphanumeric segment that's not purely numeric is preserved."""
        assert _normalize_path("/users/user123") == "/users/user123"

    def test_hyphenated_segment_preserved(self):
        """Hyphenated non-UUID segment is preserved."""
        assert _normalize_path("/items/my-item-name") == "/items/my-item-name"

    def test_underscore_segment_preserved(self):
        """Underscore segment is preserved."""
        assert _normalize_path("/items/item_name") == "/items/item_name"

    def test_extension_segment_preserved(self):
        """File extension segment is preserved."""
        assert _normalize_path("/files/document.pdf") == "/files/document.pdf"

    def test_query_string_segment_preserved(self):
        """Path with query-like characters (not actual query) is preserved."""
        # Note: In practice, query strings are stripped before normalization,
        # but if they somehow end up in the path, don't crash
        assert _normalize_path("/search?q=test") == "/search?q=test"


class TestDiffTestruns:
    """Tests for the diff_testruns pure function.

    diff_testruns compares endpoints between two testrun dicts,
    returning added/removed/changed/unchanged categorization.
    """

    def _make_testrun(self, endpoints: list) -> dict:
        """Helper to create a testrun dict with endpoints."""
        return {"state": {"endpoints": endpoints}}

    def _endpoint(self, method: str, path: str, state: str = "done-ok") -> dict:
        """Helper to create an endpoint dict."""
        return {"method": method, "path": path, "state": state}

    # ─────────────────────────────────────────────────────────────────────────
    # Basic cases
    # ─────────────────────────────────────────────────────────────────────────

    def test_identical_testruns_produces_all_unchanged(self):
        """Two identical testruns should have no diff, just unchanged."""
        endpoints = [
            self._endpoint("GET", "/api/status"),
            self._endpoint("POST", "/api/data"),
        ]
        run_a = self._make_testrun(endpoints)
        run_b = self._make_testrun(endpoints)

        result = diff_testruns(run_a, run_b)

        assert result["added"] == []
        assert result["removed"] == []
        assert result["changed"] == []
        assert len(result["unchanged"]) == 2

    def test_empty_testruns_produces_empty_result(self):
        """Two empty testruns should produce empty lists."""
        run_a = self._make_testrun([])
        run_b = self._make_testrun([])

        result = diff_testruns(run_a, run_b)

        assert result["added"] == []
        assert result["removed"] == []
        assert result["changed"] == []
        assert result["unchanged"] == []

    # ─────────────────────────────────────────────────────────────────────────
    # Fully disjoint sets
    # ─────────────────────────────────────────────────────────────────────────

    def test_fully_disjoint_sets(self):
        """When A and B have no common endpoints, all are added/removed."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/v1/users"),
            self._endpoint("POST", "/api/v1/users"),
        ])
        run_b = self._make_testrun([
            self._endpoint("GET", "/api/v2/accounts"),
            self._endpoint("DELETE", "/api/v2/accounts"),
        ])

        result = diff_testruns(run_a, run_b)

        assert len(result["added"]) == 2
        assert len(result["removed"]) == 2
        assert result["changed"] == []
        assert result["unchanged"] == []
        # Verify content
        added_paths = {ep["path"] for ep in result["added"]}
        removed_paths = {ep["path"] for ep in result["removed"]}
        assert added_paths == {"/api/v2/accounts"}
        assert removed_paths == {"/api/v1/users"}

    # ─────────────────────────────────────────────────────────────────────────
    # Partial overlap
    # ─────────────────────────────────────────────────────────────────────────

    def test_partial_overlap_with_state_changes(self):
        """Some endpoints shared, some unique, some with state changes."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/status", "done-ok"),       # unchanged
            self._endpoint("POST", "/api/create", "done-drift"),   # changed
            self._endpoint("DELETE", "/api/old", "done-ok"),       # removed
        ])
        run_b = self._make_testrun([
            self._endpoint("GET", "/api/status", "done-ok"),       # unchanged
            self._endpoint("POST", "/api/create", "done-ok"),      # changed (state differs)
            self._endpoint("PUT", "/api/new", "idle"),             # added
        ])

        result = diff_testruns(run_a, run_b)

        assert len(result["added"]) == 1
        assert result["added"][0]["path"] == "/api/new"

        assert len(result["removed"]) == 1
        assert result["removed"][0]["path"] == "/api/old"

        assert len(result["changed"]) == 1
        assert result["changed"][0]["a"]["state"] == "done-drift"
        assert result["changed"][0]["b"]["state"] == "done-ok"

        assert len(result["unchanged"]) == 1
        assert result["unchanged"][0]["a"]["path"] == "/api/status"

    # ─────────────────────────────────────────────────────────────────────────
    # Endpoint key collision handling
    # ─────────────────────────────────────────────────────────────────────────

    def test_same_path_different_method_treated_separately(self):
        """GET /api/data and POST /api/data are different endpoints."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/data", "done-ok"),
        ])
        run_b = self._make_testrun([
            self._endpoint("POST", "/api/data", "done-ok"),
        ])

        result = diff_testruns(run_a, run_b)

        # GET removed, POST added
        assert len(result["added"]) == 1
        assert result["added"][0]["method"] == "POST"

        assert len(result["removed"]) == 1
        assert result["removed"][0]["method"] == "GET"

        assert result["changed"] == []
        assert result["unchanged"] == []

    def test_same_method_different_path_treated_separately(self):
        """GET /api/v1 and GET /api/v2 are different endpoints."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/v1", "done-ok"),
        ])
        run_b = self._make_testrun([
            self._endpoint("GET", "/api/v2", "done-ok"),
        ])

        result = diff_testruns(run_a, run_b)

        assert len(result["added"]) == 1
        assert result["added"][0]["path"] == "/api/v2"

        assert len(result["removed"]) == 1
        assert result["removed"][0]["path"] == "/api/v1"

    def test_path_normalization_openapi_template(self):
        """OpenAPI template params like {id} normalized to {param}."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/users/{user_id}", "done-ok"),
        ])
        run_b = self._make_testrun([
            self._endpoint("GET", "/api/users/{id}", "done-ok"),
        ])

        result = diff_testruns(run_a, run_b)

        # Same endpoint after normalization - both become /api/users/{param}
        assert result["added"] == []
        assert result["removed"] == []
        assert len(result["unchanged"]) == 1

    def test_path_normalization_numeric_segment(self):
        """Numeric path segments normalized to {param}."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/users/123", "done-ok"),
        ])
        run_b = self._make_testrun([
            self._endpoint("GET", "/api/users/456", "done-ok"),
        ])

        result = diff_testruns(run_a, run_b)

        # Same endpoint after normalization - both become /api/users/{param}
        assert result["added"] == []
        assert result["removed"] == []
        assert len(result["unchanged"]) == 1

    def test_path_normalization_uuid_segment(self):
        """UUID path segments normalized to {param}."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/users/550e8400-e29b-41d4-a716-446655440000", "done-ok"),
        ])
        run_b = self._make_testrun([
            self._endpoint("GET", "/api/users/{user_id}", "done-ok"),
        ])

        result = diff_testruns(run_a, run_b)

        # Same endpoint after normalization - both become /api/users/{param}
        assert result["added"] == []
        assert result["removed"] == []
        assert len(result["unchanged"]) == 1

    # ─────────────────────────────────────────────────────────────────────────
    # Edge cases
    # ─────────────────────────────────────────────────────────────────────────

    def test_missing_state_field_in_testrun(self):
        """Testrun without state field should return empty."""
        run_a = {"no_state": True}
        run_b = {"no_state": True}

        result = diff_testruns(run_a, run_b)

        assert result["added"] == []
        assert result["removed"] == []
        assert result["changed"] == []
        assert result["unchanged"] == []

    def test_missing_endpoints_field_in_state(self):
        """State without endpoints field should return empty."""
        run_a = {"state": {"other": "data"}}
        run_b = {"state": {"other": "data"}}

        result = diff_testruns(run_a, run_b)

        assert result["added"] == []
        assert result["removed"] == []
        assert result["changed"] == []
        assert result["unchanged"] == []

    def test_endpoint_missing_method_defaults_to_get(self):
        """Endpoint without method field defaults to GET."""
        run_a = self._make_testrun([
            {"path": "/api/status", "state": "done-ok"},  # no method
        ])
        run_b = self._make_testrun([
            {"method": "GET", "path": "/api/status", "state": "done-ok"},
        ])

        result = diff_testruns(run_a, run_b)

        # Should match as same endpoint
        assert result["added"] == []
        assert result["removed"] == []
        assert len(result["unchanged"]) == 1

    def test_endpoint_missing_path_uses_empty_string(self):
        """Endpoint without path field uses empty string."""
        run_a = self._make_testrun([
            {"method": "GET", "state": "done-ok"},  # no path
        ])
        run_b = self._make_testrun([
            {"method": "GET", "path": "", "state": "done-ok"},
        ])

        result = diff_testruns(run_a, run_b)

        # Should match as same endpoint
        assert result["added"] == []
        assert result["removed"] == []
        assert len(result["unchanged"]) == 1

    def test_changed_output_includes_both_versions(self):
        """Changed endpoints include both a and b versions."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/status", "done-ok"),
        ])
        run_b = self._make_testrun([
            self._endpoint("GET", "/api/status", "done-drift"),
        ])

        result = diff_testruns(run_a, run_b)

        assert len(result["changed"]) == 1
        change = result["changed"][0]
        assert "key" in change
        assert "a" in change
        assert "b" in change
        assert change["a"]["state"] == "done-ok"
        assert change["b"]["state"] == "done-drift"

    def test_unchanged_output_includes_both_versions(self):
        """Unchanged endpoints also include both a and b versions."""
        run_a = self._make_testrun([
            self._endpoint("GET", "/api/status", "done-ok"),
        ])
        run_b = self._make_testrun([
            self._endpoint("GET", "/api/status", "done-ok"),
        ])

        result = diff_testruns(run_a, run_b)

        assert len(result["unchanged"]) == 1
        unchanged = result["unchanged"][0]
        assert "key" in unchanged
        assert "a" in unchanged
        assert "b" in unchanged

    def test_many_endpoints_performance(self):
        """Test with a larger number of endpoints using distinct paths."""
        # Create 100 endpoints with distinct non-numeric paths
        # (numeric paths would be normalized and collide)
        endpoints_a = [self._endpoint("GET", f"/api/endpoint-{i:03d}", "done-ok")
                       for i in range(100)]
        endpoints_b = [self._endpoint("GET", f"/api/endpoint-{i:03d}", "done-ok")
                       for i in range(50, 150)]

        run_a = self._make_testrun(endpoints_a)
        run_b = self._make_testrun(endpoints_b)

        result = diff_testruns(run_a, run_b)

        # 000-049 removed (50), 100-149 added (50), 050-099 unchanged (50)
        assert len(result["removed"]) == 50
        assert len(result["added"]) == 50
        assert len(result["unchanged"]) == 50
        assert len(result["changed"]) == 0
