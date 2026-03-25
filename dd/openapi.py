# dd/openapi.py

"""
OpenAPI spec parsing and schema diff routes.

NOTE: This module is a bespoke OpenAPI parser that grew organically. ~90% of
the code (ref resolution, schema composition, type normalization, operation
iteration) duplicates what libraries like prance or openapi-core provide.
The drift-detection-specific logic (drift_ignore tagging, field diffing,
rename detection) is only ~50 lines. Replace the generic parsing layer with
a spec-compliant library when the opportunity arises.
"""

import json
import logging
from collections import defaultdict
from difflib import SequenceMatcher

import requests as req
import yaml
from fastapi import APIRouter, File, Form, Request, UploadFile

from dd.auth import get_session_hash
from dd.config import TEMPORAL_FORMATS

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------
def normalize_type(type_value, default: str = "string") -> str:
    """Normalize OpenAPI 3.1 type arrays to a single type string.

    In 3.1, type can be ["string", "null"] to indicate nullable.
    This picks the first non-null type from the array, or falls back to default.
    If type_value is already a string, it's returned as-is.
    """
    if isinstance(type_value, list):
        non_null = [t for t in type_value if t != "null"]
        return non_null[0] if non_null else default
    if isinstance(type_value, str):
        return type_value
    return default


import re

# Pattern to match API version prefixes like /api/v1/, /api/v2/, /v1/, /v2/, etc.
# Also handles /api/v{major}.{minor}/ patterns.
_VERSION_PREFIX_PATTERN = re.compile(
    r'^(/api)?/v\d+(\.\d+)?(/|$)',
    re.IGNORECASE
)


def normalize_path_for_diff(path: str) -> str:
    """Normalize path by stripping version prefixes for cross-version comparison.

    Converts paths like:
    - /api/v2/secret/conceal -> /secret/conceal
    - /api/v3/secret/conceal -> /secret/conceal
    - /v1/users -> /users
    - /v2.0/items -> /items

    This allows matching semantically equivalent endpoints across different
    API versions for field-level diff comparison.
    """
    # Strip version prefix, preserving the rest of the path
    normalized = _VERSION_PREFIX_PATTERN.sub('/', path)
    # Clean up any double slashes
    while '//' in normalized:
        normalized = normalized.replace('//', '/')
    return normalized


def resolve_ref(obj: dict, spec: dict, _seen: set | None = None) -> dict:
    """Resolve $ref pointers recursively with cycle detection.

    Follows ref chains (e.g. requestBody.$ref -> schema.$ref) until stable.
    Tracks visited ref paths to prevent infinite loops on recursive schemas.
    """
    if _seen is None:
        _seen = set()

    ref = obj.get("$ref")
    if not ref or not ref.startswith("#/"):
        return obj

    # Cycle detection: if we've already visited this ref, stop
    if ref in _seen:
        return obj
    _seen.add(ref)

    parts = ref.lstrip("#/").split("/")
    node = spec
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            logger.warning("$ref target not found: %s (missing segment '%s')", ref, p)
            return obj
        node = node[p]

    if not isinstance(node, dict):
        logger.warning("$ref target resolved to non-dict: %s", ref)
        return obj

    # If the resolved node itself contains a $ref, resolve it too
    if "$ref" in node:
        node = resolve_ref(node, spec, _seen)

    return node


def resolve_anyof_type(prop: dict, spec: dict) -> tuple[str, dict]:
    """Resolve anyOf to find the most specific non-null type.

    Returns (type_string, merged_prop_dict). Handles nested anyOf by
    recursing when a branch has no direct 'type' but contains inner anyOf.
    Skips 'null' type branches to find the actual content type.
    """
    if "anyOf" not in prop:
        return normalize_type(prop.get("type", "string")), prop

    for branch in prop["anyOf"]:
        branch = resolve_ref(branch, spec)
        # Skip null branches
        if branch.get("type") == "null":
            continue
        # Direct type found - use it
        if branch.get("type"):
            return normalize_type(branch["type"]), {**prop, **branch}
        # Nested anyOf - recurse into it
        if "anyOf" in branch:
            inner_type, inner_prop = resolve_anyof_type(branch, spec)
            if inner_type != "null":
                return inner_type, {**prop, **inner_prop}

    # Fallback: no non-null type found
    return "string", prop


