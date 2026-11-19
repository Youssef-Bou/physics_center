"""Explicitly local FastAPI factory; authentication for deployment is not implemented."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.dependencies import get_actor
from app.api.retrieval import router as retrieval_router
from app.api.routes import MAX_UPLOAD_BYTES, router
from app.api.tutor import router as tutor_router
from app.infrastructure.database import make_engine, make_session_factory
from app.modules.knowledge.service import KnowledgeError
from app.modules.retrieval.contracts import EmbeddingProvider
from app.modules.sources.pipeline import AnalysisPipeline
from app.modules.tutor.contracts import Provider
from app.modules.tutor.mathematics import MathTool, SympyMathTool
from app.modules.tutor.providers import DEFAULT_REAL_MODEL, provider_from_environment

__all__ = ["create_app", "get_actor"]


class BodyLimitMiddleware:
    """Bound incoming request bytes including chunked multipart bodies."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = MAX_UPLOAD_BYTES + 64 * 1024
        headers = dict(scope.get("headers", []))
        try:
            announced = int(headers.get(b"content-length", b"0"))
        except ValueError:
            response = JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)
            await response(scope, receive, send)
            return
        if announced > limit:
            response = JSONResponse({"detail": "Request body is too large."}, status_code=413)
            await response(scope, receive, send)
            return
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail="Request body is too large.")
            return message

        await self.app(scope, bounded_receive, send)


def create_app(
    database_url: str | None = None,
    storage_root: str | Path | None = None,
    pipeline: AnalysisPipeline | None = None,
    local_mode: bool | None = None,
    actor_id: str = "local-developer",
    embedding_provider: EmbeddingProvider | None = None,
    tutor_provider: Provider | None = None,
    math_tool: MathTool | None = None,
    tutor_model: str | None = None,
) -> FastAPI:
    if local_mode is None:
        local_mode = os.environ.get("PHYSICS_LOCAL_MODE") == "1"
    if not local_mode:
        raise RuntimeError(
            "Only explicit local development mode is supported. "
            "Set PHYSICS_LOCAL_MODE=1 and bind to 127.0.0.1. "
            "Public deployment requires real authentication."
        )
    if not actor_id.strip():
        raise ValueError("A local actor identity is required.")

    configured_provider = (
        tutor_provider if tutor_provider is not None else provider_from_environment()
    )
    configured_model = tutor_model or os.environ.get("PHYSICS_LLM_MODEL")
    if not configured_model:
        if configured_provider.is_mock:
            configured_model = "mock-v1"
        else:
            configured_model = DEFAULT_REAL_MODEL

    engine = make_engine(database_url)
    storage = Path(storage_root or os.environ.get("PHYSICS_STORAGE_ROOT", ".local/documents"))
    storage.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title="Physics Center – local knowledge linking prototype",
        version="0.1.0",
        description="Local development only. All analysis links require manual review.",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.pipeline = pipeline or AnalysisPipeline()
    app.state.storage_root = storage.resolve()
    app.state.actor_id = actor_id
    app.state.embedding_provider = embedding_provider
    app.state.tutor_provider = configured_provider
    app.state.math_tool = math_tool if math_tool is not None else SympyMathTool()
    app.state.tutor_model = configured_model
    app.add_middleware(BodyLimitMiddleware)
    app.include_router(router)
    app.include_router(retrieval_router)
    app.include_router(tutor_router)

    @app.exception_handler(KnowledgeError)
    async def knowledge_error(request: Request, exc: KnowledgeError):
        return JSONResponse({"code": exc.code, "detail": exc.message}, status_code=exc.status_code)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse(
            {"code": "integrity_conflict", "detail": "The change conflicts with stored data."},
            status_code=409,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        return JSONResponse(
            {
                "code": "database_unavailable",
                "detail": "The database operation could not complete.",
            },
            status_code=503,
        )

    @app.get("/health/ready")
    def readiness():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "mode": "local"}

    return app
