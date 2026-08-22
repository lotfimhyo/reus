"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

هذا الملف مبني حول `create_app()` بدل تطبيق FastAPI واحد ثابت، لسبب أمني
محدَّد اكتُشِف عند المراجعة: قبل هذه الحلقة، كل المسارات الإدارية
(`/agents`, `/workflows`, `/agents/{id}/memory`, `/metrics`,
`/observability`, `/dashboard`) وكل المسارات العامة (`/chat`, `/app`)
كانت تُخدَم من **نفس عملية FastAPI، نفس المنفذ، نفس المستمِع الشبكي**.
الفصل بينهما كان فصلًا منطقيًا فقط (مفتاح API مختلف) — لا فصلًا شبكيًا
فعليًا. من يستطيع الوصول لـ`/chat` عبر الإنترنت يستطيع تقنيًا محاولة
الوصول لـ`/agents` على نفس العنوان والمنفذ بالضبط؛ الحماية الوحيدة كانت
رفض المصادقة (401)، لا غياب المسار عن السطح الشبكي أصلًا.

`create_app(include_public, include_admin)` يسمح ببناء ثلاثة تطبيقات:
  - `app` (كلاهما معًا، الافتراضي) — نفس السلوك الحالي تمامًا، صفر تغيير
    لأي نشر قائم (docker-compose.yml، run.sh، CI، كل الاختبارات).
  - `public_app` (`/chat`, `/app`, `/health`, `/ready` فقط) — لا يحتوي
    `/agents` ولا أي مسار إداري آخر إطلاقًا، ليس فقط محميًا بمفتاح؛ غائب
    تمامًا عن جدول التوجيه، فطلب له يُعيد 404 لا 401. يمكن نشره على منفذ
    عام مكشوف للإنترنت بثقة أكبر.
  - `admin_app` (كل شيء ما عدا `/chat`/`/app`) — يُقصَد تشغيله خلف جدار
    ناري/VPN/شبكة داخلية فقط، لا مكشوفًا للإنترنت العام.

كل تطبيق لا يزال يملك `/health`/`/ready` (أي عملية مُشغَّلة بمفردها تحتاج
فحوصات حيوية/جهوزية خاصة بها، بصرف النظر عن أي المسارات الأخرى تخدمها).

قرار مهم آخر: عند التشغيل المنفصل (public_app/admin_app كعمليتين
منفصلتين فعليًا)، يجب ألا تبدأ كلتاهما نفس عمّال الخلفية (عامل المهام،
استقصاء تلغرام، التقرير اليومي) — تشغيلهما مرتين يعني معالجة كل حدث
مرتين. القرار: عمّال الخلفية بالكامل مسؤولية `admin_app`/`app` فقط؛
`public_app` وحده لا يُشغِّل أي عامل خلفية إطلاقًا — /chat لا يحتاج أيًا
منها (المنفِّذ يُستدعى مباشرة ومتزامنًا لكل طلب، لا عبر طابور خلفي).
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

        # تسجيل الأحداث للوحة المراقبة يبدأ دائمًا، بصرف النظر عن تفعيل العامل
        # التلقائي — رخيص، ولا يعالج أحداثًا مكرَّرة حتى لو عملية عامة أيضًا.
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

                get_telegram_service().start()  # يبدأ الاشتراك في نتائج المهام لتوصيلها لاحقًا
                telegram_worker = get_telegram_polling_worker()
                telegram_worker.start()
                logger.info("telegram_enabled_on_startup", extra={"event_name": "telegram_enabled_on_startup"})

                if settings.ollama_enabled:
                    # يسجّل /model_status، /promote_model، /demote_model. يحدث هنا
                    # (لا داخل get_telegram_service نفسها) عمدًا — انظر التعليق في
                    # container.py: استدعاؤها من داخل get_telegram_service يسبب
                    # استدعاءً دائريًا حقيقيًا عبر lru_cache غير المكتمل بعد.
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
        # عند الإغلاق: يُغلق ناقل الأحداث بأمان (مهم لـ RedisEventBus التي تُشغّل خيط استماع بالخلفية)
        bus = get_event_bus()
        if hasattr(bus, "close"):
            bus.close()

    return lifespan


