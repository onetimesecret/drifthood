# tests/test_compare.py

"""
Tests for dd.compare: response validation against parsed schema fields,
type helpers, and nested dict traversal.
"""

from dd.compare import (
    _python_type_name,
    _type_matches,
    _get_nested,
    validate_response_against_schema,
    classify_severity,
)
from dd.config import derive_ignore_paths


# ═══════════════════════════════════════════════════════════════════════════
# _python_type_name
# ═══════════════════════════════════════════════════════════════════════════


class TestPythonTypeName:
    def test_none(self):
        assert _python_type_name(None) == "null"

    def test_bool_before_int(self):
        """bool is a subclass of int in Python; must be checked first."""
        assert _python_type_name(True) == "boolean"
        assert _python_type_name(False) == "boolean"

    def test_int(self):
        assert _python_type_name(42) == "integer"

    def test_float(self):
        assert _python_type_name(3.14) == "number"

    def test_string(self):
        assert _python_type_name("hello") == "string"
        assert _python_type_name("") == "string"

    def test_list(self):
        assert _python_type_name([1, 2, 3]) == "array"
        assert _python_type_name([]) == "array"

    def test_dict(self):
        assert _python_type_name({"a": 1}) == "object"
        assert _python_type_name({}) == "object"

    def test_unknown_type(self):
        """Fallback to the class name for unrecognized types."""
        assert _python_type_name(object()) == "object"  # object.__name__
        result = _python_type_name(frozenset([1, 2]))
        assert result == "frozenset"


# ═══════════════════════════════════════════════════════════════════════════
# _type_matches
# ═══════════════════════════════════════════════════════════════════════════


class TestTypeMatches:
    def test_exact_match(self):
        assert _type_matches("string", "string") is True
        assert _type_matches("integer", "integer") is True

    def test_number_accepts_integer(self):
        """OpenAPI 'number' should accept Python int values."""
        assert _type_matches("number", "integer") is True
        assert _type_matches("number", "number") is True

    def test_mismatch(self):
        assert _type_matches("string", "integer") is False
        assert _type_matches("integer", "string") is False
        assert _type_matches("boolean", "string") is False

    def test_integer_does_not_accept_number(self):
        """An integer field should not accept a float."""
        assert _type_matches("integer", "number") is False


# ═══════════════════════════════════════════════════════════════════════════
# _get_nested
# ═══════════════════════════════════════════════════════════════════════════


class TestGetNested:
    def test_top_level_key(self):
        found, value = _get_nested({"status": "ok"}, "status")
        assert found is True
        assert value == "ok"

    def test_dotted_path(self):
        body = {"data": {"user": {"name": "Alice"}}}
        found, value = _get_nested(body, "data.user.name")
        assert found is True
        assert value == "Alice"

    def test_missing_key(self):
        found, value = _get_nested({"a": 1}, "b")
        assert found is False
        assert value is None

    def test_missing_nested_key(self):
        found, value = _get_nested({"a": {"b": 1}}, "a.c")
        assert found is False
        assert value is None

    def test_non_dict_intermediate(self):
        """If a path segment hits a non-dict, return not-found."""
        found, value = _get_nested({"a": "string_not_dict"}, "a.b")
        assert found is False
        assert value is None

    def test_null_value(self):
        """A key present with value None should still be 'found'."""
        found, value = _get_nested({"x": None}, "x")
        assert found is True
        assert value is None