def extract_fields(schema: dict, spec: dict, prefix: str = "", _seen: set | None = None) -> list[dict]:
    """Walk a schema and return a flat list of field descriptors.

    Each field: {name, path, type, required, example, enum, const, min, max,
                 nested, description, format, drift_ignore}
    Nested objects get flattened with dot-separated paths so the UI can render them
    as grouped inputs (secret.kind, secret.ttl, etc.).

    Array fields with object items are also recursed into, with paths like
    records[].field_name to indicate the array item structure."""
    if not schema:
        return []
    if _seen is None:
        _seen = set()
    schema = resolve_ref(schema, spec)
    # Track $ref to detect circular references
    schema_ref = id(schema)
    if schema_ref in _seen:
        return []
    _seen = _seen | {schema_ref}  # Copy to allow sibling branches

    # allOf: merge all sub-schemas' properties and required arrays, then
    # overlay any top-level properties (valid extension pattern in OpenAPI).
    if "allOf" in schema:
        merged_props = {}
        merged_required = list(schema.get("required", []))
        for sub in schema["allOf"]:
            sub = resolve_ref(sub, spec)
            merged_props.update(sub.get("properties", {}))
            merged_required.extend(sub.get("required", []))
        # Top-level properties take precedence over allOf contributions
        merged_props.update(schema.get("properties", {}))
        schema = {**schema, "properties": merged_props, "required": merged_required}

    # oneOf: pick the first branch that has properties
    if "oneOf" in schema and not schema.get("properties"):
        for branch in schema["oneOf"]:
            branch = resolve_ref(branch, spec)
            if branch.get("properties"):
                schema = {**schema, "properties": branch["properties"],
                          "required": list(schema.get("required", [])) + list(branch.get("required", []))}
                break

    props = schema.get("properties", {})
    additional_props = schema.get("additionalProperties")

    # If no properties and no additionalProperties, nothing to extract
    if not props and not additional_props:
        return []

    required_set = set(schema.get("required", []))
    fields = []
    for name, prop in props.items():
        prop = resolve_ref(prop, spec)
        path = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"
        ftype = normalize_type(prop.get("type", "string"))
        # anyOf: pick the most specific non-null type (handles nested anyOf)
        if "anyOf" in prop:
            ftype, prop = resolve_anyof_type(prop, spec)
        fmt = prop.get("format", "")
        # Detect fields that should be auto-ignored in drift comparison
        drift_ignore = bool(
            prop.get("x-drift-ignore")
            or fmt in TEMPORAL_FORMATS
        )
        field = {
            "name": name,
            "path": path,
            "type": ftype,
            "required": name in required_set,
            "example": prop.get("example", prop.get("default")),
            "enum": prop.get("enum"),
            "const": prop.get("const"),
            "description": prop.get("description", ""),
            "format": fmt,
            "drift_ignore": drift_ignore,
            "deprecated": prop.get("deprecated", False),
        }
        if ftype in ("integer", "number"):
            if "minimum" in prop:
                field["min"] = prop["minimum"]
            if "maximum" in prop:
                field["max"] = prop["maximum"]
        # Recurse into nested objects (with properties or additionalProperties)
        if ftype == "object" and (prop.get("properties") or prop.get("additionalProperties")):
            field["nested"] = True
            fields.append(field)
            fields.extend(extract_fields(prop, spec, path, _seen))
        # Recurse into array items that are objects
        elif ftype == "array" and prop.get("items"):
            items_schema = resolve_ref(prop.get("items", {}), spec)
            if items_schema.get("type") == "object" and items_schema.get("properties"):
                field["nested"] = True
                fields.append(field)
                # Use [] suffix to indicate array item fields
                array_path = f"{path}[]"
                fields.extend(extract_fields(items_schema, spec, array_path, _seen))
            else:
                field["nested"] = False
                fields.append(field)
        else:
            field["nested"] = False
            fields.append(field)

    # Handle additionalProperties: create a synthetic field to indicate dynamic keys
    if additional_props and additional_props is not True:
        # additionalProperties can be True (any type) or a schema (typed)
        additional_props = resolve_ref(additional_props, spec)
        add_type = normalize_type(additional_props.get("type", "any"))
        # Handle anyOf in additionalProperties
        if "anyOf" in additional_props:
            add_type, additional_props = resolve_anyof_type(additional_props, spec)
        add_path = f"{prefix}[*]" if not prefix else f"{prefix}.[*]"
        fields.append({
            "name": "[*]",
            "path": add_path,
            "type": add_type,
            "required": False,
            "example": additional_props.get("example"),
            "enum": additional_props.get("enum"),
            "const": None,
            "description": "Dynamic additional properties",
            "format": additional_props.get("format", ""),
            "drift_ignore": False,
            "deprecated": False,
            "nested": False,
            "additional_properties": True,
        })
    elif additional_props is True:
        # additionalProperties: true means any type allowed
        add_path = f"{prefix}[*]" if not prefix else f"{prefix}.[*]"
        fields.append({
            "name": "[*]",
            "path": add_path,
            "type": "any",
            "required": False,
            "example": None,
            "enum": None,
            "const": None,
            "description": "Dynamic additional properties (any type)",
            "format": "",
            "drift_ignore": False,
            "deprecated": False,
            "nested": False,
            "additional_properties": True,
        })

    return fields


