# dd/compare.py

"""
Compare routes: single endpoint compare, batch compare, host connectivity test.
Also contains the HTTP client helper (hit) and request models.
"""

import json
from datetime import datetime, timezone
from collections.abc import Sequence
from typing import Optional

import requests as req
from deepdiff import DeepDiff
from fastapi import APIRouter, Request
from pydantic import BaseModel

from dd.auth import get_session_hash
from dd.config import DEFAULT_ENVIRONMENTS, DEFAULT_IGNORE, HOST_A, HOST_B, VERIFY_SSL, TEMPORAL_FORMATS, derive_ignore_paths

router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ResponseSchemaField(BaseModel):
    """A single field from a parsed response schema."""
    name: str
    path: str
    type: str
    required: bool = False
    nested: bool = False
    format: str = ""
    description: str = ""
    drift_ignore: bool = False
    deprecated: bool = False


class CompareRequest(BaseModel):
    label: str
    method: str  # GET, POST, PUT, DELETE
    path: str  # e.g. /api/v1/status
    body: Optional[str] = None  # form-encoded body string or JSON string
    content_type: Optional[str] = (
        "query"  # "query" | "application/x-www-form-urlencoded" | "application/json"
    )
    group: Optional[str] = (
        None  # UI grouping label (pass-through, not used by backend)
    )
    host_a: Optional[str] = None  # override per-request
    host_b: Optional[str] = None  # override per-request
    auth_a: Optional[str] = None  # "user:token" for host A
    auth_b: Optional[str] = None  # "user:token" for host B
    ignore_paths: Optional[list[str]] = None
    response_schema: Optional[dict[str, list[ResponseSchemaField]]] = (
        None  # keyed by status code, e.g. {"200": [...fields]}
    )
    extra_ignore_paths: Optional[list[str]] = None  # spec-derived ignore paths


class BatchRequest(BaseModel):
    host_a: Optional[str] = None
    host_b: Optional[str] = None
    requests: list[CompareRequest]
    ignore_paths: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

# Allowed HTTP methods - prevents SSRF-adjacent attacks via CONNECT or other
# unusual methods that could be used to tunnel or probe internal networks
ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"})


def hit(
    host: str,
    method: str,
    path: str,
    body: str | None,
    content_type: str,
    auth: str | None,
) -> dict:
    # Validate method to prevent SSRF-adjacent attacks
    method_upper = method.upper()
    if method_upper not in ALLOWED_METHODS:
        return {
            "status": None,
            "headers": {},
            "body": None,
            "error": f"Method '{method}' not allowed. Allowed: {', '.join(sorted(ALLOWED_METHODS))}",
            "elapsed_ms": None,
            "request_headers": {},
            "request_url": None,
            "request_body": None,
        }

    url = f"{host}{path}"
    headers = {}
    data = None
    json_body = None
    params = None

    if body:
        if content_type == "application/json":
            try:
                json_body = json.loads(body)
            except json.JSONDecodeError:
                data = body
        elif content_type == "query":
            from urllib.parse import parse_qs

            params = {
                k: v[0] if len(v) == 1 else v
                for k, v in parse_qs(body, keep_blank_values=True).items()
            }
        else:
            data = body

    if content_type and content_type != "query" and not json_body:
        headers["Content-Type"] = content_type

    auth_tuple: tuple[str, str] | None = None
    if auth:
        parts = auth.split(":", 1)
        if len(parts) == 2:
            auth_tuple = (parts[0], parts[1])

    try:
        r = req.request(
            method_upper,
            url,
            data=data,
            json=json_body,
            params=params,
            headers=headers,
            auth=auth_tuple,
            timeout=15,
            verify=VERIFY_SSL,
        )
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            resp_body = r.json()
        else:
            resp_body = r.text
        # Capture request body for curl reproduction
        req_body = r.request.body
        if isinstance(req_body, bytes):
            req_body = req_body.decode("utf-8", errors="replace")

        return {
            "status": r.status_code,
            "headers": dict(r.headers),
            "body": resp_body,
            "error": None,
            "elapsed_ms": int(r.elapsed.total_seconds() * 1000),
            "request_headers": dict(r.request.headers),
            "request_url": r.request.url,
            "request_body": req_body,
        }
    except Exception as e:
        return {
            "status": None,
            "headers": {},
            "body": None,
            "error": str(e),
            "elapsed_ms": None,
            "request_headers": {},
            "request_url": None,
            "request_body": None,
        }


