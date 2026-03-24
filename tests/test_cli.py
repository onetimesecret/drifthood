# drift-detector/tests/test_cli.py

"""
Tests for dd.cli module: CLI exit codes, output modes, and helper functions.
"""

import json
import tempfile
import os
from unittest.mock import patch, MagicMock
import argparse

import pytest

from dd.cli import (
    substitute_path_params,
    form_body_to_json,
    build_parser,
    run_compare,
)


# ============================================================================
# Path parameter substitution tests
# ============================================================================


class TestSubstitutePathParams:
    """Tests for path parameter substitution."""

    def test_no_params_returns_original(self):
        """Path without placeholders returns unchanged."""
        assert substitute_path_params("/api/status", None) == "/api/status"
        assert substitute_path_params("/api/status", {}) == "/api/status"

    def test_single_param_substitution(self):
        """Single parameter gets substituted."""
        path = "/users/{id}"
        result = substitute_path_params(path, {"id": "123"})
        assert result == "/users/123"

    def test_multiple_params_substitution(self):
        """Multiple parameters get substituted."""
        path = "/users/{user_id}/posts/{post_id}"
        result = substitute_path_params(path, {"user_id": "abc", "post_id": "456"})
        assert result == "/users/abc/posts/456"

    def test_missing_param_preserved(self):
        """Missing parameter placeholder remains as-is."""
        path = "/secrets/{key}"
        result = substitute_path_params(path, {"other": "value"})
        assert result == "/secrets/{key}"

    def test_partial_substitution(self):
        """Some params substituted, others preserved."""
        path = "/users/{id}/secrets/{key}"
        result = substitute_path_params(path, {"id": "123"})
        assert result == "/users/123/secrets/{key}"

    def test_numeric_value_coercion(self):
        """Numeric values get stringified."""
        path = "/items/{count}"
        result = substitute_path_params(path, {"count": 42})
        assert result == "/items/42"


# ============================================================================
# Form body to JSON conversion tests
# ============================================================================


class TestFormBodyToJson:
    """Tests for form-encoded body to JSON conversion."""

    def test_empty_body_unchanged(self):
        """Empty body returns unchanged."""
        assert form_body_to_json("") == ""
        assert form_body_to_json(None) is None

    def test_no_equals_unchanged(self):
        """Body without '=' returns unchanged (already JSON)."""
        body = '{"key": "value"}'
        assert form_body_to_json(body) == body

    def test_simple_form_conversion(self):
        """Simple form fields convert to JSON."""
        body = "name=test&value=hello"
        result = json.loads(form_body_to_json(body))
        assert result == {"name": "test", "value": "hello"}

    def test_boolean_true_coercion(self):
        """'true' string becomes boolean True."""
        body = "enabled=true"
        result = json.loads(form_body_to_json(body))
        assert result["enabled"] is True

    def test_boolean_false_coercion(self):
        """'false' string becomes boolean False."""
        body = "enabled=false"
        result = json.loads(form_body_to_json(body))
        assert result["enabled"] is False

    def test_boolean_case_sensitive(self):
        """Boolean coercion is case-sensitive."""
        body = "a=True&b=FALSE&c=true&d=false"
        result = json.loads(form_body_to_json(body))
        assert result["a"] == "True"  # Not coerced
        assert result["b"] == "FALSE"  # Not coerced
        assert result["c"] is True
        assert result["d"] is False

    def test_integer_coercion(self):
        """Integer strings become integers."""
        body = "ttl=300&count=0"
        result = json.loads(form_body_to_json(body))
        assert result["ttl"] == 300
        assert isinstance(result["ttl"], int)
        assert result["count"] == 0

    def test_float_coercion(self):
        """Float strings become floats."""
        body = "ratio=0.5&temp=98.6"
        result = json.loads(form_body_to_json(body))
        assert result["ratio"] == 0.5
        assert result["temp"] == 98.6

    def test_mixed_types(self):
        """Mixed types in form body."""
        body = "name=test&count=10&enabled=true&ratio=0.5"
        result = json.loads(form_body_to_json(body))
        assert result == {
            "name": "test",
            "count": 10,
            "enabled": True,
            "ratio": 0.5,
        }

    def test_url_decoding(self):
        """URL-encoded values get decoded."""
        body = "message=hello%20world&path=%2Fapi%2Fstatus"
        result = json.loads(form_body_to_json(body))
        assert result["message"] == "hello world"
        assert result["path"] == "/api/status"


