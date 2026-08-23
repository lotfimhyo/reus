"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

This module is built around `create_app()` instead of one fixed FastAPI
application because an earlier review found that administrative routes
(`/agents`, `/workflows`, `/agents/{id}/memory`, `/metrics`,
`/observability`, `/dashboard`) and public routes (`/chat`, `/app`) were
served by the same process, port, and network listener. Different API keys are
logical separation, not network separation: an internet client able to reach
`/chat` could still attempt `/agents` on the same address. Authentication
rejection alone is not equivalent to removing an administrative route from the
network surface.

`create_app(include_public, include_admin)` builds three deployable forms:
  - `app`, the backwards-compatible default with both route groups;
  - `public_app`, with only `/chat`, `/app`, `/health`, and `/ready`, where
    administrative paths are absent from routing and return 404 rather than
    merely being key-protected;
  - `admin_app`, containing all non-public routes and intended for a firewall,
    VPN, or internal network only.

Every form retains `/health` and `/ready` because each independently running
process needs its own liveness and readiness checks.

When public and administrative applications run as separate processes, only
`admin_app` or the combined `app` starts background workers. Starting task,
Telegram polling, or daily-report workers twice would process events twice.
The standalone `public_app` starts no background worker because `/chat`
executes its compatible executor directly and synchronously per request.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from infrastructure.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("reus_veritas.api")

_STATIC_DIR = Path(__file__).parent / "static"
_request_count = 0


def _make_lifespan(*, start_background_workers: bool):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from config import get_settings
        from container import get_event_bus, get_observability_service

        settings = get_settings()

        # Start observability for every application form. It is inexpensive and
        # does not process duplicate events even when a public process also runs.
        get_observability_service().start()

        worker = None
        telegram_worker = None
        daily_report_service = None
        cluster_worker_runtime_started = False

        if start_background_workers:
            if settings.auto_seed_default_agent:
                from container import get_agent_service
                from infrastructure.seed_default_agent import seed_default_agent

                seeded_id = seed_default_agent(get_agent_service(), name=settings.default_agent_name)
                if seeded_id is not None:
                    logger.info(
                        "default_agent_seeded_on_startup",
                        extra={"event_name": "default_agent_seeded_on_startup", "payload": {"agent_id": seeded_id}},
                    )

            if settings.worker_enabled:
                from container import get_task_worker, start_cluster_worker_runtime

                if settings.cluster_worker_enabled:
                    start_cluster_worker_runtime()
                    cluster_worker_runtime_started = True
                    logger.info("cluster_worker_runtime_enabled", extra={"event_name": "cluster_worker_runtime_enabled"})

                worker = get_task_worker()
                worker.start()
                logger.info("worker_enabled_on_startup", extra={"event_name": "worker_enabled_on_startup"})

            if settings.task_executor == "cognitive":
                from container import get_agent_capability_binder, get_capability_layer
                from infrastructure.seed_capabilities import seed_default_capabilities

                published = seed_default_capabilities(get_agent_capability_binder(), get_capability_layer())
                logger.info(
                    "default_capabilities_seeded",
                    extra={"event_name": "default_capabilities_seeded", "published": published},
                )

            if settings.telegram_enabled:
                from container import get_telegram_polling_worker, get_telegram_service

                get_telegram_service().start()  # Subscribe to task results for later delivery.
                telegram_worker = get_telegram_polling_worker()
                telegram_worker.start()
                logger.info("telegram_enabled_on_startup", extra={"event_name": "telegram_enabled_on_startup"})

                if settings.ollama_enabled:
                    # Register model status and promotion commands here rather
                    # than inside get_telegram_service: that call path would
                    # create a real cycle through an incomplete lru_cache.
                    from container import get_model_promotion_service

                    get_model_promotion_service()

            if settings.daily_report_enabled:
                from container import get_daily_report_service

                daily_report_service = get_daily_report_service()
                daily_report_service.start()
                logger.info("daily_report_enabled_on_startup", extra={"event_name": "daily_report_enabled_on_startup"})

        yield

        if daily_report_service is not None:
            daily_report_service.stop()
        if telegram_worker is not None:
            telegram_worker.stop()
        if worker is not None:
            worker.stop()
        if cluster_worker_runtime_started:
            from container import stop_cluster_worker_runtime

            stop_cluster_worker_runtime()
        # Close the event bus safely at shutdown, including Redis listener threads.
        bus = get_event_bus()
        if hasattr(bus, "close"):
            bus.close()

    return lifespan


