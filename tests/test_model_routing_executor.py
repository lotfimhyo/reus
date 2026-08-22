# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from application.memory_service import MemoryService
from application.model_router import ModelProfile, ModelRouter
from application.model_routing_executor import ModelRoutingExecutor
from application.task_executor import TaskExecutionError
from domain.workflow import TaskNode
from infrastructure.embedding import HashingEmbedder
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.faiss_memory_repository import FaissMemoryRepository
from infrastructure.memory_repository import InMemoryAgentRepository
from infrastructure.model_client import ModelClient, ModelInvocationError
from infrastructure.model_client_registry import ModelClientRegistry

DIM = 128

CHEAP = ModelProfile(
    name="cheap-model",
    provider="test-provider",
    capability_tags=frozenset({"chat"}),
    input_cost_per_1k_tokens_usd=0.001,
    output_cost_per_1k_tokens_usd=0.002,
    max_context_tokens=8_000,
    relative_speed_rank=1,
)
CAPABLE = ModelProfile(
    name="capable-model",
    provider="test-provider",
    capability_tags=frozenset({"chat", "reasoning"}),
    input_cost_per_1k_tokens_usd=0.01,
    output_cost_per_1k_tokens_usd=0.02,
    max_context_tokens=100_000,
    relative_speed_rank=2,
)
OTHER_PROVIDER_MODEL = ModelProfile(
    name="other-provider-model",
    provider="another-provider",
    capability_tags=frozenset({"chat"}),
    input_cost_per_1k_tokens_usd=0.0001,
    output_cost_per_1k_tokens_usd=0.0002,
    max_context_tokens=8_000,
    relative_speed_rank=1,
)


class FakeModelClient(ModelClient):
    """بديل اختباري لمنفذ ModelClient — يتحقق من صحة منطق ModelRoutingExecutor دون أي شبكة."""

    def __init__(self, response: str = "fake response", should_fail: bool = False) -> None:
        self.response = response
        self.should_fail = should_fail
        self.calls: list[dict] = []

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        self.calls.append({"model_id": model_id, "prompt": prompt, "max_tokens": max_tokens})
        if self.should_fail:
            raise ModelInvocationError("محاكاة فشل شبكي")
        return self.response


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter(profiles=[CHEAP, CAPABLE])


@pytest.fixture
def multi_provider_router() -> ModelRouter:
    return ModelRouter(profiles=[CHEAP, CAPABLE, OTHER_PROVIDER_MODEL])


@pytest.fixture
def fake_client() -> FakeModelClient:
    return FakeModelClient()


@pytest.fixture
def registry(fake_client: FakeModelClient) -> ModelClientRegistry:
    return ModelClientRegistry({"test-provider": fake_client, "another-provider": FakeModelClient()})


def test_execute_without_prompt_raises(router: ModelRouter, registry: ModelClientRegistry, fake_client):
    executor = ModelRoutingExecutor(router=router, client_registry=registry)
    task = TaskNode(name="no-prompt-task", payload={})

    with pytest.raises(TaskExecutionError):
        executor.execute(task)
    assert fake_client.calls == []


def test_execute_routes_to_cheapest_by_default(router: ModelRouter, registry: ModelClientRegistry, fake_client):
    fake_client.response = "hello!"
    executor = ModelRoutingExecutor(router=router, client_registry=registry)
    task = TaskNode(name="simple-chat", payload={"prompt": "قل مرحبًا"})

    result = executor.execute(task)

    assert result["model_used"] == "cheap-model"
    assert result["provider"] == "test-provider"
    assert result["response"] == "hello!"
    assert fake_client.calls[0]["prompt"] == "قل مرحبًا"


def test_execute_routes_to_capable_when_reasoning_required(router: ModelRouter, registry: ModelClientRegistry):
    executor = ModelRoutingExecutor(router=router, client_registry=registry)
    task = TaskNode(
        name="analysis-task",
        payload={"prompt": "حلّل هذا التقرير المالي", "required_capabilities": ["reasoning"]},
    )

    result = executor.execute(task)

    assert result["model_used"] == "capable-model"


def test_execute_dispatches_to_correct_provider_client(multi_provider_router: ModelRouter, registry: ModelClientRegistry):
    """التحقق الحاسم أن التوجيه متعدد المزوّدين يستدعي عميل المزوّد الصحيح فعليًا."""
    executor = ModelRoutingExecutor(router=multi_provider_router, client_registry=registry)
    task = TaskNode(
        name="cheapest-overall",
        payload={"prompt": "أرخص نموذج على الإطلاق عبر كل المزوّدين"},
    )

    result = executor.execute(task)

    # other-provider-model أرخص من كل نماذج test-provider، فيجب اختياره وعميله تحديدًا
    assert result["model_used"] == "other-provider-model"
    assert result["provider"] == "another-provider"