def _python_type_name(value) -> str:
    """Return a simplified type name for a Python value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _type_matches(expected_type: str, actual_type: str) -> bool:
    """Check if an actual Python type matches an expected OpenAPI type."""
    if expected_type == actual_type:
        return True
    if expected_type == "number" and actual_type in ("integer", "number"):
        return True
    return False


def _get_nested(body: dict, dotted_path: str):
    """Walk a dict by dotted path. Returns (found, value)."""
    parts = dotted_path.split(".")
    node = body
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return False, None
        node = node[p]
    return True, node


# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------
def _extract_field_path(deepdiff_path: str) -> str:
    """
    Convert DeepDiff path like "root['body']['user']['id']" to dotted path "user.id".
    Strips the root['body'] prefix since schema paths are relative to body.
    """
    import re
    matches = re.findall(r"\['([^']+)'\]", deepdiff_path)
    if len(matches) > 1 and matches[0] == "body":
        return ".".join(matches[1:])
    return ".".join(matches) if matches else deepdiff_path


def _severity_order(severity: str) -> int:
    """Return numeric order for severity comparison."""
    return {"none": 0, "cosmetic": 1, "structural": 2, "breaking": 3}.get(severity, 0)


def classify_severity(
    diff: dict,
    response_schema: dict | None,
    status_a: int | None,
    status_b: int | None,
) -> tuple[str, list[dict]]:
    """
    Classify drift severity and return (severity, reasons).

    Severity levels (lowest to highest):
    - "none": no drift detected
    - "cosmetic": value changes in existing fields
    - "structural": fields added/removed (optional), array changes
    - "breaking": status change, required field missing, type mismatch on required

    Args:
        diff: DeepDiff result dict
        response_schema: dict mapping status codes to lists of field dicts with 'path', 'required', etc.
        status_a: HTTP status from host A (may be None on connection error)
        status_b: HTTP status from host B (may be None on connection error)

    Returns:
        (severity, reasons) where each reason is {category, path, detail, severity}
    """
    if not diff and status_a == status_b:
        return ("none", [])

    reasons = []
    max_severity = "cosmetic" if diff else "none"

    def upgrade(new_sev):
        nonlocal max_severity
        if _severity_order(new_sev) > _severity_order(max_severity):
            max_severity = new_sev

    # Build required-field and deprecated-field lookups from schema
    required_fields: set[str] = set()
    deprecated_fields: set[str] = set()
    if response_schema:
        # response_schema is keyed by status code string
        for status_str, fields in response_schema.items():
            for f in fields:
                fd = f.model_dump() if hasattr(f, "model_dump") else f
                if fd.get("required"):
                    required_fields.add(fd["path"])
                if fd.get("deprecated"):
                    deprecated_fields.add(fd["path"])

    # Status code change = breaking (includes None from connection errors)
    if status_a != status_b:
        reasons.append({
            "category": "status_change",
            "path": "status",
            "detail": f"{status_a} → {status_b}",
            "severity": "breaking",
        })
        upgrade("breaking")

    # Type changes
    for path, change in diff.get("type_changes", {}).items():
        field_path = _extract_field_path(path)
        is_required = field_path in required_fields
        sev = "breaking" if is_required else "structural"
        reasons.append({
            "category": "type_change",
            "path": field_path,
            "detail": f"{change.get('old_type', '?')} → {change.get('new_type', '?')}",
            "severity": sev,
        })
        upgrade(sev)

    # Removed fields (in A but not B)
    for path, value in diff.get("dictionary_item_removed", {}).items():
        field_path = _extract_field_path(path)
        is_required = field_path in required_fields
        is_deprecated = field_path in deprecated_fields
        # Base severity: breaking for required, structural for optional
        sev = "breaking" if is_required else "structural"
        detail = "missing in B"
        # Deprecated fields get severity downgrade:
        # - breaking (required) -> structural
        # - structural (optional) -> cosmetic
        if is_deprecated:
            sev = "structural" if is_required else "cosmetic"
            detail = "missing in B (deprecated)"
        reasons.append({
            "category": "field_removed",
            "path": field_path,
            "detail": detail,
            "severity": sev,
        })
        upgrade(sev)

    # Added fields (in B but not A) = structural (additive, backward-compatible)
    for path, value in diff.get("dictionary_item_added", {}).items():
        field_path = _extract_field_path(path)
        reasons.append({
            "category": "field_added",
            "path": field_path,
            "detail": "new in B",
            "severity": "structural",
        })
        upgrade("structural")

    # Value changes = cosmetic (unless status, handled above)
    for path, change in diff.get("values_changed", {}).items():
        if "['status']" in path:
            continue  # Already handled as status_change
        field_path = _extract_field_path(path)
        reasons.append({
            "category": "value_changed",
            "path": field_path,
            "detail": "value differs",
            "severity": "cosmetic",
        })
        # Don't upgrade — cosmetic is baseline

    # Array item changes
    for path, value in diff.get("iterable_item_added", {}).items():
        field_path = _extract_field_path(path)
        reasons.append({
            "category": "array_item_added",
            "path": field_path,
            "detail": "item added in B",
            "severity": "structural",
        })
        upgrade("structural")

    for path, value in diff.get("iterable_item_removed", {}).items():
        field_path = _extract_field_path(path)
        reasons.append({
            "category": "array_item_removed",
            "path": field_path,
            "detail": "item missing in B",
            "severity": "structural",
        })
        upgrade("structural")

    return (max_severity, reasons)


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------
def validate_response_against_schema(
    response: dict, schema_fields: Sequence[dict]
) -> list[dict]:
    """Validate a response body against parsed schema fields."""
    body = response.get("body")
    if not isinstance(body, dict):
        return []

    results = []
    for f in schema_fields:
        if f.get("nested"):
            continue
        path = f["path"]
        expected_type = f["type"]
        present, value = _get_nested(body, path)
        actual_type = _python_type_name(value) if present else None
        required = f.get("required", False)
        if not present:
            conforms = not required  # missing optional fields still conform
        else:
            conforms = _type_matches(expected_type, actual_type or "")
        results.append(
            {
                "field": path,
                "expected_type": expected_type,
                "actual_type": actual_type,
                "present": present,
                "conforms": conforms,
                "required": required,
            }
        )
    return results


def do_compare(
    host_a: str,
    host_b: str,
    cr: CompareRequest,
    global_ignore: list[str] | None,
) -> dict:
    ignore = DEFAULT_IGNORE.copy()
    if global_ignore:
        ignore.extend(global_ignore)
    if cr.ignore_paths:
        ignore.extend(cr.ignore_paths)
    if cr.extra_ignore_paths:
        ignore.extend(cr.extra_ignore_paths)
    elif cr.response_schema:
        # Derive ignore paths from response_schema fields marked as drift_ignore
        # when extra_ignore_paths was not explicitly provided by the caller.
        for _, fields in cr.response_schema.items():
            field_dicts = [f.model_dump() for f in fields]
            derived = derive_ignore_paths(field_dicts)
            if derived:
                ignore.extend(derived)

    a = hit(
        host_a,
        cr.method,
        cr.path,
        cr.body,
        cr.content_type or "query",
        cr.auth_a,
    )
    b = hit(
        host_b,
        cr.method,
        cr.path,
        cr.body,
        cr.content_type or "query",
        cr.auth_b,
    )

    # Compare status + body (skip headers and timing for drift purposes)
    comparable_a = {"status": a["status"], "body": a["body"]}
    comparable_b = {"status": b["status"], "body": b["body"]}

    diff = DeepDiff(
        comparable_a, comparable_b, ignore_order=True, exclude_paths=ignore
    )

    diff_dict = json.loads(diff.to_json()) if diff else {}

    # Build schema dict for severity classification
    schema_for_severity = None
    if cr.response_schema:
        schema_for_severity = {
            k: [f.model_dump() if hasattr(f, "model_dump") else f for f in v]
            for k, v in cr.response_schema.items()
        }

    # Classify severity
    severity, severity_reasons = classify_severity(
        diff=diff_dict,
        response_schema=schema_for_severity,
        status_a=a["status"],
        status_b=b["status"],
    )

    result = {
        "label": cr.label,
        "method": cr.method,
        "path": cr.path,
        "group": cr.group,
        "has_drift": bool(diff),
        "diff": diff_dict,
        "severity": severity,
        "severity_reasons": severity_reasons,
        "ignored_paths": ignore,
        "response_a": a,
        "response_b": b,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    # Spec-conformance validation
    if cr.response_schema:
        conformance = {}
        for resp_label, resp in [("a", a), ("b", b)]:
            status_str = str(resp.get("status", ""))
            schema_fields = cr.response_schema.get(status_str)
            if schema_fields:
                fields_dicts: list[dict] = [
                    f.model_dump() if isinstance(f, ResponseSchemaField) else f
                    for f in schema_fields
                ]
                conformance[resp_label] = validate_response_against_schema(
                    resp, fields_dicts
                )
        if conformance:
            result["conformance"] = conformance

    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/api/config")
async def get_config():
    return {
        "default_environments": DEFAULT_ENVIRONMENTS,
        "default_ignore": DEFAULT_IGNORE,
        "temporal_formats": sorted(TEMPORAL_FORMATS),
    }


@router.post("/api/test-host")
async def test_host(request: Request, payload: dict):
    """Quick connectivity test: hit GET on the host root or /api/v1/status.

    Requires authentication to prevent SSRF attacks where unauthenticated
    callers could use the server as a proxy to probe internal networks.
    """
    get_session_hash(request)  # Require valid session token; raises 401 if missing
    host = (payload.get("host") or "").strip()
    auth = (payload.get("auth") or "").strip()
    if not host:
        return {"ok": False, "error": "No host provided"}
    result = hit(host, "GET", "/api/v1/status", None, "query", auth or None)
    return {
        "ok": result["error"] is None and result["status"] is not None,
        "status": result["status"],
        "elapsed_ms": result["elapsed_ms"],
        "error": result["error"],
    }


@router.post("/api/compare")
async def compare_single(request: Request, cr: CompareRequest):
    """Compare API responses between host_a and host_b.

    Requires authentication to prevent SSRF attacks where unauthenticated
    callers could use the server to probe internal networks via host_a/host_b.
    """
    get_session_hash(request)  # Require valid session token; raises 401 if missing
    host_a = (cr.host_a or "").strip() or HOST_A
    host_b = (cr.host_b or "").strip() or HOST_B
    return do_compare(host_a, host_b, cr, None)


@router.post("/api/batch")
async def compare_batch(request: Request, batch: BatchRequest):
    """Batch compare multiple endpoints between host_a and host_b.

    Requires authentication to prevent SSRF attacks where unauthenticated
    callers could use the server to probe internal networks via host_a/host_b.
    """
    get_session_hash(request)  # Require valid session token; raises 401 if missing
    host_a = (batch.host_a or "").strip() or HOST_A
    host_b = (batch.host_b or "").strip() or HOST_B
    results = []
    for cr in batch.requests:
        results.append(do_compare(host_a, host_b, cr, batch.ignore_paths))
    summary = {
        "total": len(results),
        "drifts": sum(1 for r in results if r["has_drift"]),
        "ok": sum(1 for r in results if not r["has_drift"]),
    }
    return {"summary": summary, "results": results}
