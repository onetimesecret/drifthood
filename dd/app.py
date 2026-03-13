# drift-detector/dd/app.py

"""
Drift Detector - FastAPI app factory.
Mounts routers and serves the Vite-built frontend from dist/.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dd.auth import router as auth_router
from dd.compare import router as compare_router
from dd.documents import router as documents_router
from dd.openapi import router as openapi_router


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
    app.include_router(openapi_router)

    # ── Frontend (Vite build output) ──
    dist_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "dist"
    )

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(dist_dir, "index.html"))

    # Vite puts hashed JS/CSS in dist/assets/
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(dist_dir, "assets")),
        name="assets",
    )

    return app


app = create_app()
