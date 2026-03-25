# dd/app.py

"""
Drift Detector - FastAPI app factory.
Mounts routers and serves the Vite-built frontend from dist/.
"""

import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dd.auth import router as auth_router
from dd.compare import router as compare_router
from dd.config import CORS_ORIGINS
from dd.documents import router as documents_router
from dd.endpoints_api import router as endpoints_router
from dd.environments import router as environments_router
from dd.openapi import router as openapi_router
import dd.store as store

# UUIDv7 is a standard UUID format — validate with the general UUID regex
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def create_app(dist_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Drift Detector")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ── API routers ──
    app.include_router(auth_router)
    app.include_router(compare_router)
    app.include_router(documents_router)
    app.include_router(endpoints_router)
    app.include_router(environments_router)
    app.include_router(openapi_router)

    # ── Frontend (Vite build output) ──
    # Routes are always registered. In dev/test without a build, they
    # return 503 instead of silently missing from the router.
    if dist_dir is None:
        dist_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "dist"
        )
    index_html = os.path.join(dist_dir, "index.html")

    def _serve_index():
        """Return index.html or raise 503 if frontend is not built."""
        if not os.path.isfile(index_html):
            raise HTTPException(
                status_code=503,
                detail="Frontend not built — run npm run build",
            )
        return FileResponse(index_html)

    @app.get("/")
    async def index():
        return _serve_index()

    # SPA fallback — serve index.html for /s/{extid} session routes.
    # Rejects non-UUID paths and unknown session extids with 404.
    @app.get("/s/{extid:path}")
    async def session_spa_fallback(extid: str):
        if not _UUID_RE.match(extid):
            raise HTTPException(status_code=404, detail="Not found")
        session = store.get_session_by_extid(extid)
        if not session:
            raise HTTPException(status_code=404, detail="Not found")
        return _serve_index()

    # SPA fallback — serve index.html for /e/{extid} environment detail routes
    @app.get("/e/{extid:path}")
    async def environment_spa_fallback(extid: str):
        if not _UUID_RE.match(extid):
            raise HTTPException(status_code=404, detail="Not found")
        return _serve_index()

    # SPA fallback — serve index.html for /t/{extid} shared testrun routes.
    # Only validates UUID format; DB validation happens in /api/share/{extid}.
    @app.get("/t/{extid:path}")
    async def testrun_spa_fallback(extid: str):
        if not _UUID_RE.match(extid):
            raise HTTPException(status_code=404, detail="Not found")
        return _serve_index()

    # Vite puts hashed JS/CSS in dist/assets/
    assets_dir = os.path.join(dist_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="assets",
        )

    return app


app = create_app()
