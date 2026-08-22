# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="REUS_", extra="ignore")

    api_key: str = "change-me-in-production"  # يجب ضبطه عبر REUS_API_KEY في بيئة الإنتاج
    environment: str = "development"
    log_level: str = "INFO"
    # حد حماية أولي لحجم JSON الوارد؛ تمنع القيمة المحدودة استنزاف الذاكرة قبل
    # وصول الطلب إلى منطق المسار. ارفعها صراحة عند الحاجة مع مراجعة المخاطر.
    max_request_body_bytes: int = 1_048_576
    security_headers_enabled: bool = True
    # "memory": مستودعات في الذاكرة (اختبار سريع، بلا ديمومة).
    # "postgres": PostgreSQL + pgvector (ديمومة كاملة). التبديل عبر REUS_STORAGE_BACKEND فقط.
    storage_backend: str = "memory"
    database_url: str = "postgresql+psycopg://reus_veritas:reus_veritas_dev_pw@localhost:5432/reus_veritas_os"

    # "memory": ناقل أحداث داخل العملية الواحدة فقط (In-Process، متزامن).
    # "redis": ناقل موزّع عبر Redis Pub/Sub (يدعم تعدد العُقد والعمّال المنفصلين).
    event_bus_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"

    # عامل تنفيذ تلقائي: يشترك في task.ready وينفّذ المهام فعليًا دون تدخل يدوي عبر API
    worker_enabled: bool = False
    worker_pool_size: int = 4
    # تفعيل صريح فقط لمسار عامل مهام عنقودي داخل عملية FastAPI الإدارية.
    # يبقى معطلاً افتراضياً حتى لا تُنشأ هوية عقدة أو منافذ mTLS أو قيادة Raft
    # ضمن التشغيل المحلي الشخصي العادي.
    cluster_worker_enabled: bool = False
    cluster_worker_role_id: str = "text-node"
    cluster_worker_data_dir: str = "data/cluster_worker"
    cluster_worker_mtls_host: str = "127.0.0.1"
    cluster_worker_mtls_port: int = 18443
    cluster_worker_bootstrap_host: str = "127.0.0.1"
    cluster_worker_bootstrap_port: int = 18080
    cluster_worker_node_label: str = ""
    cluster_worker_seed_url: str = ""
    cluster_worker_join_timeout_seconds: float = 300.0

    # "default": DefaultTaskExecutor (يستخدم قدرات الوكيل/الذاكرة الحالية فقط).
    # "model_router": ModelRoutingExecutor (يوجّه المهمة لأنسب نموذج ويستدعيه فعليًا عبر Anthropic API).
    # "cognitive": CognitiveTaskExecutor (دورة Veritas الإدراكية الكاملة: تحليل
    #   قدرات مسجَّلة -> خطط مرشّحة مقيَّمة بالتكلفة/المخاطر -> تنفيذ محلي معزول
    #   بـ sandbox -> تعلّم مستمر من موثوقية كل قدرة عبر التشغيلات اللاحقة).
    # "default" | "model_router" (نماذج API ثانوية حصرًا) | "ollama" (Ollama
    # أساسيًا + سقوط تلقائي حقيقي للنماذج الثانوية عند تعذّر الوصول له —
    # انظر application/ollama_task_executor.py) | "cognitive"
    task_executor: str = "default"

    # مسار بيانات نواة Veritas الإدراكية (سجل القدرات + الذاكرة الحدثية/الدلالية)
    cognitive_core_data_dir: str = "data/cognitive_core"
    # سجل تدقيق append-only بسلسلة هاشات مشترك بين هوية/قدرة/ذاكرة/محرك إدراكي
    cognitive_core_audit_log_path: str = "data/cognitive_core/audit_log.jsonl"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # تكامل تلغرام: إرسال/استلام المهام عبر بوت حقيقي (Long Polling)
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_poll_timeout: int = 25
    # مدة بقاء التأكيدات الإدارية الحساسة صالحة. تنتهي الطلبات في الذاكرة عند
    # إعادة التشغيل أيضاً؛ لا تستعاد callbacks غير قابلة للتحقق تلقائياً.
    telegram_approval_ttl_seconds: float = 300.0
    telegram_approval_store_path: str = "data/telegram_approvals.json"
    telegram_approval_audit_path: str = "data/telegram_approval_audit.jsonl"
    # مدة تفويض ربط لوحة التحكم التي يقرها المشرف عبر Telegram. يرسل التفويض
    # عبر HTTPS مباشرة بين النواة واللوحة، ولا يحتوي Telegram على سر.
    control_plane_pairing_ttl_seconds: float = 300.0
    control_plane_pairing_store_path: str = "data/control_plane_pairings.json"
    control_plane_pairing_audit_path: str = "data/control_plane_pairing_audit.jsonl"
    # قائمة سماح صريحة بمعرّفات المحادثات المصرَّح لها فقط (مفصولة بفواصل).
    # أي رسالة من chat_id غير مُدرَج هنا تُسجَّل وتُهمَل قبل الوصول لأي أمر أو مهمة.
    telegram_allowed_chat_ids: str = ""

    # مفتاح Fernet لتشفير محتوى الذاكرة عند التخزين في PostgreSQL. إلزامي عمليًا
    # عند storage_backend=postgres (يُتحقق منه عند إنشاء EncryptionService، لا صمت).
    encryption_key: str = ""

    # تكامل النماذج المحلية عبر Ollama (خادم محلي حقيقي، `ollama serve`):
    # OllamaSynthesizer/IndependentTestReviewer (اقتراح مهارات جديدة للعقد)،
    # وLocalModelBuilder (بناء نموذج متطوّر معزول عبر `ollama create` من
    # بيانات تدريب متراكمة فعليًا — انظر infrastructure/model_training/).
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    # Kimi خدمة API خارجية متوافقة مع OpenAI وليست محركاً محلياً؛ لذلك تبقى
    # معطلة افتراضياً ولا تستخدم إلا كسقوط اختياري عندما يقرر المطور ذلك.
    kimi_enabled: bool = False
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k3"
    # Supabase مرآة اختيارية للملخصات المعتمدة فقط، وليست مستودع النواة المحلية.
    supabase_sync_enabled: bool = False
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_sync_table: str = "reus_sync_events"
    # اسم النموذج المتطوّر المعزول — مختلف عمدًا عن ollama_model (نموذج
    # الاستخدام اليومي) حتى يبقى معزولًا كما طُلِب صراحةً.
    ollama_evolved_model_name: str = "reus-evolved"
    # دورة الاستقلالية الكاملة: عند غياب قدرة، يصمم Ollama مواصفة وكيل فقط؛
    # ثم تمر إجبارياً بمصنع العزل والحوكمة. معطلة افتراضياً حتى يفعّلها المطور.
    autonomy_enabled: bool = False
    autonomy_allow_agent_design: bool = True
    autonomy_auto_promote_low_risk: bool = False
    autonomy_max_agent_builds_per_goal: int = 1
    autonomy_governance_store_path: str = "data/autonomy_governance.json"
    autonomy_governance_audit_path: str = "data/autonomy_governance_audit.jsonl"
    # فاصل التقرير اليومي بالثواني (86400 = يوم واحد). يُضبط لقيمة أصغر في
    # التطوير/الاختبار اليدوي عبر REUS_DAILY_REPORT_INTERVAL_SECONDS.
    daily_report_interval_seconds: float = 86400.0
    daily_report_enabled: bool = False
    # الحد الأدنى لعدد أمثلة التدريب المتراكمة قبل اعتبار النموذج المتطوّر
    # "ناضجًا" للترقية — انظر application/model_promotion_service.py لبقية
    # معايير النضج (نجاح آخر بناء + عدم وجود قدرات ثبت عدم موثوقيتها).
    # القيمة الافتراضية صغيرة عمدًا؛ ارفعها بكثير في أي تشغيل إنتاجي حقيقي.
    model_promotion_min_examples: int = 200
    # عنوان بوابة تمهيد عقدة منسِّقة (coordinator) قائمة بالفعل — إن ضُبِط،
    # أي عقدة سحابية جديدة تُنشَر عبر /deploy_node تنضم تلقائيًا لهذا العنقود
    # عند إقلاعها. فارغ = عقد سحابية مستقلة بلا انضمام تلقائي (لا يزال ممكنًا
    # يدويًا لاحقًا عبر seed-url على العقدة نفسها).
    cluster_coordinator_bootstrap_url: str = ""

    # مفتاح API مخصّص لواجهة الويب العامة (/chat) — منفصل تمامًا عن api_key
    # الإداري الكامل الصلاحيات. لا يمنح أي وصول لـ/workflows، /agents،
    # /memory، أو أي مسار إداري آخر — فقط /chat. هذا الفصل على مستوى بيانات
    # الاعتماد هو الخطوة الأولى الحقيقية نحو "فصل صارم بين نطاق المستخدم
    # وواجهة المطوّر" المطلوب صراحةً؛ سياسة الفصل الكاملة عبر كل الطبقات
    # تبقى بندًا منفصلًا موثَّقًا في README تحت "ما لم يُبنَ بعد".
    user_api_key: str = ""

    # تحديد معدل على /chat فقط (الواجهة العامة الوحيدة بلا امتياز إداري):
    # سقف طلبات لكل عنوان IP خلال نافذة زمنية متحركة. القيمة الافتراضية
    # سخية عمدًا (استخدام تفاعلي طبيعي) لا تُضيّق على مستخدم حقيقي، لكنها
    # تمنع إغراقًا آليًا واضحًا. اضبط عبر REUS_CHAT_RATE_LIMIT_PER_MINUTE.
    chat_rate_limit_per_minute: int = 30

    # تحديد معدل على كل مسار يتحقق بمفتاح إداري/رمز وكيل (verify_api_key،
    # verify_agent_access، require_agent_scope) — يُطبَّق قبل مقارنة المفتاح
    # نفسها، فيحدّ من محاولات تخمين المفتاح الإداري الفعلية أيضًا، لا فقط
    # الاستخدام العادي بعد نجاح المصادقة. سقف أدنى عمدًا (المفتاح الإداري
    # أقوى صلاحية في النظام؛ استخدام لوحة تحكم بشرية طبيعي لا يقترب من هذا
    # الرقم خلال دقيقة واحدة). اضبط عبر REUS_ADMIN_RATE_LIMIT_PER_MINUTE.
    admin_rate_limit_per_minute: int = 20
    rate_limiter_max_keys: int = 10_000
    rate_limiter_cleanup_interval_seconds: float = 60.0

    # افتراضي آمن: false. لا يُوثَق بـX-Forwarded-For لتحديد هوية العميل في
    # تحديد المعدل إلا إذا كان الخادم فعليًا خلف وكيل عكسي حقيقي يضبط هذه
    # الترويسة بنفسه ويرفض أي قيمة واردة من عميل مباشر. النشر الافتراضي
    # (run.sh، Setup.bat، docker compose بلا بروفايل split) يكشف الخادم
    # مباشرة بلا وكيل — تفعيل هذا الإعداد في ذلك السياق يُبطِل تحديد المعدل
    # بالكامل (أي عميل يزوّر الترويسة يحصل على حصة جديدة في كل طلب).
    trust_proxy_headers: bool = False

    # يبذر وكيلًا افتراضيًا واحدًا جاهزًا للعمل عند أول إقلاع (مرة واحدة فقط،
    # لا تكرار عند إعادة التشغيل) — يزيل خطوة تسجيل وكيل يدويًا قبل أن يصبح
    # ربط تلغرام أو أي ميزة تعتمد على وكيل قابلة للاستخدام. معطَّل تلقائيًا
    # إن كان هناك وكيل واحد على الأقل مسجَّلًا مسبقًا بأي طريقة.
    auto_seed_default_agent: bool = True
    default_agent_name: str = "default-agent"

    # "env": القراءة من متغيرات البيئة/.env مباشرة (الافتراضي، السلوك الحالي بلا تغيير).
    # "vault": HashiCorp Vault (KV v2).  "aws": AWS Secrets Manager.
    # عند التفعيل، تُستبدل كل الحقول الحساسة أعلاه (api_key, anthropic_api_key, ...)
    # بقيمها من المزوّد المُختار إن وُجدت، فور أول استدعاء لـ get_settings().
    secrets_backend: str = "env"
    secrets_vault_addr: str = ""
    secrets_vault_token: str = ""
    secrets_vault_path: str = "reus-veritas"
    secrets_aws_region: str = "us-east-1"
    secrets_aws_secret_id: str = "reus-veritas/production"

    @model_validator(mode="after")
    def validate_runtime_safety(self) -> "Settings":
        environment = self.environment.strip().lower()
        valid_environments = {"development", "test", "staging", "production"}
        if environment not in valid_environments:
            raise ValueError(f"REUS_ENVIRONMENT must be one of {sorted(valid_environments)}")
        if self.max_request_body_bytes <= 0:
            raise ValueError("REUS_MAX_REQUEST_BODY_BYTES must be greater than zero")
        if self.chat_rate_limit_per_minute <= 0 or self.admin_rate_limit_per_minute <= 0:
            raise ValueError("rate limits must be greater than zero")
        if self.rate_limiter_max_keys <= 0 or self.rate_limiter_cleanup_interval_seconds <= 0:
            raise ValueError("rate limiter memory controls must be greater than zero")
        if self.worker_pool_size <= 0:
            raise ValueError("REUS_WORKER_POOL_SIZE must be greater than zero")
        if self.cluster_worker_mtls_port <= 0 or self.cluster_worker_bootstrap_port <= 0:
            raise ValueError("cluster worker ports must be greater than zero")
        if self.cluster_worker_join_timeout_seconds <= 0:
            raise ValueError("REUS_CLUSTER_WORKER_JOIN_TIMEOUT_SECONDS must be greater than zero")
        if self.task_executor not in {"default", "model_router", "ollama", "cognitive"}:
            raise ValueError("REUS_TASK_EXECUTOR contains an unsupported executor")
        if self.storage_backend not in {"memory", "postgres"}:
            raise ValueError("REUS_STORAGE_BACKEND must be memory or postgres")
        if self.event_bus_backend not in {"memory", "redis"}:
            raise ValueError("REUS_EVENT_BUS_BACKEND must be memory or redis")
        if self.cluster_worker_enabled and not self.worker_enabled:
            raise ValueError("REUS_CLUSTER_WORKER_ENABLED requires REUS_WORKER_ENABLED=true")
        if self.cluster_worker_enabled and not self.cluster_worker_data_dir.strip():
            raise ValueError("REUS_CLUSTER_WORKER_DATA_DIR must not be empty when cluster worker is enabled")
        if environment == "production":
            placeholders = {"", "change-me-in-production", "change-me-in-production-user"}
            if self.api_key.strip() in placeholders or len(self.api_key) < 24:
                raise ValueError("REUS_API_KEY must be a unique production secret of at least 24 characters")
            if (self.user_api_key.strip() in placeholders or len(self.user_api_key) < 24) and not self.telegram_enabled:
                raise ValueError("REUS_USER_API_KEY must be set unless Telegram-governed control-plane pairing is enabled")
            if self.storage_backend == "postgres" and len(self.encryption_key.strip()) < 32:
                raise ValueError("REUS_ENCRYPTION_KEY is required for production PostgreSQL storage")
            if self.event_bus_backend == "redis" and not self.redis_url.strip():
                raise ValueError("REUS_REDIS_URL is required when Redis event bus is enabled")
        if self.telegram_enabled and (not self.telegram_bot_token.strip() or not self.telegram_allowed_chat_ids.strip()):
            raise ValueError("Telegram requires a bot token and at least one allowed chat id")
        if self.telegram_approval_ttl_seconds <= 0:
            raise ValueError("REUS_TELEGRAM_APPROVAL_TTL_SECONDS must be greater than zero")
        if self.control_plane_pairing_ttl_seconds <= 0:
            raise ValueError("REUS_CONTROL_PLANE_PAIRING_TTL_SECONDS must be greater than zero")
        if self.ollama_enabled and not self.ollama_base_url.strip():
            raise ValueError("REUS_OLLAMA_BASE_URL is required when Ollama is enabled")
        if self.kimi_enabled and (not self.kimi_api_key.strip() or not self.kimi_base_url.strip()):
            raise ValueError("Kimi requires REUS_KIMI_API_KEY and REUS_KIMI_BASE_URL when enabled")
        if self.supabase_sync_enabled and (not self.supabase_url.strip() or not self.supabase_key.strip()):
            raise ValueError("Supabase sync requires REUS_SUPABASE_URL and REUS_SUPABASE_KEY when enabled")
        if self.autonomy_enabled and not self.ollama_enabled:
            raise ValueError("REUS_AUTONOMY_ENABLED requires REUS_OLLAMA_ENABLED=true")
        if self.autonomy_max_agent_builds_per_goal <= 0:
            raise ValueError("REUS_AUTONOMY_MAX_AGENT_BUILDS_PER_GOAL must be greater than zero")
        return self


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.secrets_backend == "env":
        return settings
    from infrastructure.secrets_resolver import resolve_secrets

    return resolve_secrets(settings)
