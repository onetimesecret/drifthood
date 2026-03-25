# dd/config.py

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
        os.path.dirname(os.path.dirname(__file__)) or ".", "data", "drift-detector.db"
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

# ── CORS ──
# Comma-separated list of allowed origins, e.g. "http://localhost:5899,https://mydomain.com"
# Defaults to allowing localhost dev ports. Set DD_CORS_ORIGINS="*" to allow all (insecure).
_cors_env = os.environ.get("DD_CORS_ORIGINS", "http://localhost:5899,http://127.0.0.1:5899")
CORS_ORIGINS: list[str] = [o.strip() for o in _cors_env.split(",") if o.strip()]

# ── Default environments ──
DEFAULT_ENVIRONMENTS = [
    {"id": "default-a", "name": "Host A", "baseUrl": HOST_A, "auth": "", "memo": "", "metadata": {}},
    {"id": "default-b", "name": "Host B", "baseUrl": HOST_B, "auth": "", "memo": "", "metadata": {}},
]

# ── Payload limits ──
# Max size for state JSON in bytes (default 1MB)
MAX_STATE_SIZE = int(os.environ.get("DD_MAX_STATE_SIZE", str(1024 * 1024)))
# Max size for encrypted blob in bytes (default 2MB)
MAX_BLOB_SIZE = int(os.environ.get("DD_MAX_BLOB_SIZE", str(2 * 1024 * 1024)))

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

# Formats that signal temporal/unique values which should be ignored by default
TEMPORAL_FORMATS = {"date-time", "date", "time", "uuid", "uri"}


def derive_ignore_paths(fields: list[dict], prefix: str = "root['body']") -> list[str]:
    """Build DeepDiff exclude_paths from schema fields marked for drift-ignore."""
    paths = []
    for f in fields:
        if f.get("nested"):
            continue
        if f.get("drift_ignore"):
            parts = f["path"].split(".")
            dp = prefix
            for part in parts:
                dp += f"['{part}']"
            paths.append(dp)
    return paths
