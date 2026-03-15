# drift-detector/tests/test_compare.py

"""
Tests for dd.compare: response validation against parsed schema fields,
type helpers, and nested dict traversal.
"""

from dd.compare import (
    _python_type_name,
    _type_matches,
    _get_nested,
    validate_response_against_schema,
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
