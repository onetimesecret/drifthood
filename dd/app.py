# drift-detector/dd/app.py

"""
Drift Detector - FastAPI app factory.
Mounts routers and static files. That's it.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
    app.include_router(compare_router)
    app.include_router(documents_router)
    app.include_router(openapi_router)

    # ── Static files ──
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static"
    )

    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    async def chrome_devtools_json():
        return FileResponse(
            os.path.join(
                static_dir, ".well-known/appspecific/com.chrome.devtools.json"
            )
        )

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(static_dir, "index.html"))

    # Mount static directory for CSS, JS, and other assets
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


app = create_app()