# ============================================================================
# CLI parser tests
# ============================================================================


class TestBuildParser:
    """Tests for CLI argument parser."""

    def test_parser_has_compare_subcommand(self):
        """Parser includes 'compare' subcommand."""
        parser = build_parser()
        args = parser.parse_args(["compare", "--spec", "api.yaml", "--host-a", "http://a", "--host-b", "http://b"])
        assert args.command == "compare"
        assert args.spec == "api.yaml"
        assert args.host_a == "http://a"
        assert args.host_b == "http://b"

    def test_compare_requires_spec(self):
        """Compare subcommand requires --spec."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["compare", "--host-a", "http://a", "--host-b", "http://b"])

    def test_compare_requires_hosts(self):
        """Compare subcommand requires both hosts."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["compare", "--spec", "api.yaml"])
        with pytest.raises(SystemExit):
            parser.parse_args(["compare", "--spec", "api.yaml", "--host-a", "http://a"])

    def test_optional_auth_args(self):
        """Auth arguments are optional."""
        parser = build_parser()
        args = parser.parse_args([
            "compare", "--spec", "api.yaml",
            "--host-a", "http://a", "--host-b", "http://b",
            "--auth-a", "user:token", "--auth-b", "user2:token2"
        ])
        assert args.auth_a == "user:token"
        assert args.auth_b == "user2:token2"

    def test_json_flag(self):
        """--json flag is parsed correctly."""
        parser = build_parser()
        args = parser.parse_args([
            "compare", "--spec", "api.yaml",
            "--host-a", "http://a", "--host-b", "http://b",
            "--json"
        ])
        assert args.output_json is True

    def test_fail_on_choices(self):
        """--fail-on accepts only valid choices."""
        parser = build_parser()
        valid_choices = ["breaking", "structural", "cosmetic", "drift", "error", "any"]
        for choice in valid_choices:
            args = parser.parse_args([
                "compare", "--spec", "api.yaml",
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", choice
            ])
            assert args.fail_on == choice

    def test_path_params_parsing(self):
        """--path-params accepts NAME=VALUE format."""
        parser = build_parser()
        args = parser.parse_args([
            "compare", "--spec", "api.yaml",
            "--host-a", "http://a", "--host-b", "http://b",
            "--path-params", "id=123", "key=abc"
        ])
        assert args.path_params == ["id=123", "key=abc"]


# ============================================================================
# run_compare exit code tests
# ============================================================================


