# drift-detector/dd/compare.py

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
from fastapi import APIRouter
from pydantic import BaseModel

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
def hit(
    host: str,
    method: str,
    path: str,
    body: str | None,
    content_type: str,
    auth: str | None,
) -> dict:
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
            method,
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

    result = {
        "label": cr.label,
        "method": cr.method,
        "path": cr.path,
        "group": cr.group,
        "has_drift": bool(diff),
        "diff": json.loads(diff.to_json()) if diff else {},
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
async def test_host(payload: dict):
    """Quick connectivity test: hit GET on the host root or /api/v1/status."""
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
async def compare_single(cr: CompareRequest):
    host_a = (cr.host_a or "").strip() or HOST_A
    host_b = (cr.host_b or "").strip() or HOST_B
    return do_compare(host_a, host_b, cr, None)


@router.post("/api/batch")
async def compare_batch(batch: BatchRequest):
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