def test_execute_raises_when_no_suitable_model(router: ModelRouter, registry: ModelClientRegistry):
    executor = ModelRoutingExecutor(router=router, client_registry=registry)
    task = TaskNode(name="vision-task", payload={"prompt": "صف هذه الصورة", "required_capabilities": ["vision"]})

    with pytest.raises(TaskExecutionError):
        executor.execute(task)


def test_execute_propagates_model_invocation_failure_as_task_execution_error(
    router: ModelRouter, registry: ModelClientRegistry, fake_client
):
    fake_client.should_fail = True
    executor = ModelRoutingExecutor(router=router, client_registry=registry)
    task = TaskNode(name="failing-task", payload={"prompt": "أي شيء"})

    with pytest.raises(TaskExecutionError):
        executor.execute(task)


def test_execute_passes_max_tokens_through(router: ModelRouter, registry: ModelClientRegistry, fake_client):
    executor = ModelRoutingExecutor(router=router, client_registry=registry)
    task = TaskNode(name="bounded-task", payload={"prompt": "لخّص هذا", "max_tokens": 50})

    executor.execute(task)

    assert fake_client.calls[0]["max_tokens"] == 50


# ---------- Tool Use ----------


class ToolCapableFakeClient(ModelClient):
    """
    بديل اختباري يدعم invoke_with_tools فعليًا، لمحاكاة سلوك عميل حقيقي يستدعي
    الأداة مرة واحدة ثم يُنتج ردًا نهائيًا — دون الحاجة لشبكة أو مفتاح API حقيقيين.
    """

    def __init__(self) -> None:
        self.dispatch_calls: list[tuple[str, dict]] = []

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        raise AssertionError("لا يجب استدعاء invoke() العادية عند enable_tools=True")

    def invoke_with_tools(self, model_id, prompt, tools, tool_dispatcher, max_tokens=1024, max_iterations=5) -> str:
        result = tool_dispatcher("search_memory", {"query": prompt})
        self.dispatch_calls.append(("search_memory", {"query": prompt}))
        return f"وجدت: {result}"


@pytest.fixture
def agent_repo() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def agent_service(agent_repo) -> AgentService:
    return AgentService(repository=agent_repo, event_bus=InMemoryEventBus())


@pytest.fixture
def memory_service(agent_repo) -> MemoryService:
    return MemoryService(
        memory_repo=FaissMemoryRepository(dimension=DIM),
        agent_repo=agent_repo,
        embedder=HashingEmbedder(dimension=DIM),
    )


def test_execute_with_tools_requires_agent_id(router: ModelRouter, registry: ModelClientRegistry, memory_service):
    executor = ModelRoutingExecutor(router=router, client_registry=registry, memory_service=memory_service)
    task = TaskNode(name="toolful-task", payload={"prompt": "ابحث عن شيء", "enable_tools": True})

    with pytest.raises(TaskExecutionError):
        executor.execute(task)


def test_execute_with_tools_requires_memory_service(router: ModelRouter, registry: ModelClientRegistry):
    executor = ModelRoutingExecutor(router=router, client_registry=registry, memory_service=None)
    task = TaskNode(name="toolful-task", agent_id="a1", payload={"prompt": "ابحث عن شيء", "enable_tools": True})

    with pytest.raises(TaskExecutionError):
        executor.execute(task)


def test_execute_with_tools_invokes_dispatcher(
    router: ModelRouter, agent_service: AgentService, memory_service: MemoryService
):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="tool-agent", permissions={"read:memory"}, goals=[])
    )
    tool_client = ToolCapableFakeClient()
    registry = ModelClientRegistry({"test-provider": tool_client, "another-provider": FakeModelClient()})
    executor = ModelRoutingExecutor(router=router, client_registry=registry, memory_service=memory_service)

    task = TaskNode(
        name="toolful-task",
        agent_id=agent.agent_id,
        payload={"prompt": "ابحث عن آخر الأسعار", "enable_tools": True},
    )

    result = executor.execute(task)

    assert len(tool_client.dispatch_calls) == 1
    assert tool_client.dispatch_calls[0][0] == "search_memory"
    assert "وجدت:" in result["response"]


def test_execute_with_tools_raises_when_client_lacks_support(
    router: ModelRouter, agent_service: AgentService, memory_service: MemoryService, fake_client
):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="tool-agent-2", permissions={"read:memory"}, goals=[])
    )
    registry = ModelClientRegistry({"test-provider": fake_client, "another-provider": FakeModelClient()})
    executor = ModelRoutingExecutor(router=router, client_registry=registry, memory_service=memory_service)

    task = TaskNode(
        name="toolful-task",
        agent_id=agent.agent_id,
        payload={"prompt": "ابحث عن شيء", "enable_tools": True},
    )

    with pytest.raises(TaskExecutionError):
        executor.execute(task)


