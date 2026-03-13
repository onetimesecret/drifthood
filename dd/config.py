# drift-detector/dd/config.py

"""
Centralized configuration. Every env var read lives here.
Import `cfg` anywhere you need settings.
"""

import os

# ── Hosts ──
HOST_A = os.environ.get("HOST_A", "http://localhost:10235")
HOST_B = os.environ.get("HOST_B", "http://localhost:10240")

# ── Database ──
# DD_DB_DRIVER: "sqlite" (default) or "turso"
DB_DRIVER = os.environ.get("DD_DB_DRIVER", "sqlite")
# For sqlite: path to the .db file
# For turso:  libsql:// URL (e.g. libsql://your-db-turso.turso.io)
DB_PATH = os.environ.get(
    "DD_DB_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)) or ".", "drift-detector.db"
    ),
)
# Turso auth token (only used when DB_DRIVER=turso)
DB_AUTH_TOKEN = os.environ.get("DD_DB_AUTH_TOKEN", "")

# ── Server ──
HOST = os.environ.get("DD_HOST", "0.0.0.0")
PORT = int(os.environ.get("DD_PORT", "8899"))

# ── SSL ──
# Set DD_VERIFY_SSL=0 to skip certificate verification (e.g. self-signed certs behind Caddy)
VERIFY_SSL = os.environ.get("DD_VERIFY_SSL", "1") not in ("0", "false", "no")

# ── Default environments ──
DEFAULT_ENVIRONMENTS = [
    {"id": "default-a", "name": "Host A", "baseUrl": HOST_A, "auth": "", "memo": "", "metadata": {}},
    {"id": "default-b", "name": "Host B", "baseUrl": HOST_B, "auth": "", "memo": "", "metadata": {}},
]

# ── Comparison defaults ──
# Fields expected to differ between instances (add as you discover them)
DEFAULT_IGNORE = [
    "root['body']['custid']",
    "root['body']['metadata_key']",
    "root['body']['secret_key']",
    "root['body']['secret_ttl']",
    "root['body']['created']",
    "root['body']['updated']",
]