def _install_common_middleware_and_handlers(app: FastAPI) -> None:
    """Install request logging, request IDs, and unified error handlers on
    every application form regardless of the route group it serves."""

    @app.middleware("http")
    async def request_metrics_middleware(request: Request, call_next):
        global _request_count
        _request_count += 1
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()

        # Check Content-Length before JSON parsing to avoid allocating large
        # memory for clearly rejectable requests. Chunked requests remain the
        # ASGI server or proxy responsibility and need an equivalent gateway limit.
        from config import get_settings
        settings = get_settings()
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > settings.max_request_body_bytes:
            from fastapi.responses import JSONResponse

            response = JSONResponse(
                status_code=413,
                content={"detail": "Request body exceeds the allowed size.", "request_id": request_id},
            )
        else:
            response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "http_request",
            extra={
                "event_name": "http_request",
                "payload": {
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "request_number": _request_count,
                    "request_id": request_id,
                },
            },
        )
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.2f}"
        response.headers["X-Request-ID"] = request_id
        if settings.security_headers_enabled:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            if settings.environment.strip().lower() == "production":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path not in {"/app", "/dashboard"}:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Preserve the existing `detail` shape and add only `request_id` for
        server-log correlation, without changing compatibility fields."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": getattr(request.state, "request_id", None)},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Normalize FastAPI 422 responses with a concise text `detail`, rich
        field failures in `errors`, and a correlation `request_id`."""
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed.",
                "errors": exc.errors(),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Final safety net: return only a stable public message while logging
        full diagnostics server-side with the correlation request ID."""
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled_exception",
            extra={"event_name": "unhandled_exception", "payload": {"request_id": request_id, "path": request.url.path}},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error.", "request_id": request_id},
        )

    @app.get("/health")
    def health() -> dict:
        """Fast liveness check that intentionally avoids external dependencies."""
        return {"status": "ok", "service": "reus-veritas-os"}

    @app.get("/ready")
    def ready() -> dict:
        """Readiness check that probes enabled database and Redis dependencies
        and returns 503 explicitly when any configured dependency is unavailable."""
        from fastapi import HTTPException

        from config import get_settings

        settings = get_settings()
        checks: dict[str, str] = {}
        all_ok = True

        if settings.storage_backend == "postgres":
            try:
                from sqlalchemy import text

                from infrastructure.postgres.session import get_engine

                with get_engine().connect() as conn:
                    conn.execute(text("SELECT 1"))
                checks["database"] = "ok"
            except Exception as exc:  # noqa: BLE001 - any connection error means not ready
                checks["database"] = f"unreachable: {exc}"
                all_ok = False
        else:
            checks["database"] = "skipped (storage_backend=memory)"

        if settings.event_bus_backend == "redis":
            try:
                import redis

                redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
                checks["redis"] = "ok"
            except Exception as exc:  # noqa: BLE001
                checks["redis"] = f"unreachable: {exc}"
                all_ok = False
        else:
            checks["redis"] = "skipped (event_bus_backend=memory)"

        if not all_ok:
            raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})

        return {"status": "ready", "checks": checks}


def _install_public_routes(app: FastAPI) -> None:
    from api.routes.chat import router as chat_router

    app.include_router(chat_router)

    @app.get("/app")
    def user_app() -> FileResponse:
        """Serve the public chat interface. It is deliberately separate from
        `/dashboard`, exposes no operational data, and uses only the dedicated
        user API key rather than the administrative key."""
        return FileResponse(_STATIC_DIR / "app.html")


def _install_admin_routes(app: FastAPI) -> None:
    from api.routes.agent_tokens import router as agent_tokens_router
    from api.routes.agents import router as agents_router
    from api.routes.autonomy import router as autonomy_router
    from api.routes.memory import router as memory_router
    from api.routes.metrics import router as metrics_router
    from api.routes.nodes import router as nodes_router
    from api.routes.observability import router as observability_router
    from api.routes.settings import router as settings_router
    from api.routes.workflows import router as workflows_router

    app.include_router(agents_router)
    app.include_router(agent_tokens_router)
    app.include_router(autonomy_router)
    app.include_router(memory_router)
    app.include_router(metrics_router)
    app.include_router(nodes_router)
    app.include_router(observability_router)
    app.include_router(settings_router)
    app.include_router(workflows_router)

    @app.get("/dashboard")
    def dashboard() -> FileResponse:
        """Serve the developer and operations dashboard static page. Its API
        requests use an `X-API-Key` entered in the browser; the public user
        interface remains separate and is absent from standalone `admin_app`."""
        return FileResponse(_STATIC_DIR / "dashboard.html")


def create_app(*, include_public: bool = True, include_admin: bool = True) -> FastAPI:
    if not include_public and not include_admin:
        raise ValueError("create_app: include at least one public or administrative route group")

    title_suffix = "" if (include_public and include_admin) else (" (Public)" if include_public else " (Admin)")
    app = FastAPI(
        title="Reus-Veritas OS" + title_suffix,
        description="A local-first, human-governed distributed AI system.",
        version="0.5.0",
        # Background workers belong only to admin_app or the combined app; see
        # the module documentation for why standalone public_app does not start them.
        lifespan=_make_lifespan(start_background_workers=include_admin),
    )

    _install_common_middleware_and_handlers(app)
    if include_public:
        _install_public_routes(app)
    if include_admin:
        _install_admin_routes(app)

    return app


# Default application: both route groups together, preserving existing single
# API service deployments, startup scripts, CI, and tests.
app = create_app()

# For actual network separation, use the docker-compose "split" profile:
#   uvicorn api.main:public_app --port 8000   # Internet-facing
#   uvicorn api.main:admin_app  --port 8001   # Internal only, behind VPN or firewall
public_app = create_app(include_admin=False)
admin_app = create_app(include_public=False)
