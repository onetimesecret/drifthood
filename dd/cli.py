# dd/cli.py

"""
CLI utilities for headless/scripted drift detection.

Ports frontend logic for operation-to-request assembly to Python,
enabling batch comparisons without the web UI.

Usage:
    python -m dd.cli compare --spec api.yaml --host-a http://localhost:8000 --host-b http://localhost:8001
    python -m dd.cli compare --spec api.yaml --host-a http://localhost:8000 --host-b http://localhost:8001 --json
    python -m dd.cli compare --spec api.yaml --host-a http://localhost:8000 --host-b http://localhost:8001 --fail-on drift
"""

import argparse
import json
import re
import sys
from typing import Optional
from urllib.parse import parse_qs

from dd.compare import CompareRequest, ResponseSchemaField, do_compare
from dd.openapi import parse_openapi


def substitute_path_params(path: str, param_values: Optional[dict] = None) -> str:
    """Replace path parameter placeholders with actual values.

    Args:
        path: Path with placeholders like /users/{id} or /secrets/{key}
        param_values: Dict mapping param name to value, e.g. {"id": "123"}
                      If None or param missing, placeholders remain as-is.

    Returns:
        Path with substitutions applied.
    """
    if not param_values:
        return path

    def replace(match):
        param_name = match.group(1)
        return str(param_values.get(param_name, match.group(0)))

    return re.sub(r"\{(\w+)\}", replace, path)


def form_body_to_json(body: str) -> str:
    """Convert form-encoded body to JSON string.

    Ports the frontend logic from OpenApiLoader.svelte:93-107.
    When content_type is application/json but body looks like form-encoded
    data (contains '='), convert to JSON with type coercion:
    - "true"/"false" (case-sensitive) become boolean
    - Numeric strings become numbers
    - Other values are URL-decoded strings

    Args:
        body: Form-encoded string like "passphrase=secret&ttl=300"

    Returns:
        JSON string like '{"passphrase":"secret","ttl":300}'
        Returns original body on parse error (fallback behavior).
    """
    if not body or "=" not in body:
        return body

    try:
        parsed = parse_qs(body, keep_blank_values=True)
        obj = {}
        for k, v in parsed.items():
            # parse_qs returns lists; take first value (like JS split('='))
            val = v[0] if len(v) == 1 else v
            if isinstance(val, str):
                # Boolean coercion (case-sensitive to match JS frontend)
                if val == "true":
                    obj[k] = True
                elif val == "false":
                    obj[k] = False
                # Number coercion: matches JS !isNaN(v) && v !== ''
                elif val and _is_number(val):
                    obj[k] = _parse_number(val)
                else:
                    # parse_qs already handles URL decoding
                    obj[k] = val
            else:
                obj[k] = val
        return json.dumps(obj)
    except Exception:
        # Keep original body on error (matches JS catch block)
        return body


def _is_number(s: str) -> bool:
    """Check if string represents a number (matches JS !isNaN behavior).

    Returns True for integers, floats, scientific notation, etc.
    Empty strings return False.
    """
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _parse_number(s: str) -> int | float:
    """Parse string to int or float, preserving integer type when possible."""
    f = float(s)
    # Return int if it's a whole number without scientific notation
    if f.is_integer() and "." not in s and "e" not in s.lower():
        return int(f)
    return f


def build_response_schema(response_fields: dict) -> dict[str, list[ResponseSchemaField]]:
    """Build response_schema dict from OpenAPI response_fields.

    Args:
        response_fields: Dict keyed by status code string, e.g.
            {"200": [{"name": "custid", "path": "custid", "type": "string", ...}]}

    Returns:
        Dict keyed by status code with lists of ResponseSchemaField.
    """
    result = {}
    for status_code, fields in response_fields.items():
        result[status_code] = [
            ResponseSchemaField(
                name=f.get("name", ""),
                path=f.get("path", ""),
                type=f.get("type", "string"),
                required=f.get("required", False),
                nested=f.get("nested", False),
                format=f.get("format", ""),
                description=f.get("description", ""),
                drift_ignore=f.get("drift_ignore", False),
                deprecated=f.get("deprecated", False),
            )
            for f in fields
        ]
    return result


