# tests/conftest.py

"""
Shared fixtures for drift-detector backend tests.

Minimal OpenAPI specs are constructed as Python dicts and serialized
to JSON/YAML strings as needed. This avoids coupling test expectations
to the large production example files in static/.
"""

import json

import pytest
import yaml


# ---------------------------------------------------------------------------
# Minimal OpenAPI 3.0 spec
# ---------------------------------------------------------------------------
@pytest.fixture
def openapi30_spec() -> dict:
    """A minimal but realistic OpenAPI 3.0.3 spec with multiple features."""
    return {
        "openapi": "3.0.3",
        "info": {"title": "Test API 3.0", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com/v1"}],
        "paths": {
            "/users": {
                "get": {
                    "operationId": "listUsers",
                    "summary": "List users",
                    "tags": ["users"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1, "maximum": 100},
                            "example": 25,
                        },
                        {
                            "name": "offset",
                            "in": "query",
                            "schema": {"type": "integer"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "User list",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/User"},
                                    }
                                }
                            },
                        }
                    },
                },
                "post": {
                    "operationId": "createUser",
                    "summary": "Create a user",
                    "tags": ["users"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateUserRequest"}
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            },
                        }
                    },
                },
            },
            "/users/{user_id}": {
                "get": {
                    "operationId": "getUser",
                    "summary": "Get a user",
                    "tags": ["users"],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "A user",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            },
                        }
                    },
                },
                "delete": {
                    "operationId": "deleteUser",
                    "summary": "Delete a user",
                    "tags": ["users"],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"204": {"description": "Deleted"}},
                },
            },
            "/health": {
                "get": {
                    "operationId": "healthCheck",
                    "summary": "Health check",
                    "tags": ["system"],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string", "const": "ok"},
                                            "uptime": {"type": "integer"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "required": ["id", "email"],
                    "properties": {
                        "id": {"type": "string", "example": "usr_123"},
                        "email": {"type": "string", "example": "alice@example.com"},
                        "name": {"type": "string"},
                        "role": {
                            "type": "string",
                            "enum": ["admin", "member", "viewer"],
                        },
                    },
                },
                "CreateUserRequest": {
                    "type": "object",
                    "required": ["email"],
                    "properties": {
                        "email": {"type": "string", "example": "new@example.com"},
                        "name": {"type": "string", "example": "Alice"},
                        "role": {
                            "type": "string",
                            "enum": ["admin", "member", "viewer"],
                            "default": "member",
                        },
                    },
                },
            }
        },
    }


