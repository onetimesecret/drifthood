"""
Compare routes: single endpoint compare, batch compare, host connectivity test.
Also contains the HTTP client helper (hit) and request models.
"""

import json
import requests as req
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from deepdiff import DeepDiff
from dd.config import HOST_A, HOST_B, DEFAULT_IGNORE

router = APIRouter()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class CompareRequest(BaseModel):
    label: str
    method: str                     # GET, POST, PUT, DELETE
    path: str                       # e.g. /api/v1/status
    body: Optional[str] = None      # form-encoded body string or JSON string
    content_type: Optional[str] = "query"  # "query" | "application/x-www-form-urlencoded" | "application/json"
    group: Optional[str] = None     # UI grouping label (pass-through, not used by backend)
    host_a: Optional[str] = None    # override per-request
    host_b: Optional[str] = None    # override per-request
    auth_a: Optional[str] = None    # "user:token" for host A
    auth_b: Optional[str] = None    # "user:token" for host B
    ignore_paths: Optional[list[str]] = None

class BatchRequest(BaseModel):
    host_a: Optional[str] = None
    host_b: Optional[str] = None
    requests: list[CompareRequest]
    ignore_paths: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------
def hit(host: str, method: str, path: str, body: str | None, content_type: str, auth: str | None) -> dict:
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
            params = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(body, keep_blank_values=True).items()}
        else:
            data = body

    if content_type and content_type != "query" and not json_body:
        headers["Content-Type"] = content_type

    auth_tuple = None
    if auth:
        parts = auth.split(":", 1)
        if len(parts) == 2:
            auth_tuple = tuple(parts)

    try:
        r = req.request(method, url, data=data, json=json_body, params=params, headers=headers, auth=auth_tuple, timeout=15)
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            resp_body = r.json()
        else:
            resp_body = r.text
        return {
            "status": r.status_code,
            "headers": dict(r.headers),
            "body": resp_body,
            "error": None,
            "elapsed_ms": int(r.elapsed.total_seconds() * 1000),
            "request_headers": dict(r.request.headers),
            "request_url": r.request.url,
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
        }


def do_compare(host_a: str, host_b: str, cr: CompareRequest, global_ignore: list[str] | None) -> dict:
    ignore = DEFAULT_IGNORE.copy()
    if global_ignore:
        ignore.extend(global_ignore)
    if cr.ignore_paths:
        ignore.extend(cr.ignore_paths)

    a = hit(host_a, cr.method, cr.path, cr.body, cr.content_type or "query", cr.auth_a)
    b = hit(host_b, cr.method, cr.path, cr.body, cr.content_type or "query", cr.auth_b)

    # Compare status + body (skip headers and timing for drift purposes)
    comparable_a = {"status": a["status"], "body": a["body"]}
    comparable_b = {"status": b["status"], "body": b["body"]}

    diff = DeepDiff(comparable_a, comparable_b, ignore_order=True, exclude_paths=ignore)

    return {
        "label": cr.label,
        "method": cr.method,
        "path": cr.path,
        "group": cr.group,
        "has_drift": bool(diff),
        "diff": json.loads(diff.to_json()) if diff else {},
        "ignored_paths": ignore,
        "response_a": a,
        "response_b": b,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/api/config")
async def get_config():
    return {"host_a": HOST_A, "host_b": HOST_B, "default_ignore": DEFAULT_IGNORE}


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
