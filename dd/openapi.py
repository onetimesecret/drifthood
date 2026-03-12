# drift-detector/dd/openapi.py

"""
OpenAPI spec parsing and schema diff routes.
"""

import json
from collections import defaultdict

import requests as req
import yaml
from fastapi import APIRouter, File, Form, UploadFile

router = APIRouter()


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------
def resolve_ref(obj: dict, spec: dict) -> dict:
    """Resolve a single $ref pointer."""
    ref = obj.get("$ref")
    if not ref or not ref.startswith("#/"):
        return obj
    parts = ref.lstrip("#/").split("/")
    node = spec
    for p in parts:
        node = node.get(p, {})
    return node if isinstance(node, dict) else obj


def extract_fields(schema: dict, spec: dict, prefix: str = "") -> list[dict]:
    """Walk a schema and return a flat list of field descriptors.

    Each field: {name, path, type, required, example, enum, const, min, max, nested, description}
    Nested objects get flattened with dot-separated paths so the UI can render them
    as grouped inputs (secret.kind, secret.ttl, etc.)."""
    if not schema:
        return []
    schema = resolve_ref(schema, spec)
    props = schema.get("properties", {})
    if not props:
        return []
    required_set = set(schema.get("required", []))
    fields = []
    for name, prop in props.items():
        prop = resolve_ref(prop, spec)
        path = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"
        ftype = prop.get("type", "string")
        # anyOf: pick the most specific branch
        if "anyOf" in prop:
            for branch in prop["anyOf"]:
                if branch.get("type"):
                    ftype = branch["type"]
                    prop = {**prop, **branch}
                    break
        field = {
            "name": name,
            "path": path,
            "type": ftype,
            "required": name in required_set,
            "example": prop.get("example", prop.get("default")),
            "enum": prop.get("enum"),
            "const": prop.get("const"),
            "description": prop.get("description", ""),
        }
        if ftype in ("integer", "number"):
            if "minimum" in prop:
                field["min"] = prop["minimum"]
            if "maximum" in prop:
                field["max"] = prop["maximum"]
        # Recurse into nested objects
        if ftype == "object" and prop.get("properties"):
            field["nested"] = True
            fields.append(field)
            fields.extend(extract_fields(prop, spec, path))
        else:
            field["nested"] = False
            fields.append(field)
    return fields


