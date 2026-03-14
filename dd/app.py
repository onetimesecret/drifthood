# drift-detector/dd/app.py

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
from dd.documents import router as documents_router
from dd.endpoints_api import router as endpoints_router
from dd.environments import router as environments_router
from dd.openapi import router as openapi_router
import dd.store as store

# UUIDv7 is a standard UUID format — validate with the general UUID regex
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def create_app() -> FastAPI:
    app = FastAPI(title="Drift Detector")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API routers ──
    app.include_router(auth_router)
    app.include_router(compare_router)
    app.include_router(documents_router)
    app.include_router(endpoints_router)
    app.include_router(environments_router)
    app.include_router(openapi_router)

    # ── Frontend (Vite build output) ──
    dist_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "dist"
    )

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(dist_dir, "index.html"))

    # SPA fallback — serve index.html for /s/{extid} session routes.
    # Rejects non-UUID paths and unknown session extids with 404.
    @app.get("/s/{extid:path}")
    async def session_spa_fallback(extid: str):
        if not _UUID_RE.match(extid):
            raise HTTPException(status_code=404, detail="Not found")
        session = store.get_session_by_extid(extid)
        if not session:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(os.path.join(dist_dir, "index.html"))

    # SPA fallback — serve index.html for /e/{extid} environment detail routes
    @app.get("/e/{extid:path}")
    async def environment_spa_fallback(extid: str):
        if not _UUID_RE.match(extid):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(os.path.join(dist_dir, "index.html"))

    # Vite puts hashed JS/CSS in dist/assets/
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(dist_dir, "assets")),
        name="assets",
    )

    return app


app = create_app()