def operation_to_compare_request(
    op: dict,
    *,
    path_params: Optional[dict] = None,
    host_a: Optional[str] = None,
    host_b: Optional[str] = None,
    auth_a: Optional[str] = None,
    auth_b: Optional[str] = None,
    ignore_paths: Optional[list[str]] = None,
) -> CompareRequest:
    """Convert a single OpenAPI operation to a CompareRequest.

    Args:
        op: Operation dict from openapi.parse() with keys:
            method, path, label, body, content_type, fields,
            query_fields, path_fields, response_fields
        path_params: Values to substitute in path placeholders
        host_a, host_b: Optional host overrides
        auth_a, auth_b: Optional auth overrides (user:token format)
        ignore_paths: Optional paths to ignore in diff

    Returns:
        CompareRequest ready for the /api/compare endpoint.
    """
    method = op.get("method", "GET").upper()
    path = op.get("path", "")
    label = op.get("label", f"{method} {path}")
    body = op.get("body", "") or ""
    content_type = op.get("content_type", "query")
    group = op.get("_group") or op.get("group")

    # Substitute path params
    if path_params:
        path = substitute_path_params(path, path_params)

    # Normalize body: convert form to JSON when content_type indicates JSON
    if content_type == "application/json" and body and "=" in body:
        body = form_body_to_json(body)

    # Build response_schema from response_fields
    response_fields = op.get("response_fields", {})
    response_schema = build_response_schema(response_fields) if response_fields else None

    return CompareRequest(
        label=label,
        method=method,
        path=path,
        body=body or None,
        content_type=content_type,
        group=group,
        host_a=host_a,
        host_b=host_b,
        auth_a=auth_a,
        auth_b=auth_b,
        ignore_paths=ignore_paths,
        response_schema=response_schema,
    )


def operations_to_compare_requests(
    operations: list[dict],
    *,
    path_params: Optional[dict] = None,
    host_a: Optional[str] = None,
    host_b: Optional[str] = None,
    auth_a: Optional[str] = None,
    auth_b: Optional[str] = None,
    ignore_paths: Optional[list[str]] = None,
) -> list[CompareRequest]:
    """Convert OpenAPI operations to CompareRequest list.

    This is the Python equivalent of the frontend's loadSelectedToEndpoints()
    logic in OpenApiLoader.svelte.

    Args:
        operations: List of operation dicts from openapi.parse()["operations"]
        path_params: Global path param values to substitute
        host_a, host_b: Host overrides
        auth_a, auth_b: Auth credentials (user:token format)
        ignore_paths: Paths to ignore in diffs

    Returns:
        List of CompareRequest objects ready for batch comparison.
    """
    return [
        operation_to_compare_request(
            op,
            path_params=path_params,
            host_a=host_a,
            host_b=host_b,
            auth_a=auth_a,
            auth_b=auth_b,
            ignore_paths=ignore_paths,
        )
        for op in operations
    ]


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="dd",
        description="Drift detection CLI for API comparison",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # compare subcommand
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare API responses between two hosts using an OpenAPI spec",
    )
    compare_parser.add_argument(
        "--spec",
        required=True,
        help="Path to OpenAPI spec file (JSON or YAML)",
    )
    compare_parser.add_argument(
        "--host-a",
        required=True,
        help="Base URL for host A (e.g., http://localhost:8000)",
    )
    compare_parser.add_argument(
        "--host-b",
        required=True,
        help="Base URL for host B (e.g., http://localhost:8001)",
    )
    compare_parser.add_argument(
        "--auth-a",
        help="Auth credentials for host A (format: user:token)",
    )
    compare_parser.add_argument(
        "--auth-b",
        help="Auth credentials for host B (format: user:token)",
    )
    compare_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output results as JSON",
    )
    compare_parser.add_argument(
        "--fail-on",
        choices=["breaking", "structural", "cosmetic", "drift", "error", "any"],
        help=(
            "Exit with non-zero status when threshold is met. "
            "Severity levels (lowest to highest): cosmetic, structural, breaking. "
            "'drift' = any drift (same as cosmetic), 'error' = connection/parse errors, "
            "'any' = drift OR error. "
            "Exit codes: 0 = OK or below threshold, 1 = errors, 2 = breaking, "
            "3 = structural (or worse), 4 = cosmetic (or worse)."
        ),
    )
    compare_parser.add_argument(
        "--tags",
        nargs="+",
        help="Filter operations by tag(s)",
    )
    compare_parser.add_argument(
        "--operations",
        nargs="+",
        help="Filter by operation ID(s) or 'METHOD /path' patterns",
    )
    compare_parser.add_argument(
        "--path-params",
        nargs="+",
        metavar="NAME=VALUE",
        help="Path parameter substitutions (e.g., id=123 key=abc)",
    )

    return parser