def extract_example_body(schema: dict, spec: dict) -> str | None:
    """Best-effort: pull example values from a request body schema into a form string or JSON."""
    if not schema:
        return None

    schema = resolve_ref(schema, spec)

    if "example" in schema:
        ex = schema["example"]
        if isinstance(ex, dict):
            return "&".join(f"{k}={v}" for k, v in ex.items())
        return str(ex)

    props = schema.get("properties", {})
    if not props:
        return None

    parts = []
    for name, prop in props.items():
        prop = resolve_ref(prop, spec)
        if "example" in prop:
            parts.append(f"{name}={prop['example']}")
        elif "default" in prop:
            parts.append(f"{name}={prop['default']}")
        elif prop.get("type") == "string":
            parts.append(f"{name}=test")
        elif prop.get("type") == "integer":
            parts.append(f"{name}=0")
        elif prop.get("type") == "boolean":
            parts.append(f"{name}=true")
    return "&".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def parse_openapi(raw: str) -> dict:
    """Parse an OpenAPI spec (JSON or YAML) into grouped operations."""
    try:
        spec = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        spec = yaml.safe_load(raw)

    info = spec.get("info", {})
    base_path = ""

    # OpenAPI 3.x: servers[0].url may have a path component
    servers = spec.get("servers", [])
    if servers:
        from urllib.parse import urlparse

        parsed = urlparse(servers[0].get("url", ""))
        if parsed.path and parsed.path != "/":
            base_path = parsed.path.rstrip("/")

    # Swagger 2.0: basePath field
    if not base_path:
        base_path = spec.get("basePath", "").rstrip("/")

    paths = spec.get("paths", {})
    operations = []

    for path_template, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in [
            "get",
            "post",
            "put",
            "delete",
            "patch",
            "head",
            "options",
        ]:
            op = path_item.get(method)
            if not op:
                continue

            full_path = base_path + path_template
            op_id = op.get("operationId", "")
            summary = op.get("summary", "")
            tags = op.get("tags", [])

            body_hint = None
            content_type = "query"
            fields = []

            # OpenAPI 3.x requestBody
            req_body = op.get("requestBody", {})
            if req_body:
                req_body = resolve_ref(req_body, spec)
                content = req_body.get("content", {})
                if "application/json" in content:
                    schema = content["application/json"].get("schema", {})
                    body_hint = extract_example_body(schema, spec)
                    content_type = "application/json"
                    fields = extract_fields(schema, spec)
                elif "application/x-www-form-urlencoded" in content:
                    schema = content["application/x-www-form-urlencoded"].get(
                        "schema", {}
                    )
                    body_hint = extract_example_body(schema, spec)
                    content_type = "application/x-www-form-urlencoded"
                    fields = extract_fields(schema, spec)

            # Swagger 2.0: body/formData parameters
            params = op.get("parameters", []) + path_item.get("parameters", [])
            form_parts = []
            for param in params:
                param = resolve_ref(param, spec)
                if param.get("in") == "formData":
                    name = param.get("name", "")
                    ex = param.get("example", param.get("default", ""))
                    form_parts.append(f"{name}={ex}")
                    content_type = "application/x-www-form-urlencoded"
                    fields.append(
                        {
                            "name": name,
                            "path": name,
                            "type": param.get("type", "string"),
                            "required": param.get("required", False),
                            "example": param.get(
                                "example", param.get("default")
                            ),
                            "enum": param.get("enum"),
                            "const": None,
                            "description": param.get("description", ""),
                            "nested": False,
                        }
                    )
                elif param.get("in") == "body":
                    schema = param.get("schema", {})
                    body_hint = extract_example_body(schema, spec)
                    content_type = "application/json"
                    if not fields:
                        fields = extract_fields(schema, spec)
            if form_parts and not body_hint:
                body_hint = "&".join(form_parts)

            # Query params
            query_parts = []
            query_fields = []
            for param in params:
                param = resolve_ref(param, spec)
                if param.get("in") == "query":
                    name = param.get("name", "")
                    ex = param.get("example", param.get("default", ""))
                    if ex:
                        query_parts.append(f"{name}={ex}")
                    query_fields.append(
                        {
                            "name": name,
                            "path": name,
                            "type": param.get("type", "string"),
                            "required": param.get("required", False),
                            "example": param.get(
                                "example", param.get("default")
                            ),
                            "enum": param.get("enum"),
                            "const": None,
                            "description": param.get("description", ""),
                            "nested": False,
                        }
                    )

            display_path = full_path
            if query_parts and method.upper() == "GET":
                display_path += "?" + "&".join(query_parts)

            # Path parameters
            path_fields = []
            for param in params:
                param = resolve_ref(param, spec)
                if param.get("in") == "path":
                    path_fields.append(
                        {
                            "name": param.get("name", ""),
                            "path": param.get("name", ""),
                            "type": param.get(
                                "type",
                                param.get("schema", {}).get("type", "string"),
                            ),
                            "required": True,
                            "example": param.get(
                                "example", param.get("default")
                            ),
                            "enum": param.get("enum"),
                            "const": None,
                            "description": param.get("description", ""),
                            "nested": False,
                        }
                    )

            operations.append(
                {
                    "method": method.upper(),
                    "path": display_path,
                    "label": op_id
                    or summary
                    or f"{method.upper()} {path_template}",
                    "summary": summary,
                    "tags": tags,
                    "body": body_hint,
                    "content_type": content_type,
                    "fields": fields,
                    "query_fields": query_fields,
                    "path_fields": path_fields,
                }
            )

    groups = group_operations(operations, base_path)

    return {
        "title": info.get("title", "Unknown API"),
        "version": info.get("version", ""),
        "base_path": base_path,
        "total_operations": len(operations),
        "groups": groups,
        "operations": operations,
    }


def group_operations(operations: list[dict], base_path: str) -> list[dict]:
    """Group operations by stripping common prefix, then grouping by first remaining segment."""
    clean_paths = []
    for op in operations:
        path = op["path"].split("?")[0]
        clean_paths.append(path)

    if clean_paths:
        split_paths = [p.strip("/").split("/") for p in clean_paths]
        common_segments = []
        for parts in zip(*split_paths):
            if len(set(parts)) == 1:
                common_segments.append(parts[0])
            else:
                break
        auto_prefix = "/" + "/".join(common_segments) if common_segments else ""
    else:
        auto_prefix = ""

    effective_prefix = (
        auto_prefix if len(auto_prefix) > len(base_path) else base_path
    )
    prefix = effective_prefix.rstrip("/") + "/" if effective_prefix else "/"

    buckets = defaultdict(list)
    for op in operations:
        path = op["path"].split("?")[0]
        relative = (
            path[len(prefix) :] if path.startswith(prefix) else path.lstrip("/")
        )
        segments = relative.split("/")
        group_key = segments[0] if segments else "(root)"
        buckets[group_key].append(op)

    # If we still end up with just 1 group, try one level deeper
    if len(buckets) == 1:
        single_key = list(buckets.keys())[0]
        deeper_prefix = prefix + single_key + "/"
        buckets = defaultdict(list)
        for op in operations:
            path = op["path"].split("?")[0]
            relative = (
                path[len(deeper_prefix) :]
                if path.startswith(deeper_prefix)
                else path.lstrip("/")
            )
            segments = relative.split("/")
            group_key = segments[0] if segments else "(root)"
            buckets[group_key].append(op)

    return [
        {"name": k, "count": len(v), "operations": v}
        for k, v in buckets.items()
    ]


# ---------------------------------------------------------------------------
# Schema Diff helpers
# ---------------------------------------------------------------------------
def fields_fingerprint(fields: list[dict]) -> dict:
    return {f["path"]: f for f in fields if not f.get("nested")}