def _install_common_middleware_and_handlers(app: FastAPI) -> None:
    """يُثبَّت على كل تطبيق (app/public_app/admin_app) بلا استثناء — سجلّ
    الطلبات، request_id، ومعالجات الأخطاء الموحَّدة يجب أن تعمل بصرف النظر
    عن أي مجموعة مسارات تخدمها هذه العملية بالتحديد."""

    @app.middleware("http")
    async def request_metrics_middleware(request: Request, call_next):
        global _request_count
        _request_count += 1
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()

        # فحص Content-Length قبل تحليل JSON يمنع حجز ذاكرة كبيرة للطلبات
        # الواضحة الرفض. الطلبات chunked تبقى تحت مسؤولية خادم ASGI/proxy،
        # لذلك يجب ضبط حد مماثل في طبقة البوابة عند نشر الإنتاج.
        from config import get_settings
        settings = get_settings()
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > settings.max_request_body_bytes:
            from fastapi.responses import JSONResponse

            response = JSONResponse(
                status_code=413,
                content={"detail": "حجم الطلب يتجاوز الحد المسموح", "request_id": request_id},
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
        """يُبقي شكل `detail` كما هو تمامًا (كل نقاط النهاية القائمة تعتمد عليه) —
        يُضيف `request_id` فقط للربط بسجلات الخادم، لا يُغيّر أي حقل موجود.
        هذا إضافي بحت (Additive)، لا كسر توافق."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": getattr(request.state, "request_id", None)},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """FastAPI الافتراضي لأخطاء التحقق (422) يُعيد شكلًا مختلفًا تمامًا عن
        أخطاء HTTPException (`detail` كقائمة كائنات، لا نص). هذا يُوحِّد الشكل:
        رسالة نصية موجزة في `detail` (لا كسر لعملاء يتوقعون نصًا)، مع تفاصيل
        كل حقل فشل في `errors` لمن يحتاج تفصيلًا برمجيًا، وrequest_id للربط."""
        return JSONResponse(
            status_code=422,
            content={
                "detail": "فشل التحقق من صحة الطلب",
                "errors": exc.errors(),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """شبكة أمان أخيرة لأي استثناء لم يُلتقَط صراحة في أي مسار. لا يُسرَّب أي
        تفصيل داخلي في الاستجابة (رسالة عامة ثابتة فقط) — لكن الاستثناء الكامل
        بسجل الاستدعاء يُسجَّل خادميًا مع request_id للتشخيص."""
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled_exception",
            extra={"event_name": "unhandled_exception", "payload": {"request_id": request_id, "path": request.url.path}},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "خطأ داخلي في الخادم", "request_id": request_id},
        )

    @app.get("/health")
    def health() -> dict:
        """فحص حيوية رخيص (Liveness) — لا يفحص أي تبعية خارجية عمدًا، يجب أن يبقى
        فوريًا ورخيصًا لاستخدامه من مُجدوِل حاويات (kubernetes liveness probe)."""
        return {"status": "ok", "service": "reus-veritas-os"}

    @app.get("/ready")
    def ready() -> dict:
        """فحص جهوزية حقيقي (Readiness) — يتحقق فعليًا من كل تبعية خارجية مُفعَّلة
        (قاعدة البيانات، Redis) قبل الإعلان عن الجهوزية، بدل الاكتفاء برد ثابت.
        يُعيد 503 صراحة إن كانت أي تبعية مُفعَّلة غير قابلة للوصول."""
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
            except Exception as exc:  # noqa: BLE001 — أي خطأ اتصال يعني عدم الجهوزية
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
        """
        يخدم واجهة الويب العامة للمستخدمين (محادثة مباشرة مع Reus عبر /chat).
        منفصلة عمدًا عن /dashboard: لا تعرض أي بيانات تشغيلية داخلية (وكلاء،
        مهام، سجلّات، تكلفة سحابية)، ولا تستخدم مفتاح API الإداري — فقط
        user_api_key المخصَّص لهذا المسار بالتحديد (انظر infrastructure/
        security.py: verify_user_api_key).
        """
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
        """
        يخدم لوحة التحكم والمراقبة (صفحة HTML/JS واحدة). لا تحتاج مصادقة بحد ذاتها
        (مجرد ملف ثابت)؛ المصادقة تتم من متصفح المستخدم عبر X-API-Key عند استدعاء
        نقاط النهاية الفعلية (يُدخله المستخدم مرة واحدة، يُحفظ في localStorage للمتصفح فقط).

        هذه الصفحة **للمطوّرين/الإدارة** (تعرض بيانات تشغيلية داخلية) — واجهة
        المستخدمين العامة منفصلة تمامًا وغائبة عن هذا التطبيق كليًا إن شُغِّل
        admin_app بمفرده، انظر _install_public_routes أعلاه.
        """
        return FileResponse(_STATIC_DIR / "dashboard.html")


def create_app(*, include_public: bool = True, include_admin: bool = True) -> FastAPI:
    if not include_public and not include_admin:
        raise ValueError("create_app: يجب تضمين مسار عام أو إداري واحد على الأقل")

    title_suffix = "" if (include_public and include_admin) else (" (Public)" if include_public else " (Admin)")
    app = FastAPI(
        title="Reus-Veritas OS" + title_suffix,
        description="نظام تشغيل الوكلاء الذكيين المستقلين",
        version="0.5.0",
        # عمّال الخلفية (المهام، تلغرام، التقرير اليومي) هم مسؤولية admin_app/app
        # فقط — انظر توثيق الوحدة أعلاه لسبب عدم تشغيلهم في public_app المستقل.
        lifespan=_make_lifespan(start_background_workers=include_admin),
    )

    _install_common_middleware_and_handlers(app)
    if include_public:
        _install_public_routes(app)
    if include_admin:
        _install_admin_routes(app)

    return app


# التطبيق الافتراضي: كل شيء معًا، نفس السلوك الحالي تمامًا — صفر تغيير لأي
# نشر قائم (docker-compose.yml بخدمة `api` واحدة، run.sh، CI، كل الاختبارات).
app = create_app()

# للنشر بفصل شبكي فعلي (انظر docker-compose.yml بروفايل "split"):
#   uvicorn api.main:public_app --port 8000   # مكشوف للإنترنت
#   uvicorn api.main:admin_app  --port 8001   # داخلي فقط (VPN/جدار ناري)
public_app = create_app(include_admin=False)
admin_app = create_app(include_public=False)
