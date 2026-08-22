# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Composition Root: المكان الوحيد في المشروع الذي يقرر "أي تطبيق فعلي"
يُستخدم لكل واجهة مجردة. اختيار محرك التخزين (ذاكرة/PostgreSQL) يتم هنا
فقط عبر REUS_STORAGE_BACKEND، دون أي تغيير في application أو domain أو api.
"""
from __future__ import annotations

from functools import lru_cache

from application.agent_service import AgentService
from application.agent_token_service import AgentTokenService
from application.memory_service import MemoryService
from application.observability_service import ObservabilityService
from application.orchestrator_service import OrchestratorService
from application.task_executor import TaskExecutor
from application.task_worker import TaskWorker
from application.telegram_service import TelegramService
from config import get_settings
from domain.agent_token_repository import AgentTokenRepository
from domain.event_log_repository import EventLogRepository
from domain.memory_repository import MemoryRepository
from domain.repositories import AgentRepository
from domain.telegram_link_repository import TelegramLinkRepository
from domain.workflow_repository import WorkflowRepository
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.default_task_executor import DefaultTaskExecutor
from infrastructure.embedding import Embedder, HashingEmbedder
from infrastructure.event_bus import EventBus, InMemoryEventBus
from infrastructure.event_log_repository import InMemoryEventLogRepository
from infrastructure.faiss_memory_repository import FaissMemoryRepository
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.telegram_link_repository import InMemoryTelegramLinkRepository
from infrastructure.workflow_repository import InMemoryWorkflowRepository

EMBEDDING_DIMENSION = 384
_cluster_worker_started = False


@lru_cache
def get_event_bus() -> EventBus:
    if get_settings().event_bus_backend == "redis":
        from infrastructure.redis_event_bus import RedisEventBus

        return RedisEventBus(redis_url=get_settings().redis_url)
    return InMemoryEventBus()


@lru_cache
def get_agent_repository() -> AgentRepository:
    if get_settings().storage_backend == "postgres":
        from infrastructure.postgres.agent_repository import PostgresAgentRepository

        return PostgresAgentRepository()
    return InMemoryAgentRepository()


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService(repository=get_agent_repository(), event_bus=get_event_bus())


@lru_cache
def get_embedder() -> Embedder:
    return HashingEmbedder(dimension=EMBEDDING_DIMENSION)


@lru_cache
def get_memory_repository() -> MemoryRepository:
    if get_settings().storage_backend == "postgres":
        from infrastructure.encryption import EncryptionService
        from infrastructure.postgres.memory_repository import PostgresMemoryRepository

        return PostgresMemoryRepository(encryption=EncryptionService(key=get_settings().encryption_key))
    return FaissMemoryRepository(dimension=EMBEDDING_DIMENSION)


@lru_cache
def get_memory_service() -> MemoryService:
    return MemoryService(
        memory_repo=get_memory_repository(),
        agent_repo=get_agent_repository(),
        embedder=get_embedder(),
    )


@lru_cache
def get_workflow_repository() -> WorkflowRepository:
    if get_settings().storage_backend == "postgres":
        from infrastructure.postgres.workflow_repository import PostgresWorkflowRepository

        return PostgresWorkflowRepository()
    return InMemoryWorkflowRepository()


@lru_cache
def get_orchestrator_service() -> OrchestratorService:
    return OrchestratorService(
        workflow_repo=get_workflow_repository(),
        agent_repo=get_agent_repository(),
        event_bus=get_event_bus(),
    )


@lru_cache
def get_cognitive_audit_log():
    from infrastructure.cognitive_core.identity import AppendOnlyAuditLog

    return AppendOnlyAuditLog(path=get_settings().cognitive_core_audit_log_path)


@lru_cache
def get_cognitive_memory_layer():
    from infrastructure.cognitive_core.memory import MemoryLayer

    return MemoryLayer(audit_log=get_cognitive_audit_log(), data_dir=get_settings().cognitive_core_data_dir)


@lru_cache
def get_capability_layer():
    from infrastructure.cognitive_core.capability import CapabilityLayer

    return CapabilityLayer(audit_log=get_cognitive_audit_log(), data_dir=get_settings().cognitive_core_data_dir)


@lru_cache
def get_learning_layer():
    from infrastructure.cognitive_core.cognitive.learning import LearningLayer

    return LearningLayer(memory=get_cognitive_memory_layer(), audit_log=get_cognitive_audit_log())


@lru_cache
def get_local_executor():
    """LocalExecutor بلا معالجات مسجَّلة افتراضيًا — تسجيل المعالجات الفعلية
    (ربط كل capability_id بمنطق تنفيذه) مسؤولية نقطة الدخول (api/main.py أو
    سكربت تشغيل)، وليست مسؤولية الحاوية؛ راجع مصنع الوكلاء في المرحلة 3."""
    from infrastructure.cognitive_core.resource.local_executor import LocalExecutor

    return LocalExecutor()


@lru_cache
def get_agent_builder():
    from infrastructure.agent_factory.builder import AgentBuilder

    return AgentBuilder(output_dir=get_settings().cognitive_core_data_dir + "/agents/generated")


@lru_cache
def get_agent_capability_binder():
    from infrastructure.capability_binder import AgentCapabilityBinder

    return AgentCapabilityBinder(
        builder=get_agent_builder(),
        capability_layer=get_capability_layer(),
        local_executor=get_local_executor(),
        event_bus=get_event_bus(),
    )


@lru_cache
def get_cognitive_engine():
    from infrastructure.cognitive_core.cognitive.engine import CognitiveEngine

    return CognitiveEngine(
        memory=get_cognitive_memory_layer(),
        capabilities=get_capability_layer(),
        audit_log=get_cognitive_audit_log(),
        learning=get_learning_layer(),
    )


def _build_model_routing_executor():
    """مُستخرَجة كدالة مستقلة (لا @lru_cache) لأنها تُستدعى من مسارين: وضع
    'model_router' المستقل (النماذج الثانوية حصرًا)، ووضع 'ollama' (كمنفّذ
    سقوط تلقائي فقط عند تعذّر Ollama). كلاهما يحتاج نفس البناء دون تكراره."""
    from application.model_routing_executor import ModelRoutingExecutor
    from infrastructure.model_client import AnthropicModelClient, GoogleModelClient, KimiModelClient, OpenAIModelClient
    from infrastructure.model_client_registry import ModelClientRegistry
    from infrastructure.model_registry import build_default_router

    settings = get_settings()
    clients = {
            "anthropic": AnthropicModelClient(api_key=settings.anthropic_api_key),
            "openai": OpenAIModelClient(api_key=settings.openai_api_key),
            "google": GoogleModelClient(api_key=settings.google_api_key),
    }
    if settings.kimi_enabled:
        clients["kimi"] = KimiModelClient(api_key=settings.kimi_api_key, base_url=settings.kimi_base_url)
    registry = ModelClientRegistry(clients)
    return ModelRoutingExecutor(
        router=build_default_router(include_kimi=settings.kimi_enabled),
        client_registry=registry,
        memory_service=get_memory_service(),
        orchestrator=get_orchestrator_service(),
        agent_repo=get_agent_repository(),
    )


@lru_cache
def get_task_executor() -> TaskExecutor:
    executor_kind = get_settings().task_executor
    if executor_kind == "model_router":
        return _build_model_routing_executor()
    if executor_kind == "ollama":
        # الوضع الموصى به عند تفعيل Ollama: النموذج المحلي أساسي دائمًا،
        # والنماذج الثانوية (Anthropic/OpenAI/Google) سقوط تلقائي حقيقي فقط
        # عند تعذّر الوصول لخادم Ollama نفسه — انظر application/
        # ollama_task_executor.py للتوثيق الكامل لهذا القرار.
        from application.ollama_task_executor import OllamaTaskExecutor

        return OllamaTaskExecutor(
            client=get_ollama_client(),
            fallback_executor=_build_model_routing_executor(),
            event_bus=get_event_bus(),
            active_model_store=get_active_model_store(),
        )
    if executor_kind == "cognitive":
        from infrastructure.cognitive_task_executor import CognitiveTaskExecutor

        supervisor = get_autonomy_supervisor() if get_settings().autonomy_enabled else None
        return CognitiveTaskExecutor(
            engine=get_cognitive_engine(), executor=get_local_executor(), autonomy_supervisor=supervisor
        )
    return DefaultTaskExecutor(agent_service=get_agent_service(), memory_service=get_memory_service())


@lru_cache
def get_ollama_client():
    from infrastructure.agent_factory.support.ollama_client import OllamaClient

    settings = get_settings()
    return OllamaClient(base_url=settings.ollama_base_url, model=settings.ollama_model)


@lru_cache
def get_ollama_agent_builder():
    """AgentBuilder ثانٍ منفصل عن get_agent_builder() (القوالب الثابتة
    المستخدمة لمهارات العقد الخمس الأصلية) — هذا مُغذّى بـOllamaSynthesizer
    + IndependentTestReviewer، ويُستخدَم حصرًا عبر CapabilityEvolutionService
    لاقتراحات مهارات جديدة تحتاج موافقة بشرية، لا لأي مهارة أساسية."""
    from infrastructure.agent_factory.builder import AgentBuilder
    from infrastructure.agent_factory.independent_test_reviewer import IndependentTestReviewer
    from infrastructure.agent_factory.ollama_synthesizer import OllamaSynthesizer

    client = get_ollama_client()
    return AgentBuilder(
        output_dir=get_settings().cognitive_core_data_dir + "/agents/ollama_generated",
        synthesizer=OllamaSynthesizer(client),
        test_reviewer=IndependentTestReviewer(client),
    )


@lru_cache
def get_ollama_capability_binder():
    from infrastructure.capability_binder import AgentCapabilityBinder

    return AgentCapabilityBinder(
        builder=get_ollama_agent_builder(),
        capability_layer=get_capability_layer(),
        local_executor=get_local_executor(),
        component_id="capability_evolution",
        event_bus=get_event_bus(),
    )


@lru_cache
def get_autonomy_governance_ledger():
    from infrastructure.autonomy.ledger import FileGovernanceLedger

    settings = get_settings()
    return FileGovernanceLedger(
        settings.autonomy_governance_store_path,
        settings.autonomy_governance_audit_path,
    )


@lru_cache
def get_autonomy_supervisor():
    """المسار المحكوم لتوسعة النواة عند اكتشاف فجوة قدرة في مهمة حقيقية."""
    from application.autonomy_supervisor import AutonomySupervisor
    from domain.autonomy import AutonomyPolicy
    from infrastructure.autonomy.ollama_designer import OllamaAgentDesigner

    settings = get_settings()
    if not settings.autonomy_enabled or not settings.ollama_enabled:
        raise RuntimeError("autonomy supervisor requires REUS_AUTONOMY_ENABLED and REUS_OLLAMA_ENABLED")
    return AutonomySupervisor(
        cognitive_engine=get_cognitive_engine(),
        agent_builder=get_ollama_agent_builder(),
        designer=OllamaAgentDesigner(get_ollama_client()),
        governance=get_autonomy_governance_ledger(),
        binder=get_ollama_capability_binder(),
        policy=AutonomyPolicy(
            allow_agent_design=settings.autonomy_allow_agent_design,
            auto_promote_low_risk=settings.autonomy_auto_promote_low_risk,
            max_agent_builds_per_goal=settings.autonomy_max_agent_builds_per_goal,
        ),
    )


@lru_cache
def get_pending_capability_store():
    from infrastructure.pending_capabilities import PendingCapabilityStore

    return PendingCapabilityStore()


@lru_cache
def get_training_dataset_store():
    from infrastructure.model_training.training_dataset import TrainingDatasetStore

    return TrainingDatasetStore(get_settings().cognitive_core_data_dir + "/model_training/dataset.jsonl")


@lru_cache
def get_local_model_builder():
    from infrastructure.model_training.local_model_builder import LocalModelBuilder

    settings = get_settings()
    return LocalModelBuilder(
        dataset=get_training_dataset_store(),
        learning=get_learning_layer(),
        model_name=settings.ollama_evolved_model_name,
        workdir=settings.cognitive_core_data_dir + "/model_training",
    )


@lru_cache
def get_daily_report_service():
    from application.daily_report_service import DailyReportService

    settings = get_settings()
    raw_ids = settings.telegram_allowed_chat_ids
    admin_chat_ids = frozenset(i.strip() for i in raw_ids.split(",") if i.strip())
    return DailyReportService(
        memory=get_cognitive_memory_layer(),
        dataset=get_training_dataset_store(),
        model_builder=get_local_model_builder(),
        telegram=get_telegram_service(),
        admin_chat_ids=admin_chat_ids,
        interval_seconds=settings.daily_report_interval_seconds,
        promotion_service=get_model_promotion_service() if settings.ollama_enabled else None,
        governance=get_autonomy_governance_ledger() if settings.autonomy_enabled else None,
    )


@lru_cache
def get_active_model_store():
    from infrastructure.model_promotion import ActiveModelStore

    settings = get_settings()
    return ActiveModelStore(
        state_path=settings.cognitive_core_data_dir + "/model_training/active_model.json",
        base_model=settings.ollama_model,
    )


@lru_cache
def get_model_promotion_service():
    from application.model_promotion_service import ModelPromotionService

    settings = get_settings()
    raw_ids = settings.telegram_allowed_chat_ids
    admin_chat_ids = frozenset(i.strip() for i in raw_ids.split(",") if i.strip())
    return ModelPromotionService(
        dataset=get_training_dataset_store(),
        learning=get_learning_layer(),
        model_builder=get_local_model_builder(),
        active_model_store=get_active_model_store(),
        telegram=get_telegram_service(),
        admin_chat_ids=admin_chat_ids,
        evolved_model_name=settings.ollama_evolved_model_name,
        min_examples=settings.model_promotion_min_examples,
        event_bus=get_event_bus(),
    )


@lru_cache
def get_agent_token_repository() -> AgentTokenRepository:
    if get_settings().storage_backend == "postgres":
        from infrastructure.postgres.agent_token_repository import PostgresAgentTokenRepository

        return PostgresAgentTokenRepository()
    return InMemoryAgentTokenRepository()


@lru_cache
def get_agent_token_service() -> AgentTokenService:
    return AgentTokenService(token_repo=get_agent_token_repository(), agent_repo=get_agent_repository())


@lru_cache
def get_task_worker() -> TaskWorker:
    settings = get_settings()
    if settings.cluster_worker_enabled:
        return get_cluster_worker_node().build_task_worker(
            get_orchestrator_service(),
            get_task_executor(),
            get_event_bus(),
            pool_size=settings.worker_pool_size,
        )
    return TaskWorker(
        orchestrator=get_orchestrator_service(),
        executor=get_task_executor(),
        event_bus=get_event_bus(),
        pool_size=get_settings().worker_pool_size,
    )


@lru_cache
def get_cluster_worker_node():
    from infrastructure.node_runtime import compose_node

    settings = get_settings()
    return compose_node(
        role_id=settings.cluster_worker_role_id,
        data_dir=settings.cluster_worker_data_dir,
        mtls_host=settings.cluster_worker_mtls_host,
        mtls_port=settings.cluster_worker_mtls_port,
        bootstrap_host=settings.cluster_worker_bootstrap_host,
        bootstrap_port=settings.cluster_worker_bootstrap_port,
        node_label=settings.cluster_worker_node_label.strip() or None,
    )


def start_cluster_worker_runtime() -> None:
    global _cluster_worker_started
    settings = get_settings()
    if not settings.cluster_worker_enabled or _cluster_worker_started:
        return

    from infrastructure.node_runtime import join_cluster, start_node, stop_node

    node = get_cluster_worker_node()
    start_node(node)
    try:
        if settings.cluster_worker_seed_url.strip():
            join_cluster(node, settings.cluster_worker_seed_url.strip(), max_wait_seconds=settings.cluster_worker_join_timeout_seconds)
        else:
            node.raft._start_election()
    except Exception:
        stop_node(node)
        raise
    _cluster_worker_started = True


def stop_cluster_worker_runtime() -> None:
    global _cluster_worker_started
    if not _cluster_worker_started:
        return
    from infrastructure.node_runtime import stop_node

    stop_node(get_cluster_worker_node())
    _cluster_worker_started = False


@lru_cache
def get_event_log_repository() -> EventLogRepository:
    return InMemoryEventLogRepository()


@lru_cache
def get_observability_service() -> ObservabilityService:
    return ObservabilityService(
        event_log_repo=get_event_log_repository(),
        agent_repo=get_agent_repository(),
        workflow_repo=get_workflow_repository(),
        event_bus=get_event_bus(),
    )


@lru_cache
def get_telegram_link_repository() -> TelegramLinkRepository:
    return InMemoryTelegramLinkRepository()


@lru_cache
def get_telegram_approval_store():
    from infrastructure.approval_store import FileApprovalStore

    settings = get_settings()
    return FileApprovalStore(settings.telegram_approval_store_path, settings.telegram_approval_audit_path)


@lru_cache
def get_control_plane_pairing_store():
    from infrastructure.control_plane_pairing_store import ControlPlanePairingStore

    settings = get_settings()
    return ControlPlanePairingStore(settings.control_plane_pairing_store_path, settings.control_plane_pairing_audit_path)


@lru_cache
def get_telegram_service() -> TelegramService:
    raw_ids = get_settings().telegram_allowed_chat_ids
    admin_chat_ids = frozenset(i.strip() for i in raw_ids.split(",") if i.strip())
    service = TelegramService(
        link_repo=get_telegram_link_repository(),
        token_service=get_agent_token_service(),
        orchestrator=get_orchestrator_service(),
        event_bus=get_event_bus(),
        admin_chat_ids=admin_chat_ids,
        approval_ttl_seconds=get_settings().telegram_approval_ttl_seconds,
        approval_store=get_telegram_approval_store(),
    )
    if admin_chat_ids:
        # نفس نموذج Phoenix: أوامر السحابة تُسجَّل فقط إن وُجدت محادثات إدارية
        # مصرَّح بها أصلًا؛ بدون ذلك، /configure_cloud وأخواتها غير موجودة أصلًا.
        from application.cloud_telegram_commands import CloudTelegramCommands

        CloudTelegramCommands(
            service,
            event_bus=get_event_bus(),
            seed_bootstrap_url_provider=lambda: get_settings().cluster_coordinator_bootstrap_url or None,
            manager_holder=get_cloud_manager_holder(),
        )
        from application.control_plane_telegram_commands import ControlPlaneTelegramCommands

        ControlPlaneTelegramCommands(service, settings=get_settings(), pairing_store=get_control_plane_pairing_store())

        if get_settings().ollama_enabled:
            # نفس المبدأ: أوامر تطوّر القدرات (/pending_capabilities،
            # /approve_capability، /reject_capability) لا تُسجَّل إطلاقًا ما
            # لم يكن Ollama مفعّلًا صراحةً (REUS_OLLAMA_ENABLED=true) — لا
            # اقتراح مهارات بلا نموذج محلي فعلي خلفه.
            from application.capability_evolution_service import CapabilityEvolutionService

            CapabilityEvolutionService(
                binder=get_ollama_capability_binder(),
                pending_store=get_pending_capability_store(),
                telegram=service,
                admin_chat_ids=admin_chat_ids,
                event_bus=get_event_bus(),
            )
            if get_settings().autonomy_enabled:
                from application.autonomy_telegram_commands import AutonomyTelegramCommands

                AutonomyTelegramCommands(
                    supervisor=get_autonomy_supervisor(),
                    governance=get_autonomy_governance_ledger(),
                    telegram=service,
                )
            # ملاحظة مهمة: تسجيل أوامر /model_status، /promote_model،
            # /demote_model (ModelPromotionService) يحدث عمدًا **من خارج**
            # هذه الدالة — عبر get_model_promotion_service() في نقطة إقلاع
            # منفصلة (api/main.py) — لأن ModelPromotionService نفسها تستدعي
            # get_telegram_service() لتسجيل أوامرها؛ استدعاؤها من هنا (قبل
            # اكتمال بناء get_telegram_service() وتخزينه في lru_cache) يسبب
            # استدعاءً دائريًا حقيقيًا لا نظريًا. لا تُعِد هذا الاستدعاء هنا.
    return service


@lru_cache
def get_telegram_client():
    from infrastructure.telegram_client import TelegramClient

    return TelegramClient(bot_token=get_settings().telegram_bot_token)


@lru_cache
def get_telegram_polling_worker():
    from infrastructure.telegram_polling_worker import TelegramPollingWorker

    return TelegramPollingWorker(
        client=get_telegram_client(),
        service=get_telegram_service(),
        poll_timeout=get_settings().telegram_poll_timeout,
    )


@lru_cache
def get_chat_rate_limiter():
    from infrastructure.rate_limiter import InMemoryRateLimiter

    settings = get_settings()
    return InMemoryRateLimiter(
        max_requests=settings.chat_rate_limit_per_minute,
        window_seconds=60.0,
        max_keys=settings.rate_limiter_max_keys,
        cleanup_interval_seconds=settings.rate_limiter_cleanup_interval_seconds,
    )


@lru_cache
def get_cloud_manager_holder():
    from infrastructure.cloud_manager_holder import CloudManagerHolder

    return CloudManagerHolder()


@lru_cache
def get_admin_rate_limiter():
    from infrastructure.rate_limiter import InMemoryRateLimiter

    settings = get_settings()
    return InMemoryRateLimiter(
        max_requests=settings.admin_rate_limit_per_minute,
        window_seconds=60.0,
        max_keys=settings.rate_limiter_max_keys,
        cleanup_interval_seconds=settings.rate_limiter_cleanup_interval_seconds,
    )