# ---------- أدوات التعاون عبر ModelRoutingExecutor ----------


class ToolNameCapturingClient(ModelClient):
    """يسجّل أسماء الأدوات المعروضة عليه فقط، دون استدعاء أي منها."""

    def __init__(self, reply: str = "لا أدوات مستخدَمة") -> None:
        self.offered_tool_names: list[str] = []
        self._reply = reply

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        raise AssertionError("لا يجب استدعاء invoke() العادية عند enable_tools=True")

    def invoke_with_tools(self, model_id, prompt, tools, tool_dispatcher, max_tokens=1024, max_iterations=5) -> str:
        self.offered_tool_names = [t["name"] for t in tools]
        return self._reply


class DelegatingFakeClient(ModelClient):
    """يستدعي أداة create_task فعليًا لمحاكاة نموذج يفوّض مهمة لوكيل آخر."""

    def invoke(self, model_id: str, prompt: str, max_tokens: int = 1024) -> str:
        raise AssertionError("لا يجب استدعاء invoke() العادية عند enable_tools=True")

    def invoke_with_tools(self, model_id, prompt, tools, tool_dispatcher, max_tokens=1024, max_iterations=5) -> str:
        result = tool_dispatcher(
            "create_task", {"task_name": "تفويض-فرعي", "prompt": "افعل كذا", "target_agent_id": prompt}
        )
        return f"فوّضت المهمة: {result}"


def test_collaboration_tools_offered_only_when_orchestrator_and_agent_repo_provided(
    router: ModelRouter, agent_service: AgentService, memory_service: MemoryService, agent_repo
):
    from application.orchestrator_service import OrchestratorService
    from infrastructure.workflow_repository import InMemoryWorkflowRepository

    agent = agent_service.register_agent(
        RegisterAgentCommand(name="a", permissions={"spawn:subagent"}, goals=[])
    )
    orchestrator = OrchestratorService(
        workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=InMemoryEventBus()
    )
    client = ToolNameCapturingClient()
    registry = ModelClientRegistry({"test-provider": client, "another-provider": FakeModelClient()})

    # بلا orchestrator/agent_repo: أدوات الذاكرة فقط
    executor_without = ModelRoutingExecutor(router=router, client_registry=registry, memory_service=memory_service)
    executor_without.execute(
        TaskNode(name="t1", agent_id=agent.agent_id, payload={"prompt": "x", "enable_tools": True})
    )
    assert "create_task" not in client.offered_tool_names
    assert "list_agents" not in client.offered_tool_names

    # مع orchestrator/agent_repo: أدوات التعاون تظهر أيضًا
    executor_with = ModelRoutingExecutor(
        router=router,
        client_registry=registry,
        memory_service=memory_service,
        orchestrator=orchestrator,
        agent_repo=agent_repo,
    )
    executor_with.execute(TaskNode(name="t2", agent_id=agent.agent_id, payload={"prompt": "x", "enable_tools": True}))
    assert "create_task" in client.offered_tool_names
    assert "list_agents" in client.offered_tool_names


def test_model_can_delegate_task_to_another_agent_end_to_end(
    router: ModelRouter, agent_service: AgentService, memory_service: MemoryService, agent_repo
):
    from application.orchestrator_service import OrchestratorService
    from infrastructure.workflow_repository import InMemoryWorkflowRepository

    coordinator = agent_service.register_agent(
        RegisterAgentCommand(name="coordinator", permissions={"spawn:subagent"}, goals=[])
    )
    worker = agent_service.register_agent(RegisterAgentCommand(name="worker", permissions=set(), goals=[]))

    orchestrator = OrchestratorService(
        workflow_repo=InMemoryWorkflowRepository(), agent_repo=agent_repo, event_bus=InMemoryEventBus()
    )
    registry = ModelClientRegistry(
        {"test-provider": DelegatingFakeClient(), "another-provider": FakeModelClient()}
    )
    executor = ModelRoutingExecutor(
        router=router,
        client_registry=registry,
        memory_service=memory_service,
        orchestrator=orchestrator,
        agent_repo=agent_repo,
    )

    # الـ "prompt" هنا يُستخدم أيضًا كـ target_agent_id بفضل DelegatingFakeClient لتبسيط الاختبار
    task = TaskNode(
        name="coordination-task",
        agent_id=coordinator.agent_id,
        payload={"prompt": worker.agent_id, "enable_tools": True},
    )

    result = executor.execute(task)

    assert "فوّضت المهمة" in result["response"]
    delegated_workflows = [w for w in orchestrator.list_workflows() if w.name.startswith("tool:")]
    assert len(delegated_workflows) == 1
    delegated_task = next(iter(delegated_workflows[0].tasks.values()))
    assert delegated_task.agent_id == worker.agent_id
    assert delegated_task.payload["prompt"] == "افعل كذا"