def extract_example_body(schema: dict, spec: dict, *, for_json: bool = False) -> str | None:
    """Best-effort: pull example values from a request body schema.

    Args:
        schema: The schema dict to extract examples from.
        spec: The full OpenAPI spec (for resolving $refs).
        for_json: If True, return JSON string. If False, return form-encoded string.

    Returns:
        A body hint string (JSON or form-encoded), or None if no examples found.
    """
    if not schema:
        return None

    schema = resolve_ref(schema, spec)

    if "example" in schema:
        ex = schema["example"]
        if for_json:
            # Return as JSON string, preserving nested structure
            return json.dumps(ex)
        # Legacy form-encoded format
        if isinstance(ex, dict):
            return "&".join(f"{k}={v}" for k, v in ex.items())
        return str(ex)

    props = schema.get("properties", {})
    if not props:
        return None

    if for_json:
        # Build a dict with proper types for JSON
        obj = {}
        for name, prop in props.items():
            prop = resolve_ref(prop, spec)
            if "example" in prop:
                obj[name] = prop["example"]
            elif "default" in prop:
                obj[name] = prop["default"]
            else:
                ptype = normalize_type(prop.get("type"))
                if ptype == "string":
                    obj[name] = "test"
                elif ptype == "integer":
                    obj[name] = 0
                elif ptype == "number":
                    obj[name] = 0.0
                elif ptype == "boolean":
                    obj[name] = True
                elif ptype == "array":
                    obj[name] = []
                elif ptype == "object":
                    # Recursively extract nested object
                    nested = extract_example_body(prop, spec, for_json=True)
                    obj[name] = json.loads(nested) if nested else {}
                else:
                    obj[name] = None
        return json.dumps(obj) if obj else None

    # Legacy form-encoded format
    parts = []
    for name, prop in props.items():
        prop = resolve_ref(prop, spec)
        if "example" in prop:
            parts.append(f"{name}={prop['example']}")
        elif "default" in prop:
            parts.append(f"{name}={prop['default']}")
        elif normalize_type(prop.get("type")) == "string":
            parts.append(f"{name}=test")
        elif normalize_type(prop.get("type")) == "integer":
            parts.append(f"{name}=0")
        elif normalize_type(prop.get("type")) == "boolean":
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

    if not isinstance(spec, dict):
        # Detect HTML responses (e.g. Vite SPA fallback, error pages)
        content_hint = "HTML" if raw.lstrip()[:1] == "<" else "plain text"
        raise ValueError(
            f"URL did not return a valid OpenAPI specification "
            f"(expected JSON or YAML, got {content_hint})"
        )

    if not spec.get("paths") and not spec.get("openapi") and not spec.get("swagger"):
        raise ValueError(
            "Content parsed as JSON/YAML but does not appear to be an OpenAPI spec "
            "(missing 'paths', 'openapi', or 'swagger' keys)"
        )

    # Explicit version detection
    spec_version = spec.get("openapi", spec.get("swagger", "unknown"))
    is_openapi3 = spec_version.startswith("3.")
    is_openapi32_plus = False
    if is_openapi3:
        try:
            minor = int(spec_version.split(".")[1])
            is_openapi32_plus = minor >= 2
        except (IndexError, ValueError):
            pass

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
        http_methods = [
            "get",
            "post",
            "put",
            "delete",
            "patch",
            "head",
            "options",
        ]
        # OpenAPI 3.2+ adds the QUERY method
        if is_openapi32_plus:
            http_methods.append("query")
        for method in http_methods:
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
                    body_hint = extract_example_body(schema, spec, for_json=True)
                    content_type = "application/json"
                    fields = extract_fields(schema, spec)
                elif "application/x-www-form-urlencoded" in content:
                    schema = content["application/x-www-form-urlencoded"].get(
                        "schema", {}
                    )
                    body_hint = extract_example_body(schema, spec, for_json=False)
                    content_type = "application/x-www-form-urlencoded"
                    fields = extract_fields(schema, spec)
                elif "multipart/form-data" in content:
                    schema = content["multipart/form-data"].get("schema", {})
                    body_hint = extract_example_body(schema, spec, for_json=False)
                    content_type = "multipart/form-data"
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
                            "type": normalize_type(param.get("type", "string")),
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
                    body_hint = extract_example_body(schema, spec, for_json=True)
                    content_type = "application/json"
                    if not fields:
                        fields = extract_fields(schema, spec)
            if form_parts and not body_hint:
                body_hint = "&".join(form_parts)

            # Response schemas: extract fields from responses section
            response_fields = {}
            responses = op.get("responses", {})
            for status_code, resp_obj in responses.items():
                if not isinstance(resp_obj, dict):
                    continue
                resp_obj = resolve_ref(resp_obj, spec)
                # OpenAPI 3.x: content.<media-type>.schema
                resp_content = resp_obj.get("content", {})
                if "application/json" in resp_content:
                    resp_schema = resp_content["application/json"].get(
                        "schema", {}
                    )
                    rf = extract_fields(resp_schema, spec)
                    if rf:
                        response_fields[str(status_code)] = rf
                # Swagger 2.0: schema directly on the response object
                elif "schema" in resp_obj and not resp_content:
                    resp_schema = resp_obj.get("schema", {})
                    rf = extract_fields(resp_schema, spec)
                    if rf:
                        response_fields[str(status_code)] = rf

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
                            "type": normalize_type(param.get(
                                "type",
                                param.get("schema", {}).get("type", "string"),
                            )),
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
                            "type": normalize_type(param.get(
                                "type",
                                param.get("schema", {}).get("type", "string"),
                            )),
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

            # Resolve security schemes for this operation
            security_schemes = []
            op_security = op.get("security", spec.get("security", []))
            components_security = spec.get("components", {}).get(
                "securitySchemes", {}
            )
            # Swagger 2.0 uses top-level securityDefinitions
            if not components_security:
                components_security = spec.get("securityDefinitions", {})
            for sec_req in op_security:
                if isinstance(sec_req, dict):
                    for scheme_name in sec_req:
                        scheme_def = components_security.get(scheme_name, {})
                        scheme_def = resolve_ref(scheme_def, spec)
                        security_schemes.append(
                            {
                                "name": scheme_name,
                                "type": scheme_def.get("type", "unknown"),
                                "scheme": scheme_def.get("scheme", ""),
                                "in": scheme_def.get("in", ""),
                                "scopes": sec_req[scheme_name],
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
                    "response_fields": response_fields,
                    "security": security_schemes,
                }
            )

    groups = group_operations(operations, base_path)

    return {
        "title": info.get("title", "Unknown API"),
        "version": info.get("version", ""),
        "spec_version": spec_version,
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

    # Best-match rename detection: for each removed field, find the single
    # best-matching added field (by name similarity).  Each added field can
    # only be claimed once, avoiding the cartesian-product false positives
    # that the old approach produced (e.g. first_name matching given_name
    # AND family_name).
    possible_renames = []
    candidates: list[tuple[dict, dict, float]] = []
    for r in removed:
        for a in added:
            if r["type"] == a["type"] and r["name"] != a["name"]:
                similarity = SequenceMatcher(
                    None, r["name"].lower(), a["name"].lower()
                ).ratio()
                if similarity >= 0.5:
                    candidates.append((r, a, similarity))
    # Sort by similarity descending so the strongest matches are claimed first
    candidates.sort(key=lambda x: x[2], reverse=True)
    claimed_removed: set[str] = set()
    claimed_added: set[str] = set()
    for r, a, similarity in candidates:
        if r["path"] in claimed_removed or a["path"] in claimed_added:
            continue
        claimed_removed.add(r["path"])
        claimed_added.add(a["path"])
        possible_renames.append(
            {
                "old_path": r["path"],
                "new_path": a["path"],
                "old_name": r["name"],
                "new_name": a["name"],
                "type": r["type"],
                "similarity": round(similarity, 2),
            }
        )

    return {
        "added": added,
        "removed": removed,
        "type_changed": type_changed,
        "const_changed": const_changed,
        "possible_renames": possible_renames,
    }


def diff_response_fields(
    resp_a: dict[str, list[dict]], resp_b: dict[str, list[dict]]
) -> dict:
    """Diff response schemas between two specs, keyed by status code.

    Returns per-status-code diffs plus overall has_changes flag."""
    codes_a = set(resp_a.keys())
    codes_b = set(resp_b.keys())

    per_code = {}
    has_changes = False

    # Status codes added/removed
    for code in sorted(codes_b - codes_a):
        per_code[code] = {"status": "added_in_b", "fields": resp_b[code], "diff": {}}
        has_changes = True
    for code in sorted(codes_a - codes_b):
        per_code[code] = {"status": "removed_from_b", "fields": resp_a[code], "diff": {}}
        has_changes = True

    # Shared status codes: diff the field lists
    for code in sorted(codes_a & codes_b):
        d = diff_operation_fields(resp_a[code], resp_b[code])
        code_has_changes = any(d[k] for k in d)
        if code_has_changes:
            has_changes = True
        per_code[code] = {
            "status": "changed" if code_has_changes else "identical",
            "fields_a": resp_a[code],
            "fields_b": resp_b[code],
            "diff": d,
        }

    return {"per_code": per_code, "has_changes": has_changes}


def detect_endpoint_renames(
    removed: list[dict], added: list[dict]
) -> list[dict]:
    """Detect possible endpoint renames using path similarity.

    Uses the same best-match algorithm as field rename detection:
    each removed endpoint can only match one added endpoint, and
    vice versa, to avoid false positives.

    Args:
        removed: List of endpoints removed from spec B (have method and path)
        added: List of endpoints added in spec B (have method and path)

    Returns:
        List of possible renames with similarity scores.
    """
    # Only consider same-method pairs as potential renames
    candidates: list[tuple[dict, dict, float]] = []

    for r in removed:
        for a in added:
            # Must be same HTTP method
            if r["method"] != a["method"]:
                continue

            # Compare path segments for similarity
            r_path = r["path"].lstrip("/")
            a_path = a["path"].lstrip("/")

            # Path similarity using SequenceMatcher
            similarity = SequenceMatcher(None, r_path.lower(), a_path.lower()).ratio()

            # Also consider segment-based matching (private/recent -> receipt/recent)
            r_segments = r_path.split("/")
            a_segments = a_path.split("/")

            # Boost similarity if last segment matches (likely same resource action)
            if r_segments and a_segments and r_segments[-1] == a_segments[-1]:
                similarity = min(1.0, similarity + 0.2)

            # Require minimum similarity threshold
            if similarity >= 0.4:
                candidates.append((r, a, similarity))

    # Sort by similarity descending, claim strongest matches first
    candidates.sort(key=lambda x: x[2], reverse=True)

    claimed_removed: set[tuple] = set()
    claimed_added: set[tuple] = set()
    possible_renames = []

    for r, a, similarity in candidates:
        r_key = (r["method"], r["path"])
        a_key = (a["method"], a["path"])

        if r_key in claimed_removed or a_key in claimed_added:
            continue

        claimed_removed.add(r_key)
        claimed_added.add(a_key)

        possible_renames.append({
            "old_method": r["method"],
            "old_path": r["path"],
            "new_method": a["method"],
            "new_path": a["path"],
            "similarity": round(similarity, 2),
        })

    return possible_renames


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/api/parse-openapi")
async def parse_openapi_upload(
    request: Request,
    file: UploadFile = File(None),
    url: str = Form(None),
):
    """Parse an OpenAPI spec from file upload or URL.

    Requires authentication to prevent SSRF attacks where unauthenticated
    callers could use the server to fetch arbitrary URLs.
    """
    get_session_hash(request)  # Require valid session token; raises 401 if missing
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
    request: Request,
    file_a: UploadFile = File(None),
    file_b: UploadFile = File(None),
    url_a: str = Form(None),
    url_b: str = Form(None),
):
    """Diff request schemas between two OpenAPI specs.

    Requires authentication to prevent SSRF attacks where unauthenticated
    callers could use the server to fetch arbitrary URLs.
    """
    get_session_hash(request)  # Require valid session token; raises 401 if missing
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
        """Build lookup from normalized (method, path) to operation.

        Uses normalize_path_for_diff to strip version prefixes, allowing
        cross-version endpoint matching (e.g., /api/v2/x matches /api/v3/x).
        """
        lookup = {}
        for op in spec["operations"]:
            path_clean = op["path"].split("?")[0]
            # Normalize path for cross-version matching
            path_normalized = normalize_path_for_diff(path_clean)
            key = (op["method"], path_normalized)
            # Store original path for display purposes
            lookup[key] = {**op, "_original_path": path_clean}
        return lookup

    lookup_a = ops_by_key(spec_a)
    lookup_b = ops_by_key(spec_b)
    all_keys = sorted(set(lookup_a.keys()) | set(lookup_b.keys()))

    results = []
    for key in all_keys:
        method, path_normalized = key
        op_a = lookup_a.get(key)
        op_b = lookup_b.get(key)

        # Use original path from ops (prefer A's path, fall back to B's)
        display_path_a = op_a["_original_path"] if op_a else None
        display_path_b = op_b["_original_path"] if op_b else None

        if op_a and not op_b:
            results.append(
                {
                    "method": method,
                    "path": display_path_a,
                    "path_normalized": path_normalized,
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
                    "path": display_path_b,
                    "path_normalized": path_normalized,
                    "status": "added_in_b",
                    "fields_a": [],
                    "fields_b": op_b.get("fields", []),
                    "diff": {},
                }
            )
        else:
            assert op_a is not None and op_b is not None
            fields_a = op_a.get("fields", [])
            fields_b = op_b.get("fields", [])
            diff = diff_operation_fields(fields_a, fields_b)

            # Diff response schemas across all status codes
            resp_a = op_a.get("response_fields", {})
            resp_b = op_b.get("response_fields", {})
            resp_diff = diff_response_fields(resp_a, resp_b)

            has_changes = any(diff[k] for k in diff) or resp_diff.get(
                "has_changes", False
            )
            results.append(
                {
                    "method": method,
                    # Show both original paths when they differ (cross-version match)
                    "path": display_path_a,
                    "path_b": display_path_b if display_path_b != display_path_a else None,
                    "path_normalized": path_normalized,
                    "status": "changed" if has_changes else "identical",
                    "fields_a": fields_a,
                    "fields_b": fields_b,
                    "diff": diff,
                    "response_fields_a": resp_a,
                    "response_fields_b": resp_b,
                    "response_diff": resp_diff,
                }
            )

    # Detect possible endpoint renames
    removed_endpoints = [r for r in results if r["status"] == "removed_from_b"]
    added_endpoints = [r for r in results if r["status"] == "added_in_b"]
    possible_endpoint_renames = detect_endpoint_renames(removed_endpoints, added_endpoints)

    summary = {
        "spec_a": f"{spec_a['title']} {spec_a['version']}",
        "spec_b": f"{spec_b['title']} {spec_b['version']}",
        "total_endpoints": len(all_keys),
        "changed": sum(1 for r in results if r["status"] == "changed"),
        "added": sum(1 for r in results if r["status"] == "added_in_b"),
        "removed": sum(1 for r in results if r["status"] == "removed_from_b"),
        "identical": sum(1 for r in results if r["status"] == "identical"),
        "possible_renames": len(possible_endpoint_renames),
    }
    return {
        "summary": summary,
        "results": results,
        "possible_endpoint_renames": possible_endpoint_renames,
    }
