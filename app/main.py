from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.account import router as account_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.data_sources import router as data_sources_router
from app.api.evaluations import router as evaluations_router
from app.api.examples import router as examples_router
from app.api.files import router as files_router
from app.api.health import router as health_router
from app.api.model_settings import router as model_settings_router
from app.api.schema import router as schema_router
from app.api.security_policies import router as security_policies_router
from app.core.config import get_settings

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Natural-language data analysis API powered by Text-to-SQL.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(account_router, prefix="/api")
    app.include_router(examples_router, prefix="/api")
    app.include_router(data_sources_router, prefix="/api")
    app.include_router(model_settings_router, prefix="/api")
    app.include_router(security_policies_router, prefix="/api")
    app.include_router(schema_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.include_router(evaluations_router, prefix="/api")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def console() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