def run_compare(args: argparse.Namespace) -> int:
    """Execute the compare subcommand.

    Args:
        args: Parsed CLI arguments

    Returns:
        Exit code based on --fail-on threshold:
        - 0: OK or severity below threshold (CI should pass)
        - 1: Connection/parse errors
        - 2: Breaking drift detected
        - 3: Structural drift (or worse) detected
        - 4: Cosmetic drift (or worse) detected

        Without --fail-on, always returns 0 (informational mode).
        This means cosmetic drift alone won't fail CI unless explicitly requested.
    """
    # Load and parse OpenAPI spec
    try:
        with open(args.spec, "r", encoding="utf-8") as f:
            raw = f.read()
        spec = parse_openapi(raw)
    except FileNotFoundError:
        print(f"Error: Spec file not found: {args.spec}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: Failed to parse spec: {e}", file=sys.stderr)
        return 1

    operations = spec.get("operations", [])
    if not operations:
        print("Warning: No operations found in spec", file=sys.stderr)
        return 0

    # Filter by tags
    if args.tags:
        tag_set = set(args.tags)
        operations = [
            op for op in operations
            if op.get("tags") and any(t in tag_set for t in op.get("tags", []))
        ]

    # Filter by operation patterns
    if args.operations:
        filtered = []
        for op in operations:
            op_id = op.get("operationId", "")
            op_key = f"{op.get('method', '')} {op.get('path', '')}"
            if op_id in args.operations or op_key in args.operations:
                filtered.append(op)
        operations = filtered

    if not operations:
        print("Warning: No operations match the filter criteria", file=sys.stderr)
        return 0

    # Parse path parameters
    path_params = {}
    if args.path_params:
        for param in args.path_params:
            if "=" in param:
                name, value = param.split("=", 1)
                path_params[name] = value

    # Convert operations to compare requests
    requests = operations_to_compare_requests(
        operations,
        path_params=path_params,
        host_a=args.host_a,
        host_b=args.host_b,
        auth_a=args.auth_a,
        auth_b=args.auth_b,
    )

    # Run comparisons
    results = []
    error_count = 0
    severity_counts = {"none": 0, "cosmetic": 0, "structural": 0, "breaking": 0}

    for cr in requests:
        result = do_compare(args.host_a, args.host_b, cr, None)
        results.append(result)
        if result.get("error"):
            error_count += 1
        else:
            sev = result.get("severity", "none")
            if sev in severity_counts:
                severity_counts[sev] += 1
            elif result.get("has_drift"):
                # Fallback if severity not available
                severity_counts["cosmetic"] += 1

    # Aggregate counts for summary
    drift_count = severity_counts["cosmetic"] + severity_counts["structural"] + severity_counts["breaking"]

    # Output results
    if args.output_json:
        print(json.dumps({
            "results": results,
            "summary": {
                "total": len(results),
                "drift": drift_count,
                "errors": error_count,
                "ok": severity_counts["none"],
                "severity": {
                    "breaking": severity_counts["breaking"],
                    "structural": severity_counts["structural"],
                    "cosmetic": severity_counts["cosmetic"],
                },
            },
        }, indent=2))
    else:
        # Human-readable output with severity indicators
        severity_labels = {
            "none": "[OK]      ",
            "cosmetic": "[COSMETIC]",
            "structural": "[STRUCT]  ",
            "breaking": "[BREAKING]",
        }
        for r in results:
            label = r.get("label", "Unknown")
            if r.get("error"):
                print(f"[ERROR]    {label}: {r['error']}")
            else:
                sev = r.get("severity", "none")
                marker = severity_labels.get(sev, "[DRIFT]   ")
                print(f"{marker} {label}")

        print()
        parts = [f"{len(results)} operations"]
        if severity_counts["breaking"]:
            parts.append(f"{severity_counts['breaking']} breaking")
        if severity_counts["structural"]:
            parts.append(f"{severity_counts['structural']} structural")
        if severity_counts["cosmetic"]:
            parts.append(f"{severity_counts['cosmetic']} cosmetic")
        if error_count:
            parts.append(f"{error_count} errors")
        print(f"Summary: {', '.join(parts)}")

    # Determine exit code based on --fail-on
    # Exit codes: 0 = OK, 1 = errors, 2 = breaking, 3 = structural+, 4 = cosmetic+
    if not args.fail_on:
        return 0

    # Error-related thresholds
    if args.fail_on == "error" and error_count > 0:
        return 1
    if args.fail_on == "any" and error_count > 0:
        return 1

    # Severity-based thresholds with distinct exit codes
    if args.fail_on in ("breaking",) and severity_counts["breaking"] > 0:
        return 2
    if args.fail_on in ("structural",):
        if severity_counts["breaking"] > 0:
            return 2
        if severity_counts["structural"] > 0:
            return 3
    if args.fail_on in ("cosmetic", "drift", "any"):
        if severity_counts["breaking"] > 0:
            return 2
        if severity_counts["structural"] > 0:
            return 3
        if severity_counts["cosmetic"] > 0:
            return 4

    return 0


def main():
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "compare":
        sys.exit(run_compare(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
