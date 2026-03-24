# drift-detector/tests/test_severity.py
"""Tests for severity classification."""

import pytest
from dd.compare import classify_severity, _extract_field_path, _severity_order


class TestExtractFieldPath:
    """Tests for DeepDiff path → schema path conversion."""

    def test_simple_body_field(self):
        assert _extract_field_path("root['body']['status']") == "status"

    def test_nested_field(self):
        assert _extract_field_path("root['body']['user']['email']") == "user.email"

    def test_deeply_nested(self):
        assert _extract_field_path("root['body']['a']['b']['c']") == "a.b.c"

    def test_root_status(self):
        # Status at root level (not in body)
        assert _extract_field_path("root['status']") == "status"

    def test_array_index(self):
        # Array indices in [N] format are not captured (only ['key'] format is)
        # This is acceptable since schema paths don't include numeric indices
        assert _extract_field_path("root['body']['items'][0]['id']") == "items.id"


class TestSeverityOrder:
    def test_order_values(self):
        assert _severity_order("none") < _severity_order("cosmetic")
        assert _severity_order("cosmetic") < _severity_order("structural")
        assert _severity_order("structural") < _severity_order("breaking")

    def test_unknown_severity(self):
        assert _severity_order("unknown") == 0


class TestClassifySeverityNoDrift:
    """Tests for no-drift scenarios."""

    def test_empty_diff_same_status(self):
        severity, reasons = classify_severity({}, None, 200, 200)
        assert severity == "none"
        assert reasons == []

    def test_empty_diff_with_schema(self):
        schema = {"200": [{"path": "id", "required": True}]}
        severity, reasons = classify_severity({}, schema, 200, 200)
        assert severity == "none"


class TestClassifySeverityStatusChange:
    """Tests for status code changes (breaking)."""

    def test_success_to_error(self):
        severity, reasons = classify_severity({}, None, 200, 500)
        assert severity == "breaking"
        assert len(reasons) == 1
        assert reasons[0]["category"] == "status_change"

    def test_success_to_not_found(self):
        severity, reasons = classify_severity({}, None, 200, 404)
        assert severity == "breaking"

    def test_different_success_codes(self):
        # 200 vs 201 is still a breaking change (contract difference)
        severity, reasons = classify_severity({}, None, 200, 201)
        assert severity == "breaking"

    def test_connection_error_one_side(self):
        # None status means connection failed
        severity, reasons = classify_severity({}, None, 200, None)
        assert severity == "breaking"

    def test_both_connection_errors(self):
        # Both failed but same status (None)
        severity, reasons = classify_severity({}, None, None, None)
        assert severity == "none"


class TestClassifySeverityRequiredFieldRemoved:
    """Tests for required field removal (breaking)."""

    def test_required_field_removed(self):
        diff = {"dictionary_item_removed": {"root['body']['id']": 123}}
        schema = {"200": [{"path": "id", "required": True}]}
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "breaking"
        assert reasons[0]["category"] == "field_removed"
        assert reasons[0]["path"] == "id"

    def test_optional_field_removed(self):
        diff = {"dictionary_item_removed": {"root['body']['memo']": "note"}}
        schema = {"200": [{"path": "memo", "required": False}]}
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "structural"

    def test_no_schema_falls_back_structural(self):
        diff = {"dictionary_item_removed": {"root['body']['id']": 123}}
        severity, reasons = classify_severity(diff, None, 200, 200)
        assert severity == "structural"  # Can't determine required without schema


class TestClassifySeverityTypeChange:
    """Tests for type changes."""

    def test_type_change_required_field(self):
        diff = {"type_changes": {"root['body']['count']": {"old_type": "int", "new_type": "str"}}}
        schema = {"200": [{"path": "count", "required": True}]}
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "breaking"

    def test_type_change_optional_field(self):
        diff = {"type_changes": {"root['body']['count']": {"old_type": "int", "new_type": "str"}}}
        schema = {"200": [{"path": "count", "required": False}]}
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "structural"


class TestClassifySeverityFieldAdded:
    """Tests for field additions (structural)."""

    def test_field_added(self):
        diff = {"dictionary_item_added": {"root['body']['new_field']": "value"}}
        severity, reasons = classify_severity(diff, None, 200, 200)
        assert severity == "structural"
        assert reasons[0]["category"] == "field_added"


class TestClassifySeverityValueChanged:
    """Tests for value changes (cosmetic)."""

    def test_value_changed(self):
        diff = {"values_changed": {"root['body']['version']": {"old_value": "1.0", "new_value": "1.1"}}}
        severity, reasons = classify_severity(diff, None, 200, 200)
        assert severity == "cosmetic"
        assert reasons[0]["category"] == "value_changed"

    def test_multiple_value_changes(self):
        diff = {"values_changed": {
            "root['body']['a']": {"old_value": 1, "new_value": 2},
            "root['body']['b']": {"old_value": "x", "new_value": "y"},
        }}
        severity, reasons = classify_severity(diff, None, 200, 200)
        assert severity == "cosmetic"
        assert len(reasons) == 2


class TestClassifySeverityMixed:
    """Tests for mixed severity scenarios."""

    def test_breaking_plus_cosmetic(self):
        diff = {
            "dictionary_item_removed": {"root['body']['id']": 123},
            "values_changed": {"root['body']['name']": {"old_value": "a", "new_value": "b"}},
        }
        schema = {"200": [{"path": "id", "required": True}]}
        severity, reasons = classify_severity(diff, schema, 200, 200)
        assert severity == "breaking"  # Max wins

    def test_structural_plus_cosmetic(self):
        diff = {
            "dictionary_item_added": {"root['body']['new']": "x"},
            "values_changed": {"root['body']['old']": {"old_value": 1, "new_value": 2}},
        }
        severity, reasons = classify_severity(diff, None, 200, 200)
        assert severity == "structural"


class TestClassifySeverityReasonsStructure:
    """Tests for reasons format."""

    def test_reason_has_required_keys(self):
        diff = {"values_changed": {"root['body']['x']": {"old_value": 1, "new_value": 2}}}
        severity, reasons = classify_severity(diff, None, 200, 200)
        assert len(reasons) == 1
        reason = reasons[0]
        assert "category" in reason
        assert "path" in reason
        assert "detail" in reason
        assert "severity" in reason

    def test_path_is_human_readable(self):
        diff = {"dictionary_item_removed": {"root['body']['user']['email']": "x@y.com"}}
        severity, reasons = classify_severity(diff, None, 200, 200)
        # Should be "user.email", not "root['body']['user']['email']"
        assert reasons[0]["path"] == "user.email"