class TestRunCompareExitCodes:
    """Tests for run_compare exit codes based on --fail-on.

    Exit code semantics:
    - 0: OK or below threshold (CI should pass)
    - 1: Connection/parse errors
    - 2: Breaking drift detected
    - 3: Structural drift (or worse) detected
    - 4: Cosmetic drift (or worse) detected

    Without --fail-on, always returns 0 (informational mode).
    """

    @pytest.fixture
    def minimal_spec(self):
        """Create a minimal OpenAPI spec file."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/status": {
                    "get": {
                        "operationId": "getStatus",
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        return json.dumps(spec)

    @pytest.fixture
    def spec_file(self, minimal_spec):
        """Write spec to temp file and return path."""
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write(minimal_spec)
        yield path
        os.unlink(path)

    def test_exit_0_no_drift(self, spec_file):
        """Exit code 0 when no drift and no errors."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "none",
                "has_drift": False,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b"
            ])
            exit_code = run_compare(args)
            assert exit_code == 0

    def test_exit_0_no_fail_on_with_drift(self, spec_file):
        """Exit code 0 when drift present but --fail-on not set (informational mode)."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "cosmetic",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b"
            ])
            exit_code = run_compare(args)
            assert exit_code == 0  # No --fail-on, so no failure

    def test_exit_4_fail_on_drift_cosmetic(self, spec_file):
        """Exit code 4 when cosmetic drift and --fail-on drift."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "cosmetic",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "drift"
            ])
            exit_code = run_compare(args)
            assert exit_code == 4  # Cosmetic severity

    def test_exit_3_fail_on_drift_structural(self, spec_file):
        """Exit code 3 when structural drift and --fail-on drift."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "structural",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "drift"
            ])
            exit_code = run_compare(args)
            assert exit_code == 3  # Structural severity

    def test_exit_2_fail_on_drift_breaking(self, spec_file):
        """Exit code 2 when breaking drift and --fail-on drift."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "breaking",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "drift"
            ])
            exit_code = run_compare(args)
            assert exit_code == 2  # Breaking severity

    def test_exit_2_fail_on_breaking_only(self, spec_file):
        """Exit code 2 only for breaking drift with --fail-on breaking."""
        with patch("dd.cli.do_compare") as mock_compare:
            # Cosmetic drift should NOT trigger exit with --fail-on breaking
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "cosmetic",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "breaking"
            ])
            exit_code = run_compare(args)
            assert exit_code == 0  # Cosmetic does not trigger breaking threshold

    def test_exit_0_fail_on_structural_with_cosmetic(self, spec_file):
        """Exit code 0 for cosmetic drift with --fail-on structural."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "cosmetic",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "structural"
            ])
            exit_code = run_compare(args)
            assert exit_code == 0  # Cosmetic is below structural threshold

    def test_exit_3_fail_on_structural(self, spec_file):
        """Exit code 3 for structural drift with --fail-on structural."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "structural",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "structural"
            ])
            exit_code = run_compare(args)
            assert exit_code == 3

    def test_exit_1_fail_on_error(self, spec_file):
        """Exit code 1 when error present and --fail-on error."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "none",
                "has_drift": False,
                "error": "Connection refused",
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "error"
            ])
            exit_code = run_compare(args)
            assert exit_code == 1

    def test_exit_1_fail_on_any_with_error(self, spec_file):
        """Exit code 1 when error present and --fail-on any."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "none",
                "has_drift": False,
                "error": "Timeout",
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "any"
            ])
            exit_code = run_compare(args)
            assert exit_code == 1

    def test_exit_4_fail_on_any_with_cosmetic(self, spec_file):
        """Exit code 4 for cosmetic drift with --fail-on any."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "cosmetic",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--fail-on", "any"
            ])
            exit_code = run_compare(args)
            assert exit_code == 4

    def test_exit_1_spec_not_found(self):
        """Exit code 1 when spec file not found."""
        parser = build_parser()
        args = parser.parse_args([
            "compare", "--spec", "/nonexistent/spec.yaml",
            "--host-a", "http://a", "--host-b", "http://b"
        ])
        exit_code = run_compare(args)
        assert exit_code == 1


# ============================================================================
# JSON output tests
# ============================================================================


class TestRunCompareJsonOutput:
    """Tests for --json output mode."""

    @pytest.fixture
    def minimal_spec_file(self):
        """Write minimal spec to temp file."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/status": {
                    "get": {
                        "operationId": "getStatus",
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(spec, f)
        yield path
        os.unlink(path)

    def test_json_output_valid(self, minimal_spec_file, capsys):
        """--json flag produces valid JSON output."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "none",
                "has_drift": False,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", minimal_spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--json"
            ])
            run_compare(args)

            captured = capsys.readouterr()
            output = json.loads(captured.out)
            assert "results" in output
            assert "summary" in output
            assert output["summary"]["total"] == 1

    def test_json_output_summary_counts(self, minimal_spec_file, capsys):
        """JSON output includes correct summary counts with severity breakdown."""
        with patch("dd.cli.do_compare") as mock_compare:
            mock_compare.return_value = {
                "label": "GET /status",
                "severity": "structural",
                "has_drift": True,
                "error": None,
            }
            parser = build_parser()
            args = parser.parse_args([
                "compare", "--spec", minimal_spec_file,
                "--host-a", "http://a", "--host-b", "http://b",
                "--json"
            ])
            run_compare(args)

            captured = capsys.readouterr()
            output = json.loads(captured.out)
            assert output["summary"]["drift"] == 1
            assert output["summary"]["errors"] == 0
            assert output["summary"]["ok"] == 0
            # New severity breakdown
            assert "severity" in output["summary"]
            assert output["summary"]["severity"]["structural"] == 1
            assert output["summary"]["severity"]["cosmetic"] == 0
            assert output["summary"]["severity"]["breaking"] == 0


# ============================================================================
# Number parsing helper tests
# ============================================================================


class TestNumberParsingHelpers:
    """Tests for _is_number and _parse_number helpers."""

    def test_is_number_integers(self):
        from dd.cli import _is_number
        assert _is_number("0") is True
        assert _is_number("42") is True
        assert _is_number("-7") is True
        assert _is_number("1000000") is True

    def test_is_number_floats(self):
        from dd.cli import _is_number
        assert _is_number("3.14") is True
        assert _is_number("-0.5") is True
        assert _is_number("1.0") is True

    def test_is_number_scientific(self):
        from dd.cli import _is_number
        assert _is_number("1e10") is True
        assert _is_number("2.5E-3") is True

    def test_is_number_rejects_non_numbers(self):
        from dd.cli import _is_number
        assert _is_number("") is False
        assert _is_number("abc") is False
        assert _is_number("12abc") is False
        # Note: "NaN" is parsed by float() so _is_number returns True
        # This matches JavaScript's !isNaN() behavior for "NaN" string

    def test_parse_number_integers(self):
        from dd.cli import _parse_number
        assert _parse_number("42") == 42
        assert isinstance(_parse_number("42"), int)
        assert _parse_number("-7") == -7

    def test_parse_number_floats(self):
        from dd.cli import _parse_number
        assert _parse_number("3.14") == 3.14
        assert isinstance(_parse_number("3.14"), float)
        assert _parse_number("1.0") == 1.0
        assert isinstance(_parse_number("1.0"), float)  # Has dot, stays float

    def test_parse_number_scientific(self):
        from dd.cli import _parse_number
        assert _parse_number("1e3") == 1000.0
        assert isinstance(_parse_number("1e3"), float)  # Has 'e', stays float


# ============================================================================
# build_response_schema tests
# ============================================================================


class TestBuildResponseSchema:
    """Tests for build_response_schema function."""

    def test_empty_response_fields(self):
        from dd.cli import build_response_schema
        result = build_response_schema({})
        assert result == {}

    def test_single_status_code(self):
        from dd.cli import build_response_schema
        response_fields = {
            "200": [
                {"name": "id", "path": "id", "type": "string", "required": True},
                {"name": "name", "path": "name", "type": "string", "required": False},
            ]
        }
        result = build_response_schema(response_fields)
        assert "200" in result
        assert len(result["200"]) == 2
        assert result["200"][0].name == "id"
        assert result["200"][0].required is True
        assert result["200"][1].name == "name"
        assert result["200"][1].required is False

    def test_multiple_status_codes(self):
        from dd.cli import build_response_schema
        response_fields = {
            "200": [{"name": "data", "path": "data", "type": "object"}],
            "404": [{"name": "error", "path": "error", "type": "string"}],
        }
        result = build_response_schema(response_fields)
        assert "200" in result
        assert "404" in result
        assert result["200"][0].name == "data"
        assert result["404"][0].name == "error"

    def test_field_defaults(self):
        from dd.cli import build_response_schema
        # Minimal field dict - defaults should be applied
        response_fields = {
            "200": [{"name": "x", "path": "x", "type": "string"}]
        }
        result = build_response_schema(response_fields)
        field = result["200"][0]
        assert field.required is False  # default
        assert field.nested is False  # default
        assert field.format == ""  # default
        assert field.drift_ignore is False  # default
        assert field.deprecated is False  # default


# ============================================================================
# operation_to_compare_request tests
# ============================================================================


class TestOperationToCompareRequest:
    """Tests for operation_to_compare_request function."""

    def test_basic_operation(self):
        from dd.cli import operation_to_compare_request
        op = {
            "method": "GET",
            "path": "/api/status",
            "label": "GET /api/status",
            "body": "",
            "content_type": "query",
        }
        cr = operation_to_compare_request(op, host_a="http://a", host_b="http://b")
        assert cr.method == "GET"
        assert cr.path == "/api/status"
        assert cr.label == "GET /api/status"
        assert cr.host_a == "http://a"
        assert cr.host_b == "http://b"

    def test_path_param_substitution(self):
        from dd.cli import operation_to_compare_request
        op = {
            "method": "GET",
            "path": "/users/{id}",
            "label": "GET /users/{id}",
        }
        cr = operation_to_compare_request(op, path_params={"id": "123"})
        assert cr.path == "/users/123"

    def test_form_body_to_json_conversion(self):
        from dd.cli import operation_to_compare_request
        op = {
            "method": "POST",
            "path": "/api/data",
            "label": "POST /api/data",
            "body": "name=test&count=10",
            "content_type": "application/json",  # Should trigger conversion
        }
        cr = operation_to_compare_request(op)
        # Body should be converted to JSON
        body = json.loads(cr.body)
        assert body["name"] == "test"
        assert body["count"] == 10

    def test_auth_credentials_passed(self):
        from dd.cli import operation_to_compare_request
        op = {"method": "GET", "path": "/", "label": "GET /"}
        cr = operation_to_compare_request(op, auth_a="user:pass", auth_b="admin:secret")
        assert cr.auth_a == "user:pass"
        assert cr.auth_b == "admin:secret"

    def test_response_schema_built(self):
        from dd.cli import operation_to_compare_request
        op = {
            "method": "GET",
            "path": "/",
            "label": "GET /",
            "response_fields": {
                "200": [{"name": "id", "path": "id", "type": "string"}]
            },
        }
        cr = operation_to_compare_request(op)
        assert cr.response_schema is not None
        assert "200" in cr.response_schema
        assert cr.response_schema["200"][0].name == "id"


# ============================================================================
# operations_to_compare_requests tests
# ============================================================================


class TestOperationsToCompareRequests:
    """Tests for operations_to_compare_requests batch conversion."""

    def test_empty_operations(self):
        from dd.cli import operations_to_compare_requests
        result = operations_to_compare_requests([])
        assert result == []

    def test_multiple_operations(self):
        from dd.cli import operations_to_compare_requests
        ops = [
            {"method": "GET", "path": "/a", "label": "GET /a"},
            {"method": "POST", "path": "/b", "label": "POST /b"},
            {"method": "DELETE", "path": "/c", "label": "DELETE /c"},
        ]
        result = operations_to_compare_requests(ops, host_a="http://a", host_b="http://b")
        assert len(result) == 3
        assert result[0].path == "/a"
        assert result[1].path == "/b"
        assert result[2].path == "/c"

    def test_shared_params_applied_to_all(self):
        from dd.cli import operations_to_compare_requests
        ops = [
            {"method": "GET", "path": "/users/{id}", "label": "GET /users/{id}"},
            {"method": "DELETE", "path": "/users/{id}", "label": "DELETE /users/{id}"},
        ]
        result = operations_to_compare_requests(
            ops,
            path_params={"id": "42"},
            host_a="http://a",
            host_b="http://b",
            auth_a="user:pass",
        )
        assert all(cr.path == "/users/42" for cr in result)
        assert all(cr.host_a == "http://a" for cr in result)
        assert all(cr.auth_a == "user:pass" for cr in result)