def diff_operation_fields(fields_a: list[dict], fields_b: list[dict]) -> dict:
    fp_a = fields_fingerprint(fields_a)
    fp_b = fields_fingerprint(fields_b)
    keys_a = set(fp_a.keys())
    keys_b = set(fp_b.keys())

    added = [fp_b[k] for k in sorted(keys_b - keys_a)]
    removed = [fp_a[k] for k in sorted(keys_a - keys_b)]

    type_changed = []
    const_changed = []
    for k in sorted(keys_a & keys_b):
        a, b = fp_a[k], fp_b[k]
        if a["type"] != b["type"]:
            type_changed.append(
                {"path": k, "type_a": a["type"], "type_b": b["type"]}
            )
        if a.get("const") != b.get("const"):
            const_changed.append(
                {
                    "path": k,
                    "const_a": a.get("const"),
                    "const_b": b.get("const"),
                }
            )

    possible_renames = []
    for r in removed:
        for a in added:
            if r["type"] == a["type"] and r["name"] != a["name"]:
                possible_renames.append(
                    {
                        "old_path": r["path"],
                        "new_path": a["path"],
                        "old_name": r["name"],
                        "new_name": a["name"],
                        "type": r["type"],
                    }
                )

    return {
        "added": added,
        "removed": removed,
        "type_changed": type_changed,
        "const_changed": const_changed,
        "possible_renames": possible_renames,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/api/parse-openapi")
async def parse_openapi_upload(
    file: UploadFile = File(None), url: str = Form(None)
):
    """Parse an OpenAPI spec from file upload or URL."""
    raw = None
    if file:
        raw = (await file.read()).decode("utf-8")
    elif url:
        try:
            r = req.get(url, timeout=15)
            r.raise_for_status()
            raw = r.text
        except Exception as e:
            return {"error": f"Failed to fetch spec from URL: {e}"}
    else:
        return {"error": "Provide either a file upload or a URL."}

    try:
        result = parse_openapi(raw)
        return result
    except Exception as e:
        return {"error": f"Failed to parse spec: {e}"}


@router.post("/api/diff-schemas")
async def diff_schemas(
    file_a: UploadFile = File(None),
    file_b: UploadFile = File(None),
    url_a: str = Form(None),
    url_b: str = Form(None),
):
    """Diff request schemas between two OpenAPI specs."""
    specs = {}
    for label, f, u in [("a", file_a, url_a), ("b", file_b, url_b)]:
        raw = None
        if f:
            raw = (await f.read()).decode("utf-8")
        elif u:
            try:
                r = req.get(u, timeout=15)
                r.raise_for_status()
                raw = r.text
            except Exception as e:
                return {"error": f"Failed to fetch spec {label.upper()}: {e}"}
        else:
            return {"error": f"Provide file or URL for spec {label.upper()}."}
        try:
            specs[label] = parse_openapi(raw)
        except Exception as e:
            return {"error": f"Failed to parse spec {label.upper()}: {e}"}

    spec_a, spec_b = specs["a"], specs["b"]

    def ops_by_key(spec):
        lookup = {}
        for op in spec["operations"]:
            path_clean = op["path"].split("?")[0]
            key = (op["method"], path_clean)
            lookup[key] = op
        return lookup

    lookup_a = ops_by_key(spec_a)
    lookup_b = ops_by_key(spec_b)
    all_keys = sorted(set(lookup_a.keys()) | set(lookup_b.keys()))

    results = []
    for key in all_keys:
        method, path = key
        op_a = lookup_a.get(key)
        op_b = lookup_b.get(key)

        if op_a and not op_b:
            results.append(
                {
                    "method": method,
                    "path": path,
                    "status": "removed_from_b",
                    "fields_a": op_a.get("fields", []),
                    "fields_b": [],
                    "diff": {},
                }
            )
        elif op_b and not op_a:
            results.append(
                {
                    "method": method,
                    "path": path,
                    "status": "added_in_b",
                    "fields_a": [],
                    "fields_b": op_b.get("fields", []),
                    "diff": {},
                }
            )
        else:
            fields_a = op_a.get("fields", [])
            fields_b = op_b.get("fields", [])
            diff = diff_operation_fields(fields_a, fields_b)
            has_changes = any(diff[k] for k in diff)
            results.append(
                {
                    "method": method,
                    "path": path,
                    "status": "changed" if has_changes else "identical",
                    "fields_a": fields_a,
                    "fields_b": fields_b,
                    "diff": diff,
                }
            )

    summary = {
        "spec_a": f"{spec_a['title']} {spec_a['version']}",
        "spec_b": f"{spec_b['title']} {spec_b['version']}",
        "total_endpoints": len(all_keys),
        "changed": sum(1 for r in results if r["status"] == "changed"),
        "added": sum(1 for r in results if r["status"] == "added_in_b"),
        "removed": sum(1 for r in results if r["status"] == "removed_from_b"),
        "identical": sum(1 for r in results if r["status"] == "identical"),
    }
    return {"summary": summary, "results": results}