# ═══════════════════════════════════════════════════════════════════════════
# validate_response_against_schema
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateResponseAgainstSchema:
    def test_empty_schema(self):
        """No schema fields -> no validation results."""
        resp = {"body": {"status": "ok"}}
        assert validate_response_against_schema(resp, []) == []

    def test_non_dict_body(self):
        """Non-dict body (e.g. plain text) -> empty results."""
        resp = {"body": "not a dict"}
        schema = [{"path": "status", "type": "string"}]
        assert validate_response_against_schema(resp, schema) == []

    def test_missing_body_key(self):
        """Response without 'body' key -> empty results."""
        resp = {"status": 200}
        schema = [{"path": "status", "type": "string"}]
        assert validate_response_against_schema(resp, schema) == []

    def test_matching_field(self):
        resp = {"body": {"status": "ok", "count": 42}}
        schema = [
            {"path": "status", "type": "string", "required": True, "nested": False},
            {"path": "count", "type": "integer", "required": False, "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert len(results) == 2
        assert results[0]["field"] == "status"
        assert results[0]["conforms"] is True
        assert results[0]["present"] is True
        assert results[0]["expected_type"] == "string"
        assert results[0]["actual_type"] == "string"
        assert results[1]["field"] == "count"
        assert results[1]["conforms"] is True

    def test_type_mismatch(self):
        resp = {"body": {"count": "not-a-number"}}
        schema = [
            {"path": "count", "type": "integer", "required": True, "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert len(results) == 1
        assert results[0]["conforms"] is False
        assert results[0]["actual_type"] == "string"
        assert results[0]["expected_type"] == "integer"

    def test_missing_field(self):
        resp = {"body": {"other": "value"}}
        schema = [
            {"path": "status", "type": "string", "required": True, "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert len(results) == 1
        assert results[0]["present"] is False
        assert results[0]["conforms"] is False
        assert results[0]["actual_type"] is None

    def test_missing_optional_field_conforms(self):
        resp = {"body": {"other": "value"}}
        schema = [
            {"path": "status", "type": "string", "required": False, "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert len(results) == 1
        assert results[0]["present"] is False
        assert results[0]["conforms"] is True

    def test_nested_fields_skipped(self):
        """Fields with nested=True are skipped (their children are validated instead)."""
        resp = {"body": {"data": {"id": "123"}}}
        schema = [
            {"path": "data", "type": "object", "nested": True},
            {"path": "data.id", "type": "string", "required": True, "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert len(results) == 1
        assert results[0]["field"] == "data.id"
        assert results[0]["conforms"] is True

    def test_number_accepts_integer_value(self):
        """OpenAPI 'number' type should accept Python int values."""
        resp = {"body": {"score": 100}}
        schema = [
            {"path": "score", "type": "number", "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert results[0]["conforms"] is True

    def test_boolean_field(self):
        resp = {"body": {"active": True}}
        schema = [
            {"path": "active", "type": "boolean", "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert results[0]["conforms"] is True
        assert results[0]["actual_type"] == "boolean"

    def test_null_value_against_string(self):
        resp = {"body": {"name": None}}
        schema = [
            {"path": "name", "type": "string", "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert results[0]["present"] is True
        assert results[0]["actual_type"] == "null"
        assert results[0]["conforms"] is False

    def test_deeply_nested_path(self):
        resp = {"body": {"a": {"b": {"c": "deep"}}}}
        schema = [
            {"path": "a.b.c", "type": "string", "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert results[0]["conforms"] is True
        assert results[0]["actual_type"] == "string"

    def test_required_flag_passthrough(self):
        """The required flag from schema is passed through to results."""
        resp = {"body": {"x": 1}}
        schema = [
            {"path": "x", "type": "integer", "required": True, "nested": False},
            {"path": "y", "type": "string", "required": False, "nested": False},
        ]
        results = validate_response_against_schema(resp, schema)
        assert results[0]["required"] is True
        assert results[1]["required"] is False


# ═══════════════════════════════════════════════════════════════════════════
# derive_ignore_paths
# ═══════════════════════════════════════════════════════════════════════════


class TestDeriveIgnorePaths:
    """Tests for config.derive_ignore_paths: building DeepDiff exclude_paths from schema fields."""

    def test_empty_input(self):
        """Empty field list produces empty ignore paths."""
        assert derive_ignore_paths([]) == []

    def test_basic_drift_ignore_field(self):
        """A field with drift_ignore=True produces the correct DeepDiff path."""
        fields = [
            {"path": "created", "type": "string", "drift_ignore": True, "nested": False},
        ]
        result = derive_ignore_paths(fields)
        assert result == ["root['body']['created']"]

    def test_non_ignored_field_skipped(self):
        """Fields without drift_ignore are not included."""
        fields = [
            {"path": "status", "type": "string", "drift_ignore": False, "nested": False},
            {"path": "created", "type": "string", "drift_ignore": True, "nested": False},
        ]
        result = derive_ignore_paths(fields)
        assert result == ["root['body']['created']"]

    def test_nested_fields_skipped(self):
        """Fields with nested=True are skipped even if drift_ignore is set."""
        fields = [
            {"path": "data", "type": "object", "drift_ignore": True, "nested": True},
            {"path": "data.id", "type": "string", "drift_ignore": True, "nested": False},
        ]
        result = derive_ignore_paths(fields)
        assert result == ["root['body']['data']['id']"]

    def test_dotted_path_produces_chained_brackets(self):
        """Dotted paths like 'a.b.c' produce chained bracket notation."""
        fields = [
            {"path": "meta.created_at", "type": "string", "drift_ignore": True, "nested": False},
        ]
        result = derive_ignore_paths(fields)
        assert result == ["root['body']['meta']['created_at']"]

    def test_deeply_nested_dotted_path(self):
        """Three-level dotted path."""
        fields = [
            {"path": "a.b.c", "type": "string", "drift_ignore": True, "nested": False},
        ]
        result = derive_ignore_paths(fields)
        assert result == ["root['body']['a']['b']['c']"]

    def test_custom_prefix(self):
        """Custom prefix replaces the default root['body']."""
        fields = [
            {"path": "timestamp", "type": "string", "drift_ignore": True, "nested": False},
        ]
        result = derive_ignore_paths(fields, prefix="root['response']")
        assert result == ["root['response']['timestamp']"]

    def test_multiple_ignored_fields(self):
        """Multiple drift_ignore fields all produce paths."""
        fields = [
            {"path": "created", "type": "string", "drift_ignore": True, "nested": False},
            {"path": "updated", "type": "string", "drift_ignore": True, "nested": False},
            {"path": "status", "type": "string", "drift_ignore": False, "nested": False},
            {"path": "nonce", "type": "string", "drift_ignore": True, "nested": False},
        ]
        result = derive_ignore_paths(fields)
        assert len(result) == 3
        assert "root['body']['created']" in result
        assert "root['body']['updated']" in result
        assert "root['body']['nonce']" in result

    def test_missing_drift_ignore_key_treated_as_false(self):
        """Fields without the drift_ignore key at all are not included."""
        fields = [
            {"path": "status", "type": "string", "nested": False},
        ]
        result = derive_ignore_paths(fields)
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# classify_severity — deprecated field handling
# ═══════════════════════════════════════════════════════════════════════════


class TestClassifySeverityDeprecation:
    """Tests for classify_severity severity downgrades on deprecated fields.

    The deprecation downgrade rule:
    - Removing a deprecated required field: breaking -> structural
    - Removing a deprecated optional field: structural -> cosmetic
    - Non-deprecated fields: no downgrade (stays at base severity)
    - Value changes on deprecated fields: stays cosmetic (already lowest)
    """

    def test_deprecated_required_removal_downgrades_to_structural(self):
        """Removing a deprecated required field is structural, not breaking."""
        diff = {
            "dictionary_item_removed": {
                "root['body']['old_field']": "some_value"
            }
        }
        schema = {
            "200": [
                {"path": "old_field", "type": "string", "required": True, "deprecated": True}
            ]
        }
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "structural"
        assert len(reasons) == 1
        assert reasons[0]["category"] == "field_removed"
        assert reasons[0]["severity"] == "structural"
        assert "deprecated" in reasons[0]["detail"]

    def test_deprecated_optional_removal_downgrades_to_cosmetic(self):
        """Removing a deprecated optional field is cosmetic, not structural."""
        diff = {
            "dictionary_item_removed": {
                "root['body']['legacy_field']": "old_value"
            }
        }
        schema = {
            "200": [
                {"path": "legacy_field", "type": "string", "required": False, "deprecated": True}
            ]
        }
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "cosmetic"
        assert len(reasons) == 1
        assert reasons[0]["category"] == "field_removed"
        assert reasons[0]["severity"] == "cosmetic"
        assert "deprecated" in reasons[0]["detail"]

    def test_non_deprecated_required_removal_stays_breaking(self):
        """Removing a non-deprecated required field is still breaking."""
        diff = {
            "dictionary_item_removed": {
                "root['body']['important_field']": "critical_value"
            }
        }
        schema = {
            "200": [
                {"path": "important_field", "type": "string", "required": True, "deprecated": False}
            ]
        }
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "breaking"
        assert len(reasons) == 1
        assert reasons[0]["severity"] == "breaking"
        assert "deprecated" not in reasons[0]["detail"]

    def test_non_deprecated_optional_removal_stays_structural(self):
        """Removing a non-deprecated optional field is still structural."""
        diff = {
            "dictionary_item_removed": {
                "root['body']['optional_field']": "some_value"
            }
        }
        schema = {
            "200": [
                {"path": "optional_field", "type": "string", "required": False, "deprecated": False}
            ]
        }
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "structural"
        assert len(reasons) == 1
        assert reasons[0]["severity"] == "structural"
        assert "deprecated" not in reasons[0]["detail"]

    def test_deprecated_value_change_is_cosmetic(self):
        """Value change on any field (deprecated or not) is cosmetic."""
        diff = {
            "values_changed": {
                "root['body']['deprecated_field']": {
                    "old_value": "old",
                    "new_value": "new"
                }
            }
        }
        schema = {
            "200": [
                {"path": "deprecated_field", "type": "string", "required": True, "deprecated": True}
            ]
        }
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "cosmetic"
        assert len(reasons) == 1
        assert reasons[0]["category"] == "value_changed"
        assert reasons[0]["severity"] == "cosmetic"

    def test_multiple_fields_with_mixed_deprecation(self):
        """Multiple removals: deprecated and non-deprecated fields together."""
        diff = {
            "dictionary_item_removed": {
                "root['body']['deprecated_req']": "val1",
                "root['body']['active_req']": "val2",
            }
        }
        schema = {
            "200": [
                {"path": "deprecated_req", "type": "string", "required": True, "deprecated": True},
                {"path": "active_req", "type": "string", "required": True, "deprecated": False},
            ]
        }
        severity, reasons = classify_severity(diff, schema, 200, 200)
        # active_req removal is breaking, which dominates
        assert severity == "breaking"
        assert len(reasons) == 2
        # Find each reason and verify
        deprecated_reason = next(r for r in reasons if r["path"] == "deprecated_req")
        active_reason = next(r for r in reasons if r["path"] == "active_req")
        assert deprecated_reason["severity"] == "structural"  # downgraded
        assert active_reason["severity"] == "breaking"  # not downgraded

    def test_no_schema_means_no_deprecation_info(self):
        """Without schema, removed fields are structural (no required/deprecated info)."""
        diff = {
            "dictionary_item_removed": {
                "root['body']['unknown_field']": "value"
            }
        }
        severity, reasons = classify_severity(diff, None, 200, 200)
        assert severity == "structural"
        assert reasons[0]["severity"] == "structural"
        assert "deprecated" not in reasons[0]["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# do_compare integration tests
# ═══════════════════════════════════════════════════════════════════════════

from unittest.mock import patch, MagicMock
from dd.compare import do_compare, CompareRequest, ResponseSchemaField


class TestDoCompare:
    """Integration tests for do_compare() with mocked HTTP."""

    def _mock_hit(self, status: int, body: dict):
        """Create a mock response dict matching hit() return format."""
        return {
            "status": status,
            "body": body,
            "headers": {"Content-Type": "application/json"},
            "timing": {"elapsed_ms": 42},
        }

    def test_basic_compare_no_drift(self):
        """Identical responses should produce has_drift=False."""
        response = self._mock_hit(200, {"status": "ok", "value": 123})

        with patch("dd.compare.hit", return_value=response):
            cr = CompareRequest(label="test", method="GET", path="/api/status")
            result = do_compare("http://a", "http://b", cr, None)

        assert result["has_drift"] is False
        assert result["diff"] == {}
        assert result["severity"] == "none"
        assert result["label"] == "test"
        assert result["method"] == "GET"
        assert result["path"] == "/api/status"

    def test_basic_compare_with_drift(self):
        """Different responses should produce has_drift=True with diff."""
        resp_a = self._mock_hit(200, {"status": "ok", "value": 100})
        resp_b = self._mock_hit(200, {"status": "ok", "value": 200})

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(label="test", method="GET", path="/api/data")
            result = do_compare("http://a", "http://b", cr, None)

        assert result["has_drift"] is True
        assert "values_changed" in result["diff"]
        assert result["severity"] == "cosmetic"

    def test_status_code_change_is_breaking(self):
        """Status code mismatch should be classified as breaking."""
        resp_a = self._mock_hit(200, {"status": "ok"})
        resp_b = self._mock_hit(500, {"error": "Internal Server Error"})

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(label="test", method="GET", path="/api/test")
            result = do_compare("http://a", "http://b", cr, None)

        assert result["has_drift"] is True
        assert result["severity"] == "breaking"
        assert any(r["category"] == "status_change" for r in result["severity_reasons"])

    def test_compare_with_schema_conformance(self):
        """Schema fields should trigger conformance validation."""
        resp_a = self._mock_hit(200, {"custid": "cust123", "name": "Alice"})
        resp_b = self._mock_hit(200, {"custid": "cust123", "name": "Alice"})

        schema = {
            "200": [
                ResponseSchemaField(
                    name="custid", path="custid", type="string", required=True
                ),
                ResponseSchemaField(
                    name="name", path="name", type="string", required=False
                ),
            ]
        }

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(
                label="test", method="GET", path="/api/user",
                response_schema=schema
            )
            result = do_compare("http://a", "http://b", cr, None)

        assert "conformance" in result
        assert "a" in result["conformance"]
        assert "b" in result["conformance"]
        # Both should conform
        for field_result in result["conformance"]["a"]:
            assert field_result["conforms"] is True

    def test_compare_with_extra_ignore_paths(self):
        """extra_ignore_paths should suppress diff on specified fields."""
        resp_a = self._mock_hit(200, {"timestamp": "2024-01-01", "data": "same"})
        resp_b = self._mock_hit(200, {"timestamp": "2024-01-02", "data": "same"})

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(
                label="test", method="GET", path="/api/time",
                extra_ignore_paths=["root['body']['timestamp']"]
            )
            result = do_compare("http://a", "http://b", cr, None)

        # timestamp diff should be ignored
        assert result["has_drift"] is False

    def test_severity_passthrough_in_result(self):
        """Severity and reasons should be included in result."""
        resp_a = self._mock_hit(200, {"field": "old"})
        resp_b = self._mock_hit(200, {"field": "new"})

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(label="test", method="POST", path="/api/update")
            result = do_compare("http://a", "http://b", cr, None)

        assert "severity" in result
        assert "severity_reasons" in result
        assert isinstance(result["severity_reasons"], list)

    def test_drift_ignore_fields_excluded_from_diff(self):
        """Fields marked drift_ignore in schema should be excluded."""
        resp_a = self._mock_hit(200, {"nonce": "abc123", "data": "same"})
        resp_b = self._mock_hit(200, {"nonce": "xyz789", "data": "same"})

        schema = {
            "200": [
                ResponseSchemaField(
                    name="nonce", path="nonce", type="string", drift_ignore=True
                ),
                ResponseSchemaField(
                    name="data", path="data", type="string"
                ),
            ]
        }

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(
                label="test", method="GET", path="/api/nonce",
                response_schema=schema
            )
            result = do_compare("http://a", "http://b", cr, None)

        # nonce diff should be ignored due to drift_ignore
        assert result["has_drift"] is False

    def test_global_ignore_paths_applied(self):
        """Global ignore paths should be merged with request-level ignores."""
        resp_a = self._mock_hit(200, {"global_field": "a", "data": "same"})
        resp_b = self._mock_hit(200, {"global_field": "b", "data": "same"})

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(label="test", method="GET", path="/api/global")
            global_ignore = ["root['body']['global_field']"]
            result = do_compare("http://a", "http://b", cr, global_ignore)

        assert result["has_drift"] is False
        assert "root['body']['global_field']" in result["ignored_paths"]

    def test_captured_at_timestamp_present(self):
        """Result should include an ISO timestamp in captured_at."""
        response = self._mock_hit(200, {"ok": True})

        with patch("dd.compare.hit", return_value=response):
            cr = CompareRequest(label="test", method="GET", path="/api/time")
            result = do_compare("http://a", "http://b", cr, None)

        assert "captured_at" in result
        # Should be ISO format
        assert "T" in result["captured_at"]

    def test_response_a_and_b_included(self):
        """Raw responses should be included for debugging."""
        resp_a = self._mock_hit(200, {"a": 1})
        resp_b = self._mock_hit(200, {"b": 2})

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(label="test", method="GET", path="/api/debug")
            result = do_compare("http://a", "http://b", cr, None)

        assert result["response_a"] == resp_a
        assert result["response_b"] == resp_b

    def test_connection_error_host_a(self):
        """Connection error on host A should produce error in response_a."""
        import requests

        error_response = {
            "status": None,
            "headers": {},
            "body": None,
            "error": "Connection refused",
            "elapsed_ms": None,
            "request_headers": {},
            "request_url": None,
            "request_body": None,
        }
        resp_b = self._mock_hit(200, {"status": "ok"})

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [error_response, resp_b]
            cr = CompareRequest(label="test", method="GET", path="/api/health")
            result = do_compare("http://a", "http://b", cr, None)

        # Result should still be returned, with error captured
        assert result["response_a"]["error"] == "Connection refused"
        assert result["response_a"]["status"] is None
        assert result["response_b"]["status"] == 200
        assert result["has_drift"] is True  # None vs 200 is a diff
        # Status change from None to 200 should be classified as breaking
        assert result["severity"] == "breaking"

    def test_connection_error_host_b(self):
        """Connection error on host B should produce error in response_b."""
        resp_a = self._mock_hit(200, {"status": "ok"})
        error_response = {
            "status": None,
            "headers": {},
            "body": None,
            "error": "Connection timed out",
            "elapsed_ms": None,
            "request_headers": {},
            "request_url": None,
            "request_body": None,
        }

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, error_response]
            cr = CompareRequest(label="test", method="GET", path="/api/health")
            result = do_compare("http://a", "http://b", cr, None)

        assert result["response_a"]["status"] == 200
        assert result["response_b"]["error"] == "Connection timed out"
        assert result["response_b"]["status"] is None
        assert result["has_drift"] is True
        assert result["severity"] == "breaking"

    def test_both_hosts_connection_error(self):
        """Connection errors on both hosts should be captured."""
        error_a = {
            "status": None,
            "headers": {},
            "body": None,
            "error": "Host A unreachable",
            "elapsed_ms": None,
            "request_headers": {},
            "request_url": None,
            "request_body": None,
        }
        error_b = {
            "status": None,
            "headers": {},
            "body": None,
            "error": "Host B unreachable",
            "elapsed_ms": None,
            "request_headers": {},
            "request_url": None,
            "request_body": None,
        }

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [error_a, error_b]
            cr = CompareRequest(label="test", method="GET", path="/api/health")
            result = do_compare("http://a", "http://b", cr, None)

        assert result["response_a"]["error"] == "Host A unreachable"
        assert result["response_b"]["error"] == "Host B unreachable"
        assert result["response_a"]["status"] is None
        assert result["response_b"]["status"] is None
        # Both None status means no diff in status (both errored the same way)
        # But body is also None for both, so no diff there either
        assert result["has_drift"] is False

    def test_both_hosts_return_errors(self):
        """Both hosts returning HTTP errors (5xx) should still diff correctly."""
        resp_a = self._mock_hit(500, {"error": "Internal Server Error"})
        resp_b = self._mock_hit(503, {"error": "Service Unavailable"})

        with patch("dd.compare.hit") as mock_hit:
            mock_hit.side_effect = [resp_a, resp_b]
            cr = CompareRequest(label="test", method="GET", path="/api/health")
            result = do_compare("http://a", "http://b", cr, None)

        assert result["has_drift"] is True
        assert result["response_a"]["status"] == 500
        assert result["response_b"]["status"] == 503
        # Status code change is breaking
        assert result["severity"] == "breaking"
        assert any(r["category"] == "status_change" for r in result["severity_reasons"])

    def test_identical_error_responses_no_drift(self):
        """Identical error responses should produce no drift."""
        resp = self._mock_hit(500, {"error": "Internal Server Error"})

        with patch("dd.compare.hit", return_value=resp):
            cr = CompareRequest(label="test", method="GET", path="/api/health")
            result = do_compare("http://a", "http://b", cr, None)

        assert result["has_drift"] is False
        assert result["severity"] == "none"
        assert result["response_a"]["status"] == 500
        assert result["response_b"]["status"] == 500
