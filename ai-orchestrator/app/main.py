"""FastAPI application factory for the AI Orchestrator."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.config import settings
from app.db import init_db
from app.orchestrator.service import fail_interrupted_runs
from app.utils.logging import configure_logging, log_structured


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set up logging and the database when the server starts."""
    configure_logging()
    await init_db()
    stopped = await fail_interrupted_runs()
    if stopped:
        log_structured("interrupted_runs_marked_failed", count=stopped)
    yield


def create_app() -> FastAPI:
    """Application factory."""

    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app


app = create_app()