# ---------------------------------------------------------------------------
# Minimal OpenAPI 3.1 spec with modern features
# ---------------------------------------------------------------------------
@pytest.fixture
def openapi31_spec() -> dict:
    """OpenAPI 3.1.0 spec using allOf, oneOf, anyOf, and nested $refs."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test API 3.1", "version": "2.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/secrets": {
                "post": {
                    "operationId": "createSecret",
                    "summary": "Create a secret",
                    "tags": ["secrets"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["secret"],
                                    "properties": {
                                        "secret": {
                                            "type": "object",
                                            "properties": {
                                                "kind": {
                                                    "type": "string",
                                                    "const": "conceal",
                                                },
                                                "value": {"type": "string"},
                                                "ttl": {
                                                    "anyOf": [
                                                        {},
                                                        {
                                                            "type": "integer",
                                                            "minimum": 0,
                                                            "maximum": 604800,
                                                        },
                                                    ]
                                                },
                                                "passphrase": {"type": "string"},
                                            },
                                        }
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Created secret",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/SecretResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/events": {
                "post": {
                    "operationId": "createEvent",
                    "summary": "Create event",
                    "tags": ["events"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EventRequest"}
                            }
                        }
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            },
        },
        "components": {
            "schemas": {
                "SecretResponse": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "ttl": {"type": "integer"},
                        "created": {"type": "string"},
                    },
                },
                "EventRequest": {
                    "allOf": [
                        {"$ref": "#/components/schemas/EventBase"},
                        {
                            "type": "object",
                            "properties": {
                                "priority": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 5,
                                }
                            },
                        },
                    ]
                },
                "EventBase": {
                    "type": "object",
                    "required": ["type", "payload"],
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["click", "view", "error"],
                        },
                        "payload": {"type": "string"},
                        "timestamp": {"type": "string"},
                    },
                },
            }
        },
    }


# ---------------------------------------------------------------------------
# Swagger 2.0 spec
# ---------------------------------------------------------------------------
@pytest.fixture
def swagger20_spec() -> dict:
    """A minimal Swagger 2.0 spec with formData, body, and query parameters."""
    return {
        "swagger": "2.0",
        "info": {"title": "Legacy API", "version": "0.9.0"},
        "basePath": "/api/v1",
        "paths": {
            "/secrets/share": {
                "post": {
                    "operationId": "shareSecret",
                    "summary": "Share a secret",
                    "tags": ["secrets"],
                    "consumes": ["application/x-www-form-urlencoded"],
                    "parameters": [
                        {
                            "name": "secret",
                            "in": "formData",
                            "type": "string",
                            "required": True,
                            "description": "The secret value",
                            "example": "shhh",
                        },
                        {
                            "name": "ttl",
                            "in": "formData",
                            "type": "integer",
                            "required": False,
                            "default": 3600,
                            "description": "Time to live in seconds",
                        },
                        {
                            "name": "passphrase",
                            "in": "formData",
                            "type": "string",
                            "required": False,
                        },
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/secrets/{key}": {
                "get": {
                    "operationId": "getSecret",
                    "summary": "Retrieve a secret",
                    "tags": ["secrets"],
                    "parameters": [
                        {
                            "name": "key",
                            "in": "path",
                            "type": "string",
                            "required": True,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/status": {
                "get": {
                    "operationId": "getStatus",
                    "summary": "API status",
                    "tags": ["system"],
                    "parameters": [
                        {
                            "name": "verbose",
                            "in": "query",
                            "type": "boolean",
                            "default": False,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    }


# ---------------------------------------------------------------------------
# Spec with nested / multi-level $refs
# ---------------------------------------------------------------------------
@pytest.fixture
def nested_ref_spec() -> dict:
    """Spec with two-hop $ref chain: A -> B -> C."""
    return {
        "openapi": "3.0.3",
        "info": {"title": "Nested Ref API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "post": {
                    "operationId": "createItem",
                    "summary": "Create item",
                    "tags": ["items"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ItemWrapper"}
                            }
                        }
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            }
        },
        "components": {
            "schemas": {
                "ItemWrapper": {
                    "type": "object",
                    "properties": {
                        "item": {"$ref": "#/components/schemas/ItemAlias"},
                    },
                },
                "ItemAlias": {"$ref": "#/components/schemas/Item"},
                "Item": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "count": {"type": "integer", "minimum": 0},
                    },
                },
            }
        },
    }


# ---------------------------------------------------------------------------
# Spec with circular $refs (should not infinite loop)
# ---------------------------------------------------------------------------
@pytest.fixture
def circular_ref_spec() -> dict:
    """Spec where TreeNode -> children -> TreeNode (circular)."""
    return {
        "openapi": "3.0.3",
        "info": {"title": "Circular Ref API", "version": "1.0.0"},
        "paths": {
            "/trees": {
                "post": {
                    "operationId": "createTree",
                    "summary": "Create tree",
                    "tags": ["trees"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/TreeNode"}
                            }
                        }
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            }
        },
        "components": {
            "schemas": {
                "TreeNode": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/TreeNode"},
                        },
                    },
                }
            }
        },
    }


# ---------------------------------------------------------------------------
# Two specs with known differences (for diff testing)
# ---------------------------------------------------------------------------
@pytest.fixture
def spec_pair_for_diff():
    """Two specs with deliberate differences: added field, removed field,
    type change, const change, and a potential rename."""
    base = {
        "openapi": "3.0.3",
        "info": {"title": "Diff Test API", "version": "1.0.0"},
        "paths": {
            "/widgets": {
                "post": {
                    "operationId": "createWidget",
                    "summary": "Create widget",
                    "tags": ["widgets"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name", "color"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "color": {"type": "string"},
                                        "weight": {"type": "number"},
                                        "version": {
                                            "type": "string",
                                            "const": "v1",
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            },
            "/widgets/{id}": {
                "get": {
                    "operationId": "getWidget",
                    "summary": "Get widget",
                    "tags": ["widgets"],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    }

    updated = {
        "openapi": "3.0.3",
        "info": {"title": "Diff Test API", "version": "2.0.0"},
        "paths": {
            "/widgets": {
                "post": {
                    "operationId": "createWidget",
                    "summary": "Create widget",
                    "tags": ["widgets"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name", "colour"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        # "color" removed, "colour" added (rename)
                                        "colour": {"type": "string"},
                                        # "weight" type changed: number -> integer
                                        "weight": {"type": "integer"},
                                        "version": {
                                            "type": "string",
                                            "const": "v2",
                                        },
                                        # "priority" added (new field)
                                        "priority": {"type": "integer", "minimum": 1},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            },
            # /widgets/{id} GET removed entirely
            # /widgets/batch POST added
            "/widgets/batch": {
                "post": {
                    "operationId": "batchCreateWidgets",
                    "summary": "Batch create",
                    "tags": ["widgets"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "widgets": {
                                            "type": "array",
                                        }
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            },
        },
    }

    return base, updated


# ---------------------------------------------------------------------------
# JSON / YAML string serializers
# ---------------------------------------------------------------------------
@pytest.fixture
def to_json():
    """Helper to serialize a dict to JSON string."""
    def _to_json(spec: dict) -> str:
        return json.dumps(spec)
    return _to_json


@pytest.fixture
def to_yaml():
    """Helper to serialize a dict to YAML string."""
    def _to_yaml(spec: dict) -> str:
        return yaml.dump(spec, default_flow_style=False)
    return _to_yaml
