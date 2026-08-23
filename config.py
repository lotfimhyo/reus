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

    api_key: str = "change-me-in-production"  # Set through REUS_API_KEY in production.
    environment: str = "development"
    log_level: str = "INFO"
    # An early limit for incoming JSON bodies prevents memory exhaustion before
    # a request reaches route logic. Raise it explicitly only after risk review.
    max_request_body_bytes: int = 1_048_576
    security_headers_enabled: bool = True
    # "memory": in-memory repositories for fast, non-persistent testing.
    # "postgres": PostgreSQL + pgvector for durable storage. Switch only via REUS_STORAGE_BACKEND.
    storage_backend: str = "memory"
    database_url: str = "postgresql+psycopg://reus_veritas:reus_veritas_dev_pw@localhost:5432/reus_veritas_os"

    # "memory": synchronous event bus within one process only.
    # "redis": distributed Redis Pub/Sub event bus for multiple nodes and separate workers.
    event_bus_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"

    # Automatic execution worker: subscribes to task.ready and runs tasks without manual API intervention.
    worker_enabled: bool = False
    worker_pool_size: int = 4
    # Explicit opt-in only for the clustered task-worker path inside the administrative FastAPI process.
    # It remains disabled by default so ordinary local operation does not create a node identity,
    # mTLS ports, or Raft leadership state.
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

    # "default": DefaultTaskExecutor, using only current agent capabilities and memory.
    # "model_router": ModelRoutingExecutor, which routes a task to a suitable model and invokes it.
    # "cognitive": CognitiveTaskExecutor, with capability analysis, cost/risk-scored candidate
    #   plans, isolated local sandbox execution, and later reliability learning per capability.
    # "default" | "model_router" (secondary API models only) | "ollama" (Ollama first,
    # with genuine fallback to secondary models when it is unavailable; see
    # application/ollama_task_executor.py) | "cognitive"
    task_executor: str = "default"

    # Cognitive-core data path (capability registry and episodic/semantic memory).
    cognitive_core_data_dir: str = "data/cognitive_core"
    # Append-only, hash-chained audit log shared by identity, capability, memory, and cognitive engine.
    cognitive_core_audit_log_path: str = "data/cognitive_core/audit_log.jsonl"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # Telegram integration: send and receive tasks through a real bot using long polling.
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_poll_timeout: int = 25
    # Lifetime for sensitive administrative confirmations. In-memory requests also expire on
    # restart; non-verifiable callbacks are never automatically restored.
    telegram_approval_ttl_seconds: float = 300.0
    telegram_approval_store_path: str = "data/telegram_approvals.json"
    telegram_approval_audit_path: str = "data/telegram_approval_audit.jsonl"
    # Lifetime for an administrator-approved control-plane pairing. Authorization travels
    # directly over HTTPS between core and control plane; Telegram contains no secret.
    control_plane_pairing_ttl_seconds: float = 300.0
    control_plane_pairing_store_path: str = "data/control_plane_pairings.json"
    control_plane_pairing_audit_path: str = "data/control_plane_pairing_audit.jsonl"
    # Explicit allowlist of authorized chat IDs only, separated by commas. Any message from an
    # unlisted chat ID is recorded and ignored before reaching a command or task.
    telegram_allowed_chat_ids: str = ""

    # Fernet key for encrypting memory content in PostgreSQL. It is operationally required for
    # storage_backend=postgres and is verified when EncryptionService is created.
    encryption_key: str = ""

    # Local model integration through an actual Ollama server (`ollama serve`):
    # OllamaSynthesizer and IndependentTestReviewer propose node capabilities, while
    # LocalModelBuilder builds an isolated evolved model via `ollama create` from accumulated
    # training data; see infrastructure/model_training/.
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    # Kimi is an external OpenAI-compatible API service, not a local engine. It remains disabled
    # by default and is used only as an optional fallback when the developer chooses it.
    kimi_enabled: bool = False
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k3"
    # Supabase is an optional mirror for approved summaries only, not the local-core store.
    supabase_sync_enabled: bool = False
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_sync_table: str = "reus_sync_events"
    # The isolated evolved-model name intentionally differs from ollama_model, the daily-use
    # model, so it remains isolated.
    ollama_evolved_model_name: str = "reus-evolved"
    # Full autonomy cycle: when a capability is absent, Ollama designs an agent specification
    # only; it must then pass the sandboxed builder and governance. Disabled until a developer enables it.
    autonomy_enabled: bool = False
    autonomy_allow_agent_design: bool = True
    autonomy_auto_promote_low_risk: bool = False
    autonomy_max_agent_builds_per_goal: int = 1
    autonomy_governance_store_path: str = "data/autonomy_governance.json"
    autonomy_governance_audit_path: str = "data/autonomy_governance_audit.jsonl"
    # Daily-report interval in seconds (86,400 = one day). Use a smaller value for development
    # or manual testing through REUS_DAILY_REPORT_INTERVAL_SECONDS.
    daily_report_interval_seconds: float = 86400.0
    daily_report_enabled: bool = False
    # Minimum accumulated training examples before an evolved model can be considered mature
    # enough for promotion. See application/model_promotion_service.py for other criteria:
    # the latest build must succeed and no capabilities may be established as unreliable.
    # The default is intentionally small; increase it substantially for genuine production use.
    model_promotion_min_examples: int = 200
    # Bootstrap address of an existing coordinator. If configured, every new cloud node deployed
    # through /deploy_node joins that cluster at startup. An empty value means independent cloud
    # nodes without automatic joining; manual joining via the node's seed URL remains possible.
    cluster_coordinator_bootstrap_url: str = ""

    # API key dedicated to the public web surface (/chat), completely separate from the
    # fully privileged administrative api_key. It grants no access to /workflows, /agents,
    # /memory, or any other administrative route. This credential-level separation is a first
    # step toward strict user/developer surface separation; the complete cross-layer policy is
    # documented in the README under "What is not built yet".
    user_api_key: str = ""

    # Rate limit for /chat only, the sole public surface without administrative privilege:
    # a request ceiling per IP address in a moving time window. The default permits ordinary
    # interactive use while blocking obvious automated flooding. Configure it with REUS_CHAT_RATE_LIMIT_PER_MINUTE.
    chat_rate_limit_per_minute: int = 30

    # Rate limit for every route verified by an administrative key or agent token
    # (verify_api_key, verify_agent_access, require_agent_scope). It is applied before key
    # comparison, limiting real administrative-key guessing attempts as well as normal use after
    # authentication. The low ceiling is intentional because a human control plane normally will
    # not approach it in one minute. Configure with REUS_ADMIN_RATE_LIMIT_PER_MINUTE.
    admin_rate_limit_per_minute: int = 20
    rate_limiter_max_keys: int = 10_000
    rate_limiter_cleanup_interval_seconds: float = 60.0

    # Secure default: false. Do not trust X-Forwarded-For for rate-limit identity unless the
    # server is genuinely behind a reverse proxy that sets the header itself and rejects values
    # from direct clients. Default deployments expose the server without such a proxy; enabling
    # this setting there defeats rate limiting because each client can forge a fresh identity.
    trust_proxy_headers: bool = False

    # Seed one ready-to-use default agent at first startup only. This removes manual agent
    # registration before Telegram pairing or agent-dependent features can be used. It is
    # automatically disabled if any agent has already been registered.
    auto_seed_default_agent: bool = True
    default_agent_name: str = "default-agent"

    # "env": read directly from environment variables/.env (default, unchanged behavior).
    # "vault": HashiCorp Vault (KV v2). "aws": AWS Secrets Manager.
    # When enabled, sensitive fields above (api_key, anthropic_api_key, and others) are replaced
    # by values from the selected provider when present, at the first get_settings() call.
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
